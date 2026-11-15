"""Token de render y generación del PDF.

El token de render lo emite la API (HS256 con PDF_SECRET), dura 5 minutos y va atado a una
instancia. El frontend lo usa en lugar de la sesión de Supabase cuando abre la ruta
/{slug}/imprimir?render=<token>. El cliente_id sigue viniendo del servidor: el token lo lleva
porque la API lo puso ahí, nunca porque el navegador lo mandó.
"""

import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import jwt
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from api.config import Configuracion

log = logging.getLogger(__name__)

TIPO_RENDER = "render"
DURACION = timedelta(minutes=5)
# Un PDF de Chromium con al menos una hoja del reporte pesa decenas de KB (fuentes, gráficos).
# Por debajo de esto el archivo está vacío o truncado. No pretende detectar una pantalla de
# error: de eso se encargan las marcas del DOM (ver decidir_impresion).
TAMANO_MINIMO_PDF = 1024


class RenderInvalidoError(Exception):
    pass


class PdfInvalidoError(Exception):
    """El PDF no se debe entregar. `motivo` es corto y seguro de mostrar al equipo: nunca
    lleva la URL de impresión ni el token de render."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class EstadoImpresion:
    """Lo que la vista de impresión dejó en el DOM cuando terminó de cargar (o falló)."""

    lista: bool
    error: bool
    bloques_con_error: int
    cargando: int
    hojas: int


def decidir_impresion(estado: EstadoImpresion) -> int:
    """Decide si la vista de impresión se puede imprimir. Devuelve las hojas esperadas o lanza
    PdfInvalidoError. Pura, para poder probarla sin lanzar Chromium."""
    if estado.error:
        raise PdfInvalidoError("la vista de impresión no pudo cargar el reporte")
    if estado.bloques_con_error:
        raise PdfInvalidoError(f"{estado.bloques_con_error} bloque(s) no se pudieron cargar")
    if not estado.lista or estado.cargando:
        raise PdfInvalidoError("el reporte no terminó de cargar")
    if estado.hojas < 1:
        raise PdfInvalidoError("el reporte no tiene páginas con datos para imprimir")
    return estado.hojas


def validar_pdf(contenido: bytes, paginas_esperadas: int) -> None:
    """Comprueba que lo generado sea un PDF entero y con al menos las hojas del reporte."""
    if not contenido or not contenido.startswith(b"%PDF-"):
        raise PdfInvalidoError("el archivo generado no es un PDF")
    if len(contenido) < TAMANO_MINIMO_PDF:
        raise PdfInvalidoError("el PDF generado está vacío o incompleto")
    try:
        paginas = len(PdfReader(io.BytesIO(contenido)).pages)
    except (PdfReadError, ValueError, OSError) as e:
        raise PdfInvalidoError("el PDF generado está dañado") from e
    if paginas < paginas_esperadas:
        raise PdfInvalidoError(
            f"el PDF tiene {paginas} página(s) y el reporte {paginas_esperadas} hoja(s)"
        )


def sin_token(texto: str, token: str | None) -> str:
    """Quita el token de render de un texto antes de registrarlo (los errores de Playwright
    citan la URL completa)."""
    return texto.replace(token, "[token]") if token else texto


@dataclass(frozen=True)
class PrincipalRender:
    cliente_id: int
    instancia_id: int


def emitir_token_render(config: Configuracion, cliente_id: int, instancia_id: int) -> str:
    if not config.pdf_secret:
        raise RenderInvalidoError("PDF_SECRET no configurado")
    ahora = datetime.now(UTC)
    return jwt.encode(
        {
            "tipo": TIPO_RENDER,
            "cliente_id": cliente_id,
            "instancia_id": instancia_id,
            "iat": ahora,
            "exp": ahora + DURACION,
        },
        config.pdf_secret,
        algorithm="HS256",
    )


def verificar_token_render(token: str, config: Configuracion) -> PrincipalRender:
    if not config.pdf_secret:
        raise RenderInvalidoError("PDF_SECRET no configurado")
    try:
        claims: dict[str, Any] = jwt.decode(token, config.pdf_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise RenderInvalidoError(f"Token de render inválido: {e}") from e
    if claims.get("tipo") != TIPO_RENDER:
        raise RenderInvalidoError("No es un token de render")
    return PrincipalRender(int(claims["cliente_id"]), int(claims["instancia_id"]))


def url_impresion(config: Configuracion, slug: str, desde: str, hasta: str, token: str) -> str:
    base = config.frontend_url.rstrip("/")
    consulta = urlencode({"desde": desde, "hasta": hasta, "modo": "print", "render": token})
    return f"{base}/{slug}/imprimir?{consulta}"


# Script que lee el estado de la vista de impresión (ver frontend/src/reporte/Imprimir.tsx).
_ESTADO_JS = """() => ({
  lista: document.querySelector('[data-impresion-lista="1"]') !== null,
  error: document.querySelector('[data-impresion-error="1"]') !== null,
  bloques_con_error: document.querySelectorAll('[data-bloque-error="1"]').length,
  cargando: document.querySelectorAll('.bloque-cargando').length,
  hojas: document.querySelectorAll('section.hoja').length,
})"""
# Termina de esperar cuando todo cargó O apareció cualquier error (no hay que esperar al
# timeout para saber que falló).
_TERMINO_JS = (
    "document.querySelector('[data-impresion-error=\"1\"]') !== null "
    "|| document.querySelector('[data-bloque-error=\"1\"]') !== null "
    "|| (document.querySelector('[data-impresion-lista=\"1\"]') !== null "
    "&& document.querySelectorAll('.bloque-cargando').length === 0)"
)


async def generar_pdf(url: str, timeout_ms: int = 60_000) -> bytes:
    """Abre la vista de impresión, espera a que todo cargue y devuelve un PDF validado.

    Lanza PdfInvalidoError si la vista marcó un error, si algún bloque falló, si se agotó el
    tiempo o si el archivo resultante no pasa validar_pdf. Nunca imprime una pantalla de error.
    """
    from playwright.async_api import Error as ErrorPlaywright
    from playwright.async_api import TimeoutError as TimeoutPlaywright
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await p.chromium.launch()
        try:
            pagina = await navegador.new_page(viewport={"width": 1240, "height": 1754})
            try:
                await pagina.goto(url, wait_until="networkidle", timeout=timeout_ms)
                await pagina.wait_for_function(_TERMINO_JS, timeout=timeout_ms)
            except TimeoutPlaywright as e:
                raise PdfInvalidoError("se agotó el tiempo esperando el reporte") from e
            except ErrorPlaywright as e:
                raise PdfInvalidoError("el navegador no pudo abrir la vista de impresión") from e
            datos: dict[str, Any] = await pagina.evaluate(_ESTADO_JS)
            hojas = decidir_impresion(EstadoImpresion(**datos))
            await pagina.evaluate("document.fonts && document.fonts.ready")
            contenido = await pagina.pdf(
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "10mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            )
        finally:
            await navegador.close()
    validar_pdf(contenido, hojas)
    return contenido

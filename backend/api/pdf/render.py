"""Token de render y generación del PDF.

El token de render lo emite la API (HS256 con PDF_SECRET), dura 5 minutos y va atado a una
instancia. El frontend lo usa en lugar de la sesión de Supabase cuando abre la ruta
/{slug}/imprimir?render=<token>. El cliente_id sigue viniendo del servidor: el token lo lleva
porque la API lo puso ahí, nunca porque el navegador lo mandó.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import jwt

from api.config import Configuracion

TIPO_RENDER = "render"
DURACION = timedelta(minutes=5)


class RenderInvalidoError(Exception):
    pass


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


async def generar_pdf(url: str, timeout_ms: int = 60_000) -> bytes:
    """Abre la vista de impresión, espera a que todos los bloques carguen y devuelve el PDF."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        navegador = await p.chromium.launch()
        try:
            pagina = await navegador.new_page(viewport={"width": 1240, "height": 1754})
            await pagina.goto(url, wait_until="networkidle", timeout=timeout_ms)
            # Cada bloque marca su propio estado: esperamos a que no quede ninguno cargando.
            await pagina.wait_for_function(
                "document.querySelector('[data-impresion-lista=\"1\"]') !== null "
                "&& document.querySelectorAll('.bloque-cargando').length === 0",
                timeout=timeout_ms,
            )
            await pagina.evaluate("document.fonts && document.fonts.ready")
            return await pagina.pdf(
                format="A4",
                landscape=True,
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "10mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            )
        finally:
            await navegador.close()

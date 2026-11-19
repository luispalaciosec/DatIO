"""Envío del reporte mensual: PDF del mes cerrado + resumen narrado, a los usuarios del
cliente. El cron lo dispara los primeros días del mes (idempotente por envios_reporte) y el
admin puede enviarlo a mano a cualquier correo para revisarlo antes."""

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import asyncpg

from api.alertas.repositorio import RepositorioAlertas
from api.config import Configuracion
from api.consulta.repositorio import RepositorioConsulta
from api.narrativa.servicio import narrar
from api.pdf import render
from api.pdf.render import PdfInvalidoError
from api.reportes.correo import MESES, enviar, html_fallo_envio, html_mensual
from api.reportes.repositorio import RepositorioReportes

log = logging.getLogger(__name__)
DIAS_DE_ENVIO = (1, 2, 3, 4, 5)  # el cron reintenta estos días si el 1 falló
COLOR_DEFECTO = "#0EA5E9"


@dataclass
class ResultadoEnvio:
    cliente: str
    # 'enviado' | 'error' | 'pdf_invalido' | 'sin_destinatarios' | 'ya_enviado'.
    # 'pdf_invalido' y 'error' se registran en envios_reporte.estado (TEXT sin CHECK) y no
    # cuentan como enviados: el cron reintenta al día siguiente dentro de DIAS_DE_ENVIO.
    estado: str
    destinatarios: list[str] = field(default_factory=list)
    error: str | None = None


def mes_anterior(hoy: date) -> tuple[date, date]:
    fin = hoy.replace(day=1) - timedelta(days=1)
    return fin.replace(day=1), fin


def limites(periodo: date) -> tuple[date, date]:
    return periodo.replace(day=1), periodo.replace(
        day=calendar.monthrange(periodo.year, periodo.month)[1]
    )


async def resumen_del_mes(
    pool: asyncpg.Pool, config: Configuracion, instancia: dict[str, Any], desde: date, hasta: date
) -> list[dict[str, Any]]:
    repo_r = RepositorioReportes(pool)
    repo_c = RepositorioConsulta(pool)
    secciones = []
    for pag in await repo_r.paginas_con_kpis(
        instancia["id"], instancia["plantilla_id"], instancia["cliente_id"]
    ):
        cuentas = await repo_c.cuentas_de_pagina(instancia["cliente_id"], pag["plataforma"])
        r = await narrar(
            repo_c,
            config,
            instancia["cliente_id"],
            cuentas,
            pag["plataforma"],
            pag["items"],
            desde,
            hasta,
        )
        if r["texto"]:
            secciones.append({"titulo": pag["titulo"], "texto": r["texto"]})
    return secciones


async def enviar_reporte(
    pool: asyncpg.Pool,
    config: Configuracion,
    cliente_id: int,
    periodo: date,
    destinatarios: list[str] | None = None,
    automatico: bool = False,
) -> ResultadoEnvio:
    repo = RepositorioReportes(pool)
    instancia = await repo.instancia_de_cliente(cliente_id)
    if instancia is None:
        return ResultadoEnvio("?", "error", error="El cliente no tiene reporte activo")
    cliente = str(instancia["cliente"])
    desde, hasta = limites(periodo)
    if automatico and await repo.ya_enviado(instancia["id"], desde):
        return ResultadoEnvio(cliente, "ya_enviado")
    para = destinatarios if destinatarios is not None else await repo.correos_cliente(cliente_id)
    if not para:
        if automatico:
            return ResultadoEnvio(cliente, "sin_destinatarios")
        return ResultadoEnvio(cliente, "sin_destinatarios", error="El cliente no tiene usuarios")
    mes = f"{MESES[desde.month - 1]} de {desde.year}"
    color = instancia.get("color_primario") or COLOR_DEFECTO
    url = (
        f"{config.frontend_url.rstrip('/')}/{instancia['slug_publico']}?desde={desde}&hasta={hasta}"
    )
    # Orden obligatorio: PDF → validación → narrativa → envío. Cualquier fallo antes del envío
    # deja al cliente sin correo (nunca se adjunta una pantalla de error).
    token: str | None = None
    try:
        token = render.emitir_token_render(config, cliente_id, instancia["id"])
        pdf = await render.generar_pdf(
            render.url_impresion(
                config, instancia["slug_publico"], desde.isoformat(), hasta.isoformat(), token
            ),
            timeout_ms=120_000,
        )
        # Segunda barrera, por si generar_pdf se reemplaza o cambia: al menos una hoja entera.
        render.validar_pdf(pdf, 1)
        secciones = await resumen_del_mes(pool, config, instancia, desde, hasta)
        ok, error = await enviar(
            config,
            para,
            f"{cliente} · Reporte de {mes}",
            html_mensual(cliente, mes, url, color, secciones),
            (f"{instancia['slug_publico']}_{desde:%Y-%m}.pdf", pdf),
        )
        estado = "enviado" if ok else "error"
    except PdfInvalidoError as e:
        log.error("Envío mensual de %s: PDF descartado (%s)", cliente, e.motivo)
        estado, error = "pdf_invalido", e.motivo
    except Exception as e:  # Playwright, red, LLM, etc.
        # El detalle va al log sin token; a la base y al equipo solo el tipo de error.
        log.error(
            "Envío mensual de %s falló: %s: %s",
            cliente,
            type(e).__name__,
            render.sin_token(str(e), token),
        )
        estado, error = "error", f"falla interna ({type(e).__name__})"
    await repo.registrar_envio(instancia["id"], desde, para, automatico, estado, error)
    if estado != "enviado":
        capturar_fallo_envio(cliente, mes, error)
        if automatico:
            await avisar_fallo_al_equipo(pool, config, cliente, mes, error or estado)
    return ResultadoEnvio(cliente, estado, para, error)


def capturar_fallo_envio(cliente: str, mes: str, motivo: str | None) -> None:
    """Reporta el fallo a Sentry si está configurado (sin DSN no hace nada)."""
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover - sentry es opcional en desarrollo
        return
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("envio_mensual", "fallo")
        scope.set_context("envio", {"cliente": cliente, "mes": mes, "motivo": motivo})
        sentry_sdk.capture_message(f"Envío mensual fallido: {cliente} ({mes})", level="error")


async def avisar_fallo_al_equipo(
    pool: asyncpg.Pool, config: Configuracion, cliente: str, mes: str, motivo: str
) -> None:
    """Correo interno al equipo cuando falla un envío automático. Nunca al cliente y nunca con
    el PDF ni el detalle técnico (eso queda en el log). Sin Resend, solo log."""
    destinatarios = await RepositorioAlertas(pool).correos_equipo()
    destinatarios += [d for d in config.alertas_destinatarios_extra if d not in destinatarios]
    if not destinatarios:
        log.warning("Envío mensual de %s falló y no hay correos del equipo para avisar", cliente)
        return
    ok, error = await enviar(
        config,
        destinatarios,
        f"[DatIO] No se envió el reporte de {mes} de {cliente}",
        html_fallo_envio(cliente, mes, motivo),
    )
    if not ok:
        log.warning("No se pudo avisar al equipo del fallo de %s: %s", cliente, error)


async def enviar_mensuales(
    pool: asyncpg.Pool, config: Configuracion, hoy: date
) -> list[ResultadoEnvio]:
    """Para el cron: los primeros días del mes envía el mes cerrado a cada cliente con usuarios."""
    if hoy.day not in DIAS_DE_ENVIO or not config.resend_api_key:
        return []
    periodo, _ = mes_anterior(hoy)
    salida = []
    for inst in await RepositorioReportes(pool).instancias_activas():
        r = await enviar_reporte(pool, config, inst["cliente_id"], periodo, automatico=True)
        if r.estado not in ("ya_enviado", "sin_destinatarios"):
            salida.append(r)
    return salida

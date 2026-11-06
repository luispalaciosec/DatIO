"""Envío del reporte mensual: PDF del mes cerrado + resumen narrado, a los usuarios del
cliente. El cron lo dispara los primeros días del mes (idempotente por envios_reporte) y el
admin puede enviarlo a mano a cualquier correo para revisarlo antes."""

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import asyncpg

from api.config import Configuracion
from api.consulta.repositorio import RepositorioConsulta
from api.narrativa.servicio import narrar
from api.pdf import render
from api.reportes.correo import MESES, enviar, html_mensual
from api.reportes.repositorio import RepositorioReportes

log = logging.getLogger(__name__)
DIAS_DE_ENVIO = (1, 2, 3, 4, 5)  # el cron reintenta estos días si el 1 falló
COLOR_DEFECTO = "#0EA5E9"


@dataclass
class ResultadoEnvio:
    cliente: str
    estado: str  # 'enviado' | 'error' | 'sin_destinatarios' | 'ya_enviado'
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
    try:
        token = render.emitir_token_render(config, cliente_id, instancia["id"])
        pdf = await render.generar_pdf(
            render.url_impresion(
                config, instancia["slug_publico"], desde.isoformat(), hasta.isoformat(), token
            ),
            timeout_ms=120_000,
        )
        secciones = await resumen_del_mes(pool, config, instancia, desde, hasta)
        ok, error = await enviar(
            config,
            para,
            f"{cliente} · Reporte de {mes}",
            html_mensual(cliente, mes, url, color, secciones),
            (f"{instancia['slug_publico']}_{desde:%Y-%m}.pdf", pdf),
        )
    except Exception as e:  # Playwright, red, etc.
        log.exception("Envío mensual de %s falló", cliente)
        ok, error = False, f"{type(e).__name__}: {e}"[:300]
    estado = "enviado" if ok else "error"
    await repo.registrar_envio(instancia["id"], desde, para, automatico, estado, error)
    return ResultadoEnvio(cliente, estado, para, error)


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

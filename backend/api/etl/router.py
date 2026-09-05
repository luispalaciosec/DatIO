"""Endpoint que dispara la captura diaria (Railway Cron 06:00 Ecuador → POST /etl/correr)."""

from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from api.config import Configuracion
from api.deps import obtener_config_app, obtener_pool
from api.etl.conectores.metricool import METRICAS_METRICOOL, ConectorMetricool
from api.etl.repositorio import RepositorioETL
from api.etl.runner import correr_todos

router = APIRouter(prefix="/etl", tags=["etl"])


def verificar_cron(
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    x_cron_secret: Annotated[str | None, Header()] = None,
) -> None:
    if not config.cron_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CRON_SECRET no configurado")
    if x_cron_secret != config.cron_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Secreto de cron inválido")


@router.post("/correr", dependencies=[Depends(verificar_cron)])
async def correr(
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    pool: Annotated[asyncpg.Pool, Depends(obtener_pool)],
    plataforma: str | None = None,
    hasta: date | None = None,
) -> dict[str, Any]:
    resumen = await correr_todos(RepositorioETL(pool), config, plataforma, hasta)
    return {
        "filas_escritas": resumen.filas_escritas,
        "cuentas_ok": [r.cuenta_id for r in resumen.resultados if r.estado == "ok"],
        "cuentas_parcial": [r.cuenta_id for r in resumen.resultados if r.estado == "parcial"],
        "errores": resumen.errores,
        "sin_conector": resumen.sin_conector,
    }


class ImportacionMetricool(BaseModel):
    """Filas tal como las devuelve getAnalyticsDataByMetrics del MCP de Metricool."""

    plataforma: str = Field(pattern="^(linkedin|tiktok)$")
    id_externo: str  # id_externo de cuentas_conectadas (urn:li:organization:... o @usuario)
    desde: date
    hasta: date
    metricas: list[str]  # field IDs en el mismo orden que las columnas de rows
    rows: list[list[Any]]  # [..valores.., 'AAAAMMDD']


@router.get("/importar/metricool/metricas")
async def metricas_metricool() -> dict[str, tuple[str, ...]]:
    """Field IDs que la rutina debe pedir por plataforma."""
    return METRICAS_METRICOOL


@router.post("/importar/metricool", dependencies=[Depends(verificar_cron)])
async def importar_metricool(
    cuerpo: ImportacionMetricool,
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    pool: Annotated[asyncpg.Pool, Depends(obtener_pool)],
) -> dict[str, Any]:
    repo = RepositorioETL(pool)
    cuenta = next(
        (
            c
            for c in await repo.cuentas_activas(cuerpo.plataforma)
            if c.id_externo == cuerpo.id_externo
        ),
        None,
    )
    if cuenta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuenta no encontrada o inactiva")
    payload = [
        {
            "fuente": "metricool_mcp",
            "desde": cuerpo.desde.isoformat(),
            "hasta": cuerpo.hasta.isoformat(),
            "metricas": cuerpo.metricas,
            "rows": cuerpo.rows,
        }
    ]
    conector = ConectorMetricool(
        cuenta, repo, await repo.mapeo_plataforma(cuerpo.plataforma), config, payload=payload
    )
    resultado = await conector.correr(hasta=cuerpo.hasta)
    return {
        "cuenta_id": resultado.cuenta_id,
        "job_id": resultado.job_id,
        "filas_escritas": resultado.filas_escritas,
        "estado": resultado.estado,
        "metricas_sin_mapeo": sorted(resultado.metricas_sin_mapeo),
    }

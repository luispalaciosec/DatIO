"""Endpoint que dispara la captura diaria (Railway Cron 06:00 Ecuador → POST /etl/correr)."""

from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.config import Configuracion
from api.deps import obtener_config_app, obtener_pool
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

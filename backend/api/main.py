"""Aplicación FastAPI (PT-01). Expone /health, auth (PT-07) y ETL (PT-03)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.admin.router import router as router_admin
from api.admin.router_conectar import router as router_conectar
from api.auth.router import router as router_auth
from api.config import Configuracion, obtener_config
from api.consulta.cache import CacheConsulta
from api.consulta.router import router as router_consulta
from api.db import crear_pool
from api.etl.router import router as router_etl
from api.pdf.router import router as router_pdf


def crear_app(config: Configuracion | None = None) -> FastAPI:
    cfg = config or obtener_config()

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        app.state.config = cfg
        app.state.pool = await crear_pool(cfg.database_url)
        app.state.cache = CacheConsulta(ttl_seg=cfg.cache_ttl_seg)
        try:
            yield
        finally:
            await app.state.pool.close()

    app = FastAPI(title="DatIO", version="0.1.0", lifespan=ciclo_de_vida)
    app.include_router(router_auth)
    app.include_router(router_etl)
    app.include_router(router_consulta)
    app.include_router(router_pdf)
    app.include_router(router_admin)
    app.include_router(router_conectar)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.origenes_permitidos,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Cron-Secret"],
    )

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        async with request.app.state.pool.acquire() as con:
            await con.fetchval("SELECT 1")
        return {"estado": "ok", "ambiente": cfg.ambiente, "base_de_datos": "ok"}

    return app


app = crear_app()

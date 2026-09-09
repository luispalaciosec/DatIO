"""SQL de alertas (PT-14). Lectura de series, detección de condiciones operativas y persistencia."""

import json
from datetime import date, datetime, timedelta
from typing import Any

import asyncpg

METRICAS_VIGILADAS: dict[str, list[str]] = {
    "meta_ig": ["alcance", "impresiones", "interacciones", "seguidores"],
    "meta_fb": ["interacciones", "visualizaciones_pagina", "seguidores"],
    "linkedin": ["impresiones", "interacciones", "seguidores"],
    "tiktok": ["impresiones", "interacciones", "seguidores"],
    "youtube": ["impresiones", "seguidores"],
    "ga4": ["sesiones", "conversiones_web"],
    "gsc": ["clics_busqueda", "impresiones_busqueda"],
    "meta_ads": ["gasto", "impresiones", "clics"],
}
REDES_CON_PUBLICACIONES = ("meta_ig", "meta_fb", "linkedin", "tiktok")


class RepositorioAlertas:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def cuentas_vigiladas(self) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT c.id, c.cliente_id, cl.nombre AS cliente, cl.slug, c.plataforma,
                   c.nombre_cuenta, c.token_expira_en, c.creado_en
            FROM   cuentas_conectadas c JOIN clientes cl ON cl.id = c.cliente_id
            WHERE  c.activo AND cl.activo
            ORDER  BY cl.nombre, c.plataforma
            """
        )
        return [dict(f) for f in filas]

    async def series(
        self, cuenta_id: int, codigos: list[str], desde: date, hasta: date
    ) -> dict[str, dict[date, float]]:
        filas = await self._pool.fetch(
            """
            SELECT metrica_codigo, fecha, valor FROM v_metrica_actual
            WHERE  cuenta_id = $1 AND metrica_codigo = ANY($2::text[])
              AND  fecha BETWEEN $3 AND $4 AND estado = 'consolidado'
            """,
            cuenta_id,
            codigos,
            desde,
            hasta,
        )
        salida: dict[str, dict[date, float]] = {}
        for f in filas:
            salida.setdefault(str(f["metrica_codigo"]), {})[f["fecha"]] = float(f["valor"])
        return salida

    async def agregaciones(self, codigos: list[str]) -> dict[str, str]:
        filas = await self._pool.fetch(
            "SELECT codigo, agregacion FROM dim_metrica WHERE codigo = ANY($1::text[])", codigos
        )
        return {str(f["codigo"]): str(f["agregacion"]) for f in filas}

    async def jobs_con_error(self, desde: datetime) -> list[dict[str, Any]]:
        """Último job fallido por cuenta y conector desde `desde`."""
        filas = await self._pool.fetch(
            """
            SELECT DISTINCT ON (cuenta_id, conector) cuenta_id, conector, error_detalle, iniciado_en
            FROM   jobs_ejecucion
            WHERE  estado = 'error' AND cuenta_id IS NOT NULL AND iniciado_en >= $1
            ORDER  BY cuenta_id, conector, iniciado_en DESC
            """,
            desde,
        )
        return [dict(f) for f in filas]

    async def ultima_publicacion(self, cuenta_id: int) -> datetime | None:
        v = await self._pool.fetchval(
            "SELECT max(publicado_en) FROM dim_publicacion WHERE cuenta_id = $1", cuenta_id
        )
        return v  # type: ignore[no-any-return]

    async def existe_abierta(self, cuenta_id: int | None, tipo: str, clave: str, dias: int) -> bool:
        v = await self._pool.fetchval(
            """
            SELECT 1 FROM alertas
            WHERE  cuenta_id IS NOT DISTINCT FROM $1 AND tipo = $2 AND detalle->>'clave' = $3
              AND  NOT resuelta AND creada_en >= now() - ($4::int || ' days')::interval
            LIMIT  1
            """,
            cuenta_id,
            tipo,
            clave,
            dias,
        )
        return v is not None

    async def crear(
        self, cuenta_id: int | None, tipo: str, severidad: str, titulo: str, detalle: dict[str, Any]
    ) -> int:
        v = await self._pool.fetchval(
            "INSERT INTO alertas (cuenta_id, tipo, severidad, titulo, detalle) "
            "VALUES ($1, $2, $3, $4, $5::jsonb) RETURNING id",
            cuenta_id,
            tipo,
            severidad,
            titulo,
            json.dumps(detalle, default=str),
        )
        return int(v)

    async def listar(self, solo_abiertas: bool = True, limite: int = 100) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT a.id, a.cuenta_id, a.tipo, a.severidad, a.titulo, a.detalle, a.resuelta,
                   a.creada_en, c.plataforma, c.nombre_cuenta, cl.nombre AS cliente,
                   cl.id AS cliente_id
            FROM   alertas a
            LEFT   JOIN cuentas_conectadas c ON c.id = a.cuenta_id
            LEFT   JOIN clientes cl ON cl.id = c.cliente_id
            WHERE  ($1::bool IS FALSE OR NOT a.resuelta)
            ORDER  BY a.resuelta,
                     CASE a.severidad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
                     a.creada_en DESC
            LIMIT  $2
            """,
            solo_abiertas,
            limite,
        )
        salida = []
        for f in filas:
            d = dict(f)
            if isinstance(d["detalle"], str):
                d["detalle"] = json.loads(d["detalle"])
            salida.append(d)
        return salida

    async def resolver(self, alerta_id: int, resuelta: bool = True) -> bool:
        r = await self._pool.execute(
            "UPDATE alertas SET resuelta = $2 WHERE id = $1", alerta_id, resuelta
        )
        return r.endswith("1")

    async def correos_equipo(self) -> list[str]:
        filas = await self._pool.fetch(
            "SELECT email FROM usuarios WHERE rol = 'equipo' AND activo ORDER BY email"
        )
        return [str(f["email"]) for f in filas]

    def ayer(self, hoy: date) -> date:
        return hoy - timedelta(days=1)

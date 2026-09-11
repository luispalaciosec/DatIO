"""SQL del explorador de datos: qué expone cada conector y consultas a medida con
descarga. Solo para el equipo (admin)."""

from datetime import date
from typing import Any

import asyncpg

GRANULARIDADES = {"dia": "day", "semana": "week", "mes": "month"}


class RepositorioDatos:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def catalogo(self) -> dict[str, Any]:
        """Por plataforma: métricas (con nombre nativo y cobertura real), dimensiones,
        métricas de publicaciones y cuentas con datos."""
        plataformas = [
            dict(f)
            for f in await self._pool.fetch(
                "SELECT codigo, nombre FROM plataformas ORDER BY nombre"
            )
        ]
        metricas = [
            dict(f)
            for f in await self._pool.fetch(
                """
            WITH cobertura AS (
                SELECT cu.plataforma, f.metrica_codigo, min(f.fecha) AS desde,
                       max(f.fecha) AS hasta, count(DISTINCT f.cuenta_id) AS cuentas
                FROM   fct_metrica_diaria f JOIN cuentas_conectadas cu ON cu.id = f.cuenta_id
                GROUP  BY 1, 2
            )
            SELECT m.plataforma, m.metrica_nativa, m.factor, d.codigo, d.nombre_es, d.unidad,
                   d.agregacion, d.es_acumulada, d.categoria,
                   c.desde, c.hasta, c.cuentas
            FROM   map_metrica_plataforma m
            JOIN   dim_metrica d ON d.codigo = m.metrica_codigo
            LEFT   JOIN cobertura c ON c.plataforma = m.plataforma AND c.metrica_codigo = d.codigo
            ORDER  BY m.plataforma, d.categoria, d.nombre_es
            """
            )
        ]
        dimensiones = [
            dict(f)
            for f in await self._pool.fetch(
                """
            SELECT cu.plataforma, x.dimension, array_agg(DISTINCT x.metrica_codigo) AS metricas,
                   min(x.fecha) AS desde, max(x.fecha) AS hasta,
                   count(DISTINCT x.valor_dimension) AS valores
            FROM   fct_metrica_dimension x JOIN cuentas_conectadas cu ON cu.id = x.cuenta_id
            GROUP  BY 1, 2 ORDER BY 1, 2
            """
            )
        ]
        publicaciones = [
            dict(f)
            for f in await self._pool.fetch(
                """
            SELECT cu.plataforma, p.metrica_codigo AS codigo, d.nombre_es, d.unidad,
                   count(DISTINCT p.publicacion_id) AS publicaciones
            FROM   fct_publicacion_diaria p
            JOIN   dim_publicacion pub ON pub.id = p.publicacion_id
            JOIN   cuentas_conectadas cu ON cu.id = pub.cuenta_id
            JOIN   dim_metrica d ON d.codigo = p.metrica_codigo
            GROUP  BY 1, 2, 3, 4 ORDER BY 1, 3
            """
            )
        ]
        cuentas = [
            dict(f)
            for f in await self._pool.fetch(
                """
            WITH cobertura AS (
                SELECT cuenta_id, min(fecha) AS desde, max(fecha) AS hasta, count(*) AS filas
                FROM   fct_metrica_diaria GROUP BY 1
            )
            SELECT cu.id, cu.plataforma, cu.nombre_cuenta, cu.id_externo, cl.id AS cliente_id,
                   cl.nombre AS cliente, cu.activo, c.desde, c.hasta, COALESCE(c.filas, 0) AS filas
            FROM   cuentas_conectadas cu JOIN clientes cl ON cl.id = cu.cliente_id
            LEFT   JOIN cobertura c ON c.cuenta_id = cu.id
            ORDER  BY cl.nombre, cu.plataforma
            """
            )
        ]
        salida: dict[str, Any] = {"plataformas": []}
        for p in plataformas:
            cod = p["codigo"]
            salida["plataformas"].append(
                {
                    **p,
                    "metricas": [m for m in metricas if m["plataforma"] == cod],
                    "dimensiones": [d for d in dimensiones if d["plataforma"] == cod],
                    "publicaciones": [x for x in publicaciones if x["plataforma"] == cod],
                    "cuentas": [c for c in cuentas if c["plataforma"] == cod],
                }
            )
        return salida

    async def consultar(
        self,
        cuentas: list[int],
        codigos: list[str],
        desde: date,
        hasta: date,
        granularidad: str,
        dimension: str | None,
        limite: int,
    ) -> list[dict[str, Any]]:
        """Filas largas: periodo, cuenta_id, [valor_dimension], metrica_codigo, valor."""
        if not cuentas or not codigos:
            return []
        if granularidad == "total":
            periodo = "$3::date"
        else:
            periodo = f"date_trunc('{GRANULARIDADES.get(granularidad, 'day')}', v.fecha)::date"
        if dimension:
            fuente = "v_metrica_dimension_actual"
            extra_col = ", v.valor_dimension"
            extra_cond = " AND v.dimension = $5"
            grupo = "1, 2, 3, 4, b.agregacion"
            params: list[Any] = [cuentas, codigos, desde, hasta, dimension, limite]
        else:
            fuente = "v_metrica_actual"
            extra_col = ", NULL::text AS valor_dimension"
            extra_cond = ""
            grupo = "1, 2, 3, 4, b.agregacion"
            params = [cuentas, codigos, desde, hasta, limite]
        lim = "$6" if dimension else "$5"
        filas = await self._pool.fetch(
            f"""
            WITH base AS (
                SELECT {periodo} AS periodo, v.cuenta_id, v.fecha, v.metrica_codigo, v.valor,
                       d.agregacion{extra_col}
                FROM   {fuente} v JOIN dim_metrica d ON d.codigo = v.metrica_codigo
                WHERE  v.cuenta_id = ANY($1::bigint[]) AND v.metrica_codigo = ANY($2::text[])
                  AND  v.fecha BETWEEN $3::date AND $4::date{extra_cond}
            ),
            ultimos AS (
                SELECT DISTINCT ON (periodo, cuenta_id, metrica_codigo, valor_dimension)
                       periodo, cuenta_id, metrica_codigo, valor_dimension, valor
                FROM base ORDER BY periodo, cuenta_id, metrica_codigo, valor_dimension, fecha DESC
            )
            SELECT b.periodo, b.cuenta_id, b.metrica_codigo, b.valor_dimension,
                   CASE b.agregacion
                        WHEN 'suma'     THEN sum(b.valor)
                        WHEN 'promedio' THEN avg(b.valor)
                        WHEN 'maximo'   THEN max(b.valor)
                        ELSE (SELECT u.valor FROM ultimos u
                              WHERE u.periodo = b.periodo AND u.cuenta_id = b.cuenta_id
                                AND u.metrica_codigo = b.metrica_codigo
                                AND u.valor_dimension IS NOT DISTINCT FROM b.valor_dimension)
                   END AS valor
            FROM   base b
            GROUP  BY {grupo}
            ORDER  BY 1, 2, 4, 3
            LIMIT  {lim}
            """,
            *params,
        )
        return [dict(f) for f in filas]

    async def nombres_cuentas(self, cuentas: list[int]) -> dict[int, str]:
        filas = await self._pool.fetch(
            "SELECT cu.id, cl.nombre || ' · ' || cu.plataforma || ' · ' || "
            "COALESCE(cu.nombre_cuenta, cu.id_externo) AS nombre "
            "FROM cuentas_conectadas cu JOIN clientes cl ON cl.id = cu.cliente_id "
            "WHERE cu.id = ANY($1::bigint[])",
            cuentas,
        )
        return {int(f["id"]): str(f["nombre"]) for f in filas}

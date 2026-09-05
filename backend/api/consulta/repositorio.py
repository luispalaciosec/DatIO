"""SQL de la capa de consulta (PT-08). Ningún resolvedor escribe SQL: todo pasa por aquí."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

GRANULARIDADES = {"dia": "day", "semana": "week", "mes": "month"}


@dataclass(frozen=True)
class Bloque:
    id: int
    pagina_id: int
    plataforma: str | None
    tipo: str
    orden: int
    ancho: int
    config: dict[str, Any]
    oculto: bool


@dataclass(frozen=True)
class Instancia:
    id: int
    cliente_id: int
    plantilla_id: int
    nombre_publico: str | None
    slug_publico: str


@dataclass(frozen=True)
class Agregado:
    valor: Decimal | None
    provisional: bool


class RepositorioConsulta:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ---- estructura ---------------------------------------------------------

    async def instancia_por_slug(self, slug_publico: str) -> Instancia | None:
        f = await self._pool.fetchrow(
            "SELECT id, cliente_id, plantilla_id, nombre_publico, slug_publico "
            "FROM reporte_instancias WHERE slug_publico = $1 AND activa",
            slug_publico,
        )
        return Instancia(*f) if f else None

    async def instancia_por_id(self, instancia_id: int) -> Instancia | None:
        f = await self._pool.fetchrow(
            "SELECT id, cliente_id, plantilla_id, nombre_publico, slug_publico "
            "FROM reporte_instancias WHERE id = $1 AND activa",
            instancia_id,
        )
        return Instancia(*f) if f else None

    async def tema(self, cliente_id: int) -> dict[str, Any]:
        f = await self._pool.fetchrow(
            """
            SELECT c.nombre, c.slug, t.logo_url, t.banner_url,
                   COALESCE(t.color_primario, '#C8102E')   AS color_primario,
                   COALESCE(t.color_secundario, '#1F1F1F') AS color_secundario,
                   COALESCE(t.color_acento, '#F5F5F5')     AS color_acento,
                   COALESCE(t.fuente_titulos, 'Inter')     AS fuente_titulos,
                   COALESCE(t.fuente_cuerpo, 'Inter')      AS fuente_cuerpo,
                   COALESCE(t.modo_oscuro, FALSE)          AS modo_oscuro
            FROM clientes c LEFT JOIN cliente_tema t ON t.cliente_id = c.id
            WHERE c.id = $1
            """,
            cliente_id,
        )
        return dict(f) if f else {}

    async def paginas(self, plantilla_id: int) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            "SELECT id, plataforma, slug, titulo, orden, icono FROM reporte_paginas "
            "WHERE plantilla_id = $1 ORDER BY orden",
            plantilla_id,
        )
        return [dict(f) for f in filas]

    async def bloques_de_pagina(self, instancia_id: int, pagina_id: int) -> list[Bloque]:
        filas = await self._pool.fetch(
            """
            SELECT b.id, b.pagina_id, p.plataforma, b.tipo, b.orden, b.ancho,
                   (b.config || COALESCE(o.config_merge, '{}'::jsonb)) AS config,
                   COALESCE(o.oculto, FALSE) AS oculto
            FROM reporte_bloques b
            JOIN reporte_paginas p ON p.id = b.pagina_id
            LEFT JOIN reporte_overrides o ON o.bloque_id = b.id AND o.instancia_id = $1
            WHERE b.pagina_id = $2
            ORDER BY b.orden
            """,
            instancia_id,
            pagina_id,
        )
        return [self._bloque(f) for f in filas]

    async def bloque_con_overrides(self, instancia_id: int, bloque_id: int) -> Bloque | None:
        f = await self._pool.fetchrow(
            """
            SELECT b.id, b.pagina_id, p.plataforma, b.tipo, b.orden, b.ancho,
                   (b.config || COALESCE(o.config_merge, '{}'::jsonb)) AS config,
                   COALESCE(o.oculto, FALSE) AS oculto
            FROM reporte_bloques b
            JOIN reporte_paginas p ON p.id = b.pagina_id
            JOIN reporte_instancias i ON i.plantilla_id = p.plantilla_id AND i.id = $1
            LEFT JOIN reporte_overrides o ON o.bloque_id = b.id AND o.instancia_id = $1
            WHERE b.id = $2
            """,
            instancia_id,
            bloque_id,
        )
        return self._bloque(f) if f else None

    @staticmethod
    def _bloque(f: asyncpg.Record) -> Bloque:
        config = f["config"]
        if isinstance(config, str):
            config = json.loads(config)
        return Bloque(
            f["id"],
            f["pagina_id"],
            f["plataforma"],
            f["tipo"],
            f["orden"],
            f["ancho"],
            config,
            f["oculto"],
        )

    async def cuentas_de_pagina(self, cliente_id: int, plataforma: str | None) -> list[int]:
        filas = await self._pool.fetch(
            "SELECT id FROM cuentas_conectadas WHERE cliente_id = $1 AND activo "
            "AND ($2::text IS NULL OR plataforma = $2) ORDER BY id",
            cliente_id,
            plataforma,
        )
        return [int(f["id"]) for f in filas]

    # ---- datos --------------------------------------------------------------

    async def agregar_metricas(
        self, cuentas: list[int], codigos: list[str], desde: date, hasta: date
    ) -> dict[str, Agregado]:
        """Agrega cada métrica según dim_metrica.agregacion sobre v_metrica_actual."""
        if not cuentas or not codigos:
            return {}
        filas = await self._pool.fetch(
            """
            WITH base AS (
                SELECT v.cuenta_id, v.fecha, v.metrica_codigo, v.valor, v.estado, d.agregacion
                FROM   v_metrica_actual v
                JOIN   dim_metrica d ON d.codigo = v.metrica_codigo
                WHERE  v.cuenta_id = ANY($1::bigint[]) AND v.metrica_codigo = ANY($2::text[])
                  AND  v.fecha BETWEEN $3 AND $4
            ),
            ultimos AS (
                SELECT DISTINCT ON (cuenta_id, metrica_codigo) cuenta_id, metrica_codigo, valor
                FROM base ORDER BY cuenta_id, metrica_codigo, fecha DESC
            )
            SELECT b.metrica_codigo,
                   CASE b.agregacion
                        WHEN 'suma'     THEN SUM(b.valor)
                        WHEN 'promedio' THEN AVG(b.valor)
                        WHEN 'maximo'   THEN MAX(b.valor)
                        WHEN 'ultimo'   THEN (SELECT SUM(u.valor) FROM ultimos u
                                              WHERE u.metrica_codigo = b.metrica_codigo)
                   END AS valor,
                   bool_or(b.estado = 'provisional') AS provisional
            FROM   base b
            GROUP  BY b.metrica_codigo, b.agregacion
            """,
            cuentas,
            codigos,
            desde,
            hasta,
        )
        return {f["metrica_codigo"]: Agregado(f["valor"], f["provisional"]) for f in filas}

    async def serie_metricas(
        self, cuentas: list[int], codigos: list[str], desde: date, hasta: date, granularidad: str
    ) -> list[dict[str, Any]]:
        """Serie por período: [{periodo, metrica_codigo, valor, provisional}] ordenada."""
        if not cuentas or not codigos:
            return []
        trunc = GRANULARIDADES.get(granularidad, "day")
        filas = await self._pool.fetch(
            f"""
            WITH base AS (
                SELECT date_trunc('{trunc}', v.fecha)::date AS periodo, v.cuenta_id, v.fecha,
                       v.metrica_codigo, v.valor, v.estado, d.agregacion
                FROM   v_metrica_actual v
                JOIN   dim_metrica d ON d.codigo = v.metrica_codigo
                WHERE  v.cuenta_id = ANY($1::bigint[]) AND v.metrica_codigo = ANY($2::text[])
                  AND  v.fecha BETWEEN $3 AND $4
            ),
            ultimos AS (
                SELECT DISTINCT ON (periodo, cuenta_id, metrica_codigo)
                       periodo, cuenta_id, metrica_codigo, valor
                FROM base ORDER BY periodo, cuenta_id, metrica_codigo, fecha DESC
            )
            SELECT b.periodo, b.metrica_codigo,
                   CASE b.agregacion
                        WHEN 'suma'     THEN SUM(b.valor)
                        WHEN 'promedio' THEN AVG(b.valor)
                        WHEN 'maximo'   THEN MAX(b.valor)
                        WHEN 'ultimo'   THEN (SELECT SUM(u.valor) FROM ultimos u
                                              WHERE u.periodo = b.periodo
                                                AND u.metrica_codigo = b.metrica_codigo)
                   END AS valor,
                   bool_or(b.estado = 'provisional') AS provisional
            FROM   base b
            GROUP  BY b.periodo, b.metrica_codigo, b.agregacion
            ORDER  BY b.periodo
            """,
            cuentas,
            codigos,
            desde,
            hasta,
        )
        return [dict(f) for f in filas]

    async def publicaciones(
        self, cuentas: list[int], desde: date, hasta: date, orden: str, limite: int
    ) -> list[dict[str, Any]]:
        """Publicaciones del período con su último snapshot de métricas."""
        if not cuentas:
            return []
        filas = await self._pool.fetch(
            """
            WITH ult AS (
                SELECT DISTINCT ON (publicacion_id, metrica_codigo)
                       publicacion_id, metrica_codigo, valor
                FROM   fct_publicacion_diaria
                ORDER  BY publicacion_id, metrica_codigo, fecha_snapshot DESC
            )
            SELECT p.id, p.id_externo, p.tipo, p.publicado_en, p.permalink, p.caption,
                   p.thumbnail_url,
                   COALESCE(jsonb_object_agg(u.metrica_codigo, u.valor)
                            FILTER (WHERE u.metrica_codigo IS NOT NULL), '{}'::jsonb) AS metricas
            FROM   dim_publicacion p
            LEFT   JOIN ult u ON u.publicacion_id = p.id
            WHERE  p.cuenta_id = ANY($1::bigint[])
              AND  p.publicado_en::date BETWEEN $2 AND $3
            GROUP  BY p.id
            ORDER  BY COALESCE((jsonb_object_agg(u.metrica_codigo, u.valor)
                       FILTER (WHERE u.metrica_codigo IS NOT NULL)) ->> $4, '0')::numeric DESC,
                     p.publicado_en DESC
            LIMIT  $5
            """,
            cuentas,
            desde,
            hasta,
            orden,
            limite,
        )
        salida = []
        for f in filas:
            d = dict(f)
            if isinstance(d["metricas"], str):
                d["metricas"] = json.loads(d["metricas"])
            salida.append(d)
        return salida

    async def metricas_info(self, codigos: list[str]) -> dict[str, dict[str, Any]]:
        filas = await self._pool.fetch(
            "SELECT codigo, nombre_es, unidad, agregacion FROM dim_metrica WHERE codigo = ANY($1)",
            codigos,
        )
        return {f["codigo"]: dict(f) for f in filas}

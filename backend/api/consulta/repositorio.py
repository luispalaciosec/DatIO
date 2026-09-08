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

    # ---- benchmark de competencia (PT-15) --------------------------------------

    async def competidores_con_snapshots(
        self, cliente_id: int, plataforma: str | None, codigos: list[str]
    ) -> list[dict[str, Any]]:
        """Competidores del cliente en la red, con su último snapshot y el anterior por métrica."""
        filas = await self._pool.fetch(
            """
            WITH ult AS (
                SELECT s.competidor_id, s.metrica_codigo, s.fecha_snapshot, s.valor,
                       row_number() OVER (PARTITION BY s.competidor_id, s.metrica_codigo
                                          ORDER BY s.fecha_snapshot DESC) AS n
                FROM   fct_competidor_snapshot s
                WHERE  s.metrica_codigo = ANY($3::text[])
            )
            SELECT k.id, k.nombre, k.handle, k.orden,
                   CASE WHEN EXISTS (SELECT 1 FROM competidor_imagenes i
                                     WHERE i.competidor_id = k.id AND i.clave = 'perfil')
                        THEN '/radar/imagen/' || k.id || '/perfil' ELSE k.logo_url END AS logo_url,
                   COALESCE(jsonb_object_agg(u.metrica_codigo, u.valor) FILTER (WHERE u.n = 1),
                            '{}'::jsonb) AS actual,
                   COALESCE(jsonb_object_agg(u.metrica_codigo, u.valor) FILTER (WHERE u.n = 2),
                            '{}'::jsonb) AS anterior,
                   max(u.fecha_snapshot) FILTER (WHERE u.n = 1) AS fecha_actual,
                   max(u.fecha_snapshot) FILTER (WHERE u.n = 2) AS fecha_anterior
            FROM   cliente_competidores k
            LEFT   JOIN ult u ON u.competidor_id = k.id
            WHERE  k.cliente_id = $1 AND ($2::text IS NULL OR k.plataforma = $2)
            GROUP  BY k.id
            ORDER  BY k.orden, k.id
            """,
            cliente_id,
            plataforma,
            codigos,
        )
        salida = []
        for f in filas:
            d = dict(f)
            for k in ("actual", "anterior"):
                if isinstance(d[k], str):
                    d[k] = json.loads(d[k])
            salida.append(d)
        return salida

    async def interacciones_ultimas_publicaciones(
        self, cuentas: list[int], n: int
    ) -> Decimal | None:
        """Suma de interacciones (último snapshot) de las N publicaciones más recientes."""
        if not cuentas:
            return None
        v = await self._pool.fetchval(
            """
            WITH recientes AS (
                SELECT id FROM dim_publicacion WHERE cuenta_id = ANY($1::bigint[])
                ORDER BY publicado_en DESC NULLS LAST LIMIT $2
            ), ult AS (
                SELECT DISTINCT ON (publicacion_id) publicacion_id, valor
                FROM fct_publicacion_diaria
                WHERE publicacion_id IN (SELECT id FROM recientes)
                  AND metrica_codigo = 'interacciones'
                ORDER BY publicacion_id, fecha_snapshot DESC
            )
            SELECT sum(valor) FROM ult
            """,
            cuentas,
            n,
        )
        return Decimal(v) if v is not None else None

    async def resumen_ultimas_publicaciones(
        self, cuentas: list[int], n: int
    ) -> dict[str, Any] | None:
        """Promedios por publicación, ritmo semanal y mezcla de formatos de las N publicaciones
        más recientes del cliente (último snapshot por métrica). Comparable con el radar."""
        if not cuentas:
            return None
        f = await self._pool.fetchrow(
            """
            WITH recientes AS (
                SELECT id, tipo, publicado_en FROM dim_publicacion
                WHERE cuenta_id = ANY($1::bigint[]) AND publicado_en IS NOT NULL
                ORDER BY publicado_en DESC LIMIT $2
            ), ult AS (
                SELECT DISTINCT ON (publicacion_id, metrica_codigo)
                       publicacion_id, metrica_codigo, valor
                FROM fct_publicacion_diaria
                WHERE publicacion_id IN (SELECT id FROM recientes)
                  AND metrica_codigo IN ('me_gusta', 'comentarios', 'interacciones')
                ORDER BY publicacion_id, metrica_codigo, fecha_snapshot DESC
            )
            SELECT (SELECT count(*) FROM recientes) AS publicaciones,
                   (SELECT min(publicado_en) FROM recientes) AS primera,
                   (SELECT max(publicado_en) FROM recientes) AS ultima,
                   (SELECT avg(valor) FROM ult WHERE metrica_codigo = 'me_gusta') AS me_gusta,
                   (SELECT avg(valor) FROM ult WHERE metrica_codigo = 'comentarios') AS comentarios,
                   (SELECT avg(valor) FROM ult WHERE metrica_codigo = 'interacciones')
                       AS interacciones,
                   (SELECT jsonb_object_agg(tipo, c) FROM
                       (SELECT COALESCE(tipo, 'otro') AS tipo, count(*) AS c
                        FROM recientes GROUP BY 1) x) AS formatos
            """,
            cuentas,
            n,
        )
        if f is None or not f["publicaciones"]:
            return None
        d = dict(f)
        if isinstance(d["formatos"], str):
            d["formatos"] = json.loads(d["formatos"])
        return d

    async def formatos_competidores(
        self, cliente_id: int, plataforma: str | None
    ) -> dict[int, dict[str, int]]:
        """Cantidad de publicaciones guardadas por formato, por competidor."""
        filas = await self._pool.fetch(
            """
            SELECT p.competidor_id, COALESCE(p.tipo, 'otro') AS tipo, count(*) AS c
            FROM   competidor_publicaciones p
            JOIN   cliente_competidores k ON k.id = p.competidor_id
            WHERE  k.cliente_id = $1 AND ($2::text IS NULL OR k.plataforma = $2)
            GROUP  BY 1, 2
            """,
            cliente_id,
            plataforma,
        )
        salida: dict[int, dict[str, int]] = {}
        for f in filas:
            salida.setdefault(int(f["competidor_id"]), {})[str(f["tipo"])] = int(f["c"])
        return salida

    async def serie_competidores(
        self, cliente_id: int, plataforma: str | None, metrica: str
    ) -> list[dict[str, Any]]:
        """Todos los snapshots de una métrica por competidor, para ver la evolución."""
        filas = await self._pool.fetch(
            """
            SELECT k.id AS competidor_id, k.nombre, s.fecha_snapshot, s.valor
            FROM   cliente_competidores k
            JOIN   fct_competidor_snapshot s ON s.competidor_id = k.id
            WHERE  k.cliente_id = $1 AND ($2::text IS NULL OR k.plataforma = $2)
              AND  s.metrica_codigo = $3
            ORDER  BY k.orden, k.id, s.fecha_snapshot
            """,
            cliente_id,
            plataforma,
            metrica,
        )
        return [dict(f) for f in filas]

    async def publicaciones_competencia(
        self, cliente_id: int, plataforma: str | None, limite: int, dias: int | None
    ) -> list[dict[str, Any]]:
        """Publicaciones de la competencia ordenadas por interacciones (me gusta + comentarios)."""
        filas = await self._pool.fetch(
            """
            SELECT p.competidor_id, k.nombre, k.handle, p.id_externo, p.tipo,
                   p.publicado_en, p.permalink, p.caption,
                   CASE WHEN ip.clave IS NOT NULL
                        THEN '/radar/imagen/' || k.id || '/perfil' ELSE k.logo_url END AS logo_url,
                   CASE WHEN im.clave IS NOT NULL
                        THEN '/radar/imagen/' || k.id || '/' || p.id_externo
                        ELSE p.thumbnail_url END AS thumbnail_url,
                   p.me_gusta, p.comentarios, p.reproducciones,
                   COALESCE(p.me_gusta, 0) + COALESCE(p.comentarios, 0) AS interacciones
            FROM   competidor_publicaciones p
            JOIN   cliente_competidores k ON k.id = p.competidor_id
            LEFT   JOIN competidor_imagenes im
                   ON im.competidor_id = p.competidor_id AND im.clave = p.id_externo
            LEFT   JOIN competidor_imagenes ip
                   ON ip.competidor_id = p.competidor_id AND ip.clave = 'perfil'
            WHERE  k.cliente_id = $1 AND ($2::text IS NULL OR k.plataforma = $2)
              AND  ($4::int IS NULL OR p.publicado_en >= now() - ($4::int || ' days')::interval)
            ORDER  BY interacciones DESC, p.publicado_en DESC
            LIMIT  $3
            """,
            cliente_id,
            plataforma,
            limite,
            dias,
        )
        return [dict(f) for f in filas]

    async def imagen_competidor(self, competidor_id: int, clave: str) -> tuple[str, bytes] | None:
        f = await self._pool.fetchrow(
            "SELECT tipo_mime, contenido FROM competidor_imagenes "
            "WHERE competidor_id = $1 AND clave = $2",
            competidor_id,
            clave,
        )
        return (str(f["tipo_mime"]), bytes(f["contenido"])) if f else None

    # ---- dimensiones (ciudad, país, canal, consulta, formato…) ---------------------

    async def agregar_dimension(
        self,
        cuentas: list[int],
        codigo: str,
        dimension: str,
        desde: date,
        hasta: date,
        limite: int = 10,
        modo: str = "suma",
    ) -> list[dict[str, Any]]:
        """Top N valores de una dimensión. modo 'suma' agrega los días del rango;
        modo 'ultimo' toma solo la última fecha disponible (métricas lifetime como demografía)."""
        if not cuentas:
            return []
        if modo == "ultimo":
            filas = await self._pool.fetch(
                """
                WITH ult AS (
                    SELECT max(fecha) AS fecha FROM v_metrica_dimension_actual
                    WHERE cuenta_id = ANY($1::bigint[]) AND metrica_codigo = $2 AND dimension = $3
                      AND fecha <= $5
                )
                SELECT v.valor_dimension, sum(v.valor) AS valor
                FROM   v_metrica_dimension_actual v, ult
                WHERE  v.cuenta_id = ANY($1::bigint[]) AND v.metrica_codigo = $2
                  AND  v.dimension = $3 AND v.fecha = ult.fecha
                GROUP  BY v.valor_dimension ORDER BY valor DESC LIMIT $4
                """,
                cuentas,
                codigo,
                dimension,
                limite,
                hasta,
            )
        else:
            filas = await self._pool.fetch(
                """
                SELECT valor_dimension, sum(valor) AS valor
                FROM   v_metrica_dimension_actual
                WHERE  cuenta_id = ANY($1::bigint[]) AND metrica_codigo = $2 AND dimension = $3
                  AND  fecha BETWEEN $5 AND $6
                GROUP  BY valor_dimension ORDER BY valor DESC LIMIT $4
                """,
                cuentas,
                codigo,
                dimension,
                limite,
                desde,
                hasta,
            )
        return [{"etiqueta": f["valor_dimension"], "valor": float(f["valor"])} for f in filas]

    async def tabla_dimension(
        self,
        cuentas: list[int],
        codigos: list[str],
        dimension: str,
        desde: date,
        hasta: date,
        orden: str,
        limite: int,
        modo: str = "suma",
    ) -> list[dict[str, Any]]:
        """Varias métricas por valor de dimensión (tabla de consultas, páginas, canales…)."""
        if not cuentas or not codigos:
            return []
        condicion_fecha = "v.fecha BETWEEN $4::date AND $5::date"
        if modo == "ultimo":
            condicion_fecha = """v.fecha = (
                SELECT max(fecha) FROM v_metrica_dimension_actual
                WHERE cuenta_id = ANY($1::bigint[]) AND dimension = $3 AND fecha <= $5::date
                  AND $4::date IS NOT NULL)"""
        filas = await self._pool.fetch(
            f"""
            WITH agg AS (
                SELECT v.valor_dimension, v.metrica_codigo, d.agregacion,
                       CASE d.agregacion WHEN 'promedio' THEN avg(v.valor)
                                         ELSE sum(v.valor) END AS valor
                FROM   v_metrica_dimension_actual v
                JOIN   dim_metrica d ON d.codigo = v.metrica_codigo
                WHERE  v.cuenta_id = ANY($1::bigint[]) AND v.metrica_codigo = ANY($2::text[])
                  AND  v.dimension = $3 AND {condicion_fecha}
                GROUP  BY v.valor_dimension, v.metrica_codigo, d.agregacion
            )
            SELECT valor_dimension, jsonb_object_agg(metrica_codigo, valor) AS valores
            FROM   agg GROUP BY valor_dimension
            ORDER  BY COALESCE((jsonb_object_agg(metrica_codigo, valor) ->> $6)::numeric, 0) DESC
            LIMIT  $7
            """,
            cuentas,
            codigos,
            dimension,
            desde,
            hasta,
            orden,
            limite,
        )
        salida = []
        for f in filas:
            valores = f["valores"]
            if isinstance(valores, str):
                valores = json.loads(valores)
            salida.append(
                {
                    "etiqueta": f["valor_dimension"],
                    "valores": {k: float(v) for k, v in valores.items()},
                }
            )
        return salida

    async def publicaciones_top(
        self, cuentas: list[int], desde: date, hasta: date, orden: str, limite: int
    ) -> list[dict[str, Any]]:
        return await self.publicaciones(cuentas, desde, hasta, orden, limite)

    async def rendimiento_por_tipo(
        self, cuentas: list[int], desde: date, hasta: date, codigos: list[str]
    ) -> list[dict[str, Any]]:
        """Promedio por publicación de cada métrica, agrupado por tipo (reel, imagen, carrusel)."""
        if not cuentas:
            return []
        filas = await self._pool.fetch(
            """
            WITH ult AS (
                SELECT DISTINCT ON (publicacion_id, metrica_codigo)
                       publicacion_id, metrica_codigo, valor
                FROM   fct_publicacion_diaria
                ORDER  BY publicacion_id, metrica_codigo, fecha_snapshot DESC
            ), por_tipo AS (
                SELECT COALESCE(p.tipo, 'otro') AS tipo, u.metrica_codigo,
                       avg(u.valor) AS promedio, count(DISTINCT p.id) AS n
                FROM   dim_publicacion p JOIN ult u ON u.publicacion_id = p.id
                WHERE  p.cuenta_id = ANY($1::bigint[]) AND p.publicado_en::date BETWEEN $2 AND $3
                  AND  u.metrica_codigo = ANY($4::text[])
                GROUP  BY 1, 2
            )
            SELECT tipo, max(n) AS publicaciones,
                   jsonb_object_agg(metrica_codigo, promedio) AS promedios
            FROM   por_tipo GROUP BY tipo ORDER BY 2 DESC
            """,
            cuentas,
            desde,
            hasta,
            codigos,
        )
        # promedio real por tipo: avg de los valores por publicación
        salida = []
        for f in filas:
            proms = f["promedios"]
            if isinstance(proms, str):
                proms = json.loads(proms)
            salida.append(
                {
                    "tipo": f["tipo"],
                    "publicaciones": int(f["publicaciones"]),
                    "promedios": {k: float(v) for k, v in proms.items()},
                }
            )
        return salida

    async def interacciones_por_dia_semana(
        self, cuentas: list[int], desde: date, hasta: date
    ) -> list[dict[str, Any]]:
        if not cuentas:
            return []
        filas = await self._pool.fetch(
            """
            WITH ult AS (
                SELECT DISTINCT ON (publicacion_id) publicacion_id, valor
                FROM fct_publicacion_diaria WHERE metrica_codigo = 'interacciones'
                ORDER BY publicacion_id, fecha_snapshot DESC
            )
            SELECT extract(isodow FROM p.publicado_en AT TIME ZONE 'America/Guayaquil')::int AS dia,
                   count(*) AS publicaciones, avg(u.valor) AS promedio
            FROM   dim_publicacion p JOIN ult u ON u.publicacion_id = p.id
            WHERE  p.cuenta_id = ANY($1::bigint[]) AND p.publicado_en::date BETWEEN $2 AND $3
            GROUP  BY 1 ORDER BY 1
            """,
            cuentas,
            desde,
            hasta,
        )
        return [
            {
                "dia": int(f["dia"]),
                "publicaciones": int(f["publicaciones"]),
                "promedio": float(f["promedio"]),
            }
            for f in filas
        ]

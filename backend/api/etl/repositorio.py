"""Repositorio del ETL (PT-03). Todo el SQL del ETL vive aquí."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg


@dataclass(frozen=True)
class Cuenta:
    id: int
    cliente_id: int
    plataforma: str
    id_externo: str
    nombre_cuenta: str | None


class RepositorioETL:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    # ---- cuentas y mapeo ----------------------------------------------------

    async def cuentas_activas(self, plataforma: str | None = None) -> list[Cuenta]:
        filas = await self._pool.fetch(
            """
            SELECT c.id, c.cliente_id, c.plataforma, c.id_externo, c.nombre_cuenta
            FROM   cuentas_conectadas c
            JOIN   clientes cl ON cl.id = c.cliente_id
            WHERE  c.activo AND cl.activo
              AND  ($1::text IS NULL OR c.plataforma = $1)
            ORDER  BY c.id
            """,
            plataforma,
        )
        return [
            Cuenta(f["id"], f["cliente_id"], f["plataforma"], f["id_externo"], f["nombre_cuenta"])
            for f in filas
        ]

    async def mapeo_plataforma(self, plataforma: str) -> dict[str, tuple[str, Decimal]]:
        filas = await self._pool.fetch(
            "SELECT metrica_nativa, metrica_codigo, factor FROM map_metrica_plataforma "
            "WHERE plataforma = $1",
            plataforma,
        )
        return {f["metrica_nativa"]: (f["metrica_codigo"], Decimal(f["factor"])) for f in filas}

    # ---- credenciales (pgcrypto) --------------------------------------------

    async def credencial(self, cuenta_id: int, clave: str) -> str | None:
        valor = await self._pool.fetchval(
            "SELECT pgp_sym_decrypt(credencial_cifrada, $2) FROM cuentas_conectadas WHERE id = $1",
            cuenta_id,
            clave,
        )
        return str(valor) if valor is not None else None

    async def guardar_credencial(self, cuenta_id: int, credencial: str, clave: str) -> None:
        await self._pool.execute(
            "UPDATE cuentas_conectadas SET credencial_cifrada = pgp_sym_encrypt($2, $3) "
            "WHERE id = $1",
            cuenta_id,
            credencial,
            clave,
        )

    # ---- jobs ---------------------------------------------------------------

    async def abrir_job(self, cuenta_id: int, conector: str) -> int:
        job_id = await self._pool.fetchval(
            "INSERT INTO jobs_ejecucion (cuenta_id, conector, estado) "
            "VALUES ($1, $2, 'corriendo') RETURNING id",
            cuenta_id,
            conector,
        )
        return int(job_id)

    async def cerrar_job(
        self, job_id: int, estado: str, filas_escritas: int, error_detalle: str | None = None
    ) -> None:
        await self._pool.execute(
            "UPDATE jobs_ejecucion SET estado = $2, filas_escritas = $3, error_detalle = $4, "
            "finalizado_en = NOW() WHERE id = $1",
            job_id,
            estado,
            filas_escritas,
            error_detalle,
        )

    async def job(self, job_id: int) -> dict[str, Any] | None:
        fila = await self._pool.fetchrow("SELECT * FROM jobs_ejecucion WHERE id = $1", job_id)
        return dict(fila) if fila else None

    # ---- raw (append-only) --------------------------------------------------

    async def guardar_raw(
        self,
        cuenta_id: int,
        endpoint: str,
        params: dict[str, Any] | None,
        payload: Any,
        job_id: int | None,
    ) -> int:
        raw_id = await self._pool.fetchval(
            "INSERT INTO raw_payloads (cuenta_id, endpoint, params, payload, job_id) "
            "VALUES ($1, $2, $3::jsonb, $4::jsonb, $5) RETURNING id",
            cuenta_id,
            endpoint,
            json.dumps(params) if params is not None else None,
            json.dumps(payload, default=str),
            job_id,
        )
        return int(raw_id)

    async def contar_raw(self, cuenta_id: int) -> int:
        return int(
            await self._pool.fetchval(
                "SELECT count(*) FROM raw_payloads WHERE cuenta_id = $1", cuenta_id
            )
        )

    # ---- hechos -------------------------------------------------------------

    async def upsert_metricas(
        self,
        cuenta_id: int,
        filas: list[tuple[date, str, Decimal]],
        fecha_snapshot: date,
        estado: str = "consolidado",
    ) -> int:
        """Upsert idempotente. Correr dos veces deja el mismo estado."""
        if not filas:
            return 0
        # Deduplicar dentro del lote: el último valor gana.
        unicas = {(f, m): v for f, m, v in filas}
        registros = [(cuenta_id, f, m, v, fecha_snapshot, estado) for (f, m), v in unicas.items()]
        async with self._pool.acquire() as con, con.transaction():
            await con.executemany(
                """
                INSERT INTO fct_metrica_diaria
                       (cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado)
                VALUES ($1, $2, $3, $4, $5, $6::estado_dato)
                ON CONFLICT (cuenta_id, fecha, metrica_codigo, fecha_snapshot)
                DO UPDATE SET valor = EXCLUDED.valor, estado = EXCLUDED.estado
                """,
                registros,
            )
        return len(registros)

    async def upsert_dimensiones(
        self,
        cuenta_id: int,
        filas: list[tuple[date, str, str, str, Decimal]],
        fecha_snapshot: date,
    ) -> int:
        """(fecha, metrica, dimension, valor_dimension, valor) → fct_metrica_dimension."""
        if not filas:
            return 0
        unicas = {(f, m, d, v): x for f, m, d, v, x in filas}
        registros = [
            (cuenta_id, f, m, d, v, x, fecha_snapshot) for (f, m, d, v), x in unicas.items()
        ]
        async with self._pool.acquire() as con, con.transaction():
            await con.executemany(
                """
                INSERT INTO fct_metrica_dimension
                       (cuenta_id, fecha, metrica_codigo, dimension, valor_dimension, valor,
                        fecha_snapshot)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (cuenta_id, fecha, metrica_codigo, dimension, valor_dimension,
                             fecha_snapshot)
                DO UPDATE SET valor = EXCLUDED.valor
                """,
                registros,
            )
        return len(registros)

    async def contar_dimensiones(self, cuenta_id: int) -> int:
        return int(
            await self._pool.fetchval(
                "SELECT count(*) FROM fct_metrica_dimension WHERE cuenta_id = $1", cuenta_id
            )
        )

    async def metricas_actuales(
        self, cuenta_id: int, desde: date, hasta: date
    ) -> list[dict[str, Any]]:
        filas = await self._pool.fetch(
            """
            SELECT fecha, metrica_codigo, valor, fecha_snapshot, estado
            FROM   v_metrica_actual
            WHERE  cuenta_id = $1 AND fecha BETWEEN $2 AND $3
            ORDER  BY fecha, metrica_codigo
            """,
            cuenta_id,
            desde,
            hasta,
        )
        return [dict(f) for f in filas]

    async def contar_metricas(self, cuenta_id: int) -> int:
        return int(
            await self._pool.fetchval(
                "SELECT count(*) FROM fct_metrica_diaria WHERE cuenta_id = $1", cuenta_id
            )
        )

    # ---- publicaciones -----------------------------------------------------

    async def upsert_publicaciones(
        self, cuenta_id: int, publicaciones: list[dict[str, Any]], visto: date
    ) -> dict[str, int]:
        """Crea o actualiza dim_publicacion. Devuelve id_externo → id."""
        ids: dict[str, int] = {}
        async with self._pool.acquire() as con, con.transaction():
            for p in publicaciones:
                pid = await con.fetchval(
                    """
                    INSERT INTO dim_publicacion
                           (cuenta_id, id_externo, tipo, publicado_en, permalink, caption,
                            thumbnail_url, visto_por_ultima_vez)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (cuenta_id, id_externo) DO UPDATE SET
                        tipo = COALESCE(EXCLUDED.tipo, dim_publicacion.tipo),
                        publicado_en = COALESCE(EXCLUDED.publicado_en,
                                                dim_publicacion.publicado_en),
                        permalink = COALESCE(EXCLUDED.permalink, dim_publicacion.permalink),
                        caption = COALESCE(EXCLUDED.caption, dim_publicacion.caption),
                        thumbnail_url = COALESCE(EXCLUDED.thumbnail_url,
                                                 dim_publicacion.thumbnail_url),
                        visto_por_ultima_vez = EXCLUDED.visto_por_ultima_vez
                    RETURNING id
                    """,
                    cuenta_id,
                    p["id_externo"],
                    p.get("tipo"),
                    p.get("publicado_en"),
                    p.get("permalink"),
                    p.get("caption"),
                    p.get("thumbnail_url"),
                    visto,
                )
                ids[p["id_externo"]] = int(pid)
        return ids

    async def upsert_metricas_publicacion(
        self, filas: list[tuple[int, str, Decimal]], fecha_snapshot: date
    ) -> int:
        """(publicacion_id, metrica_codigo, valor) → fct_publicacion_diaria, idempotente."""
        if not filas:
            return 0
        unicas = {(p, m): v for p, m, v in filas}
        registros = [(p, fecha_snapshot, m, v) for (p, m), v in unicas.items()]
        async with self._pool.acquire() as con, con.transaction():
            await con.executemany(
                """
                INSERT INTO fct_publicacion_diaria
                       (publicacion_id, fecha_snapshot, metrica_codigo, valor)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (publicacion_id, fecha_snapshot, metrica_codigo)
                DO UPDATE SET valor = EXCLUDED.valor
                """,
                registros,
            )
        return len(registros)

    async def contar_publicaciones(self, cuenta_id: int) -> int:
        return int(
            await self._pool.fetchval(
                "SELECT count(*) FROM dim_publicacion WHERE cuenta_id = $1", cuenta_id
            )
        )

    # ---- radar competitivo (PT-15) --------------------------------------------

    async def competidores_para_radar(
        self, dias_minimos: int = 7, cliente_id: int | None = None, forzar: bool = False
    ) -> list[dict[str, Any]]:
        """Competidores de clientes activos cuyo último snapshot tiene más de N días (o todos)."""
        filas = await self._pool.fetch(
            """
            SELECT k.id, k.cliente_id, k.plataforma, k.nombre, k.handle, k.logo_url,
                   (SELECT max(fecha_snapshot) FROM fct_competidor_snapshot s
                     WHERE s.competidor_id = k.id) AS ultimo
            FROM   cliente_competidores k JOIN clientes c ON c.id = k.cliente_id
            WHERE  c.activo AND ($1::bigint IS NULL OR k.cliente_id = $1)
            ORDER  BY k.plataforma, k.cliente_id, k.orden, k.id
            """,
            cliente_id,
        )
        salida = []
        for f in filas:
            d = dict(f)
            if forzar or d["ultimo"] is None or (date.today() - d["ultimo"]).days >= dias_minimos:
                salida.append(d)
        return salida

    async def guardar_raw_competidor(
        self, competidor_id: int, endpoint: str, params: dict[str, Any] | None, payload: Any
    ) -> int:
        raw_id = await self._pool.fetchval(
            "INSERT INTO raw_payloads (competidor_id, endpoint, params, payload) "
            "VALUES ($1, $2, $3::jsonb, $4::jsonb) RETURNING id",
            competidor_id,
            endpoint,
            json.dumps(params) if params else None,
            json.dumps(payload, default=str),
        )
        return int(raw_id)

    async def upsert_publicaciones_competidor(
        self, competidor_id: int, fecha_snapshot: date, publicaciones: list[dict[str, Any]]
    ) -> int:
        if not publicaciones:
            return 0
        async with self._pool.acquire() as con, con.transaction():
            await con.executemany(
                """
                INSERT INTO competidor_publicaciones
                       (competidor_id, id_externo, tipo, publicado_en, permalink, caption,
                        thumbnail_url, me_gusta, comentarios, reproducciones, fecha_snapshot)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (competidor_id, id_externo) DO UPDATE SET
                    tipo = EXCLUDED.tipo, publicado_en = EXCLUDED.publicado_en,
                    permalink = EXCLUDED.permalink, caption = EXCLUDED.caption,
                    thumbnail_url = EXCLUDED.thumbnail_url, me_gusta = EXCLUDED.me_gusta,
                    comentarios = EXCLUDED.comentarios, reproducciones = EXCLUDED.reproducciones,
                    fecha_snapshot = EXCLUDED.fecha_snapshot
                """,
                [
                    (
                        competidor_id,
                        p["id_externo"],
                        p.get("tipo"),
                        p.get("publicado_en"),
                        p.get("permalink"),
                        p.get("caption"),
                        p.get("thumbnail_url"),
                        p.get("me_gusta"),
                        p.get("comentarios"),
                        p.get("reproducciones"),
                        fecha_snapshot,
                    )
                    for p in publicaciones
                ],
            )
        return len(publicaciones)

    async def upsert_anuncios_competidor(
        self, competidor_id: int, anuncios: list[dict[str, Any]]
    ) -> int:
        """Los anuncios vistos hoy se crean o refrescan (ultima_vez_visto = hoy, activo);
        los que no aparecieron en esta corrida se marcan inactivos. primera_vez_visto nunca
        avanza: es la antigüedad real del anuncio."""
        async with self._pool.acquire() as con, con.transaction():
            await con.execute(
                "UPDATE dim_anuncio_competencia SET activo = FALSE "
                "WHERE competidor_id = $1 AND NOT (ad_archive_id = ANY($2::text[]))",
                competidor_id,
                [a["ad_archive_id"] for a in anuncios],
            )
            if not anuncios:
                return 0
            await con.executemany(
                """
                INSERT INTO dim_anuncio_competencia
                       (competidor_id, ad_archive_id, primera_vez_visto, ultima_vez_visto,
                        plataformas, creatividad_url, copy_texto, formato, oferta, titulo,
                        enlace, url_biblioteca, activo)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (competidor_id, ad_archive_id) DO UPDATE SET
                    primera_vez_visto = LEAST(dim_anuncio_competencia.primera_vez_visto,
                                              EXCLUDED.primera_vez_visto),
                    ultima_vez_visto = EXCLUDED.ultima_vez_visto,
                    plataformas = EXCLUDED.plataformas,
                    creatividad_url = COALESCE(EXCLUDED.creatividad_url,
                                               dim_anuncio_competencia.creatividad_url),
                    copy_texto = COALESCE(EXCLUDED.copy_texto, dim_anuncio_competencia.copy_texto),
                    formato = COALESCE(EXCLUDED.formato, dim_anuncio_competencia.formato),
                    oferta = COALESCE(EXCLUDED.oferta, dim_anuncio_competencia.oferta),
                    titulo = COALESCE(EXCLUDED.titulo, dim_anuncio_competencia.titulo),
                    enlace = COALESCE(EXCLUDED.enlace, dim_anuncio_competencia.enlace),
                    url_biblioteca = COALESCE(EXCLUDED.url_biblioteca,
                                              dim_anuncio_competencia.url_biblioteca),
                    activo = EXCLUDED.activo
                """,
                [
                    (
                        competidor_id,
                        a["ad_archive_id"],
                        a["primera_vez_visto"],
                        a["ultima_vez_visto"],
                        a.get("plataformas") or [],
                        a.get("creatividad_url"),
                        a.get("copy_texto"),
                        a.get("formato"),
                        a.get("oferta"),
                        a.get("titulo"),
                        a.get("enlace"),
                        a.get("url_biblioteca"),
                        bool(a.get("activo", True)),
                    )
                    for a in anuncios
                ],
            )
        return len(anuncios)

    async def imagenes_existentes(self, competidor_id: int) -> set[str]:
        filas = await self._pool.fetch(
            "SELECT clave FROM competidor_imagenes WHERE competidor_id = $1", competidor_id
        )
        return {str(f["clave"]) for f in filas}

    async def guardar_imagen_competidor(
        self, competidor_id: int, clave: str, tipo_mime: str, contenido: bytes
    ) -> None:
        await self._pool.execute(
            """
            INSERT INTO competidor_imagenes (competidor_id, clave, tipo_mime, contenido)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (competidor_id, clave) DO UPDATE
            SET tipo_mime = EXCLUDED.tipo_mime, contenido = EXCLUDED.contenido,
                actualizado_en = now()
            """,
            competidor_id,
            clave,
            tipo_mime,
            contenido,
        )

    async def upsert_snapshot_competidor(
        self, competidor_id: int, fecha_snapshot: date, valores: dict[str, Decimal]
    ) -> int:
        if not valores:
            return 0
        async with self._pool.acquire() as con, con.transaction():
            await con.executemany(
                """
                INSERT INTO fct_competidor_snapshot
                       (competidor_id, fecha_snapshot, metrica_codigo, valor)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (competidor_id, fecha_snapshot, metrica_codigo)
                DO UPDATE SET valor = EXCLUDED.valor
                """,
                [(competidor_id, fecha_snapshot, m, v) for m, v in valores.items()],
            )
        return len(valores)

    async def actualizar_logo_competidor(self, competidor_id: int, logo_url: str) -> None:
        await self._pool.execute(
            "UPDATE cliente_competidores SET logo_url = $2 "
            "WHERE id = $1 AND (logo_url IS NULL OR logo_url = '')",
            competidor_id,
            logo_url,
        )

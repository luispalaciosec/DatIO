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

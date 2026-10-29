"""Mantenimiento semanal de la base (corre los domingos desde el cron):

- Compactar snapshots: el re-sync de 28 días reescribe cada dato a diario con un fecha_snapshot
  nuevo; cuando el valor no cambió, la copia no aporta auditoría. Se conservan el primer
  snapshot, el último y cada cambio de valor. v_metrica_actual no se ve afectada.
- Caducar conexiones OAuth pendientes de más de 7 días (el token nunca se usó).
"""

from dataclasses import dataclass

import asyncpg


@dataclass
class ResumenMantenimiento:
    snapshots_borrados: int = 0
    dimensiones_borradas: int = 0
    conexiones_caducadas: int = 0


def _n(resultado: str) -> int:
    return int(resultado.split()[-1]) if resultado else 0


async def compactar_snapshots(pool: asyncpg.Pool) -> tuple[int, int]:
    metricas = await pool.execute(
        """
        DELETE FROM fct_metrica_diaria f USING (
            SELECT cuenta_id, fecha, metrica_codigo, fecha_snapshot,
                   valor, lag(valor) OVER w AS previo,
                   row_number() OVER w AS n,
                   count(*) OVER (PARTITION BY cuenta_id, fecha, metrica_codigo) AS total
            FROM   fct_metrica_diaria
            WINDOW w AS (PARTITION BY cuenta_id, fecha, metrica_codigo ORDER BY fecha_snapshot)
        ) x
        WHERE  f.cuenta_id = x.cuenta_id AND f.fecha = x.fecha
          AND  f.metrica_codigo = x.metrica_codigo AND f.fecha_snapshot = x.fecha_snapshot
          AND  x.n > 1 AND x.n < x.total AND x.valor = x.previo
        """
    )
    dimensiones = await pool.execute(
        """
        DELETE FROM fct_metrica_dimension f USING (
            SELECT cuenta_id, fecha, metrica_codigo, dimension, valor_dimension, fecha_snapshot,
                   valor, lag(valor) OVER w AS previo, row_number() OVER w AS n,
                   count(*) OVER (PARTITION BY cuenta_id, fecha, metrica_codigo, dimension,
                                  valor_dimension) AS total
            FROM   fct_metrica_dimension
            WINDOW w AS (PARTITION BY cuenta_id, fecha, metrica_codigo, dimension,
                         valor_dimension ORDER BY fecha_snapshot)
        ) x
        WHERE  f.cuenta_id = x.cuenta_id AND f.fecha = x.fecha
          AND  f.metrica_codigo = x.metrica_codigo AND f.dimension = x.dimension
          AND  f.valor_dimension = x.valor_dimension AND f.fecha_snapshot = x.fecha_snapshot
          AND  x.n > 1 AND x.n < x.total AND x.valor = x.previo
        """
    )
    return _n(metricas), _n(dimensiones)


async def caducar_conexiones(pool: asyncpg.Pool, dias: int = 7) -> int:
    r = await pool.execute(
        "DELETE FROM conexiones_oauth WHERE estado = 'pendiente' "
        "AND creado_en < now() - ($1::int || ' days')::interval",
        dias,
    )
    return _n(r)


async def mantenimiento(pool: asyncpg.Pool) -> ResumenMantenimiento:
    resumen = ResumenMantenimiento()
    resumen.snapshots_borrados, resumen.dimensiones_borradas = await compactar_snapshots(pool)
    resumen.conexiones_caducadas = await caducar_conexiones(pool)
    return resumen

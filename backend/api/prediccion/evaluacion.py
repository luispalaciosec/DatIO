"""Evaluación honesta de las proyecciones (spec/04 §6): cuando el mes proyectado cierra y el
dato real está consolidado, se guarda el real, el error absoluto y si cayó dentro de la banda.
Con eso v_precision_modelo puede decir "nuestras proyecciones tienen X % de error"."""

from datetime import date, timedelta
from typing import Any

import asyncpg


async def evaluar_proyecciones(pool: asyncpg.Pool, hoy: date) -> int:
    """Evalúa proyecciones con fecha_objetivo ya pasada (y 2 días de margen para consolidar)."""
    tope = hoy - timedelta(days=2)
    pendientes = await pool.fetch(
        """
        SELECT p.id, p.cuenta_id, p.metrica_codigo, p.fecha_objetivo, p.valor_p50, p.valor_p10,
               p.valor_p90, d.agregacion
        FROM   fct_proyeccion p
        JOIN   dim_metrica d ON d.codigo = p.metrica_codigo
        LEFT   JOIN fct_proyeccion_eval e ON e.proyeccion_id = p.id
        WHERE  e.proyeccion_id IS NULL AND p.fecha_objetivo <= $1
        """,
        tope,
    )
    n = 0
    for p in pendientes:
        fin: date = p["fecha_objetivo"]
        inicio = fin.replace(day=1)
        real = await _real(pool, p, inicio, fin)
        if real is None:
            continue
        dentro: bool | None = None
        if p["valor_p10"] is not None and p["valor_p90"] is not None:
            dentro = float(p["valor_p10"]) <= real <= float(p["valor_p90"])
        await pool.execute(
            """
            INSERT INTO fct_proyeccion_eval (proyeccion_id, valor_real, error_abs, dentro_banda)
            VALUES ($1, $2::numeric, $3::numeric, $4) ON CONFLICT (proyeccion_id) DO NOTHING
            """,
            p["id"],
            real,
            abs(real - float(p["valor_p50"])),
            dentro,
        )
        n += 1
    return n


async def _real(pool: asyncpg.Pool, p: Any, inicio: date, fin: date) -> float | None:
    if p["agregacion"] == "ultimo":
        v = await pool.fetchval(
            "SELECT valor FROM v_metrica_actual WHERE cuenta_id = $1 AND metrica_codigo = $2 "
            "AND fecha BETWEEN $3 AND $4 ORDER BY fecha DESC LIMIT 1",
            p["cuenta_id"],
            p["metrica_codigo"],
            inicio,
            fin,
        )
    else:
        f = await pool.fetchrow(
            "SELECT sum(valor) AS s, count(*) AS n FROM v_metrica_actual "
            "WHERE cuenta_id = $1 AND metrica_codigo = $2 AND fecha BETWEEN $3 AND $4",
            p["cuenta_id"],
            p["metrica_codigo"],
            inicio,
            fin,
        )
        # Mes incompleto en la base (menos del 80 % de los días): no se evalúa todavía
        v = f["s"] if f and f["n"] >= 0.8 * ((fin - inicio).days + 1) else None
    return float(v) if v is not None else None

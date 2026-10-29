# ruff: noqa: E501
"""Compactación de snapshots, evaluación de proyecciones y alerta de datos atrasados."""

from datetime import date, timedelta

from api.alertas.repositorio import RepositorioAlertas
from api.alertas.servicio import correr_alertas
from api.etl.mantenimiento import caducar_conexiones, compactar_snapshots
from api.prediccion.evaluacion import evaluar_proyecciones
from tests.conftest import requiere_db

pytestmark = requiere_db


async def test_compactar_conserva_primero_ultimo_y_cambios(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    cid = cliente_a.cuenta.id
    f = date(2026, 6, 1)
    filas = [
        (cid, f, "sesiones", v, f + timedelta(days=i), "consolidado")
        for i, v in enumerate((10, 10, 10, 12, 12, 12, 12))
    ]
    await pool.executemany(
        "INSERT INTO fct_metrica_diaria (cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado) "
        "VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT DO NOTHING",
        filas,
    )
    borrados, _ = await compactar_snapshots(pool)
    assert borrados >= 4
    quedan = await pool.fetch(
        "SELECT fecha_snapshot, valor FROM fct_metrica_diaria WHERE cuenta_id = $1 AND fecha = $2 "
        "AND metrica_codigo = 'sesiones' ORDER BY fecha_snapshot",
        cid,
        f,
    )
    # primero (10), cambio (12 el día 4) y último (12 el día 7)
    assert [(r["fecha_snapshot"].day, int(r["valor"])) for r in quedan] == [
        (1, 10),
        (4, 12),
        (7, 12),
    ]
    actual = await pool.fetchval(
        "SELECT valor FROM v_metrica_actual WHERE cuenta_id = $1 AND fecha = $2 AND metrica_codigo = 'sesiones'",
        cid,
        f,
    )
    assert int(actual) == 12
    await pool.execute("DELETE FROM fct_metrica_diaria WHERE cuenta_id = $1 AND fecha = $2", cid, f)


async def test_evaluar_proyecciones_cerradas(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    cid = cliente_a.cuenta.id
    # Mes de junio 2026 completo: 30 días × 100 sesiones = 3000
    await pool.executemany(
        "INSERT INTO fct_metrica_diaria (cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado) "
        "VALUES ($1, $2, 'sesiones', 100, $2, 'consolidado') ON CONFLICT DO NOTHING",
        [(cid, date(2026, 6, 1) + timedelta(days=i)) for i in range(30)],
    )
    pid = await pool.fetchval(
        "INSERT INTO fct_proyeccion (cuenta_id, metrica_codigo, fecha_objetivo, corrida_en, horizonte_dias, "
        "valor_p50, valor_p10, valor_p90, modelo, modelo_version) VALUES ($1, 'sesiones', '2026-06-30', "
        "'2026-06-15', 15, 2900, 2500, 3200, 'pacing', 'test') RETURNING id",
        cid,
    )
    n = await evaluar_proyecciones(pool, date(2026, 7, 5))
    assert n >= 1
    e = await pool.fetchrow(
        "SELECT valor_real, error_abs, dentro_banda FROM fct_proyeccion_eval WHERE proyeccion_id = $1",
        pid,
    )
    assert (
        float(e["valor_real"]) == 3000
        and float(e["error_abs"]) == 100
        and e["dentro_banda"] is True
    )
    assert await evaluar_proyecciones(pool, date(2026, 7, 5)) == 0  # no se evalúa dos veces
    await pool.execute("DELETE FROM fct_proyeccion WHERE id = $1", pid)
    await pool.execute(
        "DELETE FROM fct_metrica_diaria WHERE cuenta_id = $1 AND fecha BETWEEN '2026-06-01' AND '2026-06-30'",
        cid,
    )


async def test_datos_atrasados_y_autocierre(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    cid = cliente_a.cuenta.id
    repo = RepositorioAlertas(pool)
    # La cuenta de prueba tiene datos viejos (o ninguno): debe alertar una sola vez
    r1 = await correr_alertas(repo, date.today())
    mias = [a for a in r1.nuevas if a.cliente_id == cliente_a.id and "datos" in a.titulo]
    r2 = await correr_alertas(repo, date.today())
    repetidas = [a for a in r2.nuevas if a.cliente_id == cliente_a.id and "datos" in a.titulo]
    assert len(mias) <= 1 and repetidas == []
    abiertas = await pool.fetchval(
        "SELECT count(*) FROM alertas WHERE cuenta_id = $1 AND detalle->>'clave' = 'datos_atrasados' AND NOT resuelta",
        cid,
    )
    # Con datos de ayer la condición desaparece y la alerta se cierra sola
    await pool.execute(
        "INSERT INTO fct_metrica_diaria (cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado) "
        "VALUES ($1, current_date - 1, 'sesiones', 1, current_date, 'consolidado') ON CONFLICT DO NOTHING",
        cid,
    )
    r3 = await correr_alertas(repo, date.today())
    cerradas_mias = await pool.fetchval(
        "SELECT count(*) FROM alertas WHERE cuenta_id = $1 AND detalle->>'clave' = 'datos_atrasados' AND resuelta",
        cid,
    )
    assert cerradas_mias >= abiertas and r3.cerradas >= 0
    await pool.execute("DELETE FROM alertas WHERE cuenta_id = $1", cid)
    await pool.execute(
        "DELETE FROM fct_metrica_diaria WHERE cuenta_id = $1 AND fecha = current_date - 1", cid
    )


async def test_caducar_conexiones_pendientes(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    vieja = await pool.fetchval(
        "INSERT INTO conexiones_oauth (cliente_id, proveedor, creado_por, token_cifrado, creado_en) "
        "VALUES ($1, 'google', 't@t', 'x'::bytea, now() - interval '10 days') RETURNING id",
        cliente_a.id,
    )
    nueva = await pool.fetchval(
        "INSERT INTO conexiones_oauth (cliente_id, proveedor, creado_por, token_cifrado) "
        "VALUES ($1, 'google', 't@t', 'x'::bytea) RETURNING id",
        cliente_a.id,
    )
    n = await caducar_conexiones(pool, 7)
    assert n >= 1
    assert await pool.fetchval("SELECT count(*) FROM conexiones_oauth WHERE id = $1", vieja) == 0
    assert await pool.fetchval("SELECT count(*) FROM conexiones_oauth WHERE id = $1", nueva) == 1
    await pool.execute("DELETE FROM conexiones_oauth WHERE id = $1", nueva)

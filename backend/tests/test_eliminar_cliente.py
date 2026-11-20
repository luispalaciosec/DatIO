# ruff: noqa: E501
"""Eliminar un cliente borra todos sus datos (incluido raw) y nada de otros clientes."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest

from api.etl.repositorio import RepositorioETL
from api.main import crear_app
from tests.conftest import _crear_cliente, requiere_db, token_para

pytestmark = requiere_db


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


async def _poblar(pool, c) -> None:  # type: ignore[no-untyped-def]
    repo = RepositorioETL(pool)
    cid = c.cuenta.id
    await repo.upsert_metricas(
        cid, [(date(2026, 11, 1), "sesiones", Decimal(5))], date(2026, 11, 2)
    )
    job = await repo.abrir_job(cid, "ga4")
    await repo.guardar_raw(cid, "ga4", {}, [{"x": 1}], job)
    await repo.cerrar_job(job, "ok", 1)
    ids = await repo.upsert_publicaciones(
        cid,
        [
            {
                "id_externo": "p1",
                "tipo": "video",
                "publicado_en": datetime(2026, 11, 1, tzinfo=UTC),
                "permalink": None,
                "caption": None,
                "thumbnail_url": None,
            }
        ],
        date(2026, 11, 2),
    )
    await repo.upsert_metricas_publicacion([(ids["p1"], "me_gusta", Decimal(3))], date(2026, 11, 2))
    await pool.execute(
        "INSERT INTO alertas (cuenta_id, tipo, severidad, titulo, detalle) "
        "VALUES ($1, 'operativa', 'media', 'x', '{}')",
        cid,
    )
    await pool.execute(
        "INSERT INTO cliente_competidores (cliente_id, plataforma, nombre, handle) "
        "VALUES ($1, 'meta_ig', 'Rival', 'rival')",
        c.id,
    )


async def _cuantas(pool, c) -> dict[str, int]:  # type: ignore[no-untyped-def]
    cid = c.cuenta.id
    return {
        "clientes": await pool.fetchval("SELECT count(*) FROM clientes WHERE id = $1", c.id),
        "metricas": await pool.fetchval(
            "SELECT count(*) FROM fct_metrica_diaria WHERE cuenta_id = $1", cid
        ),
        "raw": await pool.fetchval("SELECT count(*) FROM raw_payloads WHERE cuenta_id = $1", cid),
        "publicaciones": await pool.fetchval(
            "SELECT count(*) FROM dim_publicacion WHERE cuenta_id = $1", cid
        ),
        "alertas": await pool.fetchval("SELECT count(*) FROM alertas WHERE cuenta_id = $1", cid),
        "usuarios": await pool.fetchval(
            "SELECT count(*) FROM usuarios WHERE cliente_id = $1", c.id
        ),
        "competidores": await pool.fetchval(
            "SELECT count(*) FROM cliente_competidores WHERE cliente_id = $1", c.id
        ),
    }


async def test_eliminar_cliente_borra_todo_lo_suyo_y_nada_ajeno(  # type: ignore[no-untyped-def]
    http, pool, usuario_equipo, cliente_b
) -> None:
    victima = await _crear_cliente(pool)
    await _poblar(pool, victima)
    await _poblar(pool, cliente_b)
    antes_b = await _cuantas(pool, cliente_b)
    equipo = {"Authorization": f"Bearer {token_para(usuario_equipo)}"}
    url = f"/admin/clientes/{victima.id}"

    # Un usuario cliente no puede eliminar
    r = await http.request(
        "DELETE",
        url,
        json={"confirmar": victima.slug},
        headers={"Authorization": f"Bearer {token_para(cliente_b.email)}"},
    )
    assert r.status_code == 403
    # Slug mal escrito: no borra nada
    r = await http.request("DELETE", url, json={"confirmar": "otro"}, headers=equipo)
    assert r.status_code == 400 and (await _cuantas(pool, victima))["clientes"] == 1

    r = await http.request("DELETE", url, json={"confirmar": victima.slug}, headers=equipo)
    assert r.status_code == 200, r.text
    assert r.json()["eliminado"] == victima.slug and r.json()["filas"]["raw_payloads"] == 1
    assert all(v == 0 for v in (await _cuantas(pool, victima)).values())
    assert (
        await pool.fetchval(
            "SELECT count(*) FROM cuentas_conectadas WHERE id = $1", victima.cuenta.id
        )
        == 0
    )
    assert await _cuantas(pool, cliente_b) == antes_b  # el otro cliente, intacto
    # Ya no existe
    assert (
        await http.request("DELETE", url, json={"confirmar": victima.slug}, headers=equipo)
    ).status_code == 404

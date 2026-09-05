"""PT-07: cliente_id se deriva del token; leer data de otro cliente → 403."""

from collections.abc import AsyncIterator

import httpx
import pytest

from api.main import crear_app
from tests.conftest import requiere_db, token_para

pytestmark = requiere_db


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


def _auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_para(email)}"}


async def test_sin_token_401(http) -> None:  # type: ignore[no-untyped-def]
    assert (await http.get("/yo")).status_code == 401


async def test_token_expirado_401(http, cliente_a) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(
        "/yo", headers={"Authorization": f"Bearer {token_para(cliente_a.email, expirado=True)}"}
    )
    assert r.status_code == 401


async def test_usuario_no_registrado_403(http) -> None:  # type: ignore[no-untyped-def]
    assert (await http.get("/yo", headers=_auth("nadie@desconocido.test"))).status_code == 403


async def test_yo_deriva_cliente_del_token(http, cliente_a) -> None:  # type: ignore[no-untyped-def]
    r = await http.get("/yo", headers=_auth(cliente_a.email))
    assert r.status_code == 200
    assert r.json() == {"email": cliente_a.email, "rol": "cliente", "cliente_id": cliente_a.id}


async def test_mis_cuentas_solo_devuelve_las_propias(http, cliente_a, cliente_b) -> None:  # type: ignore[no-untyped-def]
    r = await http.get("/mi/cuentas", headers=_auth(cliente_a.email))
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()}
    assert ids == {cliente_a.cuenta.id}
    assert cliente_b.cuenta.id not in ids


async def test_aislamiento_leer_otro_cliente_da_403(http, cliente_a, cliente_b) -> None:  # type: ignore[no-untyped-def]
    propio = await http.get(f"/clientes/{cliente_a.slug}/cuentas", headers=_auth(cliente_a.email))
    ajeno = await http.get(f"/clientes/{cliente_b.slug}/cuentas", headers=_auth(cliente_a.email))
    assert propio.status_code == 200
    assert ajeno.status_code == 403


async def test_cliente_id_en_query_o_header_se_ignora(http, cliente_a, cliente_b) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(
        "/mi/cuentas",
        params={"cliente_id": cliente_b.id},
        headers={**_auth(cliente_a.email), "X-Cliente-Id": str(cliente_b.id)},
    )
    assert r.status_code == 200
    assert {c["id"] for c in r.json()} == {cliente_a.cuenta.id}


async def test_equipo_ve_cualquier_cliente(http, usuario_equipo, cliente_a, cliente_b) -> None:  # type: ignore[no-untyped-def]
    for c in (cliente_a, cliente_b):
        r = await http.get(f"/clientes/{c.slug}/cuentas", headers=_auth(usuario_equipo))
        assert r.status_code == 200
    assert (await http.get("/mi/cuentas", headers=_auth(usuario_equipo))).status_code == 400


async def test_cron_requiere_secreto(http, config) -> None:  # type: ignore[no-untyped-def]
    assert (await http.post("/etl/correr")).status_code == 403
    assert (await http.post("/etl/correr", headers={"X-Cron-Secret": "malo"})).status_code == 403
    r = await http.post(
        "/etl/correr",
        params={"plataforma": "tiktok"},
        headers={"X-Cron-Secret": config.cron_secret},
    )
    assert r.status_code == 200
    assert r.json()["errores"] == {}

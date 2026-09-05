"""Módulo administrador: solo equipo, alta de cliente con reporte, tema, cuentas, usuarios."""

import uuid
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


@pytest.fixture
async def cliente_creado(http, pool, usuario_equipo) -> AsyncIterator[dict]:  # type: ignore[no-untyped-def]
    slug = f"test-{uuid.uuid4().hex[:8]}"
    r = await http.post(
        "/admin/clientes",
        json={"nombre": "Cliente Admin", "slug": slug, "sector": "retail"},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 201, r.text
    yield {"id": r.json()["id"], "slug": slug}
    await pool.execute("DELETE FROM clientes WHERE slug = $1", slug)


async def test_cliente_no_puede_administrar(http, cliente_a) -> None:  # type: ignore[no-untyped-def]
    assert (await http.get("/admin/clientes", headers=_auth(cliente_a.email))).status_code == 403


async def test_alta_de_cliente_crea_tema_e_instancia(
    http, pool, usuario_equipo, cliente_creado
) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(f"/admin/clientes/{cliente_creado['id']}", headers=_auth(usuario_equipo))
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["tema"]["color_primario"] == "#C8102E"
    assert cuerpo["cuentas"] == [] and cuerpo["usuarios"] == []
    instancia = await pool.fetchrow(
        "SELECT slug_publico, nombre_publico FROM reporte_instancias WHERE cliente_id = $1",
        cliente_creado["id"],
    )
    assert instancia["slug_publico"] == cliente_creado["slug"]
    assert instancia["nombre_publico"] == "Cliente Admin - RRSS"
    listado = await http.get("/admin/clientes", headers=_auth(usuario_equipo))
    assert any(c["slug"] == cliente_creado["slug"] for c in listado.json())


async def test_slug_duplicado_o_invalido(http, usuario_equipo, cliente_creado) -> None:  # type: ignore[no-untyped-def]
    r = await http.post(
        "/admin/clientes",
        json={"nombre": "Xy", "slug": cliente_creado["slug"]},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 409
    r = await http.post(
        "/admin/clientes",
        json={"nombre": "Xy", "slug": "Con Espacios"},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 400


async def test_tema_y_cuenta_con_credencial_cifrada(
    http, pool, usuario_equipo, cliente_creado, config
) -> None:  # type: ignore[no-untyped-def]
    cid = cliente_creado["id"]
    r = await http.put(
        f"/admin/clientes/{cid}/tema",
        json={"color_primario": "#123456", "logo_url": "https://x/logo.png"},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 200 and r.json()["color_primario"] == "#123456"
    r = await http.put(
        f"/admin/clientes/{cid}/tema",
        json={"color_primario": "rojo"},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 422

    r = await http.post(
        f"/admin/clientes/{cid}/cuentas",
        json={
            "plataforma": "meta_ig",
            "id_externo": f"ig-{cid}",
            "nombre_cuenta": "@x",
            "credencial": "token-secreto",
        },
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 201, r.text
    cuenta_id = r.json()["id"]
    detalle = await http.get(f"/admin/clientes/{cid}", headers=_auth(usuario_equipo))
    cuenta = detalle.json()["cuentas"][0]
    assert cuenta["tiene_credencial"] is True and "credencial" not in cuenta
    en_claro = await pool.fetchval(
        "SELECT pgp_sym_decrypt(credencial_cifrada, $2) FROM cuentas_conectadas WHERE id = $1",
        cuenta_id,
        config.clave_cifrado,
    )
    assert en_claro == "token-secreto"
    r = await http.post(
        f"/admin/clientes/{cid}/cuentas",
        json={"plataforma": "no_existe", "id_externo": "1"},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 400


async def test_usuarios_alta_y_baja(http, pool, usuario_equipo, cliente_creado) -> None:  # type: ignore[no-untyped-def]
    email = f"gerente-{cliente_creado['slug']}@banco-prueba.com"
    r = await http.post(
        "/admin/usuarios",
        json={"email": email, "rol": "cliente", "cliente_id": cliente_creado["id"]},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 201
    r = await http.post(
        "/admin/usuarios", json={"email": email, "rol": "cliente"}, headers=_auth(usuario_equipo)
    )
    assert r.status_code == 400  # cliente sin cliente_id
    # el nuevo usuario ya puede entrar a su reporte y a nada más
    assert (await http.get("/yo", headers=_auth(email))).json()["cliente_id"] == cliente_creado[
        "id"
    ]
    assert (await http.get("/admin/clientes", headers=_auth(email))).status_code == 403
    r = await http.delete(f"/admin/usuarios/{email}", headers=_auth(usuario_equipo))
    assert r.status_code == 200
    assert (await http.get("/yo", headers=_auth(email))).status_code == 403
    r = await http.delete(f"/admin/usuarios/{usuario_equipo}", headers=_auth(usuario_equipo))
    assert r.status_code == 400  # no se desactiva a sí mismo


async def test_catalogos_y_capturas(http, usuario_equipo) -> None:  # type: ignore[no-untyped-def]
    cat = (await http.get("/admin/catalogos", headers=_auth(usuario_equipo))).json()
    assert {p["codigo"] for p in cat["plataformas"]} >= {"meta_ig", "ga4", "linkedin"}
    r = await http.get("/admin/capturas", params={"limite": 5}, headers=_auth(usuario_equipo))
    assert r.status_code == 200 and len(r.json()) <= 5

"""Botones "Conectar con ...": state firmado, retorno con proveedor simulado y activación."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from api.admin import conectar
from api.main import crear_app
from tests.conftest import requiere_db, token_para

pytestmark = requiere_db


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(
        config.model_copy(
            update={
                "meta_login_config_id": "999",
                "meta_app_id": "111",
                "google_oauth_client_id": "gid",
            }
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


def _auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_para(email)}"}


def test_estado_firmado_ida_y_vuelta(config) -> None:  # type: ignore[no-untyped-def]
    estado = conectar.emitir_estado(config, "meta", 7, "equipo@geeks.test")
    assert conectar.verificar_estado(config, estado, "meta") == (7, "equipo@geeks.test")
    with pytest.raises(conectar.ConexionError):
        conectar.verificar_estado(config, estado, "google")  # otro proveedor
    with pytest.raises(conectar.ConexionError):
        conectar.verificar_estado(config, "basura", "meta")


async def test_iniciar_devuelve_url_del_proveedor(http, usuario_equipo, cliente_a) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(
        f"/admin/conectar/meta/iniciar?cliente_id={cliente_a.id}", headers=_auth(usuario_equipo)
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert (
        url.startswith("https://www.facebook.com/") and "config_id=999" in url and "state=" in url
    )
    r = await http.get(
        f"/admin/conectar/google/iniciar?cliente_id={cliente_a.id}", headers=_auth(usuario_equipo)
    )
    assert "accounts.google.com" in r.json()["url"] and "access_type=offline" in r.json()["url"]
    assert (
        await http.get(
            f"/admin/conectar/meta/iniciar?cliente_id={cliente_a.id}",
            headers=_auth(cliente_a.email),
        )
    ).status_code == 403
    assert (
        await http.get(
            f"/admin/conectar/otro/iniciar?cliente_id={cliente_a.id}", headers=_auth(usuario_equipo)
        )
    ).status_code == 404


async def test_retorno_lista_activos_y_activar_crea_cuentas(
    http, pool, config, usuario_equipo, cliente_a, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    async def falso_intercambio(cfg: Any, proveedor: str, codigo: str) -> dict[str, Any]:
        assert codigo == "codigo-123"
        return {"access_token": "token-meta-secreto", "expires_in": 5183944}

    async def falsos_activos(
        cfg: Any, proveedor: str, token: dict[str, Any]
    ) -> list[conectar.Activo]:
        return [
            conectar.Activo("meta_fb", f"pag-{cliente_a.id}", "Página Prueba", {}),
            conectar.Activo("meta_ig", f"ig-{cliente_a.id}", "@prueba", {"pagina": "pag"}),
            conectar.Activo("meta_ads", f"act_{cliente_a.id}", "Ads Prueba", {}),
        ]

    monkeypatch.setattr(conectar, "intercambiar_codigo", falso_intercambio)
    monkeypatch.setattr(conectar, "listar_activos", falsos_activos)

    estado = conectar.emitir_estado(config, "meta", cliente_a.id, usuario_equipo)
    r = await http.get(
        "/admin/conectar/meta/retorno", params={"state": estado, "code": "codigo-123"}
    )
    assert r.status_code in (302, 307), r.text
    destino = r.headers["location"]
    assert f"/admin/clientes/{cliente_a.id}?conexion=" in destino
    conexion_id = int(destino.split("conexion=")[1])

    c = (await http.get(f"/admin/conexiones/{conexion_id}", headers=_auth(usuario_equipo))).json()
    assert (
        c["estado"] == "pendiente"
        and len(c["activos"]) == 3
        and "token" not in str(c).lower().replace("token_expira_en", "")
    )

    # activar solo página e instagram; el ads no
    r = await http.post(
        f"/admin/conexiones/{conexion_id}/activar",
        json={
            "activos": [
                {"plataforma": "meta_fb", "id_externo": f"pag-{cliente_a.id}"},
                {"plataforma": "meta_ig", "id_externo": f"ig-{cliente_a.id}"},
            ]
        },
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["cuentas"]) == 2
    filas = await pool.fetch(
        "SELECT plataforma, nombre_cuenta, pgp_sym_decrypt(credencial_cifrada, $2) AS cred "
        "FROM cuentas_conectadas WHERE cliente_id = $1 "
        "AND plataforma IN ('meta_fb','meta_ig') ORDER BY 1",
        cliente_a.id,
        config.clave_cifrado,
    )
    assert [(f["plataforma"], f["cred"]) for f in filas] == [
        ("meta_fb", "token-meta-secreto"),
        ("meta_ig", "token-meta-secreto"),
    ]
    # segunda activación de la misma conexión: ya no está pendiente
    r = await http.post(
        f"/admin/conexiones/{conexion_id}/activar",
        json={"activos": [{"plataforma": "meta_ads", "id_externo": f"act_{cliente_a.id}"}]},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 409
    # activo no ofrecido
    estado2 = conectar.emitir_estado(config, "meta", cliente_a.id, usuario_equipo)
    r = await http.get(
        "/admin/conectar/meta/retorno", params={"state": estado2, "code": "codigo-123"}
    )
    cid2 = int(r.headers["location"].split("conexion=")[1])
    r = await http.post(
        f"/admin/conexiones/{cid2}/activar",
        json={"activos": [{"plataforma": "meta_fb", "id_externo": "otra"}]},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 400


async def test_retorno_con_state_malo_o_error_del_proveedor(
    http, config, usuario_equipo, cliente_a
) -> None:  # type: ignore[no-untyped-def]
    r = await http.get("/admin/conectar/google/retorno", params={"state": "x", "code": "y"})
    assert r.status_code in (302, 307) and "/admin?error=" in r.headers["location"]
    estado = conectar.emitir_estado(config, "google", cliente_a.id, usuario_equipo)
    r = await http.get(
        "/admin/conectar/google/retorno", params={"state": estado, "error": "access_denied"}
    )
    assert f"/admin/clientes/{cliente_a.id}?error=" in r.headers["location"]


def test_credencial_google_exige_refresh_token() -> None:
    with pytest.raises(conectar.ConexionError):
        conectar.credencial_para_guardar("google", {"access_token": "a"})
    assert '"refresh_token"' in conectar.credencial_para_guardar(
        "google", {"access_token": "a", "refresh_token": "r"}
    )
    assert conectar.credencial_para_guardar("meta", {"access_token": "m"}) == "m"

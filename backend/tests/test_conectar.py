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


async def test_iniciar_linkedin(http, usuario_equipo, cliente_a) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(
        f"/admin/conectar/linkedin/iniciar?cliente_id={cliente_a.id}", headers=_auth(usuario_equipo)
    )
    assert r.status_code == 200, r.text
    assert "linkedin.com/oauth/v2/authorization" in r.json()["url"]
    assert "r_organization_social" in r.json()["url"]
    assert conectar.credencial_para_guardar("linkedin", {"access_token": "li"}) == "li"


async def test_api_url_localhost_se_reemplaza_por_el_host_real(
    http, usuario_equipo, cliente_a
) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(
        f"/admin/conectar/google/iniciar?cliente_id={cliente_a.id}",
        headers={**_auth(usuario_equipo), "host": "datio-production.up.railway.app"},
    )
    assert "redirect_uri=https%3A%2F%2Fdatio-production.up.railway.app" in r.json()["url"]
    r = await http.get(
        f"/admin/conectar/google/iniciar?cliente_id={cliente_a.id}",
        headers={**_auth(usuario_equipo), "host": "localhost:8000"},
    )
    assert "redirect_uri=http%3A%2F%2Flocalhost" in r.json()["url"]  # en local sigue igual


def test_credencial_google_exige_refresh_token() -> None:
    with pytest.raises(conectar.ConexionError):
        conectar.credencial_para_guardar("google", {"access_token": "a"})
    assert '"refresh_token"' in conectar.credencial_para_guardar(
        "google", {"access_token": "a", "refresh_token": "r"}
    )
    assert conectar.credencial_para_guardar("meta", {"access_token": "m"}) == "m"


def test_error_de_listado_google_se_vuelve_aviso() -> None:
    """Una API deshabilitada (403) no debe perderse en silencio: aparece como aviso."""
    import httpx

    from api.admin.conectar import AVISO, _aviso

    r = httpx.Response(
        403, json={"error": {"message": "Google Analytics Admin API has not been used"}}
    )
    a = _aviso("Google Analytics", r)
    assert a.plataforma == AVISO and a.extra == {"codigo": 403}
    assert a.nombre.startswith("Google Analytics: Google Analytics Admin API")


async def _conexion_pendiente(http, config, cliente, equipo, activos, monkeypatch) -> int:  # type: ignore[no-untyped-def]
    async def falso_intercambio(cfg: Any, proveedor: str, codigo: str) -> dict[str, Any]:
        return {"access_token": f"token-{cliente.id}", "expires_in": 5183944}

    async def falsos_activos(cfg: Any, proveedor: str, token: Any) -> list[conectar.Activo]:
        return activos

    monkeypatch.setattr(conectar, "intercambiar_codigo", falso_intercambio)
    monkeypatch.setattr(conectar, "listar_activos", falsos_activos)
    estado = conectar.emitir_estado(config, "meta", cliente.id, equipo)
    r = await http.get("/admin/conectar/meta/retorno", params={"state": estado, "code": "c"})
    return int(r.headers["location"].split("conexion=")[1])


async def test_activar_no_mueve_cuentas_de_otro_cliente(  # B-1
    http, pool, config, usuario_equipo, cliente_a, cliente_b, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    # La cuenta de cliente_a (creada por el fixture) aparece también en la conexión de cliente_b
    ajena = conectar.Activo(cliente_a.cuenta.plataforma, cliente_a.cuenta.id_externo, "Ajena", {})
    propia = conectar.Activo("meta_fb", f"pag-b-{cliente_b.id}", "Propia de B", {})
    conexion = await _conexion_pendiente(
        http, config, cliente_b, usuario_equipo, [propia, ajena], monkeypatch
    )
    r = await http.post(
        f"/admin/conexiones/{conexion}/activar",
        json={
            "activos": [
                {"plataforma": propia.plataforma, "id_externo": propia.id_externo},
                {"plataforma": ajena.plataforma, "id_externo": ajena.id_externo},
            ]
        },
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "Esa cuenta ya está conectada a un cliente"
    assert cliente_a.slug not in r.text
    # La cuenta sigue en su cliente; ninguna del lote se creó; la conexión no quedó activada
    duena = await pool.fetchval(
        "SELECT cliente_id FROM cuentas_conectadas WHERE id = $1", cliente_a.cuenta.id
    )
    assert duena == cliente_a.id
    assert not await pool.fetchval(
        "SELECT count(*) FROM cuentas_conectadas WHERE id_externo = $1", propia.id_externo
    )
    estado = await pool.fetchval("SELECT estado FROM conexiones_oauth WHERE id = $1", conexion)
    assert estado == "pendiente"


async def test_reconectar_cuenta_del_mismo_cliente_renueva_token(  # B-1, camino feliz
    http, pool, config, usuario_equipo, cliente_a, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    propia = conectar.Activo(cliente_a.cuenta.plataforma, cliente_a.cuenta.id_externo, "Nueva", {})
    conexion = await _conexion_pendiente(
        http, config, cliente_a, usuario_equipo, [propia], monkeypatch
    )
    r = await http.post(
        f"/admin/conexiones/{conexion}/activar",
        json={"activos": [{"plataforma": propia.plataforma, "id_externo": propia.id_externo}]},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 200 and r.json()["cuentas"] == [cliente_a.cuenta.id]
    fila = await pool.fetchrow(
        "SELECT cliente_id, nombre_cuenta, pgp_sym_decrypt(credencial_cifrada, $2) AS cred "
        "FROM cuentas_conectadas WHERE id = $1",
        cliente_a.cuenta.id,
        config.clave_cifrado,
    )
    assert (fila["cliente_id"], fila["nombre_cuenta"]) == (cliente_a.id, "Nueva")
    assert fila["cred"] == f"token-{cliente_a.id}"


def test_linkedin_solo_lee() -> None:  # S-3
    """Con rw_organization_admin el código solo hace GET: el cliente del conector no expone
    métodos de escritura y el único POST a LinkedIn es el canje del código OAuth."""
    import inspect

    from api.etl.conectores import linkedin

    metodos = {n for n, _ in inspect.getmembers(linkedin.LinkedInBase, inspect.isfunction)}
    assert not metodos & {"post", "put", "patch", "delete"}
    fuente = inspect.getsource(linkedin)
    assert not any(f"http.{v}(" in fuente for v in ("post", "put", "patch", "delete"))
    oauth = inspect.getsource(conectar)
    posts_linkedin = [
        linea for linea in oauth.splitlines() if "linkedin.com" in linea and "/oauth/v2/" in linea
    ]
    assert any("accessToken" in linea for linea in posts_linkedin)
    assert set(conectar.SCOPES_LINKEDIN) <= {"r_organization_social", "rw_organization_admin"}

"""#12: con shouldCreateUser:false los invitados se crean en Supabase Auth desde el servidor,
con el correo confirmado y sin devolver enlaces ni tokens."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from api.admin import router_reporte
from api.auth.admin_supabase import asegurar_usuario_auth
from api.main import crear_app
from tests.conftest import requiere_db, token_para
from tests.test_estreno import _borrar_instancia, _instancia_de_prueba


def _cliente(
    estado: int, cuerpo: dict[str, object], vistas: list[httpx.Request]
) -> httpx.AsyncClient:
    def responder(req: httpx.Request) -> httpx.Response:
        vistas.append(req)
        return httpx.Response(estado, json=cuerpo)

    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


@pytest.mark.parametrize(
    ("estado", "cuerpo", "esperado"),
    [
        (200, {"id": "u1", "email": "a@b.com"}, "creado"),
        (
            422,
            {
                "code": "email_exists",
                "msg": "A user with this email address has already been registered",
            },
            "existente",
        ),
        (500, {"msg": "boom"}, "error_auth"),
    ],
)
async def test_asegurar_usuario_auth(config, estado, cuerpo, esperado) -> None:  # type: ignore[no-untyped-def]
    cfg = config.model_copy(update={"supabase_service_role_key": "clave-servicio-de-prueba"})
    vistas: list[httpx.Request] = []
    async with _cliente(estado, cuerpo, vistas) as http:
        assert await asegurar_usuario_auth(cfg, "a@b.com", http) == esperado
    pedido = vistas[0]
    assert pedido.url.path == "/auth/v1/admin/users" and pedido.method == "POST"
    assert json.loads(pedido.content) == {"email": "a@b.com", "email_confirm": True}


async def test_sin_clave_no_llama_a_supabase(config) -> None:  # type: ignore[no-untyped-def]
    vistas: list[httpx.Request] = []
    async with _cliente(200, {}, vistas) as http:
        assert await asegurar_usuario_auth(config, "a@b.com", http) == "sin_clave_auth"
    assert vistas == []


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


@requiere_db
async def test_invitar_crea_en_auth_y_no_devuelve_enlaces(  # type: ignore[no-untyped-def]
    http, pool, cliente_a, usuario_equipo, monkeypatch: pytest.MonkeyPatch
) -> None:
    creados: list[str] = []

    async def auth_falso(cfg, email, http=None):  # type: ignore[no-untyped-def]
        creados.append(email)
        return "creado"

    monkeypatch.setattr(router_reporte, "asegurar_usuario_auth", auth_falso)
    plantilla = await _instancia_de_prueba(pool, cliente_a.id)
    correo = f"invitado-{cliente_a.id}@cliente-prueba.com"
    try:
        r = await http.post(
            f"/admin/clientes/{cliente_a.id}/invitar",
            json={"emails": [correo], "enviar_correo": False},
            headers={"Authorization": f"Bearer {token_para(usuario_equipo)}"},
        )
        assert r.status_code == 200 and creados == [correo]
        assert r.json()["resultados"][0]["estado"] == "habilitado"
        texto = r.text.lower()
        assert "token" not in texto and "access" not in texto and "link" not in texto
    finally:
        await pool.execute("DELETE FROM usuarios WHERE email = $1", correo)
        await _borrar_instancia(pool, plantilla)


@requiere_db
async def test_invitar_sin_clave_avisa_al_equipo(  # type: ignore[no-untyped-def]
    http, pool, cliente_a, usuario_equipo
) -> None:
    plantilla = await _instancia_de_prueba(pool, cliente_a.id)
    correo = f"invitado2-{cliente_a.id}@cliente-prueba.com"
    try:
        r = await http.post(
            f"/admin/clientes/{cliente_a.id}/invitar",
            json={"emails": [correo], "enviar_correo": True},
            headers={"Authorization": f"Bearer {token_para(usuario_equipo)}"},
        )
        fila = r.json()["resultados"][0]
        assert fila["estado"] == "habilitado_sin_auth" and "sin_clave_auth" in fila["detalle"]
    finally:
        await pool.execute("DELETE FROM usuarios WHERE email = $1", correo)
        await _borrar_instancia(pool, plantilla)

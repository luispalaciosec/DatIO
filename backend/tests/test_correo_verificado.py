"""S-2: la API solo acepta tokens cuyo correo esté verificado; el cron compara en tiempo
constante; los errores de token no exponen la configuración (B-11)."""

from collections.abc import AsyncIterator

import httpx
import pytest

from api.auth.supabase import correo_verificado
from api.main import crear_app
from tests.conftest import requiere_db, token_para


@pytest.mark.parametrize(
    "claims",
    [
        {"amr": [{"method": "otp"}]},  # enlace mágico
        {"amr": [{"method": "magiclink"}]},
        {"amr": [{"method": "oauth"}], "user_metadata": {"email_verified": True}},  # Google
        {"email_verified": True},
        {"user_metadata": {"email_verified": True}},
    ],
)
def test_correo_verificado_acepta_logins_que_lo_prueban(claims: dict[str, object]) -> None:
    assert correo_verificado(claims)


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"amr": [{"method": "password"}]},  # registro con contraseña sin confirmar
        {"amr": [{"method": "anonymous"}]},
        {"amr": [{"method": "otp"}], "is_anonymous": True},
        {"user_metadata": {"email_verified": False}, "amr": [{"method": "password"}]},
        {"amr": "otp"},  # forma inesperada
    ],
)
def test_correo_verificado_rechaza_el_resto(claims: dict[str, object]) -> None:
    assert not correo_verificado(claims)


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


@requiere_db
async def test_token_sin_correo_verificado_401(http, usuario_equipo) -> None:  # type: ignore[no-untyped-def]
    sin = token_para(usuario_equipo, metodo="password")
    r = await http.get("/yo", headers={"Authorization": f"Bearer {sin}"})
    assert r.status_code == 401 and r.json()["detail"] == "El correo no está verificado"
    con = token_para(usuario_equipo)  # otp
    assert (await http.get("/yo", headers={"Authorization": f"Bearer {con}"})).status_code == 200


@requiere_db
async def test_token_invalido_mensaje_generico(http) -> None:  # type: ignore[no-untyped-def]
    r = await http.get("/yo", headers={"Authorization": "Bearer no.es.valido"})
    assert r.status_code == 401 and r.json()["detail"] == "Token inválido o vencido"
    assert "SUPABASE" not in r.text


@requiere_db
async def test_cron_secreto(http, config) -> None:  # type: ignore[no-untyped-def]
    malo = await http.post("/etl/correr", headers={"x-cron-secret": "otro-valor"})
    assert malo.status_code == 403
    vacio = await http.post("/etl/correr")
    assert vacio.status_code == 403

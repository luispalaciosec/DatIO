"""N-1: invitar y guardar_usuario nunca mueven un usuario de cliente ni le cambian el rol."""

from collections.abc import AsyncIterator

import httpx
import pytest

from api.main import crear_app
from api.reportes.repositorio import RepositorioReportes
from tests.conftest import requiere_db, token_para
from tests.test_estreno import _borrar_instancia, _instancia_de_prueba

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


async def _usuario(pool, email: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return dict(
        await pool.fetchrow("SELECT rol, cliente_id, activo FROM usuarios WHERE email = $1", email)
    )


async def test_invitar_estados_por_correo(pool, cliente_a, cliente_b) -> None:  # type: ignore[no-untyped-def]
    repo = RepositorioReportes(pool)
    nuevo = f"nuevo-{cliente_a.id}@cliente-prueba.com"
    equipo = f"equipo-{cliente_a.id}@geeks-prueba.com"
    await pool.execute("INSERT INTO usuarios (email, rol) VALUES ($1, 'equipo')", equipo)
    try:
        assert await repo.invitar(cliente_a.id, nuevo) == "creado"
        assert await repo.invitar(cliente_a.id, nuevo) == "reinvitado"
        # Usuario de B invitado desde A: no se mueve
        assert await repo.invitar(cliente_a.id, cliente_b.email) == "pertenece_a_otro_cliente"
        assert (await _usuario(pool, cliente_b.email))["cliente_id"] == cliente_b.id
        # Usuario del equipo: rol intacto
        assert await repo.invitar(cliente_a.id, equipo) == "es_equipo"
        assert await _usuario(pool, equipo) == {"rol": "equipo", "cliente_id": None, "activo": True}
        # Desactivado del MISMO cliente: se reactiva de forma explícita
        await pool.execute("UPDATE usuarios SET activo = FALSE WHERE email = $1", nuevo)
        assert await repo.invitar(cliente_a.id, nuevo) == "reactivado"
        assert (await _usuario(pool, nuevo))["activo"] is True
    finally:
        await pool.execute("DELETE FROM usuarios WHERE email = ANY($1::text[])", [nuevo, equipo])


@pytest.fixture
async def correos(pool, cliente_b) -> AsyncIterator[tuple[str, str]]:  # type: ignore[no-untyped-def]
    """Un usuario de cliente_b y uno del equipo con dominios que EmailStr acepta."""
    de_b = f"gerente-{cliente_b.id}@cliente-b-prueba.com"
    equipo = f"equipo-{cliente_b.id}@geeks-prueba.com"
    await pool.execute(
        "INSERT INTO usuarios (email, rol, cliente_id) VALUES ($1, 'cliente', $2)",
        de_b,
        cliente_b.id,
    )
    await pool.execute("INSERT INTO usuarios (email, rol) VALUES ($1, 'equipo')", equipo)
    yield de_b, equipo
    await pool.execute("DELETE FROM usuarios WHERE email = ANY($1::text[])", [de_b, equipo])


async def test_endpoint_invitar_informa_conflicto_sin_revelar_cliente(  # type: ignore[no-untyped-def]
    http, pool, usuario_equipo, cliente_a, cliente_b, correos
) -> None:
    de_b, equipo = correos
    plantilla = await _instancia_de_prueba(pool, cliente_a.id)
    try:
        r = await http.post(
            f"/admin/clientes/{cliente_a.id}/invitar",
            json={"emails": [de_b, equipo], "enviar_correo": False},
            headers=_auth(usuario_equipo),
        )
        assert r.status_code == 200, r.text
        estados = {x["email"]: x["estado"] for x in r.json()["resultados"]}
        assert estados == {de_b: "pertenece_a_otro_cliente", equipo: "es_equipo"}
        assert cliente_b.slug not in r.text and "Cliente prueba" not in r.text
        assert (await _usuario(pool, de_b))["cliente_id"] == cliente_b.id
        assert (await _usuario(pool, equipo))["rol"] == "equipo"
    finally:
        await _borrar_instancia(pool, plantilla)


async def test_guardar_usuario_no_cambia_cliente_ni_rol(  # type: ignore[no-untyped-def]
    http, pool, usuario_equipo, cliente_a, cliente_b, correos
) -> None:
    de_b, _ = correos
    # Correo de B dado de alta "en A" -> 409 sin cambios
    r = await http.post(
        "/admin/usuarios",
        json={"email": de_b, "rol": "cliente", "cliente_id": cliente_a.id},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "Ese correo ya pertenece a otro cliente o al equipo"
    assert (await _usuario(pool, de_b))["cliente_id"] == cliente_b.id
    # Convertir un usuario cliente en equipo -> 409
    r = await http.post(
        "/admin/usuarios",
        json={"email": de_b, "rol": "equipo"},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 409
    assert (await _usuario(pool, de_b))["rol"] == "cliente"
    # Mismo rol y cliente: reactiva (camino feliz)
    await pool.execute("UPDATE usuarios SET activo = FALSE WHERE email = $1", de_b)
    r = await http.post(
        "/admin/usuarios",
        json={"email": de_b, "rol": "cliente", "cliente_id": cliente_b.id},
        headers=_auth(usuario_equipo),
    )
    assert r.status_code == 201 and (await _usuario(pool, de_b))["activo"] is True

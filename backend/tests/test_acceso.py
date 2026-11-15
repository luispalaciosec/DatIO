"""S-1: al desactivar un cliente se revocan los accesos de sus usuarios (Términos §9).
También fija que cada 403 de un reporte queda registrado (AntiSlop 2)."""

import logging
from collections.abc import AsyncIterator

import httpx
import pytest

from api.auth.repositorio import RepositorioAuth
from api.main import crear_app
from api.pdf import render
from tests.conftest import pdf_valido, requiere_db, token_para


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config.model_copy(update={"pdf_secret": "p" * 32}))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


@pytest.fixture
async def instancia(pool, cliente_a) -> AsyncIterator[tuple[int, int]]:  # type: ignore[no-untyped-def]
    plantilla = await pool.fetchval(
        "INSERT INTO reporte_plantillas (nombre) VALUES ('acceso-' || $1) RETURNING id",
        cliente_a.slug,
    )
    pagina = await pool.fetchval(
        "INSERT INTO reporte_paginas (plantilla_id, slug, titulo, orden) "
        "VALUES ($1, 'metricas', 'Métricas', 1) RETURNING id",
        plantilla,
    )
    bloque = await pool.fetchval(
        "INSERT INTO reporte_bloques (pagina_id, tipo, orden) VALUES ($1, 'separador', 1) "
        "RETURNING id",
        pagina,
    )
    inst = await pool.fetchval(
        "INSERT INTO reporte_instancias (cliente_id, plantilla_id, slug_publico) "
        "VALUES ($1, $2, $3) RETURNING id",
        cliente_a.id,
        plantilla,
        cliente_a.slug,
    )
    yield int(inst), int(bloque)
    await pool.execute("UPDATE clientes SET activo = TRUE WHERE id = $1", cliente_a.id)
    await pool.execute("DELETE FROM reporte_visitas WHERE instancia_id = $1", inst)
    await pool.execute("DELETE FROM reporte_instancias WHERE id = $1", inst)
    await pool.execute("DELETE FROM reporte_plantillas WHERE id = $1", plantilla)


def _auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_para(email)}"}


async def _pedir_todo(http, slug: str, inst: int, bloque: int, email: str) -> list[int]:  # type: ignore[no-untyped-def]
    rango = {"desde": "2026-10-01", "hasta": "2026-10-31"}
    estructura = await http.get(f"/reportes/{slug}", headers=_auth(email))
    consulta = await http.post(
        "/consulta",
        json={"instancia_id": inst, "bloque_id": bloque, **rango},
        headers=_auth(email),
    )
    pdf = await http.get(f"/reportes/{slug}/pdf", params=rango, headers=_auth(email))
    return [estructura.status_code, consulta.status_code, pdf.status_code]


@requiere_db
async def test_cliente_activo_entra(http, cliente_a, instancia, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def falso(url: str, timeout_ms: int = 0) -> bytes:
        return pdf_valido()

    monkeypatch.setattr(render, "generar_pdf", falso)
    inst, bloque = instancia
    assert await _pedir_todo(http, cliente_a.slug, inst, bloque, cliente_a.email) == [200] * 3


@requiere_db
async def test_cliente_desactivado_pierde_el_acceso(  # type: ignore[no-untyped-def]
    http, pool, cliente_a, instancia, usuario_equipo, caplog
) -> None:
    inst, bloque = instancia
    await pool.execute("UPDATE clientes SET activo = FALSE WHERE id = $1", cliente_a.id)

    # El usuario del cliente ya no existe para la API
    assert await RepositorioAuth(pool).usuario_por_email(cliente_a.email) is None
    propios = await _pedir_todo(http, cliente_a.slug, inst, bloque, cliente_a.email)
    assert propios == [403, 403, 403]

    # El equipo sigue entrando a la plataforma, pero el reporte del cliente inactivo da 403
    assert await RepositorioAuth(pool).usuario_por_email(usuario_equipo) is not None
    assert (await http.get("/yo", headers=_auth(usuario_equipo))).status_code == 200
    with caplog.at_level(logging.WARNING, logger="api.deps"):
        codigos = await _pedir_todo(http, cliente_a.slug, inst, bloque, usuario_equipo)
    assert codigos == [403, 403, 403]
    assert "cliente_inactivo" in caplog.text and usuario_equipo in caplog.text


@requiere_db
async def test_reporte_ajeno_403_y_queda_registrado(  # type: ignore[no-untyped-def]
    http, cliente_a, cliente_b, instancia, caplog
) -> None:
    inst, bloque = instancia
    with caplog.at_level(logging.WARNING, logger="api.deps"):
        codigos = await _pedir_todo(http, cliente_a.slug, inst, bloque, cliente_b.email)
    assert codigos == [403, 403, 403]
    assert "otro_cliente" in caplog.text and cliente_b.email in caplog.text
    assert "Bearer" not in caplog.text


@requiere_db
async def test_reporte_inexistente_404(http, cliente_a) -> None:  # type: ignore[no-untyped-def]
    r = await http.get("/reportes/no-existe-este-reporte", headers=_auth(cliente_a.email))
    assert r.status_code == 404

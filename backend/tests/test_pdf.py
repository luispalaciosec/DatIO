"""PT-11: token de render, URL de impresión y endpoint /reportes/{slug}/pdf."""

from collections.abc import AsyncIterator

import httpx
import pytest

from api.main import crear_app
from api.pdf import render
from api.pdf.render import RenderInvalidoError, emitir_token_render, verificar_token_render
from tests.conftest import requiere_db, token_para


def test_token_render_ida_y_vuelta(config) -> None:  # type: ignore[no-untyped-def]
    token = emitir_token_render(config, cliente_id=7, instancia_id=3)
    principal = verificar_token_render(token, config)
    assert (principal.cliente_id, principal.instancia_id) == (7, 3)


def test_token_ajeno_o_alterado_se_rechaza(config) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(RenderInvalidoError):
        verificar_token_render("no.es.un.token", config)
    # Un token de Supabase (otro secreto) tampoco pasa como render
    with pytest.raises(RenderInvalidoError):
        verificar_token_render(token_para("x@y.z"), config)


def test_url_impresion(config) -> None:  # type: ignore[no-untyped-def]
    url = render.url_impresion(config, "banco-amazonas", "2026-08-01", "2026-08-28", "abc")
    assert url.startswith("http://front.test/banco-amazonas/imprimir?")
    assert "modo=print" in url and "render=abc" in url and "desde=2026-08-01" in url


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


@pytest.fixture
async def instancia(pool, cliente_a) -> AsyncIterator[int]:  # type: ignore[no-untyped-def]
    plantilla = await pool.fetchval(
        "INSERT INTO reporte_plantillas (nombre) VALUES ('pdf-' || $1) RETURNING id", cliente_a.slug
    )
    inst = await pool.fetchval(
        "INSERT INTO reporte_instancias (cliente_id, plantilla_id, slug_publico) "
        "VALUES ($1, $2, $3) RETURNING id",
        cliente_a.id,
        plantilla,
        cliente_a.slug,
    )
    yield int(inst)
    await pool.execute("DELETE FROM reporte_instancias WHERE id = $1", inst)
    await pool.execute("DELETE FROM reporte_plantillas WHERE id = $1", plantilla)


def _auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_para(email)}"}


@requiere_db
async def test_endpoint_pdf_devuelve_archivo(http, cliente_a, instancia, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    capturada: dict[str, str] = {}

    async def falso_pdf(url: str, timeout_ms: int = 0) -> bytes:
        capturada["url"] = url
        return b"%PDF-1.4 falso"

    monkeypatch.setattr(render, "generar_pdf", falso_pdf)
    r = await http.get(
        f"/reportes/{cliente_a.slug}/pdf",
        params={"desde": "2026-08-01", "hasta": "2026-08-28"},
        headers=_auth(cliente_a.email),
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert f"/{cliente_a.slug}/imprimir?" in capturada["url"]
    # el token de render embebido en la URL abre la API como ese cliente
    token = capturada["url"].split("render=")[1]
    yo = await http.get("/yo", headers={"Authorization": f"Bearer {token}"})
    assert yo.status_code == 200 and yo.json()["cliente_id"] == cliente_a.id


@requiere_db
async def test_endpoint_pdf_otro_cliente_403(http, cliente_b, instancia, cliente_a) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(
        f"/reportes/{cliente_a.slug}/pdf",
        params={"desde": "2026-08-01", "hasta": "2026-08-28"},
        headers=_auth(cliente_b.email),
    )
    assert r.status_code == 403


@requiere_db
async def test_endpoint_pdf_error_de_render_502(http, cliente_a, instancia, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def explota(url: str, timeout_ms: int = 0) -> bytes:
        raise RuntimeError("chromium no encontrado")

    monkeypatch.setattr(render, "generar_pdf", explota)
    r = await http.get(
        f"/reportes/{cliente_a.slug}/pdf",
        params={"desde": "2026-08-01", "hasta": "2026-08-28"},
        headers=_auth(cliente_a.email),
    )
    assert r.status_code == 502 and "chromium" in r.json()["detail"]

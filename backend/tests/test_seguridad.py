"""Cabeceras defensivas, límite de peticiones por IP (#11) y límites por usuario."""

import httpx
import pytest
from fastapi import FastAPI

from api.pdf import render
from api.seguridad import CabecerasSeguridad, LimitePeticiones, LimiteVentana
from tests.conftest import pdf_valido, requiere_db, token_para


def test_limite_ventana_deslizante() -> None:
    lim = LimiteVentana(maximo=3, segundos=10)
    assert all(lim.permitir("1.1.1.1", ahora=t) for t in (0, 1, 2))
    assert lim.permitir("1.1.1.1", ahora=3) is False  # cuarta dentro de la ventana
    assert lim.permitir("2.2.2.2", ahora=3) is True  # otra IP no se ve afectada
    assert lim.permitir("1.1.1.1", ahora=11) is True  # la primera ya salió de la ventana


def _app_minima(maximo: int) -> FastAPI:
    """Solo los middlewares de seguridad, sin base de datos (R-4: corre sin DATABASE_URL)."""
    app = FastAPI()

    @app.get("/algo")
    async def algo() -> dict[str, str]:
        return {"ok": "si"}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"estado": "ok"}

    app.add_middleware(CabecerasSeguridad)
    app.add_middleware(LimitePeticiones, maximo=maximo, segundos=60.0)
    return app


def _http(app: FastAPI, ip: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(ip, 1234)), base_url="http://test"
    )


async def test_cabeceras_y_429() -> None:
    app = _app_minima(3)
    async with _http(app, "9.9.9.9") as http:
        r = await http.get("/algo")
        assert r.status_code == 200
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["cache-control"] == "no-store"
        for _ in range(2):
            await http.get("/algo")
        r = await http.get("/algo")
        assert r.status_code == 429 and r.headers["retry-after"] == "60"
        assert (await http.get("/health")).status_code == 200  # /health nunca se limita
    async with _http(app, "8.8.8.8") as otra:
        assert (await otra.get("/algo")).status_code == 200  # otra IP sigue pasando


async def test_x_forwarded_for_no_salta_el_limite() -> None:
    """#11: la IP sale de uvicorn (--proxy-headers), no de una cabecera que manda el cliente."""
    app = _app_minima(2)
    async with _http(app, "9.9.9.9") as http:
        codigos = [
            (await http.get("/algo", headers={"X-Forwarded-For": f"10.0.0.{i}"})).status_code
            for i in range(3)
        ]
    assert codigos == [200, 200, 429]


@requiere_db
async def test_pdf_limitado_por_usuario(  # type: ignore[no-untyped-def]
    config, pool, cliente_a, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.main import crear_app

    async def falso(url: str, timeout_ms: int = 0) -> bytes:
        return pdf_valido()

    monkeypatch.setattr(render, "generar_pdf", falso)
    plantilla = await pool.fetchval(
        "INSERT INTO reporte_plantillas (nombre) VALUES ('lim-' || $1) RETURNING id", cliente_a.slug
    )
    inst = await pool.fetchval(
        "INSERT INTO reporte_instancias (cliente_id, plantilla_id, slug_publico) "
        "VALUES ($1, $2, $3) RETURNING id",
        cliente_a.id,
        plantilla,
        cliente_a.slug,
    )
    app = crear_app(config.model_copy(update={"pdf_secret": "p" * 32}))
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http:
                cab = {"Authorization": f"Bearer {token_para(cliente_a.email)}"}
                rango = {"desde": "2026-10-01", "hasta": "2026-10-31"}
                codigos = [
                    (
                        await http.get(f"/reportes/{cliente_a.slug}/pdf", params=rango, headers=cab)
                    ).status_code
                    for _ in range(7)
                ]
        assert codigos == [200] * 6 + [429]
    finally:
        await pool.execute("DELETE FROM reporte_instancias WHERE id = $1", inst)
        await pool.execute("DELETE FROM reporte_plantillas WHERE id = $1", plantilla)

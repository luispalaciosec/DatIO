"""Cabeceras defensivas y límite de peticiones por IP."""

import httpx

from api.config import Configuracion
from api.main import crear_app
from api.seguridad import LimiteVentana


def test_limite_ventana_deslizante() -> None:
    lim = LimiteVentana(maximo=3, segundos=10)
    assert all(lim.permitir("1.1.1.1", ahora=t) for t in (0, 1, 2))
    assert lim.permitir("1.1.1.1", ahora=3) is False  # cuarta dentro de la ventana
    assert lim.permitir("2.2.2.2", ahora=3) is True  # otra IP no se ve afectada
    assert lim.permitir("1.1.1.1", ahora=11) is True  # la primera ya salió de la ventana


async def test_cabeceras_y_429(config: Configuracion) -> None:
    cfg = config.model_copy(update={"limite_peticiones_min": 3})
    app = crear_app(cfg)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            r = await http.get("/yo", headers={"X-Forwarded-For": "9.9.9.9"})
            assert r.status_code == 401
            assert r.headers["x-frame-options"] == "DENY"
            assert r.headers["x-content-type-options"] == "nosniff"
            assert r.headers["cache-control"] == "no-store"
            for _ in range(2):
                await http.get("/yo", headers={"X-Forwarded-For": "9.9.9.9"})
            r = await http.get("/yo", headers={"X-Forwarded-For": "9.9.9.9"})
            assert r.status_code == 429 and r.headers["retry-after"] == "60"
            # /health nunca se limita y otra IP sigue pasando
            assert (await http.get("/health")).status_code == 200
            assert (
                await http.get("/yo", headers={"X-Forwarded-For": "8.8.8.8"})
            ).status_code == 401

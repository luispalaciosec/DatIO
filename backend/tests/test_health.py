import httpx

from api.main import crear_app
from tests.conftest import requiere_db


@requiere_db
async def test_health_responde_ok(config) -> None:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            r = await http.get("/health")
    assert r.status_code == 200
    assert r.json()["estado"] == "ok"
    assert r.json()["base_de_datos"] == "ok"

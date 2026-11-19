"""B-7: lo editado en el reporte se ve en /consulta de inmediato (sin esperar el TTL), y el
PDF (token de render) nunca lee de la cache."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from api.main import crear_app
from api.pdf.render import emitir_token_render
from api.resolvedores import REGISTRO, Contexto, Resultado
from tests.conftest import requiere_db, token_para

pytestmark = requiere_db
TIPO = "prueba_cache_config"


async def _eco(ctx: Contexto) -> Resultado:
    """Resolvedor de prueba: devuelve la configuración efectiva del bloque."""
    return Resultado({"limite": ctx.config.get("limite")})


@pytest.fixture
async def app_con_cache(config, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setitem(REGISTRO, TIPO, _eco)
    app = crear_app(config.model_copy(update={"cache_ttl_seg": 900, "pdf_secret": "p" * 32}))
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def http(app_con_cache) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_con_cache), base_url="http://test"
    ) as cliente:
        yield cliente


@pytest.fixture
async def reporte(pool, cliente_a) -> AsyncIterator[tuple[int, int]]:  # type: ignore[no-untyped-def]
    plantilla = await pool.fetchval(
        "INSERT INTO reporte_plantillas (nombre) VALUES ('cache-' || $1) RETURNING id",
        cliente_a.slug,
    )
    pagina = await pool.fetchval(
        "INSERT INTO reporte_paginas (plantilla_id, slug, titulo, orden) "
        "VALUES ($1, 'metricas', 'Métricas', 1) RETURNING id",
        plantilla,
    )
    bloque = await pool.fetchval(
        "INSERT INTO reporte_bloques (pagina_id, tipo, orden, config) "
        "VALUES ($1, $2, 1, '{\"limite\": 5}') RETURNING id",
        pagina,
        TIPO,
    )
    inst = await pool.fetchval(
        "INSERT INTO reporte_instancias (cliente_id, plantilla_id, slug_publico) "
        "VALUES ($1, $2, $3) RETURNING id",
        cliente_a.id,
        plantilla,
        cliente_a.slug,
    )
    yield int(inst), int(bloque)
    await pool.execute("DELETE FROM reporte_instancias WHERE id = $1", inst)
    await pool.execute("DELETE FROM reporte_bloques WHERE id = $1", bloque)
    await pool.execute("DELETE FROM reporte_paginas WHERE id = $1", pagina)
    await pool.execute("DELETE FROM reporte_plantillas WHERE id = $1", plantilla)


async def _consultar(http, inst: int, bloque: int, token: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    r = await http.post(
        "/consulta",
        json={
            "instancia_id": inst,
            "bloque_id": bloque,
            "desde": "2026-10-01",
            "hasta": "2026-10-31",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    datos: dict[str, Any] = r.json()
    return datos


async def test_editar_override_se_ve_de_inmediato(  # type: ignore[no-untyped-def]
    http, cliente_a, usuario_equipo, reporte
) -> None:
    inst, bloque = reporte
    cliente = token_para(cliente_a.email)
    assert (await _consultar(http, inst, bloque, cliente))["datos"] == {"limite": 5}
    segunda = await _consultar(http, inst, bloque, cliente)
    assert segunda["meta"].get("cache") is True  # la cache sí está activa

    r = await http.put(
        f"/admin/clientes/{cliente_a.id}/reporte/bloques/{bloque}",
        json={"oculto": False, "config": {"limite": 9}},
        headers={"Authorization": f"Bearer {token_para(usuario_equipo)}"},
    )
    assert r.status_code == 200, r.text
    tras = await _consultar(http, inst, bloque, cliente)
    assert tras["datos"] == {"limite": 9} and not tras["meta"].get("cache")


async def test_otro_proceso_invalida_por_version_de_configuracion(  # type: ignore[no-untyped-def]
    http, app_con_cache, pool, cliente_a, reporte
) -> None:
    inst, bloque = reporte
    cliente = token_para(cliente_a.email)
    await _consultar(http, inst, bloque, cliente)
    # Otra réplica (o el panel SQL) escribe el override: este proceso no se entera por vaciar()
    await pool.execute(
        "INSERT INTO reporte_overrides (instancia_id, bloque_id, config_merge) "
        "VALUES ($1, $2, '{\"limite\": 7}')",
        inst,
        bloque,
    )
    # ...pero al re-chequear la generación (cada 60 s; aquí lo forzamos) la cache se invalida
    app_con_cache.state.cache._generacion_vista_en = 0.0
    assert (await _consultar(http, inst, bloque, cliente))["datos"] == {"limite": 7}


async def test_token_de_render_no_lee_de_la_cache(  # type: ignore[no-untyped-def]
    http, app_con_cache, cliente_a, reporte
) -> None:
    inst, bloque = reporte
    await _consultar(http, inst, bloque, token_para(cliente_a.email))
    render = emitir_token_render(app_con_cache.state.config, cliente_a.id, inst)
    for _ in range(2):
        r = await _consultar(http, inst, bloque, render)
        assert not r["meta"].get("cache")

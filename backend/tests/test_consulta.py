"""PT-08: POST /consulta resuelve bloques sin SQL fuera del repositorio y respeta el aislamiento."""

import json
from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest

from api.etl.conectores.demo import ConectorDemo
from api.etl.repositorio import RepositorioETL
from api.main import crear_app
from api.resolvedores import REGISTRO, delta_porcentual, periodo_anterior
from tests.conftest import requiere_db, token_para

pytestmark = requiere_db
HASTA = date(2026, 9, 1)


@pytest.fixture
async def http(config) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    app = crear_app(config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as cliente:
            yield cliente


@pytest.fixture
async def reporte(pool, cliente_a, config) -> AsyncIterator[dict]:  # type: ignore[no-untyped-def]
    """Plantilla mínima con página ga4 + bloques, instancia para cliente_a y datos del demo."""
    plantilla = await pool.fetchval(
        "INSERT INTO reporte_plantillas (nombre) VALUES ('test-' || $1) RETURNING id",
        cliente_a.slug,
    )
    pagina = await pool.fetchval(
        "INSERT INTO reporte_paginas (plantilla_id, plataforma, slug, titulo, orden) "
        "VALUES ($1, 'ga4', 'metricas', 'Web', 1) RETURNING id",
        plantilla,
    )
    kpi = await pool.fetchval(
        "INSERT INTO reporte_bloques (pagina_id, tipo, orden, config) "
        "VALUES ($1, 'kpi_fila', 1, $2::jsonb) RETURNING id",
        pagina,
        json.dumps(
            {
                "items": [
                    {"metrica": "sesiones", "etiqueta": "Sesiones", "comparar": "periodo_anterior"},
                    {
                        "metrica": "tasa_rebote",
                        "formato": "porcentaje",
                        "decimales": 1,
                        "comparar": None,
                    },
                ]
            }
        ),
    )
    serie = await pool.fetchval(
        "INSERT INTO reporte_bloques (pagina_id, tipo, orden, config) "
        "VALUES ($1, 'serie_temporal', 2, $2::jsonb) RETURNING id",
        pagina,
        json.dumps(
            {"granularidad": "semana", "series": [{"metrica": "sesiones", "color": "#000"}]}
        ),
    )
    tabla = await pool.fetchval(
        "INSERT INTO reporte_bloques (pagina_id, tipo, orden, config) "
        "VALUES ($1, 'tabla_publicaciones', 3, '{}') RETURNING id",
        pagina,
    )
    raro = await pool.fetchval(
        "INSERT INTO reporte_bloques (pagina_id, tipo, orden, config) "
        "VALUES ($1, 'bloque_futuro', 4, '{}') RETURNING id",
        pagina,
    )
    instancia = await pool.fetchval(
        "INSERT INTO reporte_instancias (cliente_id, plantilla_id, slug_publico) "
        "VALUES ($1, $2, $3) RETURNING id",
        cliente_a.id,
        plantilla,
        cliente_a.slug,
    )
    await pool.execute(
        "INSERT INTO reporte_overrides (instancia_id, bloque_id, config_merge) "
        'VALUES ($1, $2, \'{"granularidad":"dia"}\')',
        instancia,
        serie,
    )
    repo = RepositorioETL(pool)
    conector = ConectorDemo(cliente_a.cuenta, repo, await repo.mapeo_plataforma("ga4"), config)
    await conector.correr(hasta=HASTA)
    yield {"instancia": instancia, "kpi": kpi, "serie": serie, "tabla": tabla, "raro": raro}
    await pool.execute("DELETE FROM reporte_instancias WHERE id = $1", instancia)
    await pool.execute("DELETE FROM reporte_plantillas WHERE id = $1", plantilla)


def _auth(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_para(email)}"}


def _consulta(reporte, bloque: str, comparar: str | None = "periodo_anterior") -> dict:  # type: ignore[no-untyped-def]
    return {
        "instancia_id": reporte["instancia"],
        "bloque_id": reporte[bloque],
        "desde": "2026-08-26",
        "hasta": "2026-09-01",
        "comparar": comparar,
    }


async def test_kpi_fila_agrega_y_compara(http, cliente_a, reporte) -> None:  # type: ignore[no-untyped-def]
    r = await http.post("/consulta", json=_consulta(reporte, "kpi"), headers=_auth(cliente_a.email))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["estado"] == "consolidado" and cuerpo["meta"]["cuentas"] == 1
    sesiones, rebote = cuerpo["datos"]
    assert sesiones["etiqueta"] == "Sesiones" and sesiones["valor"] > 0
    assert sesiones["anterior"] is not None and sesiones["delta"] is not None
    assert len(sesiones["sparkline"]) == 7
    assert rebote["formato"] == "porcentaje" and 30 <= rebote["valor"] <= 40  # promedio
    assert rebote["anterior"] is None  # ese item no compara


async def test_serie_temporal_aplica_override_de_instancia(http, cliente_a, reporte) -> None:  # type: ignore[no-untyped-def]
    r = await http.post(
        "/consulta", json=_consulta(reporte, "serie"), headers=_auth(cliente_a.email)
    )
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["meta"]["granularidad"] == "dia"  # la plantilla decía semana; el override manda
    assert len(cuerpo["datos"]["puntos"]) == 7
    assert cuerpo["datos"]["series"][0]["etiqueta"] == "Sesiones"


async def test_tabla_publicaciones_vacia_y_bloque_desconocido(http, cliente_a, reporte) -> None:  # type: ignore[no-untyped-def]
    r = await http.post(
        "/consulta", json=_consulta(reporte, "tabla"), headers=_auth(cliente_a.email)
    )
    assert r.status_code == 200 and r.json()["datos"] == []
    r = await http.post(
        "/consulta", json=_consulta(reporte, "raro"), headers=_auth(cliente_a.email)
    )
    assert r.status_code == 200 and r.json()["datos"] is None


async def test_otro_cliente_no_puede_consultar_403(http, cliente_b, reporte) -> None:  # type: ignore[no-untyped-def]
    r = await http.post("/consulta", json=_consulta(reporte, "kpi"), headers=_auth(cliente_b.email))
    assert r.status_code == 403


async def test_rango_invalido_400(http, cliente_a, reporte) -> None:  # type: ignore[no-untyped-def]
    cuerpo = {**_consulta(reporte, "kpi"), "desde": "2026-09-02"}
    r = await http.post("/consulta", json=cuerpo, headers=_auth(cliente_a.email))
    assert r.status_code == 400


async def test_estructura_reporte(http, cliente_a, cliente_b, reporte) -> None:  # type: ignore[no-untyped-def]
    r = await http.get(f"/reportes/{cliente_a.slug}", headers=_auth(cliente_a.email))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["instancia_id"] == reporte["instancia"]
    assert cuerpo["tema"]["color_primario"] == "#C8102E"  # default sin fila en cliente_tema
    assert [b["tipo"] for b in cuerpo["paginas"][0]["bloques"]] == [
        "kpi_fila",
        "serie_temporal",
        "tabla_publicaciones",
        "bloque_futuro",
    ]
    assert cuerpo["paginas"][0]["bloques"][1]["config"]["granularidad"] == "dia"
    assert (
        await http.get(f"/reportes/{cliente_a.slug}", headers=_auth(cliente_b.email))
    ).status_code == 403


def test_utilidades_de_resolvedores() -> None:
    assert periodo_anterior(date(2026, 9, 1), date(2026, 9, 7)) == (
        date(2026, 8, 25),
        date(2026, 8, 31),
    )
    assert delta_porcentual(120, 100) == 20.0
    assert delta_porcentual(5, 0) is None and delta_porcentual(None, 3) is None
    assert {"kpi_fila", "serie_temporal", "tabla_publicaciones", "distribucion_geo"} <= set(
        REGISTRO
    )

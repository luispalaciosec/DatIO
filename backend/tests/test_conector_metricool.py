"""Puente Metricool: normaliza filas del MCP (LinkedIn/TikTok) y el endpoint las importa."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from api.etl.conectores.metricool import METRICAS_METRICOOL, ConectorMetricool
from api.etl.repositorio import Cuenta
from tests.semilla import mapeos_del_seed

FIXTURES = Path(__file__).parent / "fixtures"


def _payload() -> list[dict[str, Any]]:
    datos: list[dict[str, Any]] = json.loads((FIXTURES / "metricool_linkedin.json").read_text())
    return datos


def _conector(config, plataforma: str = "linkedin") -> ConectorMetricool:  # type: ignore[no-untyped-def]
    cuenta = Cuenta(1, 1, plataforma, "urn:li:organization:1", None)
    return ConectorMetricool(
        cuenta, None, mapeos_del_seed()[plataforma], config, payload=_payload()
    )  # type: ignore[arg-type]


def test_metricool_normaliza_y_omite_nulos(config) -> None:  # type: ignore[no-untyped-def]
    conector = _conector(config)
    filas = conector.normalizar(_payload())
    por_clave = {(f, m): v for f, m, v in filas}
    assert por_clave[(date(2026, 9, 1), "seguidores")] == Decimal("156.0")
    assert por_clave[(date(2026, 9, 1), "seguidores_nuevos")] == Decimal("2.0")
    assert por_clave[(date(2026, 9, 1), "impresiones")] == Decimal("340.0")
    assert por_clave[(date(2026, 9, 3), "seguidores")] == Decimal("158.0")
    assert (date(2026, 9, 2), "impresiones") not in por_clave  # null → no se inventa un cero
    assert conector.metricas_sin_mapeo == set()
    assert conector.plataforma == "linkedin"


def test_metricas_pedidas_estan_todas_mapeadas() -> None:
    mapeos = mapeos_del_seed()
    for plataforma, ids in METRICAS_METRICOOL.items():
        assert set(ids) <= set(mapeos[plataforma]), plataforma


async def test_extraer_devuelve_el_payload_recibido(config) -> None:  # type: ignore[no-untyped-def]
    conector = _conector(config)
    assert await conector.extraer(date(2026, 9, 1), date(2026, 9, 3)) == _payload()

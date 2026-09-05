"""PT-04: GA4 y Search Console normalizan payloads fijos sin tocar la API real."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from api.etl.conectores.ga4 import ConectorGA4
from api.etl.conectores.gsc import ConectorGSC
from api.etl.repositorio import Cuenta
from tests.semilla import mapeos_del_seed

FIXTURES = Path(__file__).parent / "fixtures"


def _cargar(nombre: str) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
    return datos


def _ga4(config) -> ConectorGA4:  # type: ignore[no-untyped-def]
    return ConectorGA4(Cuenta(1, 1, "ga4", "123456", None), None, mapeos_del_seed()["ga4"], config)  # type: ignore[arg-type]


def _gsc(config) -> ConectorGSC:  # type: ignore[no-untyped-def]
    return ConectorGSC(
        Cuenta(2, 1, "gsc", "sc-domain:ejemplo.com", None), None, mapeos_del_seed()["gsc"], config
    )  # type: ignore[arg-type]


def test_ga4_normaliza_fechas_metricas_y_factores(config) -> None:  # type: ignore[no-untyped-def]
    filas = _ga4(config).normalizar([_cargar("ga4_run_report.json")])
    assert len(filas) == 2 * len(ConectorGA4.METRICAS_NATIVAS)
    por_clave = {(f, m): v for f, m, v in filas}
    assert por_clave[(date(2026, 9, 1), "sesiones")] == Decimal("1250")
    assert por_clave[(date(2026, 9, 1), "tasa_rebote")] == Decimal("42.12")
    assert por_clave[(date(2026, 9, 2), "conversiones_web")] == Decimal("21")
    assert por_clave[(date(2026, 9, 2), "duracion_sesion_promedio_seg")] == Decimal("90.1")


def test_ga4_payload_vacio_no_rompe(config) -> None:  # type: ignore[no-untyped-def]
    conector = _ga4(config)
    assert conector.normalizar([{"metricHeaders": [], "rowCount": 0}]) == []
    assert conector.metricas_sin_mapeo == set()


def test_ga4_columna_desconocida_se_ignora_sin_inventar_metrica(config) -> None:  # type: ignore[no-untyped-def]
    conector = _ga4(config)
    payload = {
        "metricHeaders": [{"name": "sessions"}, {"name": "metricaNueva"}],
        "rows": [
            {
                "dimensionValues": [{"value": "20260903"}],
                "metricValues": [{"value": "7"}, {"value": "99"}],
            }
        ],
    }
    filas = conector.normalizar([payload])
    assert filas == [(date(2026, 9, 3), "sesiones", Decimal("7"))]
    assert conector.metricas_sin_mapeo == {"metricaNueva"}


def test_gsc_normaliza_ctr_a_porcentaje(config) -> None:  # type: ignore[no-untyped-def]
    filas = _gsc(config).normalizar([_cargar("gsc_search_analytics.json")])
    assert len(filas) == 2 * 4
    por_clave = {(f, m): v for f, m, v in filas}
    assert por_clave[(date(2026, 9, 1), "clics_busqueda")] == Decimal("342")
    assert por_clave[(date(2026, 9, 1), "ctr_busqueda")] == Decimal("2.653")
    assert por_clave[(date(2026, 9, 2), "posicion_promedio")] == Decimal("14.2")


def test_gsc_fila_malformada_lanza_error(config) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises((KeyError, IndexError)):
        _gsc(config).normalizar([{"rows": [{"clicks": 1}]}])


async def test_google_sin_service_account_falla_claro(config) -> None:  # type: ignore[no-untyped-def]
    conector = _ga4(config)
    conector.config = config.model_copy(
        update={"google_service_account_json": "", "clave_cifrado": ""}
    )
    with pytest.raises(RuntimeError, match="GOOGLE_SERVICE_ACCOUNT_JSON"):
        await conector.token_acceso()

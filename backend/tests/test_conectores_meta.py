"""PT-05 / PT-06: FB, IG y Meta Ads normalizan payloads fijos sin llamar al Graph API."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from api.etl.conectores.meta_ads import ConectorMetaAds
from api.etl.conectores.meta_base import ConectorMetaBase
from api.etl.conectores.meta_fb import ConectorMetaFB
from api.etl.conectores.meta_ig import ConectorMetaIG
from api.etl.repositorio import Cuenta
from tests.semilla import mapeos_del_seed

FIXTURES = Path(__file__).parent / "fixtures"


def _cargar(nombre: str) -> list[dict[str, Any]]:
    datos: list[dict[str, Any]] = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
    return datos


def _conector(clase: type[ConectorMetaBase], config) -> ConectorMetaBase:  # type: ignore[no-untyped-def]
    cuenta = Cuenta(1, 1, clase.plataforma, "123", None)
    return clase(cuenta, None, mapeos_del_seed()[clase.plataforma], config)  # type: ignore[arg-type]


def test_fb_normaliza_fecha_desde_end_time_y_suma_reacciones(config) -> None:  # type: ignore[no-untyped-def]
    filas = _conector(ConectorMetaFB, config).normalizar(_cargar("meta_fb_insights.json"))
    por_clave = {(f, m): v for f, m, v in filas}
    # end_time 2026-09-03T07:00 corresponde al día 2026-09-02
    assert por_clave[(date(2026, 9, 2), "seguidores")] == Decimal("15451")
    assert por_clave[(date(2026, 9, 1), "seguidores_nuevos")] == Decimal("3")
    assert por_clave[(date(2026, 9, 1), "me_gusta")] == Decimal("10")  # like + love + wow
    assert por_clave[(date(2026, 9, 2), "me_gusta")] == Decimal("0")
    assert por_clave[(date(2026, 9, 1), "clics")] == Decimal("2")
    assert len(filas) == 2 * len(ConectorMetaFB.METRICAS_NATIVAS)


def test_fb_payload_vacio(config) -> None:  # type: ignore[no-untyped-def]
    assert _conector(ConectorMetaFB, config).normalizar([{"tipo": "insights", "data": []}]) == []


def test_ig_normaliza_dias_y_perfil(config) -> None:  # type: ignore[no-untyped-def]
    conector = _conector(ConectorMetaIG, config)
    filas = conector.normalizar(_cargar("meta_ig_insights.json"))
    por_clave = {(f, m): v for f, m, v in filas}
    assert por_clave[(date(2026, 9, 2), "alcance")] == Decimal("16")
    assert por_clave[(date(2026, 9, 2), "impresiones")] == Decimal("23")  # views → impresiones
    assert por_clave[(date(2026, 9, 1), "compartidos")] == Decimal("1")
    assert por_clave[(date(2026, 9, 2), "seguidores")] == Decimal("3518")
    assert por_clave[(date(2026, 9, 2), "publicaciones")] == Decimal("422")
    assert conector.metricas_sin_mapeo == set()
    assert len(filas) == 2 * len(ConectorMetaIG.METRICAS_DIARIAS) + len(
        ConectorMetaIG.METRICAS_PERFIL
    )


def test_ig_dia_sin_total_value_se_omite(config) -> None:  # type: ignore[no-untyped-def]
    payload = [{"tipo": "dia", "fecha": "2026-09-03", "data": [{"name": "reach", "period": "day"}]}]
    assert _conector(ConectorMetaIG, config).normalizar(payload) == []


def test_ads_consolida_acciones_y_aplica_factores(config) -> None:  # type: ignore[no-untyped-def]
    filas = _conector(ConectorMetaAds, config).normalizar(_cargar("meta_ads_insights.json"))
    por_clave = {(f, m): v for f, m, v in filas}
    assert por_clave[(date(2026, 9, 1), "inversion")] == Decimal("48.75")
    assert por_clave[(date(2026, 9, 1), "conversiones")] == Decimal("10")  # purchase + lead
    assert por_clave[(date(2026, 9, 1), "roas")] == Decimal("657.4359")  # ×100 → porcentaje
    assert por_clave[(date(2026, 9, 1), "reproducciones_video")] == Decimal("800")
    assert por_clave[(date(2026, 9, 2), "impresiones_pauta")] == Decimal("9000")
    # el segundo día no trae conversiones: no se inventa un cero
    assert (date(2026, 9, 2), "conversiones") not in por_clave


def test_ads_fila_sin_fecha_lanza_error(config) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(KeyError):
        _conector(ConectorMetaAds, config).normalizar(
            [{"tipo": "insights", "data": [{"spend": "1"}]}]
        )


def test_fecha_de_end_time_resta_un_dia() -> None:
    assert ConectorMetaBase.fecha_de_end_time("2026-09-03T07:00:00+0000") == date(2026, 9, 2)


async def test_meta_sin_token_falla_claro(config) -> None:  # type: ignore[no-untyped-def]
    conector = _conector(ConectorMetaFB, config)
    conector.config = config.model_copy(update={"meta_system_user_token": "", "clave_cifrado": ""})
    with pytest.raises(RuntimeError, match="META_SYSTEM_USER_TOKEN"):
        await conector.token_acceso()

"""Router LLM: modelo por configuración, sector regulado fuerza host occidental."""

import pytest

from api.llm.router import resolver_config


def test_resuelve_modelo_desde_configuracion(config) -> None:  # type: ignore[no-untyped-def]
    cfg = resolver_config("clasificacion", config)
    assert cfg.nombre_litellm == "gemini/gemini-3.1-flash-lite"
    assert cfg.batch is True


def test_sector_financiero_usa_variante_regulada(config) -> None:  # type: ignore[no-untyped-def]
    assert resolver_config("narrativa", config, sector="retail").tarea == "narrativa"
    regulado = resolver_config("narrativa", config, sector="banca")
    assert regulado.tarea == "narrativa_regulado"
    assert regulado.proveedor == "together_ai"


def test_tarea_sin_configuracion_falla(config) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(KeyError):
        resolver_config("inexistente", config)

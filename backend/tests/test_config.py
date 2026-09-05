"""ORIGENES_PERMITIDOS acepta lista JSON, coma, comillas sueltas y barras finales."""

import pytest

from api.config import Configuracion


@pytest.mark.parametrize(
    "valor",
    [
        '["https://datio.vercel.app","http://localhost:5174"]',
        "https://datio.vercel.app,http://localhost:5174",
        '"https://datio.vercel.app","http://localhost:5174"',
        "https://datio.vercel.app/, http://localhost:5174/",
        "[https://datio.vercel.app, http://localhost:5174]",
    ],
)
def test_origenes_permitidos_tolerante(valor: str, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ORIGENES_PERMITIDOS", valor)
    cfg = Configuracion(database_url="postgresql://x")
    assert cfg.origenes_permitidos == ["https://datio.vercel.app", "http://localhost:5174"]

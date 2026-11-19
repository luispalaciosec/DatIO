"""ORIGENES_PERMITIDOS acepta lista JSON, coma, comillas sueltas y barras finales."""

import pytest
from pydantic import ValidationError

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


def test_linkedin_scopes_dentro_de_la_lista_blanca(monkeypatch: pytest.MonkeyPatch) -> None:  # N-2
    monkeypatch.setenv("LINKEDIN_SCOPES", "r_organization_social, rw_organization_admin")
    assert Configuracion().linkedin_scopes == ["r_organization_social", "rw_organization_admin"]


def test_linkedin_scope_fuera_de_la_lista_blanca_impide_arrancar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # N-2
    monkeypatch.setenv("LINKEDIN_SCOPES", "r_organization_social w_member_social")
    with pytest.raises(ValidationError, match="w_member_social"):
        Configuracion()


def test_produccion_exige_https(monkeypatch: pytest.MonkeyPatch) -> None:  # S-6
    monkeypatch.setenv("AMBIENTE", "produccion")
    monkeypatch.setenv("API_URL", "http://datio.example")
    monkeypatch.setenv("FRONTEND_URL", "https://datio.example")
    monkeypatch.setenv("ORIGENES_PERMITIDOS", "https://datio.example")
    with pytest.raises(ValidationError, match="API_URL"):
        Configuracion(database_url="postgresql://x")
    monkeypatch.setenv("API_URL", "https://api.datio.example")
    monkeypatch.setenv("ORIGENES_PERMITIDOS", "https://datio.example,http://localhost:5174")
    with pytest.raises(ValidationError, match="ORIGENES_PERMITIDOS"):
        Configuracion(database_url="postgresql://x")
    monkeypatch.setenv("ORIGENES_PERMITIDOS", "https://datio.example")
    assert Configuracion(database_url="postgresql://x").es_produccion


def test_desarrollo_permite_http(monkeypatch: pytest.MonkeyPatch) -> None:  # S-6
    monkeypatch.setenv("AMBIENTE", "desarrollo")
    monkeypatch.setenv("API_URL", "http://localhost:8000")
    assert not Configuracion(database_url="postgresql://x").es_produccion

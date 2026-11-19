"""#14: el admin valida tipos, formatos y rangos antes de guardar."""

import pydantic
import pytest

from api.admin.router import CuentaNueva, TemaCambios
from api.admin.router_reporte import errores_override


@pytest.mark.parametrize(
    "url",
    [
        "https://proyecto.supabase.co/storage/v1/object/public/marcas/b/logo-1.png",
        "/clientes/l.png",
        "",
    ],
)
def test_tema_acepta_https_o_ruta_propia(url: str) -> None:
    assert TemaCambios(logo_url=url).logo_url == url


@pytest.mark.parametrize(
    "url", ["http://x.com/a.png", "data:image/png;base64,AAA", "https://x/a b"]
)
def test_tema_rechaza_otras_urls(url: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        TemaCambios(banner_url=url)


def test_tema_fuentes_acotadas() -> None:
    assert TemaCambios(fuente_titulos="Outfit", fuente_cuerpo="Inter Tight").fuente_cuerpo
    with pytest.raises(pydantic.ValidationError):
        TemaCambios(fuente_titulos="Inter; } body { display:none")
    with pytest.raises(pydantic.ValidationError):
        TemaCambios(fuente_cuerpo="x" * 61)


def test_cuenta_nueva_limites() -> None:
    with pytest.raises(pydantic.ValidationError):
        CuentaNueva(plataforma="Meta IG", id_externo="1")
    with pytest.raises(pydantic.ValidationError):
        CuentaNueva(plataforma="meta_ig", id_externo="x" * 301)
    assert CuentaNueva(plataforma="meta_ig", id_externo="1784").plataforma == "meta_ig"


def test_override_valores_validos() -> None:
    assert (
        errores_override(
            {
                "titulo": "Resumen",
                "limite": 10,
                "objetivo": 1500.5,
                "ia": True,
                "items": [
                    {"metrica": "alcance", "etiqueta": "Alcance", "comparar": "periodo_anterior"}
                ],
            }
        )
        == []
    )


@pytest.mark.parametrize(
    "config",
    [
        {"limite": 0},
        {"limite": 500},
        {"limite": "10"},
        {"limite": True},
        {"objetivo": -1},
        {"objetivo": "mil"},
        {"ia": "si"},
        {"titulo": "x" * 201},
        {"items": "alcance"},
        {"items": [{"etiqueta": "sin métrica"}]},
        {"items": [{"metrica": "alcance", "extra": {"anidado": 1}}]},
        {"items": [{"metrica": f"m{i}"} for i in range(13)]},
    ],
)
def test_override_valores_invalidos(config: dict[str, object]) -> None:
    assert errores_override(config)

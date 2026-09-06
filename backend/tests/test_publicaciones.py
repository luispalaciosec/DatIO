"""Publicaciones: normalización de posts de IG y FB con fixtures, y escritura idempotente."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from api.etl.conectores.meta_publicaciones import (
    ConectorMetaFBPublicaciones,
    ConectorMetaIGPublicaciones,
)
from api.etl.repositorio import Cuenta
from tests.conftest import requiere_db
from tests.semilla import mapeos_del_seed

FIXTURES = Path(__file__).parent / "fixtures"


def _cargar(nombre: str) -> list[dict[str, Any]]:
    datos: list[dict[str, Any]] = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
    return datos


def test_ig_media_a_publicaciones(config) -> None:  # type: ignore[no-untyped-def]
    c = ConectorMetaIGPublicaciones(
        Cuenta(1, 1, "meta_ig", "x", None), None, mapeos_del_seed()["meta_ig"], config
    )  # type: ignore[arg-type]
    pubs = c.normalizar_publicaciones(_cargar("meta_ig_media.json"))
    assert len(pubs) == 2
    imagen, reel = pubs
    assert imagen.tipo == "imagen" and reel.tipo == "reel"
    assert imagen.thumbnail_url == "https://cdn/x.jpg" and reel.thumbnail_url == "https://cdn/y.jpg"
    assert imagen.metricas["alcance"] == Decimal(511)
    assert imagen.metricas["impresiones"] == Decimal(1122)  # views → impresiones
    assert imagen.metricas["guardados"] == Decimal(4)
    assert imagen.metricas["seguidores_nuevos"] == Decimal(2)  # follows
    assert imagen.metricas["interacciones"] == Decimal(29)
    assert c.metricas_sin_mapeo == {"metricaRara"}


def test_fb_posts_a_publicaciones(config) -> None:  # type: ignore[no-untyped-def]
    c = ConectorMetaFBPublicaciones(
        Cuenta(1, 1, "meta_fb", "x", None), None, mapeos_del_seed()["meta_fb"], config
    )  # type: ignore[arg-type]
    pubs = c.normalizar_publicaciones(_cargar("meta_fb_posts.json"))
    assert len(pubs) == 2
    foto, video = pubs
    assert foto.tipo == "imagen" and video.tipo == "video"
    assert foto.metricas["me_gusta"] == Decimal(20)
    assert foto.metricas["comentarios"] == Decimal(4)
    assert foto.metricas["compartidos"] == Decimal(3)
    assert foto.metricas["clics"] == Decimal(15)
    assert foto.metricas["interacciones"] == Decimal(27)  # reacciones + comentarios + compartidos
    assert video.metricas["me_gusta"] == Decimal(5) and video.metricas["compartidos"] == Decimal(0)
    assert "clics" not in video.metricas  # sin insights: no se inventa un cero
    assert c.metricas_sin_mapeo == set()
    assert {m for m in ConectorMetaFBPublicaciones.METRICAS_NATIVAS} <= set(
        mapeos_del_seed()["meta_fb"]
    )
    assert {m for m in ConectorMetaIGPublicaciones.METRICAS_NATIVAS} <= set(
        mapeos_del_seed()["meta_ig"]
    )


@requiere_db
async def test_publicaciones_escriben_y_son_idempotentes(repo, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    class Falso(ConectorMetaIGPublicaciones):
        codigo = "ig_pub_falso"
        reintentos = 1

        async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
            return _cargar("meta_ig_media.json")

    mapeo = await repo.mapeo_plataforma("meta_ig")
    conector = Falso(cliente_a.cuenta, repo, mapeo, config)
    r1 = await conector.correr(hasta=date(2026, 9, 1))
    assert r1.estado == "parcial" and r1.filas_escritas == 11  # 9 + 2 métricas mapeadas
    r2 = await Falso(cliente_a.cuenta, repo, mapeo, config).correr(hasta=date(2026, 9, 1))
    assert await repo.contar_publicaciones(cliente_a.cuenta.id) == 2
    assert r2.filas_escritas == 11
    pubs = await repo._pool.fetch(
        "SELECT id_externo, tipo, thumbnail_url FROM dim_publicacion "
        "WHERE cuenta_id = $1 ORDER BY 1",
        cliente_a.cuenta.id,
    )
    assert [p["tipo"] for p in pubs] == ["reel", "imagen"]
    await repo._pool.execute(
        "DELETE FROM dim_publicacion WHERE cuenta_id = $1", cliente_a.cuenta.id
    )

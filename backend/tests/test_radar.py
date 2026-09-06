"""PT-15: normalización de perfiles de Apify y bloque benchmark_grid."""

import json
from datetime import date
from decimal import Decimal

import pytest

from api.consulta.repositorio import RepositorioConsulta
from api.etl.radar import clave_perfil, entrada_actor, normalizar_instagram
from api.resolvedores import Contexto
from api.resolvedores.benchmark_grid import resolver
from tests.conftest import requiere_db


def test_normalizar_instagram_suma_ultimas_publicaciones() -> None:
    perfil = {
        "username": "bancoguayaquil",
        "followersCount": 184094,
        "postsCount": 633,
        "latestPosts": [
            {"likesCount": 391, "commentsCount": 144},
            {"likesCount": 9, "commentsCount": 1},
        ],
    }
    v = normalizar_instagram(perfil)
    assert v["seguidores"] == Decimal(184094) and v["publicaciones"] == Decimal(633)
    assert v["me_gusta"] == Decimal(400) and v["comentarios"] == Decimal(145)
    assert v["interacciones"] == Decimal(545)
    assert "me_gusta" not in normalizar_instagram({"followersCount": 1})  # sin posts, sin inventar
    assert entrada_actor("meta_ig", ["a", "b"]) == {"usernames": ["a", "b"]}
    assert clave_perfil("meta_ig", {"username": "BancoX"}) == "bancox"
    assert clave_perfil("meta_fb", {"pageUrl": "https://www.facebook.com/BancoX/"}) == "bancox"


@requiere_db
async def test_benchmark_grid_compara_con_snapshots(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    kid = await pool.fetchval(
        "INSERT INTO cliente_competidores (cliente_id, plataforma, nombre, handle, orden) "
        "VALUES ($1, 'ga4', 'Rival', 'rival', 0) RETURNING id",
        cliente_a.id,
    )
    await pool.executemany(
        "INSERT INTO fct_competidor_snapshot (competidor_id, fecha_snapshot, metrica_codigo, valor) "
        "VALUES ($1, $2, $3, $4)",
        [
            (kid, date(2026, 8, 25), "seguidores", 100),
            (kid, date(2026, 9, 1), "seguidores", 110),
            (kid, date(2026, 9, 1), "publicaciones", 50),
        ],
    )
    repo = RepositorioConsulta(pool)
    ctx = Contexto(
        repo,
        [cliente_a.cuenta.id],
        cliente_a.id,
        {"plataforma": "ga4", "metricas": ["seguidores", "publicaciones"], "etiqueta_propio": "Yo"},
        date(2026, 8, 26),
        date(2026, 9, 1),
        None,
    )
    r = await resolver(ctx)
    assert r.meta["snapshot"] == "2026-09-01" and r.meta["sin_competidores"] is False
    propio, rival = r.datos
    assert propio["propio"] is True and propio["nombre"] == "Yo"
    assert rival["valores"] == {"seguidores": 110.0, "publicaciones": 50.0}
    assert rival["deltas"]["seguidores"] == 10.0 and rival["deltas"]["publicaciones"] is None
    json.dumps(r.datos)  # serializable
    await pool.execute("DELETE FROM cliente_competidores WHERE id = $1", kid)


@requiere_db
async def test_benchmark_sin_competidores(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    ctx = Contexto(
        RepositorioConsulta(pool),
        [cliente_a.cuenta.id],
        cliente_a.id,
        {"plataforma": "ga4"},
        date(2026, 8, 26),
        date(2026, 9, 1),
        None,
    )
    r = await resolver(ctx)
    assert r.meta["sin_competidores"] is True and len(r.datos) == 1
    with pytest.raises(KeyError):
        _ = r.datos[0]["valores"]["inexistente"]

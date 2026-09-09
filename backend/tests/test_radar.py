"""PT-15: normalización de perfiles de Apify y bloque benchmark_grid."""

import json
from datetime import date
from decimal import Decimal

import pytest

from api.consulta.repositorio import RepositorioConsulta
from api.etl.radar import clave_perfil, entrada_actor, normalizar_instagram, publicaciones_instagram
from api.resolvedores import Contexto
from api.resolvedores.benchmark_grid import resolver
from api.resolvedores.benchmark_publicaciones import resolver as resolver_pubs
from api.resolvedores.benchmark_serie import resolver as resolver_serie
from api.resolvedores.benchmark_tabla import resolver as resolver_tabla
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
        "INSERT INTO fct_competidor_snapshot "
        "(competidor_id, fecha_snapshot, metrica_codigo, valor) VALUES ($1, $2, $3, $4)",
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


def test_normalizar_instagram_promedios_ritmo_y_engagement() -> None:
    perfil = {
        "followersCount": 10000,
        "postsCount": 50,
        "latestPosts": [
            {
                "id": "1",
                "likesCount": 300,
                "commentsCount": 20,
                "timestamp": "2026-09-01T10:00:00.000Z",
            },
            {
                "id": "2",
                "likesCount": 100,
                "commentsCount": 0,
                "timestamp": "2026-08-25T10:00:00.000Z",
            },
        ],
    }
    v = normalizar_instagram(perfil)
    assert v["me_gusta_promedio"] == Decimal(200) and v["comentarios_promedio"] == Decimal(10)
    assert v["interacciones_promedio"] == Decimal(210)
    assert v["tasa_engagement"] == Decimal("2.1")  # 210 / 10000 * 100
    assert v["publicaciones_semana"] == Decimal(2)  # 2 posts en 7 días
    sin_fechas = normalizar_instagram({"followersCount": 1, "latestPosts": [{"likesCount": 1}]})
    assert "publicaciones_semana" not in sin_fechas  # sin fechas no se inventa el ritmo


def test_publicaciones_instagram_mapea_formato_y_miniatura() -> None:
    perfil = {
        "latestPosts": [
            {
                "id": "abc",
                "type": "Sidecar",
                "url": "https://www.instagram.com/p/abc/",
                "caption": "Hola",
                "displayUrl": "https://img/abc.jpg",
                "likesCount": 5,
                "commentsCount": 2,
                "timestamp": "2026-09-01T10:00:00.000Z",
            },
            {"id": "v1", "type": "Video", "videoViewCount": 900, "images": ["https://img/v1.jpg"]},
            {"type": "Image"},  # sin id: se descarta
        ]
    }
    pubs = publicaciones_instagram(perfil)
    assert [p["tipo"] for p in pubs] == ["carrusel", "reel"]
    assert pubs[0]["thumbnail_url"] == "https://img/abc.jpg" and pubs[0]["me_gusta"] == Decimal(5)
    assert pubs[0]["publicado_en"] is not None and pubs[0]["publicado_en"].year == 2026
    assert (
        pubs[1]["reproducciones"] == Decimal(900)
        and pubs[1]["thumbnail_url"] == "https://img/v1.jpg"
    )
    assert pubs[1]["me_gusta"] is None  # ausente ≠ cero


@requiere_db
async def test_benchmark_completo(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    """Tabla comparativa con ranking, serie de seguidores y publicaciones de la competencia."""
    kid = await pool.fetchval(
        "INSERT INTO cliente_competidores (cliente_id, plataforma, nombre, handle, orden) "
        "VALUES ($1, 'ga4', 'Rival', 'rival', 0) RETURNING id",
        cliente_a.id,
    )
    await pool.executemany(
        "INSERT INTO fct_competidor_snapshot "
        "(competidor_id, fecha_snapshot, metrica_codigo, valor) VALUES ($1, $2, $3, $4)",
        [
            (kid, date(2026, 8, 25), "seguidores", 100),
            (kid, date(2026, 9, 1), "seguidores", 110),
            (kid, date(2026, 9, 1), "interacciones_promedio", 50),
            (kid, date(2026, 9, 1), "tasa_engagement", Decimal("45.45")),
            (kid, date(2026, 9, 1), "publicaciones_semana", 3),
        ],
    )
    await pool.execute(
        "INSERT INTO competidor_publicaciones (competidor_id, id_externo, tipo, publicado_en, "
        "permalink, caption, me_gusta, comentarios, fecha_snapshot) VALUES "
        "($1, 'p1', 'reel', '2026-08-30', 'https://x/p1', 'Reel', 40, 10, '2026-09-01'), "
        "($1, 'p2', 'carrusel', '2026-08-20', 'https://x/p2', 'Carrusel', 5, 1, '2026-09-01'), "
        "($1, 'p3', 'reel', '2026-08-10', 'https://x/p3', 'Reel 2', 1, 0, '2026-09-01')",
        kid,
    )
    repo = RepositorioConsulta(pool)
    ctx = Contexto(
        repo,
        [cliente_a.cuenta.id],
        cliente_a.id,
        {"plataforma": "ga4"},
        date(2026, 8, 26),
        date(2026, 9, 1),
        None,
    )
    tabla = await resolver_tabla(ctx)
    assert tabla.meta["sin_competidores"] is False and tabla.meta["marcas"] == 2
    propio, rival = tabla.datos
    assert propio["propio"] is True and rival["valores"]["seguidores"] == 110.0
    assert rival["delta_seguidores"] == 10.0
    assert rival["posicion"]["seguidores"] == 1 and rival["formato_dominante"] == "reel"
    assert rival["formatos"] == {"reel": 2, "carrusel": 1}
    assert rival["share_interacciones"] == 100.0  # el cliente de prueba no tiene publicaciones
    assert tabla.meta["lider_engagement"] == "Rival"
    json.dumps(tabla.datos)

    serie = await resolver_serie(ctx)
    claves = [s["clave"] for s in serie.datos["series"]]
    assert claves[1] == "Rival" and claves[0].startswith("Cliente prueba")  # nombre del cliente
    assert propio["nombre"].startswith("Cliente prueba")
    assert serie.meta["snapshots"] == 2
    assert {p["fecha"]: p.get("Rival") for p in serie.datos["puntos"]} == {
        "2026-08-25": 100.0,
        "2026-09-01": 110.0,
    }

    pubs = await resolver_pubs(
        Contexto(
            repo,
            [cliente_a.cuenta.id],
            cliente_a.id,
            {"plataforma": "ga4", "limite": 5},
            date(2026, 8, 26),
            date(2026, 9, 1),
            None,
        )
    )
    assert [p["caption"] for p in pubs.datos] == ["Reel", "Carrusel", "Reel 2"]  # por interacciones
    assert (
        pubs.datos[0]["competidor"] == "Rival"
        and pubs.datos[0]["metricas"]["interacciones"] == 50.0
    )
    json.dumps(pubs.datos)

    # Aislamiento: otro cliente no ve estos competidores ni sus publicaciones
    ajeno = Contexto(
        repo,
        [],
        cliente_a.id + 100000,
        {"plataforma": "ga4"},
        date(2026, 8, 26),
        date(2026, 9, 1),
        None,
    )
    assert (await resolver_tabla(ajeno)).meta["sin_competidores"] is True
    assert (await resolver_pubs(ajeno)).meta["sin_datos"] is True
    await pool.execute("DELETE FROM cliente_competidores WHERE id = $1", kid)


def test_reducir_imagen_a_jpeg_pequeno() -> None:
    import io

    from PIL import Image

    from api.etl.imagenes import reducir

    lienzo = io.BytesIO()
    Image.new("RGBA", (1600, 900), (200, 30, 30, 255)).save(lienzo, format="PNG")
    contenido, mime = reducir(lienzo.getvalue(), lado_maximo=640)
    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(contenido)) as img:
        assert img.size == (640, 360) and img.mode == "RGB"
    with pytest.raises(OSError):  # PIL.UnidentifiedImageError
        reducir(b"esto no es una imagen")


@requiere_db
async def test_imagen_competidor_endpoint(pool, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    import httpx

    from api.main import crear_app

    app = crear_app(config)
    kid = await pool.fetchval(
        "INSERT INTO cliente_competidores (cliente_id, plataforma, nombre, handle, orden) "
        "VALUES ($1, 'ga4', 'Rival', 'rival', 0) RETURNING id",
        cliente_a.id,
    )
    await pool.execute(
        "INSERT INTO competidor_imagenes (competidor_id, clave, tipo_mime, contenido) "
        "VALUES ($1, 'perfil', 'image/jpeg', $2)",
        kid,
        b"\xff\xd8\xff\xd9",
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            r = await http.get(f"/radar/imagen/{kid}/perfil")
            assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
            assert r.content == b"\xff\xd8\xff\xd9"
            assert "max-age" in r.headers["cache-control"]
            assert (await http.get(f"/radar/imagen/{kid}/no-existe")).status_code == 404
    # Con imagen local, el benchmark apunta a la API en vez de a la CDN que caduca
    repo = RepositorioConsulta(pool)
    comps = await repo.competidores_con_snapshots(cliente_a.id, "ga4", ["seguidores"])
    assert comps[0]["logo_url"] == f"/radar/imagen/{kid}/perfil"
    await pool.execute("DELETE FROM cliente_competidores WHERE id = $1", kid)

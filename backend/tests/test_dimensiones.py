"""Dimensiones: normalización en conectores (fixtures) y bloques distribucion/tabla_ranking."""

from datetime import date
from decimal import Decimal

from api.consulta.repositorio import RepositorioConsulta
from api.etl.conectores.ga4 import ConectorGA4
from api.etl.conectores.gsc import ConectorGSC
from api.etl.conectores.meta_ig import ConectorMetaIG
from api.etl.repositorio import Cuenta, RepositorioETL
from api.resolvedores import Contexto
from api.resolvedores.dimensiones import demografia, distribucion, tabla_ranking
from tests.conftest import requiere_db
from tests.semilla import mapeos_del_seed


def test_ig_demografia_y_formato(config) -> None:  # type: ignore[no-untyped-def]
    c = ConectorMetaIG(
        Cuenta(1, 1, "meta_ig", "x", None), None, mapeos_del_seed()["meta_ig"], config
    )  # type: ignore[arg-type]
    payload = [
        {
            "tipo": "demografia",
            "desglose": "city",
            "fecha": "2026-09-05",
            "data": [
                {
                    "name": "follower_demographics",
                    "total_value": {
                        "breakdowns": [
                            {
                                "results": [
                                    {
                                        "dimension_values": ["Guayaquil, Guayas Province"],
                                        "value": 1467,
                                    },
                                    {
                                        "dimension_values": ["Quito, Pichincha Province"],
                                        "value": 383,
                                    },
                                ]
                            }
                        ]
                    },
                }
            ],
        },
        {
            "tipo": "formato",
            "fecha": "2026-09-04",
            "data": [
                {
                    "name": "reach",
                    "total_value": {
                        "breakdowns": [
                            {
                                "results": [
                                    {"dimension_values": ["REEL"], "value": 11},
                                    {"dimension_values": ["POST"], "value": 66},
                                ]
                            }
                        ]
                    },
                },
                {
                    "name": "views",
                    "total_value": {
                        "breakdowns": [{"results": [{"dimension_values": ["AD"], "value": 5}]}]
                    },
                },
            ],
        },
        {
            "tipo": "dia",
            "fecha": "2026-09-04",
            "data": [{"name": "reach", "total_value": {"value": 77}}],
        },
    ]
    dims = c.normalizar_dimensiones(payload)
    assert (
        date(2026, 9, 5),
        "seguidores",
        "ciudad",
        "Guayaquil, Guayas Province",
        Decimal(1467),
    ) in dims
    assert (date(2026, 9, 4), "alcance", "formato", "reel", Decimal(11)) in dims
    assert (date(2026, 9, 4), "impresiones", "formato", "anuncio", Decimal(5)) in dims
    assert len(dims) == 5
    # la normalización diaria ignora los bloques de dimensión sin marcar "sin mapeo"
    assert c.normalizar(payload) == [(date(2026, 9, 4), "alcance", Decimal(77))]
    assert c.metricas_sin_mapeo == set()


def test_ga4_y_gsc_dimensiones(config) -> None:  # type: ignore[no-untyped-def]
    ga = ConectorGA4(Cuenta(1, 1, "ga4", "1", None), None, mapeos_del_seed()["ga4"], config)  # type: ignore[arg-type]
    payload = [
        {
            "metricHeaders": [{"name": "sessions"}],
            "rows": [
                {"dimensionValues": [{"value": "20260901"}], "metricValues": [{"value": "10"}]}
            ],
        },
        {
            "tipo": "dimension",
            "dimension": "canal",
            "metricHeaders": [{"name": "sessions"}, {"name": "activeUsers"}],
            "rows": [
                {
                    "dimensionValues": [{"value": "20260901"}, {"value": "Organic Search"}],
                    "metricValues": [{"value": "7"}, {"value": "6"}],
                },
                {
                    "dimensionValues": [{"value": "20260901"}, {"value": ""}],
                    "metricValues": [{"value": "1"}, {"value": "1"}],
                },
            ],
        },
        {"tipo": "dimension", "dimension": "pais", "error": "cuota"},
    ]
    assert ga.normalizar(payload) == [(date(2026, 9, 1), "sesiones", Decimal(10))]
    dims = ga.normalizar_dimensiones(payload)
    assert (date(2026, 9, 1), "sesiones", "canal", "Organic Search", Decimal(7)) in dims
    assert (date(2026, 9, 1), "usuarios_activos", "canal", "(sin dato)", Decimal(1)) in dims

    gs = ConectorGSC(
        Cuenta(2, 1, "gsc", "sc-domain:x", None), None, mapeos_del_seed()["gsc"], config
    )  # type: ignore[arg-type]
    payload = [
        {
            "rows": [
                {"keys": ["2026-09-01"], "clicks": 3, "impressions": 30, "ctr": 0.1, "position": 5}
            ]
        },
        {
            "tipo": "dimension",
            "dimension": "consulta",
            "dims": ["query"],
            "fecha": "2026-09-04",
            "rows": [
                {
                    "keys": ["geeks"],
                    "clicks": 15,
                    "impressions": 91,
                    "ctr": 0.1648,
                    "position": 6.66,
                }
            ],
        },
        {
            "tipo": "dimension",
            "dimension": "dispositivo",
            "dims": ["date", "device"],
            "fecha": "2026-09-04",
            "rows": [
                {
                    "keys": ["2026-09-02", "DESKTOP"],
                    "clicks": 2,
                    "impressions": 9,
                    "ctr": 0.22,
                    "position": 4,
                }
            ],
        },
    ]
    assert len(gs.normalizar(payload)) == 4
    dims = gs.normalizar_dimensiones(payload)
    assert (date(2026, 9, 4), "clics_busqueda", "consulta", "geeks", Decimal(15)) in dims
    assert (date(2026, 9, 4), "ctr_busqueda", "consulta", "geeks", Decimal("16.48")) in dims
    assert (date(2026, 9, 2), "clics_busqueda", "dispositivo", "DESKTOP", Decimal(2)) in dims


@requiere_db
async def test_bloques_de_dimension(pool, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    repo_etl = RepositorioETL(pool)
    cuenta = cliente_a.cuenta.id
    await repo_etl.upsert_dimensiones(
        cuenta,
        [
            (date(2026, 9, 1), "sesiones", "canal", "Direct", Decimal(5)),
            (date(2026, 9, 2), "sesiones", "canal", "Direct", Decimal(7)),
            (date(2026, 9, 2), "sesiones", "canal", "Organic Search", Decimal(20)),
            (date(2026, 9, 2), "usuarios_activos", "canal", "Organic Search", Decimal(9)),
            (date(2026, 9, 1), "seguidores", "edad", "25-34", Decimal(100)),
            (date(2026, 9, 2), "seguidores", "edad", "25-34", Decimal(120)),
            (date(2026, 9, 2), "seguidores", "genero", "F", Decimal(70)),
            (date(2026, 9, 2), "seguidores", "genero", "M", Decimal(50)),
        ],
        date(2026, 9, 3),
    )
    # idempotente
    await repo_etl.upsert_dimensiones(
        cuenta, [(date(2026, 9, 2), "sesiones", "canal", "Direct", Decimal(7))], date(2026, 9, 3)
    )
    assert await repo_etl.contar_dimensiones(cuenta) == 8

    repo = RepositorioConsulta(pool)
    ctx = Contexto(
        repo,
        [cuenta],
        cliente_a.id,
        {"metrica": "sesiones", "dimension": "canal", "modo": "suma"},
        date(2026, 9, 1),
        date(2026, 9, 2),
        None,
    )
    r = await distribucion(ctx)
    assert [(f["etiqueta"], f["valor"]) for f in r.datos] == [
        ("Organic Search", 20.0),
        ("Direct", 12.0),
    ]
    assert r.datos[0]["porcentaje"] == 62.5

    ctx.config = {"metrica": "seguidores"}
    r = await demografia(ctx)
    assert r.datos["edades"] == [{"etiqueta": "25-34", "valor": 120.0}]  # último snapshot, no suma
    assert [g["etiqueta"] for g in r.datos["generos"]] == ["Mujeres", "Hombres"]

    ctx.config = {
        "dimension": "canal",
        "columnas": ["sesiones", "usuarios_activos"],
        "orden": "sesiones",
        "limite": 5,
    }
    r = await tabla_ranking(ctx)
    assert r.datos[0] == {
        "etiqueta": "Organic Search",
        "valores": {"sesiones": 20.0, "usuarios_activos": 9.0},
    }
    assert r.datos[1]["valores"] == {"sesiones": 12.0}

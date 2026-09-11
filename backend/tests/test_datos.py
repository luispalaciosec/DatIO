"""Explorador de datos: catálogo por conector y consultas a medida con pivote y CSV."""

from datetime import date

import httpx

from api.admin.router_datos import pivotar
from api.datos.repositorio import RepositorioDatos
from api.main import crear_app
from tests.conftest import requiere_db


def test_pivotar_una_fila_por_periodo_cuenta_y_dimension() -> None:
    filas = [
        {
            "periodo": date(2026, 9, 1),
            "cuenta_id": 1,
            "metrica_codigo": "sesiones",
            "valor_dimension": "Direct",
            "valor": 10,
        },
        {
            "periodo": date(2026, 9, 1),
            "cuenta_id": 1,
            "metrica_codigo": "usuarios_activos",
            "valor_dimension": "Direct",
            "valor": 8,
        },
        {
            "periodo": date(2026, 9, 1),
            "cuenta_id": 1,
            "metrica_codigo": "sesiones",
            "valor_dimension": "Organic",
            "valor": 5,
        },
    ]
    columnas, tabla = pivotar(filas, ["sesiones", "usuarios_activos"], {1: "Geeks · ga4"})
    assert columnas == ["periodo", "cuenta", "dimension", "sesiones", "usuarios_activos"]
    assert tabla[0] == {
        "periodo": "2026-09-01",
        "cuenta": "Geeks · ga4",
        "dimension": "Direct",
        "sesiones": 10.0,
        "usuarios_activos": 8.0,
    }
    assert tabla[1]["usuarios_activos"] is None  # métrica sin dato en esa dimensión
    sin_dim, _ = pivotar([{**filas[0], "valor_dimension": None}], ["sesiones"], {})
    assert sin_dim == ["periodo", "cuenta", "sesiones"]


@requiere_db
async def test_catalogo_y_consulta(pool, cliente_a, config) -> None:  # type: ignore[no-untyped-def]
    cid = cliente_a.cuenta.id
    await pool.executemany(
        "INSERT INTO fct_metrica_diaria "
        "(cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado) "
        "VALUES ($1, $2, $3, $4, $5, 'consolidado') ON CONFLICT DO NOTHING",
        [
            (cid, date(2026, 9, 1), "sesiones", 10, date(2026, 9, 2)),
            (cid, date(2026, 9, 2), "sesiones", 20, date(2026, 9, 3)),
            (cid, date(2026, 9, 1), "seguidores", 100, date(2026, 9, 2)),  # 'ultimo'
            (cid, date(2026, 9, 2), "seguidores", 120, date(2026, 9, 3)),
        ],
    )
    await pool.execute(
        "INSERT INTO fct_metrica_dimension (cuenta_id, fecha, metrica_codigo, dimension, "
        "valor_dimension, valor, fecha_snapshot) VALUES "
        "($1, '2026-09-01', 'sesiones', 'canal', 'Direct', 7, '2026-09-02'), "
        "($1, '2026-09-02', 'sesiones', 'canal', 'Direct', 13, '2026-09-03'), "
        "($1, '2026-09-02', 'sesiones', 'canal', 'Organic', 4, '2026-09-03') "
        "ON CONFLICT DO NOTHING",
        cid,
    )
    repo = RepositorioDatos(pool)
    cat = await repo.catalogo()
    ga4 = next(p for p in cat["plataformas"] if p["codigo"] == "ga4")
    sesiones = next(m for m in ga4["metricas"] if m["codigo"] == "sesiones")
    assert (
        sesiones["metrica_nativa"]
        and sesiones["agregacion"] == "suma"
        and sesiones["hasta"] >= date(2026, 9, 2)
    )
    assert any(d["dimension"] == "canal" for d in ga4["dimensiones"])
    assert any(c["id"] == cid for c in ga4["cuentas"])

    # Total del rango: suma para sesiones, último valor para seguidores
    filas = await repo.consultar(
        [cid],
        ["sesiones", "seguidores"],
        date(2026, 9, 1),
        date(2026, 9, 2),
        "total",
        None,
        100,
    )
    valores = {f["metrica_codigo"]: float(f["valor"]) for f in filas}
    assert valores == {"sesiones": 30.0, "seguidores": 120.0}
    # Por dimensión
    dim = await repo.consultar(
        [cid], ["sesiones"], date(2026, 9, 1), date(2026, 9, 2), "total", "canal", 100
    )
    assert {f["valor_dimension"]: float(f["valor"]) for f in dim} == {
        "Direct": 20.0,
        "Organic": 4.0,
    }

    # Endpoint CSV como equipo; un usuario cliente recibe 403
    app = crear_app(config)
    from tests.conftest import token_para

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as http:
            cuerpo = {
                "cuentas": [cid],
                "metricas": ["sesiones"],
                "desde": "2026-09-01",
                "hasta": "2026-09-02",
                "granularidad": "dia",
                "dimension": None,
            }
            r = await http.post(
                "/admin/datos/consulta.csv",
                json=cuerpo,
                headers={"Authorization": f"Bearer {token_para(cliente_a.email)}"},
            )
            assert r.status_code == 403
    await pool.execute("DELETE FROM fct_metrica_dimension WHERE cuenta_id = $1", cid)

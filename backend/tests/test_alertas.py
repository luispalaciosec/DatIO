"""PT-14: detector de anomalías, corrida de alertas y resumen por correo."""

from datetime import date, timedelta

import pytest

from api.alertas.correo import enviar_resumen, renderizar_resumen
from api.alertas.detector import detectar
from api.alertas.repositorio import RepositorioAlertas
from api.alertas.servicio import AlertaNueva, correr_alertas
from api.config import Configuracion
from tests.conftest import requiere_db


def _serie(desde: date, dias: int, base: float = 1000.0) -> dict[date, float]:
    out = {}
    for i in range(dias):
        f = desde + timedelta(days=i)
        ruido = (i % 5 - 2) * 10  # ±20, determinista
        out[f] = (base if f.weekday() < 5 else base / 2) + ruido
    return out


def test_detecta_caida_fuera_de_banda() -> None:
    serie = _serie(date(2026, 7, 1), 60)
    dia = date(2026, 8, 29)  # sábado
    serie[dia] = 120.0  # esperado ~500
    a = detectar(serie, dia)
    assert a is not None and a.tipo == "anomalia" and a.severidad == "alta"
    assert a.esperado == pytest.approx(500, abs=25) and a.cambio < -0.7 and a.z < -3


def test_detecta_subida_como_oportunidad_y_respeta_umbral() -> None:
    serie = _serie(date(2026, 7, 1), 60)
    dia = date(2026, 8, 26)  # miércoles
    serie[dia] = 1900.0
    a = detectar(serie, dia)
    assert a is not None and a.tipo == "oportunidad"
    serie[dia] = 1040.0  # dentro de la banda
    assert detectar(serie, dia) is None


def test_sin_historia_o_volumen_chico_no_alerta() -> None:
    corta = _serie(date(2026, 8, 20), 10)
    assert detectar(corta, date(2026, 8, 29)) is None
    chica = _serie(date(2026, 7, 1), 60, base=8.0)
    chica[date(2026, 8, 29)] = 0.0
    assert detectar(chica, date(2026, 8, 29)) is None  # esperado < 20: ruido, no alerta
    assert detectar(_serie(date(2026, 7, 1), 60), date(2026, 9, 5)) is None  # sin dato del día


def test_seguidores_evalua_el_incremento_diario() -> None:
    serie = {date(2026, 7, 1) + timedelta(days=i): 10000.0 + 5 * i + (i % 3) for i in range(60)}
    dia = date(2026, 8, 29)
    serie[dia] = serie[dia - timedelta(days=1)] - 400  # perdió 400 seguidores en un día
    a = detectar(serie, dia, agregacion="ultimo")
    assert a is not None and a.tipo == "anomalia" and a.valor == -400.0


def test_renderizar_resumen_agrupa_por_cliente() -> None:
    alertas = [
        AlertaNueva(
            1,
            "Banco",
            1,
            "Instagram",
            "anomalia",
            "alta",
            "Banco · Instagram: alcance cayó 58 %",
            {},
        ),
        AlertaNueva(
            2,
            "Banco",
            1,
            "Facebook",
            "operativa",
            "media",
            "Banco · Facebook: 15 días sin publicar",
            {},
        ),
        AlertaNueva(
            3,
            "Geeks <script>",
            2,
            "Sitio web",
            "oportunidad",
            "media",
            "Geeks: sesiones subió 90 %",
            {},
        ),
    ]
    html = renderizar_resumen(alertas, "2026-09-09", "https://dat-io.vercel.app/admin/alertas")
    assert html.count("<h2") == 2 and "Geeks &lt;script&gt;" in html and "cayó 58 %" in html
    assert "https://dat-io.vercel.app/admin/alertas" in html


async def test_enviar_resumen_sin_clave_no_envia(config: Configuracion) -> None:
    alertas = [AlertaNueva(1, "Banco", 1, "Instagram", "anomalia", "alta", "x", {})]
    assert await enviar_resumen(config, ["a@b.c"], alertas, "2026-09-09") is False
    assert await enviar_resumen(config, [], [], "2026-09-09") is False


@requiere_db
async def test_correr_alertas_detecta_y_no_duplica(pool, cliente_a) -> None:  # type: ignore[no-untyped-def]
    cuenta = cliente_a.cuenta.id
    hoy = date(2026, 9, 9)
    ayer = hoy - timedelta(days=1)
    serie = _serie(ayer - timedelta(days=59), 60)
    serie[ayer] = 100.0  # caída fuerte de sesiones
    await pool.executemany(
        "INSERT INTO fct_metrica_diaria "
        "(cuenta_id, fecha, metrica_codigo, valor, fecha_snapshot, estado) "
        "VALUES ($1, $2, 'sesiones', $3, $4, 'consolidado') ON CONFLICT DO NOTHING",
        [(cuenta, f, v, hoy) for f, v in serie.items()],
    )
    await pool.execute(
        "INSERT INTO jobs_ejecucion (cuenta_id, conector, estado, error_detalle, iniciado_en) "
        "VALUES ($1, 'ga4', 'error', 'GraphAPIError: token', now())",
        cuenta,
    )
    repo = RepositorioAlertas(pool)
    r = await correr_alertas(repo, hoy)
    mias = [a for a in r.nuevas if a.detalle.get("cliente_id") == cliente_a.id]
    tipos = {a.tipo for a in mias}
    assert "anomalia" in tipos and "operativa" in tipos
    caida = next(a for a in mias if a.tipo == "anomalia")
    assert caida.detalle["metrica"] == "sesiones" and "cayó" in caida.titulo
    # Segunda corrida el mismo día: nada nuevo (dedupe por clave abierta)
    r2 = await correr_alertas(repo, hoy)
    assert not [a for a in r2.nuevas if a.detalle.get("cliente_id") == cliente_a.id]
    abiertas = await repo.listar()
    assert any(a["id"] == caida.id for a in abiertas)
    assert await repo.resolver(caida.id) is True
    assert not any(a["id"] == caida.id for a in await repo.listar())
    assert await repo.resolver(999999999) is False
    await pool.execute("DELETE FROM alertas WHERE cuenta_id = $1", cuenta)
    await pool.execute(
        "DELETE FROM jobs_ejecucion WHERE cuenta_id = $1 AND estado = 'error'", cuenta
    )

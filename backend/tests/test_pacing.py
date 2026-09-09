"""PT-13: pacing del mes en curso."""

from datetime import date, timedelta

from api.prediccion.pacing import calcular_pacing, limites_mes


def _serie(desde: date, dias: int, base: float = 100.0) -> dict[date, float]:
    # Lunes a viernes 100, fines de semana 50: estacionalidad semanal clara.
    return {
        desde + timedelta(days=i): base if (desde + timedelta(days=i)).weekday() < 5 else base / 2
        for i in range(dias)
    }


def test_limites_mes() -> None:
    assert limites_mes(date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))


def test_pacing_suma_respeta_dia_de_semana() -> None:
    serie = _serie(date(2026, 8, 1), 45)  # hasta el 14 de septiembre
    p = calcular_pacing(serie, hoy=date(2026, 9, 15), agregacion="suma")
    assert (p.mes_inicio, p.mes_fin, p.corte) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
        date(2026, 9, 14),
    )
    assert p.dias_transcurridos == 14 and p.dias_restantes == 16
    assert p.acumulado == sum(v for f, v in serie.items() if f.month == 9)
    # Sin ruido la proyección es exacta: cada día restante aporta su valor de día de semana.
    esperado = p.acumulado + sum(
        100.0 if (date(2026, 9, 14) + timedelta(days=i)).weekday() < 5 else 50.0
        for i in range(1, 17)
    )
    assert p.proyeccion_p50 == esperado
    assert p.proyeccion_p10 == p.proyeccion_p50 == p.proyeccion_p90  # sigma 0 → sin banda
    assert p.dias_referencia == 28


def test_pacing_ultimo_extrapola_incrementos() -> None:
    inicio = date(2026, 8, 20)
    serie = {inicio + timedelta(days=i): 1000.0 + 10 * i for i in range(20)}  # +10/día hasta 8 sep
    p = calcular_pacing(serie, hoy=date(2026, 9, 9), agregacion="ultimo")
    assert p.corte == date(2026, 9, 8) and p.acumulado == 1190.0
    assert p.dias_restantes == 22 and p.proyeccion_p50 == 1190.0 + 10 * 22
    assert p.ritmo_diario == 10.0


def test_pacing_sin_datos_del_mes() -> None:
    p = calcular_pacing({}, hoy=date(2026, 9, 9))
    assert p.acumulado == 0 and p.proyeccion_p50 is None and p.dias_transcurridos == 0


def test_pacing_mes_cerrado_no_proyecta_mas_alla() -> None:
    serie = _serie(date(2026, 7, 1), 62)  # julio y agosto completos
    p = calcular_pacing(serie, hoy=date(2026, 9, 9), agregacion="suma", mes=date(2026, 8, 15))
    assert p.corte == date(2026, 8, 31) and p.dias_restantes == 0
    assert p.proyeccion_p50 == p.acumulado


def test_pacing_usa_el_nivel_del_mes_y_la_forma_de_la_referencia() -> None:
    # Agosto al doble de nivel que septiembre: el cierre debe seguir el nivel de septiembre.
    serie = _serie(date(2026, 8, 1), 31, base=200.0) | _serie(date(2026, 9, 1), 14, base=100.0)
    p = calcular_pacing(serie, hoy=date(2026, 9, 15), agregacion="suma")
    esperado = sum(
        100.0 if (date(2026, 9, 1) + timedelta(days=i)).weekday() < 5 else 50.0 for i in range(30)
    )
    assert p.proyeccion_p50 is not None and abs(p.proyeccion_p50 - esperado) < 1e-6

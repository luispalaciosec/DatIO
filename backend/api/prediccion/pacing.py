"""Pacing del mes en curso (PT-13, spec/04 §4.1).

Curva de acumulación intra-mes ponderada por día de semana. De las últimas semanas se toma
solo la FORMA (cuánto pesa cada día de semana); el NIVEL sale del propio mes: si el mes lleva
el 22 % de su peso semanal y acumula X, el cierre es X / 0,22. Así un mes con menos pauta que
el anterior no hereda el nivel viejo. Con menos de 7 días de mes, el nivel se mezcla con el de
la referencia para no proyectar sobre dos o tres días. La banda (p10/p90) sale de la
dispersión de los residuos diarios de la referencia, escalada por los días que faltan.

Métricas 'suma' (alcance, sesiones, interacciones): el cierre es el acumulado del mes.
Métricas 'ultimo' (seguidores): el cierre es el nivel al fin de mes, extrapolando el
incremento diario promedio reciente.
Funciona desde ~30 días de historia; no requiere modelo estacional.
"""

import calendar
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

SEMANAS_REFERENCIA = 4
Z_P90 = 1.2816  # cuantil 90 % de una normal


@dataclass(frozen=True)
class Pacing:
    mes_inicio: date
    mes_fin: date
    corte: date  # último día con dato del mes
    dias_transcurridos: int
    dias_restantes: int
    acumulado: float  # lo que va del mes (o nivel actual si es 'ultimo')
    proyeccion_p50: float | None
    proyeccion_p10: float | None
    proyeccion_p90: float | None
    ritmo_diario: float | None  # promedio diario reciente
    dias_referencia: int  # cuántos días reales se usaron para el ritmo


def limites_mes(dia: date) -> tuple[date, date]:
    ultimo = calendar.monthrange(dia.year, dia.month)[1]
    return dia.replace(day=1), dia.replace(day=ultimo)


def _promedio_por_dia_semana(puntos: dict[date, float]) -> tuple[dict[int, float], float]:
    """Promedio por día de semana y desviación de los residuos (valor − promedio del día)."""
    por_dia: dict[int, list[float]] = {}
    for f, v in puntos.items():
        por_dia.setdefault(f.weekday(), []).append(v)
    medias = {d: statistics.fmean(vs) for d, vs in por_dia.items()}
    global_ = statistics.fmean(puntos.values()) if puntos else 0.0
    residuos = [v - medias.get(f.weekday(), global_) for f, v in puntos.items()]
    sigma = statistics.pstdev(residuos) if len(residuos) > 1 else 0.0
    return medias, sigma


def calcular_pacing(
    serie: dict[date, float], hoy: date, agregacion: str = "suma", mes: date | None = None
) -> Pacing:
    """serie: valor diario por fecha (puede incluir meses anteriores: se usan como referencia).
    hoy: hoy real; el corte es el último día con dato dentro del mes, nunca después de ayer."""
    mes_inicio, mes_fin = limites_mes(mes or hoy)
    tope = min(mes_fin, hoy - timedelta(days=1)) if mes is None or mes_fin >= hoy else mes_fin
    en_mes = {f: v for f, v in serie.items() if mes_inicio <= f <= tope}
    corte = max(en_mes) if en_mes else mes_inicio - timedelta(days=1)
    transcurridos = (corte - mes_inicio).days + 1 if en_mes else 0
    restantes = (mes_fin - corte).days

    # Referencia: las últimas N semanas hasta el corte (cruza al mes anterior si hace falta).
    ref_desde = corte - timedelta(days=7 * SEMANAS_REFERENCIA - 1)
    if agregacion == "ultimo":
        niveles = {f: v for f, v in serie.items() if ref_desde - timedelta(days=1) <= f <= corte}
        fechas = sorted(niveles)
        incrementos = {
            fechas[i]: niveles[fechas[i]] - niveles[fechas[i - 1]]
            for i in range(1, len(fechas))
            if (fechas[i] - fechas[i - 1]).days == 1
        }
        nivel = niveles[fechas[-1]] if fechas else 0.0
        if not incrementos:
            return Pacing(
                mes_inicio,
                mes_fin,
                corte,
                transcurridos,
                restantes,
                nivel,
                None,
                None,
                None,
                None,
                0,
            )
        medias, sigma = _promedio_por_dia_semana(incrementos)
        global_ = statistics.fmean(incrementos.values())
        faltante = sum(
            medias.get((corte + timedelta(days=i)).weekday(), global_)
            for i in range(1, restantes + 1)
        )
        banda = Z_P90 * sigma * (restantes**0.5)
        return Pacing(
            mes_inicio,
            mes_fin,
            corte,
            transcurridos,
            restantes,
            nivel,
            nivel + faltante,
            nivel + faltante - banda,
            nivel + faltante + banda,
            global_,
            len(incrementos),
        )

    acumulado = sum(en_mes.values())
    referencia = {f: v for f, v in serie.items() if ref_desde <= f <= corte}
    if not referencia or not en_mes:
        return Pacing(
            mes_inicio,
            mes_fin,
            corte,
            transcurridos,
            restantes,
            acumulado,
            None,
            None,
            None,
            None,
            0,
        )
    medias, sigma = _promedio_por_dia_semana(referencia)
    global_ = statistics.fmean(referencia.values()) or 1.0
    # Peso relativo de cada día de semana (1.0 = día promedio de la referencia)
    peso = {d: m / global_ for d, m in medias.items()}
    peso_transcurrido = sum(peso.get(f.weekday(), 1.0) for f in en_mes)
    peso_restante = sum(
        peso.get((corte + timedelta(days=i)).weekday(), 1.0) for i in range(1, restantes + 1)
    )
    nivel_mes = acumulado / peso_transcurrido if peso_transcurrido else global_
    alfa = min(1.0, len(en_mes) / 7)  # con pocos días del mes, pesa más la referencia
    nivel = alfa * nivel_mes + (1 - alfa) * global_
    faltante = nivel * peso_restante
    error_nivel = sigma / (len(en_mes) ** 0.5)
    banda = Z_P90 * error_nivel * peso_restante
    return Pacing(
        mes_inicio,
        mes_fin,
        corte,
        transcurridos,
        restantes,
        acumulado,
        acumulado + faltante,
        max(acumulado, acumulado + faltante - banda),
        acumulado + faltante + banda,
        nivel,
        len(referencia),
    )

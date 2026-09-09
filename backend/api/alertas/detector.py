"""Detector de anomalías diarias (PT-14).

Modelo, sin dependencias pesadas: esperado = mediana del mismo día de semana en la ventana
(descomposición estacional semanal simplificada); la escala es el MAD de los residuos
(robusto a los propios picos). Se dispara cuando el valor de ayer queda a |z| >= z_minimo
Y se desvía al menos `cambio_minimo` del esperado (evita alertas por ruido en volúmenes
chicos). Métricas 'ultimo' (seguidores) se evalúan sobre el incremento diario.
"""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

VENTANA_DIAS = 56
MINIMO_PUNTOS = 21
Z_MINIMO = 3.0
CAMBIO_MINIMO = 0.30
VOLUMEN_MINIMO = 20.0
CONSISTENCIA_MAD = 1.4826


@dataclass(frozen=True)
class Anomalia:
    fecha: date
    valor: float
    esperado: float
    z: float
    cambio: float  # relativo al esperado (−0.58 = cayó 58 %)
    tipo: str  # 'anomalia' (negativa) | 'oportunidad' (positiva)
    severidad: str  # 'alta' | 'media'


def _incrementos(serie: dict[date, float]) -> dict[date, float]:
    fechas = sorted(serie)
    return {
        fechas[i]: serie[fechas[i]] - serie[fechas[i - 1]]
        for i in range(1, len(fechas))
        if (fechas[i] - fechas[i - 1]).days == 1
    }


def detectar(
    serie: dict[date, float],
    dia: date,
    agregacion: str = "suma",
    z_minimo: float = Z_MINIMO,
    cambio_minimo: float = CAMBIO_MINIMO,
) -> Anomalia | None:
    """serie: valor diario por fecha, incluyendo `dia`. None si no hay anomalía o falta historia."""
    if agregacion == "ultimo":
        serie = _incrementos(serie)
    if dia not in serie:
        return None
    valor = serie[dia]
    ventana = {f: v for f, v in serie.items() if dia - timedelta(days=VENTANA_DIAS) <= f < dia}
    if len(ventana) < MINIMO_PUNTOS:
        return None
    mismos = [v for f, v in ventana.items() if f.weekday() == dia.weekday()]
    esperado = (
        statistics.median(mismos) if len(mismos) >= 3 else statistics.median(ventana.values())
    )
    por_dia: dict[int, list[float]] = {}
    for f, v in ventana.items():
        por_dia.setdefault(f.weekday(), []).append(v)
    medianas = {d: statistics.median(vs) for d, vs in por_dia.items()}
    global_ = statistics.median(ventana.values())
    residuos = [v - medianas.get(f.weekday(), global_) for f, v in ventana.items()]
    mad = statistics.median(abs(r) for r in residuos)
    escala = CONSISTENCIA_MAD * mad if mad > 0 else (statistics.pstdev(residuos) or 0.0)
    if escala <= 0:
        return None
    if agregacion != "ultimo" and abs(esperado) < VOLUMEN_MINIMO:
        return None
    z = (valor - esperado) / escala
    cambio = (valor - esperado) / esperado if esperado else (1.0 if valor > 0 else -1.0)
    if abs(z) < z_minimo or (agregacion != "ultimo" and abs(cambio) < cambio_minimo):
        return None
    tipo = "anomalia" if valor < esperado else "oportunidad"
    severidad = "alta" if abs(z) >= 5 or abs(cambio) >= 0.6 else "media"
    return Anomalia(dia, valor, esperado, round(z, 2), round(cambio, 4), tipo, severidad)

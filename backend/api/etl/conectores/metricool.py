"""Puente Metricool (PT-04d / PT-04e): LinkedIn y TikTok mientras no existe conector nativo.

Metricool no expone API en el plan actual, solo MCP. El MCP corre en una sesión de Claude
(rutina programada), no en Railway, así que el flujo es:

    rutina Claude → getAnalyticsDataByMetrics → POST /etl/importar/metricool → este conector

`extraer` no llama a ninguna red: devuelve el payload que llegó por el endpoint. El resto
(raw antes de normalizar, mapeo semántico, upsert idempotente, job) es el mismo de siempre.
Las métricas nativas son los field IDs de Metricool (LIEV01, TKEV07...), mapeados en el seed.
El día que exista el conector nativo, solo cambia la fuente: el esquema no se entera.
"""

from datetime import date, datetime
from typing import Any

from api.etl.conector_base import ConectorBase, Fila

# Field IDs de Metricool que se piden por plataforma (todos deben estar en el seed).
METRICAS_METRICOOL: dict[str, tuple[str, ...]] = {
    "linkedin": (
        "LIEV01",  # followers
        "LIEV08",  # deltaFollowers
        "LIEV22",  # accountPostImpressions
        "LIEV30",  # accountPageUniqueImpressions
        "LIEV21",  # accountPostReactions
        "LIEV23",  # accountPostComments
        "LIEV20",  # accountPostShares
        "LIEV24",  # accountPostClicks
        "LIEV28",  # accountPostInteractions
        "LIEV27",  # accountPostCount
    ),
    "tiktok": (
        "TKEV07",  # followers
        "TKEV16",  # followersAcquired
        "TKEV17",  # followersLost
        "TKEV12",  # accountViews
        "TKEV11",  # reach
        "TKEV13",  # accountLikes
        "TKEV14",  # accountComments
        "TKEV15",  # accountShares
        "TKEV06",  # interactions
        "TKEV09",  # profileViews
        "TKEV01",  # videos
    ),
}


class ConectorMetricool(ConectorBase):
    codigo = "metricool"
    plataforma = "linkedin"  # se sobreescribe por instancia con la plataforma de la cuenta
    reintentos = 1

    def __init__(self, *args: Any, payload: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plataforma = self.cuenta.plataforma
        self._payload = payload

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        return self._payload

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            metricas: list[str] = bloque["metricas"]
            for fila in bloque.get("rows", []):
                # Formato Metricool: [valor_metrica_1, ..., valor_metrica_n, 'AAAAMMDD']
                fecha = datetime.strptime(str(fila[-1]), "%Y%m%d").date()
                for nativa, valor in zip(metricas, fila[:-1], strict=True):
                    mapeada = self.mapear(nativa, valor)
                    if mapeada is not None:
                        salida.append((fecha, *mapeada))
        return salida

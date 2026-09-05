"""Conector GA4 (PT-04): Data API v1beta runReport, un día por fila."""

from datetime import date, datetime
from typing import Any

from api.etl.conector_base import Fila
from api.etl.conectores.google_base import ConectorGoogleBase
from api.etl.registro import registrar

URL_BASE = "https://analyticsdata.googleapis.com/v1beta"


@registrar
class ConectorGA4(ConectorGoogleBase):
    codigo = "ga4"
    plataforma = "ga4"
    scopes = ("https://www.googleapis.com/auth/analytics.readonly",)

    # Toda métrica aquí DEBE existir en map_metrica_plataforma para 'ga4' (test_semantica).
    METRICAS_NATIVAS = (
        "sessions",
        "activeUsers",
        "newUsers",
        "totalUsers",
        "screenPageViews",
        "bounceRate",
        "engagementRate",
        "averageSessionDuration",
        "keyEvents",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        # id_externo = property_id numérico de GA4
        url = f"{URL_BASE}/properties/{self.cuenta.id_externo}:runReport"
        cuerpo = {
            "dateRanges": [{"startDate": desde.isoformat(), "endDate": hasta.isoformat()}],
            "dimensions": [{"name": "date"}],
            "metrics": [{"name": m} for m in self.METRICAS_NATIVAS],
            "limit": 100000,
        }
        return [await self.post_json(url, cuerpo)]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for reporte in payload:
            cabeceras = [h["name"] for h in reporte.get("metricHeaders", [])]
            for fila in reporte.get("rows", []):
                fecha = datetime.strptime(fila["dimensionValues"][0]["value"], "%Y%m%d").date()
                for nativa, celda in zip(cabeceras, fila["metricValues"], strict=True):
                    mapeada = self.mapear(nativa, celda.get("value"))
                    if mapeada is not None:
                        salida.append((fecha, mapeada[0], mapeada[1]))
        return salida

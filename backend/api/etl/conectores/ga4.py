"""Conector GA4 (PT-04): Data API v1beta runReport, un día por fila."""

from datetime import date, datetime
from typing import Any

from api.etl.conector_base import Fila, FilaDimension
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

    # Desagregaciones diarias: dimensión GA4 → (nombre en español, métricas, límite de filas)
    DIMENSIONES = {
        "sessionDefaultChannelGroup": ("canal", ("sessions", "activeUsers", "keyEvents"), 5000),
        "deviceCategory": ("dispositivo", ("sessions", "activeUsers"), 1000),
        "country": ("pais", ("sessions", "activeUsers"), 5000),
        "city": ("ciudad", ("sessions", "activeUsers"), 20000),
        "pagePath": ("pagina", ("screenPageViews", "sessions"), 20000),
        "landingPage": ("pagina_destino", ("sessions", "keyEvents"), 20000),
    }

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        # id_externo = property_id numérico de GA4
        url = f"{URL_BASE}/properties/{self.cuenta.id_externo}:runReport"
        rango = [{"startDate": desde.isoformat(), "endDate": hasta.isoformat()}]
        cuerpo = {
            "dateRanges": rango,
            "dimensions": [{"name": "date"}],
            "metrics": [{"name": m} for m in self.METRICAS_NATIVAS],
            "limit": 100000,
        }
        payload = [await self.post_json(url, cuerpo)]
        for dimension, (nombre, metricas, limite) in self.DIMENSIONES.items():
            try:
                r = await self.post_json(
                    url,
                    {
                        "dateRanges": rango,
                        "dimensions": [{"name": "date"}, {"name": dimension}],
                        "metrics": [{"name": m} for m in metricas],
                        "limit": limite,
                    },
                )
            except Exception as e:  # una dimensión que falle no bloquea los totales
                r = {"error": str(e)[:200]}
            payload.append({"tipo": "dimension", "dimension": nombre, **r})
        return payload

    def normalizar_dimensiones(self, payload: list[dict[str, Any]]) -> list[FilaDimension]:
        salida: list[FilaDimension] = []
        for reporte in payload:
            if reporte.get("tipo") != "dimension":
                continue
            dimension = reporte["dimension"]
            cabeceras = [h["name"] for h in reporte.get("metricHeaders", [])]
            for fila in reporte.get("rows", []):
                fecha = datetime.strptime(fila["dimensionValues"][0]["value"], "%Y%m%d").date()
                valor_dim = fila["dimensionValues"][1]["value"] or "(sin dato)"
                for nativa, celda in zip(cabeceras, fila["metricValues"], strict=True):
                    mapeada = self.mapear(nativa, celda.get("value"))
                    if mapeada is not None:
                        salida.append((fecha, mapeada[0], dimension, valor_dim, mapeada[1]))
        return salida

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for reporte in payload:
            if reporte.get("tipo") == "dimension":
                continue
            cabeceras = [h["name"] for h in reporte.get("metricHeaders", [])]
            for fila in reporte.get("rows", []):
                fecha = datetime.strptime(fila["dimensionValues"][0]["value"], "%Y%m%d").date()
                for nativa, celda in zip(cabeceras, fila["metricValues"], strict=True):
                    mapeada = self.mapear(nativa, celda.get("value"))
                    if mapeada is not None:
                        salida.append((fecha, mapeada[0], mapeada[1]))
        return salida

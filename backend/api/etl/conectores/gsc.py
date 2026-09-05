"""Conector Google Search Console (PT-04): searchAnalytics.query por fecha."""

from datetime import date
from typing import Any
from urllib.parse import quote

from api.etl.conector_base import Fila
from api.etl.conectores.google_base import ConectorGoogleBase
from api.etl.registro import registrar

URL_BASE = "https://searchconsole.googleapis.com/webmasters/v3/sites"


@registrar
class ConectorGSC(ConectorGoogleBase):
    codigo = "gsc"
    plataforma = "gsc"
    scopes = ("https://www.googleapis.com/auth/webmasters.readonly",)

    METRICAS_NATIVAS = ("clicks", "impressions", "ctr", "position")

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        # id_externo = siteUrl tal como aparece en Search Console
        # ('https://ejemplo.com/' o 'sc-domain:ejemplo.com')
        url = f"{URL_BASE}/{quote(self.cuenta.id_externo, safe='')}/searchAnalytics/query"
        cuerpo = {
            "startDate": desde.isoformat(),
            "endDate": hasta.isoformat(),
            "dimensions": ["date"],
            "rowLimit": 1000,
        }
        return [await self.post_json(url, cuerpo)]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for reporte in payload:
            for fila in reporte.get("rows", []):
                fecha = date.fromisoformat(fila["keys"][0])
                for nativa in self.METRICAS_NATIVAS:
                    mapeada = self.mapear(nativa, fila.get(nativa))
                    if mapeada is not None:
                        salida.append((fecha, mapeada[0], mapeada[1]))
        return salida

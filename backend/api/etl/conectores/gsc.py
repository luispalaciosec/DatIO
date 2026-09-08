"""Conector Google Search Console (PT-04): searchAnalytics.query por fecha."""

from datetime import date
from typing import Any
from urllib.parse import quote

from api.etl.conector_base import Fila, FilaDimension
from api.etl.conectores.google_base import ConectorGoogleBase
from api.etl.registro import registrar

URL_BASE = "https://searchconsole.googleapis.com/webmasters/v3/sites"


@registrar
class ConectorGSC(ConectorGoogleBase):
    codigo = "gsc"
    plataforma = "gsc"
    scopes = ("https://www.googleapis.com/auth/webmasters.readonly",)

    METRICAS_NATIVAS = ("clicks", "impressions", "ctr", "position")

    # (dimensiones GSC, nombre en español, límite). Con 'date' se guardan por día; sin 'date'
    # son totales del período y se guardan con fecha = hasta.
    DIMENSIONES = (
        (["query"], "consulta", 250),
        (["page"], "pagina", 250),
        (["date", "device"], "dispositivo", 1000),
        (["date", "country"], "pais", 5000),
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        # id_externo = siteUrl tal como aparece en Search Console
        # ('https://ejemplo.com/' o 'sc-domain:ejemplo.com')
        url = f"{URL_BASE}/{quote(self.cuenta.id_externo, safe='')}/searchAnalytics/query"
        base = {"startDate": desde.isoformat(), "endDate": hasta.isoformat()}
        payload = [await self.post_json(url, {**base, "dimensions": ["date"], "rowLimit": 1000})]
        for dims, nombre, limite in self.DIMENSIONES:
            try:
                r = await self.post_json(url, {**base, "dimensions": dims, "rowLimit": limite})
            except Exception as e:
                r = {"error": str(e)[:200]}
            payload.append(
                {
                    "tipo": "dimension",
                    "dimension": nombre,
                    "dims": dims,
                    "fecha": hasta.isoformat(),
                    **r,
                }
            )
        return payload

    def normalizar_dimensiones(self, payload: list[dict[str, Any]]) -> list[FilaDimension]:
        salida: list[FilaDimension] = []
        for reporte in payload:
            if reporte.get("tipo") != "dimension":
                continue
            dims: list[str] = reporte["dims"]
            for fila in reporte.get("rows", []):
                claves = fila["keys"]
                if dims[0] == "date":
                    fecha, valor_dim = date.fromisoformat(claves[0]), claves[1]
                else:
                    fecha, valor_dim = date.fromisoformat(reporte["fecha"]), claves[0]
                for nativa in self.METRICAS_NATIVAS:
                    mapeada = self.mapear(nativa, fila.get(nativa))
                    if mapeada is not None:
                        salida.append(
                            (fecha, mapeada[0], reporte["dimension"], valor_dim, mapeada[1])
                        )
        return salida

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for reporte in payload:
            if reporte.get("tipo") == "dimension":
                continue
            for fila in reporte.get("rows", []):
                fecha = date.fromisoformat(fila["keys"][0])
                for nativa in self.METRICAS_NATIVAS:
                    mapeada = self.mapear(nativa, fila.get(nativa))
                    if mapeada is not None:
                        salida.append((fecha, mapeada[0], mapeada[1]))
        return salida

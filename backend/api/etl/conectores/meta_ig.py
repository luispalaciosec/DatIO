"""Conector Instagram orgánico (PT-05): insights de cuenta business.

En v21 casi todas las métricas de cuenta solo aceptan `metric_type=total_value`, que devuelve
un único total por rango. Para tener granularidad diaria se pide un rango de un día por cada
día de la ventana (29 llamadas por corrida). `impressions` fue reemplazada por `views`.
"""

from datetime import date, timedelta
from typing import Any

from api.etl.conector_base import Fila
from api.etl.conectores.meta_base import ConectorMetaBase
from api.etl.registro import registrar


@registrar
class ConectorMetaIG(ConectorMetaBase):
    codigo = "meta_ig"
    plataforma = "meta_ig"

    METRICAS_DIARIAS = (
        "reach",
        "views",
        "profile_views",
        "website_clicks",
        "accounts_engaged",
        "total_interactions",
        "likes",
        "comments",
        "shares",
        "saves",
    )
    METRICAS_PERFIL = ("followers_count", "media_count")
    METRICAS_NATIVAS = METRICAS_DIARIAS + METRICAS_PERFIL

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self.token_acceso()
        ig = self.cuenta.id_externo
        payload: list[dict[str, Any]] = []
        for dia in self.dias(desde, hasta):
            r = await self.get(
                f"{ig}/insights",
                token,
                metric=",".join(self.METRICAS_DIARIAS),
                period="day",
                metric_type="total_value",
                since=dia.isoformat(),
                until=(dia + timedelta(days=1)).isoformat(),
            )
            payload.append({"tipo": "dia", "fecha": dia.isoformat(), "data": r.get("data", [])})
        perfil = await self.get(ig, token, fields=",".join(self.METRICAS_PERFIL))
        payload.append({"tipo": "perfil", "fecha": hasta.isoformat(), "data": perfil})
        return payload

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            fecha = date.fromisoformat(bloque["fecha"])
            if bloque["tipo"] == "perfil":
                for nativa in self.METRICAS_PERFIL:
                    mapeada = self.mapear(nativa, bloque["data"].get(nativa))
                    if mapeada is not None:
                        salida.append((fecha, *mapeada))
                continue
            for serie in bloque["data"]:
                valor = (serie.get("total_value") or {}).get("value")
                mapeada = self.mapear(serie["name"], valor)
                if mapeada is not None:
                    salida.append((fecha, *mapeada))
        return salida

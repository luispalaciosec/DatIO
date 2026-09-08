"""Conector Instagram orgánico (PT-05): insights de cuenta business.

En v21 casi todas las métricas de cuenta solo aceptan `metric_type=total_value`, que devuelve
un único total por rango. Para tener granularidad diaria se pide un rango de un día por cada
día de la ventana (29 llamadas por corrida). `impressions` fue reemplazada por `views`.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from api.etl.conector_base import Fila, FilaDimension
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
    # Desagregaciones: demografía de seguidores (lifetime) y alcance/visualizaciones por formato
    DEMOGRAFIA = {"city": "ciudad", "country": "pais", "age": "edad", "gender": "genero"}
    FORMATOS = {
        "POST": "publicación",
        "REEL": "reel",
        "CAROUSEL_CONTAINER": "carrusel",
        "STORY": "historia",
        "AD": "anuncio",
    }

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
            try:
                f = await self.get(
                    f"{ig}/insights",
                    token,
                    metric="reach,views",
                    period="day",
                    metric_type="total_value",
                    breakdown="media_product_type",
                    since=dia.isoformat(),
                    until=(dia + timedelta(days=1)).isoformat(),
                )
                payload.append(
                    {"tipo": "formato", "fecha": dia.isoformat(), "data": f.get("data", [])}
                )
            except Exception as e:  # el desglose no bloquea la captura diaria
                payload.append(
                    {"tipo": "formato", "fecha": dia.isoformat(), "data": [], "error": str(e)[:200]}
                )
        perfil = await self.get(ig, token, fields=",".join(self.METRICAS_PERFIL))
        payload.append({"tipo": "perfil", "fecha": hasta.isoformat(), "data": perfil})
        for desglose in self.DEMOGRAFIA:
            try:
                d = await self.get(
                    f"{ig}/insights",
                    token,
                    metric="follower_demographics",
                    period="lifetime",
                    metric_type="total_value",
                    breakdown=desglose,
                )
                payload.append(
                    {
                        "tipo": "demografia",
                        "desglose": desglose,
                        "fecha": hasta.isoformat(),
                        "data": d.get("data", []),
                    }
                )
            except Exception as e:
                payload.append(
                    {
                        "tipo": "demografia",
                        "desglose": desglose,
                        "fecha": hasta.isoformat(),
                        "data": [],
                        "error": str(e)[:200],
                    }
                )
        return payload

    def normalizar_dimensiones(self, payload: list[dict[str, Any]]) -> list[FilaDimension]:
        salida: list[FilaDimension] = []
        for bloque in payload:
            fecha = date.fromisoformat(bloque["fecha"])
            if bloque["tipo"] == "demografia":
                dimension = self.DEMOGRAFIA[bloque["desglose"]]
                for serie in bloque["data"]:
                    for desglose in (serie.get("total_value") or {}).get("breakdowns", []):
                        for r in desglose.get("results", []):
                            salida.append(
                                (
                                    fecha,
                                    "seguidores",
                                    dimension,
                                    str(r["dimension_values"][0]),
                                    Decimal(r["value"]),
                                )
                            )
            elif bloque["tipo"] == "formato":
                for serie in bloque["data"]:
                    mapeada = self.mapeo.get(serie["name"])
                    if mapeada is None:
                        continue
                    for desglose in (serie.get("total_value") or {}).get("breakdowns", []):
                        for r in desglose.get("results", []):
                            formato = self.FORMATOS.get(
                                r["dimension_values"][0], r["dimension_values"][0].lower()
                            )
                            salida.append(
                                (
                                    fecha,
                                    mapeada[0],
                                    "formato",
                                    formato,
                                    Decimal(r["value"]) * mapeada[1],
                                )
                            )
        return salida

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            if bloque["tipo"] in ("demografia", "formato"):
                continue  # van por normalizar_dimensiones
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

"""Conector Facebook orgánico (PT-05): insights de página con Page Access Token.

Meta retiró en 2024 las métricas de impresiones/alcance a nivel página
(page_impressions*, page_fans, page_engaged_users). Alcance e impresiones quedan a nivel
publicación (fct_publicacion_diaria, ola siguiente). Aquí va el conjunto vigente en v21.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from api.etl.conector_base import Fila
from api.etl.conectores.meta_base import ConectorMetaBase
from api.etl.registro import registrar


@registrar
class ConectorMetaFB(ConectorMetaBase):
    codigo = "meta_fb"
    plataforma = "meta_fb"

    METRICAS_NATIVAS = (
        "page_follows",
        "page_daily_follows",
        "page_daily_unfollows",
        "page_post_engagements",
        "page_views_total",
        "page_video_views",
        "page_actions_post_reactions_total",
        "page_total_actions",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self.token_acceso()
        # Los insights de página exigen Page Access Token; se deriva del token del System User.
        pagina = await self.get(self.cuenta.id_externo, token, fields="access_token")
        token_pagina = str(pagina["access_token"])
        insights = await self.get(
            f"{self.cuenta.id_externo}/insights",
            token_pagina,
            metric=",".join(self.METRICAS_NATIVAS),
            period="day",
            since=desde.isoformat(),
            until=(hasta + timedelta(days=1)).isoformat(),  # `until` es exclusivo en Meta
        )
        # Solo la respuesta de insights: nunca el token de página.
        return [{"tipo": "insights", "data": insights.get("data", [])}]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            for serie in bloque.get("data", []):
                nativa = serie["name"]
                for punto in serie.get("values", []):
                    valor = punto.get("value")
                    if isinstance(valor, dict):  # reacciones desglosadas por tipo
                        valor = sum(Decimal(str(v)) for v in valor.values())
                    mapeada = self.mapear(nativa, valor)
                    if mapeada is not None:
                        salida.append((self.fecha_de_end_time(punto["end_time"]), *mapeada))
        return salida

"""Conector Meta Ads (PT-06): insights de cuenta publicitaria, un día por fila.

Decisión: los campos que Meta devuelve como lista de {action_type, value} (conversions,
conversion_values, cost_per_conversion, purchase_roas) se consolidan sumando todos los tipos.
Granularidad por campaña/adset queda para cuando la spec lo pida (spec/01 §12.4).
"""

from datetime import date
from decimal import Decimal
from typing import Any

from api.etl.conector_base import Fila
from api.etl.conectores.meta_base import ConectorMetaBase
from api.etl.registro import registrar


@registrar
class ConectorMetaAds(ConectorMetaBase):
    codigo = "meta_ads"
    plataforma = "meta_ads"

    METRICAS_NATIVAS = (
        "impressions",
        "reach",
        "clicks",
        "inline_link_clicks",
        "spend",
        "cpm",
        "cpc",
        "ctr",
        "frequency",
        "conversions",
        "conversion_values",
        "cost_per_conversion",
        "purchase_roas",
        "video_play_actions",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self.token_acceso()
        filas = await self.get_paginado(
            f"{self.cuenta.id_externo}/insights",
            token,
            fields=",".join(self.METRICAS_NATIVAS),
            time_range=f'{{"since":"{desde.isoformat()}","until":"{hasta.isoformat()}"}}',
            time_increment=1,
            limit=500,
        )
        return [{"tipo": "insights", "data": filas}]

    @staticmethod
    def _consolidar(valor: Any) -> Any:
        if isinstance(valor, list):
            return sum(Decimal(str(v.get("value", 0))) for v in valor)
        return valor

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            for fila in bloque.get("data", []):
                fecha = date.fromisoformat(fila["date_start"])
                for nativa in self.METRICAS_NATIVAS:
                    if nativa not in fila:
                        continue
                    mapeada = self.mapear(nativa, self._consolidar(fila[nativa]))
                    if mapeada is not None:
                        salida.append((fecha, *mapeada))
        return salida

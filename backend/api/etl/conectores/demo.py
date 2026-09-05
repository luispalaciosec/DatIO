"""ConectorDemo (PT-03): payload determinista, sin red. Valida el patrón de punta a punta.

Usa el mapeo de GA4 para no inventar métricas. No se registra en el runner: se instancia
explícitamente en tests y pruebas manuales.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from api.etl.conector_base import ConectorBase, Fila


class ConectorDemo(ConectorBase):
    codigo = "demo"
    plataforma = "ga4"
    reintentos = 1

    METRICAS_NATIVAS = ("sessions", "activeUsers", "bounceRate")

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        filas = []
        dia = desde
        while dia <= hasta:
            semilla = dia.toordinal() % 97
            filas.append(
                {
                    "fecha": dia.isoformat(),
                    "metricas": {
                        "sessions": 100 + semilla,
                        "activeUsers": 80 + semilla,
                        "bounceRate": round(0.30 + semilla / 1000, 4),
                    },
                }
            )
            dia += timedelta(days=1)
        return filas

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for fila in payload:
            fecha = date.fromisoformat(fila["fecha"])
            for nativa, valor in fila["metricas"].items():
                mapeada = self.mapear(nativa, valor)
                if mapeada is not None:
                    salida.append((fecha, mapeada[0], Decimal(mapeada[1])))
        return salida

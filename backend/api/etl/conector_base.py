"""Contrato ConectorBase (PT-03). NO cambiar la firma sin acuerdo (spec/06, tabla de contratos).

Reglas obligatorias:
  * ventana de re-sync de 28 días
  * guardar_raw SIEMPRE antes de normalizar
  * upsert idempotente (lo garantiza el repositorio)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from api.config import Configuracion
from api.etl.repositorio import Cuenta, RepositorioETL

log = logging.getLogger(__name__)

Fila = tuple[date, str, Decimal]
FilaDimension = tuple[date, str, str, str, Decimal]  # fecha, metrica, dimension, valor_dim, valor
Mapeo = dict[str, tuple[str, Decimal]]  # metrica_nativa → (metrica_codigo, factor)


@dataclass
class ResultadoCorrida:
    cuenta_id: int
    conector: str
    job_id: int
    desde: date
    hasta: date
    filas_escritas: int
    estado: str
    metricas_sin_mapeo: set[str] = field(default_factory=set)


def hoy_en(zona: str) -> date:
    return datetime.now(ZoneInfo(zona)).date()


class ConectorBase(ABC):
    codigo: str  # identificador del conector ('ga4', 'gsc', 'demo'...)
    plataforma: str  # código en `plataformas` cuyo mapeo semántico usa

    reintentos: int = 5
    espera_min_seg: float = 4
    espera_max_seg: float = 120

    def __init__(
        self, cuenta: Cuenta, repo: RepositorioETL, mapeo: Mapeo, config: Configuracion
    ) -> None:
        self.cuenta = cuenta
        self.repo = repo
        self.mapeo = mapeo
        self.config = config
        self.metricas_sin_mapeo: set[str] = set()

    @abstractmethod
    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        """Devuelve el payload crudo de la API, sin transformar."""

    @abstractmethod
    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        """(fecha, metrica_codigo, valor) usando map_metrica_plataforma."""

    def normalizar_dimensiones(self, payload: list[dict[str, Any]]) -> list[FilaDimension]:
        """Desagregaciones (ciudad, canal, consulta…). Opcional: por defecto ninguna."""
        return []

    # ---- utilidades para los conectores concretos --------------------------

    def mapear(self, metrica_nativa: str, valor: Any) -> tuple[str, Decimal] | None:
        """Traduce una métrica nativa a canónica aplicando el factor. None si no está mapeada.

        Nunca se inventa una métrica: lo que no está en map_metrica_plataforma se ignora
        y se reporta en `metricas_sin_mapeo`.
        """
        entrada = self.mapeo.get(metrica_nativa)
        if entrada is None:
            self.metricas_sin_mapeo.add(metrica_nativa)
            return None
        if valor is None or valor == "":
            return None
        codigo, factor = entrada
        return codigo, Decimal(str(valor)) * factor

    def rango_por_defecto(self, hasta: date | None) -> tuple[date, date]:
        hasta = hasta or hoy_en(self.config.zona_horaria) - timedelta(days=1)
        desde = hasta - timedelta(days=self.config.ventana_resync_dias)
        return desde, hasta

    async def _extraer_con_reintentos(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        async for intento in AsyncRetrying(
            stop=stop_after_attempt(self.reintentos),
            wait=wait_exponential(multiplier=2, min=self.espera_min_seg, max=self.espera_max_seg),
            reraise=True,
        ):
            with intento:
                return await self.extraer(desde, hasta)
        raise RuntimeError("extraer no devolvió resultado")  # pragma: no cover

    # ---- corrida completa ---------------------------------------------------

    async def correr(self, hasta: date | None = None) -> ResultadoCorrida:
        desde, hasta = self.rango_por_defecto(hasta)
        fecha_snapshot = hoy_en(self.config.zona_horaria)
        job_id = await self.repo.abrir_job(self.cuenta.id, self.codigo)
        try:
            crudo = await self._extraer_con_reintentos(desde, hasta)
            # Regla de oro: raw antes de normalizar.
            await self.repo.guardar_raw(
                cuenta_id=self.cuenta.id,
                endpoint=self.codigo,
                params={"desde": desde.isoformat(), "hasta": hasta.isoformat()},
                payload=crudo,
                job_id=job_id,
            )
            filas = self.normalizar(crudo)
            n = await self.repo.upsert_metricas(self.cuenta.id, filas, fecha_snapshot)
            n += await self.repo.upsert_dimensiones(
                self.cuenta.id, self.normalizar_dimensiones(crudo), fecha_snapshot
            )
            estado = "ok" if not self.metricas_sin_mapeo else "parcial"
            detalle = (
                f"Métricas sin mapeo ignoradas: {sorted(self.metricas_sin_mapeo)}"
                if self.metricas_sin_mapeo
                else None
            )
            await self.repo.cerrar_job(job_id, estado, n, detalle)
            if detalle:
                log.warning("%s cuenta=%s %s", self.codigo, self.cuenta.id, detalle)
            return ResultadoCorrida(
                self.cuenta.id,
                self.codigo,
                job_id,
                desde,
                hasta,
                n,
                estado,
                set(self.metricas_sin_mapeo),
            )
        except Exception as e:
            await self.repo.cerrar_job(job_id, "error", 0, f"{type(e).__name__}: {e}")
            raise

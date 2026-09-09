"""Conectores de publicaciones: métricas por post (dim_publicacion + fct_publicacion_diaria).

Comparte con ConectorBase el ciclo raw → normalizar → upsert, el job y el mapeo semántico.
`normalizar` (contrato PT-03) no aplica a publicaciones y devuelve []; el trabajo real lo hace
`normalizar_publicaciones`, que devuelve la ficha de cada post y sus métricas ya canónicas.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from api.etl.conector_base import ConectorBase, Fila, ResultadoCorrida, hoy_en


@dataclass
class Publicacion:
    id_externo: str
    tipo: str | None
    publicado_en: datetime | None
    permalink: str | None
    caption: str | None
    thumbnail_url: str | None
    metricas: dict[str, Decimal] = field(default_factory=dict)  # metrica_codigo → valor

    def ficha(self) -> dict[str, Any]:
        return {
            "id_externo": self.id_externo,
            "tipo": self.tipo,
            "publicado_en": self.publicado_en,
            "permalink": self.permalink,
            "caption": self.caption,
            "thumbnail_url": self.thumbnail_url,
        }


class ConectorPublicacionesBase(ConectorBase):
    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        return []

    def normalizar_publicaciones(self, payload: list[dict[str, Any]]) -> list[Publicacion]:
        raise NotImplementedError

    def metricas_canonicas(self, nativas: dict[str, Any]) -> dict[str, Decimal]:
        salida: dict[str, Decimal] = {}
        for nativa, valor in nativas.items():
            m = self.mapear(nativa, valor)
            if m is not None:
                salida[m[0]] = salida.get(m[0], Decimal(0)) + m[1]
        return salida

    async def correr(
        self, hasta: date | None = None, provisional_desde: date | None = None
    ) -> ResultadoCorrida:
        # provisional_desde no aplica: las métricas por publicación llevan su propio snapshot.
        desde, hasta = self.rango_por_defecto(hasta)
        fecha_snapshot = hoy_en(self.config.zona_horaria)
        job_id = await self.repo.abrir_job(self.cuenta.id, self.codigo)
        try:
            crudo = await self._extraer_con_reintentos(desde, hasta)
            await self.repo.guardar_raw(
                self.cuenta.id,
                self.codigo,
                {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
                crudo,
                job_id,
            )
            publicaciones = self.normalizar_publicaciones(crudo)
            ids = await self.repo.upsert_publicaciones(
                self.cuenta.id, [p.ficha() for p in publicaciones], fecha_snapshot
            )
            filas = [
                (ids[p.id_externo], codigo, valor)
                for p in publicaciones
                for codigo, valor in p.metricas.items()
            ]
            n = await self.repo.upsert_metricas_publicacion(filas, fecha_snapshot)
            estado = "ok" if not self.metricas_sin_mapeo else "parcial"
            detalle = (
                f"{len(publicaciones)} publicaciones. Sin mapeo: {sorted(self.metricas_sin_mapeo)}"
                if self.metricas_sin_mapeo
                else f"{len(publicaciones)} publicaciones"
            )
            await self.repo.cerrar_job(job_id, estado, n, detalle)
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

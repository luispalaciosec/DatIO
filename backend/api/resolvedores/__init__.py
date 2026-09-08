"""Registro de resolvedores de bloques (PT-08). Agregar un bloque = registrar una función."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from api.consulta.repositorio import RepositorioConsulta


@dataclass
class Contexto:
    repo: RepositorioConsulta
    cuentas: list[int]
    cliente_id: int
    config: dict[str, Any]
    desde: date
    hasta: date
    comparar: str | None


@dataclass
class Resultado:
    datos: Any
    estado: str = "consolidado"  # 'consolidado' | 'provisional'
    meta: dict[str, Any] = field(default_factory=dict)


Resolvedor = Callable[[Contexto], Awaitable[Resultado]]
REGISTRO: dict[str, Resolvedor] = {}


def registrar(tipo: str) -> Callable[[Resolvedor], Resolvedor]:
    def decorador(fn: Resolvedor) -> Resolvedor:
        REGISTRO[tipo] = fn
        return fn

    return decorador


def periodo_anterior(desde: date, hasta: date) -> tuple[date, date]:
    from datetime import timedelta

    dias = (hasta - desde).days + 1
    return desde - timedelta(days=dias), desde - timedelta(days=1)


def delta_porcentual(actual: Any, anterior: Any) -> float | None:
    if actual is None or anterior in (None, 0):
        return None
    return round((float(actual) - float(anterior)) / float(anterior) * 100, 2)


from api.resolvedores import (  # noqa: E402, F401 — registra los resolvedores base
    benchmark_grid,
    dimensiones,
    distribucion_geo,
    kpi_fila,
    serie_temporal,
    tabla_publicaciones,
)

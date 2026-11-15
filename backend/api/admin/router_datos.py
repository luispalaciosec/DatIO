"""Explorador de datos (self-service para el equipo): catálogo de conectores y consultas a
medida con descarga CSV. Ver api/datos/repositorio.py."""

import csv
import io
from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, model_validator

from api.admin.router import usuario_equipo
from api.datos.repositorio import RepositorioDatos
from api.deps import UsuarioActual, obtener_pool

router = APIRouter(prefix="/admin/datos", tags=["admin-datos"])


def _repo(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioDatos:
    return RepositorioDatos(pool)


Equipo = Annotated[UsuarioActual, Depends(usuario_equipo)]
Repo = Annotated[RepositorioDatos, Depends(_repo)]


class Consulta(BaseModel):
    cuentas: list[int] = Field(min_length=1, max_length=50)
    metricas: list[str] = Field(min_length=1, max_length=20)
    desde: date
    hasta: date
    granularidad: str = Field(default="dia", pattern="^(dia|semana|mes|total)$")
    dimension: str | None = None
    limite: int = Field(default=5000, ge=1, le=50000)

    @model_validator(mode="after")
    def _rango_valido(self) -> "Consulta":
        # B-9: vale para la consulta en pantalla y para el CSV
        if self.hasta < self.desde:
            raise ValueError("El rango de fechas es inválido: hasta es anterior a desde")
        return self


# S-4: una celda de texto que empieza con estos caracteres la interpreta como fórmula una hoja
# de cálculo al abrir el CSV. Se antepone un apóstrofo. Los números reales (float/int) no se
# tocan, así que los valores negativos siguen siendo números.
INICIO_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def celda_segura(valor: Any) -> Any:
    if isinstance(valor, str) and valor.startswith(INICIO_FORMULA):
        return "'" + valor
    return valor


@router.get("/catalogo")
async def catalogo(_: Equipo, repo: Repo) -> dict[str, Any]:
    return await repo.catalogo()


def pivotar(
    filas: list[dict[str, Any]], codigos: list[str], nombres: dict[int, str]
) -> tuple[list[str], list[dict[str, Any]]]:
    """Filas largas → una fila por (periodo, cuenta, valor_dimension) con una columna por
    métrica. Devuelve (columnas, filas)."""
    con_dimension = any(f["valor_dimension"] is not None for f in filas)
    columnas = ["periodo", "cuenta"] + (["dimension"] if con_dimension else []) + list(codigos)
    salida: dict[tuple[Any, ...], dict[str, Any]] = {}
    for f in filas:
        clave = (f["periodo"], f["cuenta_id"], f["valor_dimension"])
        fila = salida.setdefault(
            clave,
            {
                "periodo": f["periodo"].isoformat(),
                "cuenta": nombres.get(int(f["cuenta_id"]), str(f["cuenta_id"])),
                **({"dimension": f["valor_dimension"]} if con_dimension else {}),
                **{c: None for c in codigos},
            },
        )
        fila[str(f["metrica_codigo"])] = float(f["valor"]) if f["valor"] is not None else None
    return columnas, list(salida.values())


@router.post("/consulta")
async def consultar(cuerpo: Consulta, _: Equipo, repo: Repo) -> dict[str, Any]:
    filas = await repo.consultar(
        cuerpo.cuentas,
        cuerpo.metricas,
        cuerpo.desde,
        cuerpo.hasta,
        cuerpo.granularidad,
        cuerpo.dimension,
        cuerpo.limite,
    )
    nombres = await repo.nombres_cuentas(cuerpo.cuentas)
    columnas, tabla = pivotar(filas, cuerpo.metricas, nombres)
    return {"columnas": columnas, "filas": tabla, "truncado": len(filas) >= cuerpo.limite}


@router.post("/consulta.csv")
async def consultar_csv(cuerpo: Consulta, _: Equipo, repo: Repo) -> Response:
    filas = await repo.consultar(
        cuerpo.cuentas,
        cuerpo.metricas,
        cuerpo.desde,
        cuerpo.hasta,
        cuerpo.granularidad,
        cuerpo.dimension,
        cuerpo.limite,
    )
    nombres = await repo.nombres_cuentas(cuerpo.cuentas)
    columnas, tabla = pivotar(filas, cuerpo.metricas, nombres)
    buffer = io.StringIO()
    w = csv.writer(buffer)
    w.writerow([celda_segura(c) for c in columnas])
    for fila in tabla:
        w.writerow([celda_segura(fila.get(c)) for c in columnas])
    nombre = f"datio_{cuerpo.desde}_{cuerpo.hasta}.csv"
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )

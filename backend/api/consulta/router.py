"""POST /consulta (contrato PT-08) y GET /reportes/{slug} (estructura para el renderer)."""

from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.consulta.repositorio import Instancia, RepositorioConsulta
from api.deps import UsuarioActual, obtener_pool, usuario_actual
from api.resolvedores import REGISTRO, Contexto

router = APIRouter(tags=["consulta"])


class ConsultaBloque(BaseModel):
    instancia_id: int
    bloque_id: int
    desde: date
    hasta: date
    comparar: str | None = None  # 'periodo_anterior' | None


def _repo(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioConsulta:
    return RepositorioConsulta(pool)


def _verificar_acceso(usuario: UsuarioActual, instancia: Instancia) -> None:
    """La instancia pertenece a un cliente; el cliente_id del usuario viene del token."""
    if not usuario.es_equipo and usuario.cliente_id != instancia.cliente_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin acceso a este reporte")


@router.post("/consulta")
async def resolver_bloque(
    req: ConsultaBloque,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    repo: Annotated[RepositorioConsulta, Depends(_repo)],
) -> dict[str, Any]:
    if req.hasta < req.desde:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rango de fechas es inválido")
    instancia = await repo.instancia_por_id(req.instancia_id)
    if instancia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    _verificar_acceso(usuario, instancia)

    bloque = await repo.bloque_con_overrides(instancia.id, req.bloque_id)
    if bloque is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bloque no encontrado en este reporte")
    resolvedor = REGISTRO.get(bloque.tipo)
    if resolvedor is None:
        return {"datos": None, "estado": "consolidado", "meta": {"tipo": bloque.tipo}}

    cuentas = await repo.cuentas_de_pagina(instancia.cliente_id, bloque.plataforma)
    ctx = Contexto(repo, cuentas, bloque.config, req.desde, req.hasta, req.comparar)
    resultado = await resolvedor(ctx)
    return {
        "datos": resultado.datos,
        "estado": resultado.estado,
        "meta": {
            "tipo": bloque.tipo,
            "cuentas": len(cuentas),
            "desde": req.desde.isoformat(),
            "hasta": req.hasta.isoformat(),
            **resultado.meta,
        },
    }


@router.get("/reportes/{slug_publico}")
async def estructura_reporte(
    slug_publico: str,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    repo: Annotated[RepositorioConsulta, Depends(_repo)],
) -> dict[str, Any]:
    """Tema, páginas y bloques (con overrides) de un reporte. Sin datos: esos van por /consulta."""
    instancia = await repo.instancia_por_slug(slug_publico)
    if instancia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    _verificar_acceso(usuario, instancia)

    paginas = []
    for p in await repo.paginas(instancia.plantilla_id):
        bloques = await repo.bloques_de_pagina(instancia.id, p["id"])
        paginas.append(
            {
                **p,
                "bloques": [
                    {
                        "id": b.id,
                        "tipo": b.tipo,
                        "orden": b.orden,
                        "ancho": b.ancho,
                        "config": b.config,
                    }
                    for b in bloques
                    if not b.oculto
                ],
            }
        )
    return {
        "instancia_id": instancia.id,
        "nombre_publico": instancia.nombre_publico,
        "slug_publico": instancia.slug_publico,
        "tema": await repo.tema(instancia.cliente_id),
        "paginas": paginas,
    }

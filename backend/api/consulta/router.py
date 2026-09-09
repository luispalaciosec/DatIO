"""POST /consulta (contrato PT-08) y GET /reportes/{slug} (estructura para el renderer)."""

from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from api.consulta.cache import CacheConsulta
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


def _cache(request: Request) -> CacheConsulta | None:
    cache: CacheConsulta | None = getattr(request.app.state, "cache", None)
    return cache if cache is not None and cache.ttl_seg > 0 else None


@router.post("/consulta")
async def resolver_bloque(
    req: ConsultaBloque,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    repo: Annotated[RepositorioConsulta, Depends(_repo)],
    cache: Annotated[CacheConsulta | None, Depends(_cache)],
) -> dict[str, Any]:
    if req.hasta < req.desde:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rango de fechas es inválido")
    instancia = await repo.instancia_por_id(req.instancia_id)
    if instancia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    _verificar_acceso(usuario, instancia)

    # El acceso ya se verificó: la clave no incluye al usuario porque la respuesta es la misma
    # para todo el que puede ver este reporte.
    clave = (
        req.instancia_id,
        req.bloque_id,
        req.desde.isoformat(),
        req.hasta.isoformat(),
        req.comparar,
    )
    if cache is not None:
        if not cache.generacion_vigente():
            cache.fijar_generacion(await repo.generacion_datos())
        en_cache = cache.obtener(clave)
        if en_cache is not None:
            return {**en_cache, "meta": {**en_cache["meta"], "cache": True}}

    bloque = await repo.bloque_con_overrides(instancia.id, req.bloque_id)
    if bloque is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bloque no encontrado en este reporte")
    resolvedor = REGISTRO.get(bloque.tipo)
    if resolvedor is None:
        return {"datos": None, "estado": "consolidado", "meta": {"tipo": bloque.tipo}}

    cuentas = await repo.cuentas_de_pagina(instancia.cliente_id, bloque.plataforma)
    config_bloque = {**bloque.config}
    config_bloque.setdefault("plataforma", bloque.plataforma)
    ctx = Contexto(
        repo, cuentas, instancia.cliente_id, config_bloque, req.desde, req.hasta, req.comparar
    )
    resultado = await resolvedor(ctx)
    respuesta = {
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
    if cache is not None:
        cache.guardar(clave, respuesta)
    return respuesta


@router.get("/radar/imagen/{competidor_id}/{clave}")
async def imagen_competidor(
    competidor_id: int,
    clave: str,
    repo: Annotated[RepositorioConsulta, Depends(_repo)],
) -> Response:
    """Imagen pública de un competidor (foto de perfil o miniatura de publicación) copiada por el
    radar. Sin autenticación: son imágenes públicas de Instagram y las carga un <img>."""
    imagen = await repo.imagen_competidor(competidor_id, clave)
    if imagen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada")
    return Response(
        content=imagen[1],
        media_type=imagen[0],
        headers={"Cache-Control": "public, max-age=86400"},
    )


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
        cuentas = await repo.cuentas_de_pagina(instancia.cliente_id, p["plataforma"])
        paginas.append(
            {
                **p,
                "cuentas": len(cuentas),
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

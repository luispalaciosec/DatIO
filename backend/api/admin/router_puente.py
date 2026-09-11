"""Endpoints del puente CRM (PT-16): configuración por cliente, prueba de conexión, empresas
del CRM para elegir, evaluación (simulada o real) y bitácora de disparos."""

from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.admin.router import usuario_equipo
from api.config import Configuracion
from api.deps import UsuarioActual, obtener_config_app, obtener_pool
from api.etl.conector_base import hoy_en
from api.puente.crm import CrmError, CrmHubspot, CrmPrometio, adaptador
from api.puente.disparadores import correr_puente, evaluar_cliente
from api.puente.repositorio import RepositorioPuente

router = APIRouter(prefix="/admin", tags=["admin-puente"])


def _repo(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioPuente:
    return RepositorioPuente(pool)


Equipo = Annotated[UsuarioActual, Depends(usuario_equipo)]
Repo = Annotated[RepositorioPuente, Depends(_repo)]
Config = Annotated[Configuracion, Depends(obtener_config_app)]


class CrmCambios(BaseModel):
    proveedor: str | None = Field(default=None, pattern="^(prometio|hubspot)$")
    empresa_ref: str | None = None
    contacto_ref: str | None = None
    config: dict[str, Any] | None = None
    credencial: str | None = None  # token de app privada de HubSpot; se cifra y no vuelve


async def _cliente(repo: RepositorioPuente, cliente_id: int) -> dict[str, Any]:
    filas = await repo.clientes_con_crm(cliente_id)
    if not filas:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Cliente sin CRM configurado (proveedor y empresa)"
        )
    return filas[0]


async def _crm(repo: RepositorioPuente, config: Configuracion, cliente: dict[str, Any]) -> Any:
    cred = (
        await repo.credencial_crm(int(cliente["id"]), config.clave_cifrado)
        if config.clave_cifrado
        else None
    )
    crm = adaptador(config, cliente["crm_proveedor"], cred, cliente["crm_config"])
    if crm is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "CRM sin credencial: guarda el token antes de probar"
        )
    return crm


@router.put("/clientes/{cliente_id}/crm")
async def guardar_crm(
    cliente_id: int, cuerpo: CrmCambios, _: Equipo, repo: Repo, config: Config
) -> dict[str, Any]:
    if cuerpo.credencial and not config.clave_cifrado:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Falta CLAVE_CIFRADO")
    await repo.guardar_crm(
        cliente_id,
        cuerpo.proveedor,
        cuerpo.empresa_ref,
        cuerpo.contacto_ref,
        cuerpo.config,
        cuerpo.credencial,
        config.clave_cifrado,
    )
    return {"estado": "guardado"}


@router.post("/clientes/{cliente_id}/crm/probar")
async def probar_crm(cliente_id: int, _: Equipo, repo: Repo, config: Config) -> dict[str, Any]:
    """Prueba la conexión con el CRM del cliente. Para PrometIO basta el proveedor."""
    filas = await repo.clientes_con_crm(cliente_id)
    proveedor = filas[0]["crm_proveedor"] if filas else None
    try:
        if proveedor == "prometio" or (not filas and CrmPrometio(config).configurado()):
            return await CrmPrometio(config).probar()
        if not filas:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Configura el CRM primero")
        crm = await _crm(repo, config, filas[0])
        return dict(await crm.probar())
    except CrmError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e


@router.get("/crm/{proveedor}/empresas")
async def empresas_crm(
    proveedor: str, _: Equipo, repo: Repo, config: Config, cliente_id: int | None = None
) -> list[dict[str, Any]]:
    """Empresas (y contactos) del CRM para elegir la referencia del cliente."""
    try:
        if proveedor == "prometio":
            return await CrmPrometio(config).empresas()
        if proveedor == "hubspot" and cliente_id is not None:
            cred = (
                await repo.credencial_crm(cliente_id, config.clave_cifrado)
                if config.clave_cifrado
                else None
            )
            if not cred:
                raise HTTPException(status.HTTP_409_CONFLICT, "Guarda el token de HubSpot primero")
            return await CrmHubspot(cred).empresas()
    except CrmError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from e
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Proveedor desconocido")


@router.post("/clientes/{cliente_id}/crm/evaluar")
async def evaluar_crm(
    cliente_id: int, _: Equipo, repo: Repo, config: Config, ejecutar: bool = False
) -> dict[str, Any]:
    """Qué disparadores aplican hoy para el cliente. Con ejecutar=true crea las acciones en el
    CRM (respetando la ventana anti-duplicado de 30 días)."""
    cliente = await _cliente(repo, cliente_id)
    hoy = hoy_en(config.zona_horaria)
    if ejecutar:
        resumen = await correr_puente(repo, config, hoy, cliente_id=cliente_id)
    else:
        resumen = await correr_puente(repo, config, hoy, cliente_id=cliente_id, simular=True)
    candidatos = await evaluar_cliente(repo, cliente, hoy)
    return {
        "cliente": cliente["nombre"],
        "crm": cliente["crm_proveedor"],
        "candidatos": [
            {
                "codigo": d.accion.codigo,
                "tipo": d.accion.tipo,
                "titulo": d.accion.titulo,
                "evidencia": d.accion.evidencia,
                "valor": d.accion.valor,
                "prioridad": d.accion.prioridad,
            }
            for d in candidatos
        ],
        "disparados": [
            {
                "codigo": d.accion.codigo,
                "titulo": d.accion.titulo,
                "objeto_ref": d.objeto_ref,
                "error": d.error,
                "url": d.contexto.get("url"),
            }
            for d in resumen.disparos
        ],
        "ejecutado": ejecutar,
        "omitidos": resumen.omitidos,
    }


@router.get("/puente/disparos")
async def disparos(
    _: Equipo, repo: Repo, limite: int = 100, cliente_id: int | None = None
) -> list[dict[str, Any]]:
    return await repo.disparos(limite, cliente_id)

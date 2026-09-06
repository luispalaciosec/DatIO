"""Endpoints de los botones "Conectar con ...". Ver api/admin/conectar.py."""

from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from api.admin import conectar
from api.admin.repositorio import RepositorioAdmin
from api.admin.router import usuario_equipo
from api.config import Configuracion
from api.deps import UsuarioActual, obtener_config_app, obtener_pool

router = APIRouter(prefix="/admin", tags=["admin-conectar"])


def _repo(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioAdmin:
    return RepositorioAdmin(pool)


Equipo = Annotated[UsuarioActual, Depends(usuario_equipo)]
Repo = Annotated[RepositorioAdmin, Depends(_repo)]
Config = Annotated[Configuracion, Depends(obtener_config_app)]


def _validar_proveedor(proveedor: str) -> None:
    if proveedor not in conectar.PROVEEDORES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proveedor desconocido")


@router.get("/conectar/{proveedor}/iniciar")
async def iniciar(
    proveedor: str, cliente_id: int, usuario: Equipo, repo: Repo, config: Config
) -> dict[str, str]:
    _validar_proveedor(proveedor)
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    try:
        estado = conectar.emitir_estado(config, proveedor, cliente_id, usuario.email)
        return {"url": conectar.url_inicio(config, proveedor, estado)}
    except conectar.ConexionError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e


@router.get("/conectar/{proveedor}/retorno", include_in_schema=False)
async def retorno(
    proveedor: str,
    repo: Repo,
    config: Config,
    state: str = Query(default=""),
    code: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
) -> RedirectResponse:
    """Llega el navegador desde el proveedor. Sin token de usuario: el `state` es la prueba."""
    _validar_proveedor(proveedor)
    front = config.frontend_url.rstrip("/")
    try:
        cliente_id, email = conectar.verificar_estado(config, state, proveedor)
    except conectar.ConexionError as e:
        return RedirectResponse(f"{front}/admin?error={_url(str(e))}")
    if error or not code:
        detalle = error_description or error or "sin código de autorización"
        return RedirectResponse(f"{front}/admin/clientes/{cliente_id}?error={_url(detalle)}")
    try:
        token = await conectar.intercambiar_codigo(config, proveedor, code)
        activos = await conectar.listar_activos(config, proveedor, token)
        credencial = conectar.credencial_para_guardar(proveedor, token)
    except conectar.ConexionError as e:
        return RedirectResponse(f"{front}/admin/clientes/{cliente_id}?error={_url(str(e))}")
    if not config.clave_cifrado:
        return RedirectResponse(f"{front}/admin/clientes/{cliente_id}?error=CLAVE_CIFRADO")
    conexion_id = await repo.crear_conexion(
        cliente_id,
        proveedor,
        email,
        credencial,
        config.clave_cifrado,
        conectar.expiracion(proveedor, token),
        [a.como_dict() for a in activos],
    )
    return RedirectResponse(f"{front}/admin/clientes/{cliente_id}?conexion={conexion_id}")


@router.get("/conexiones/{conexion_id}")
async def ver_conexion(conexion_id: int, _: Equipo, repo: Repo) -> dict[str, Any]:
    c = await repo.conexion(conexion_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión no encontrada")
    return c


class Activar(BaseModel):
    activos: list[dict[str, Any]]  # subconjunto de lo listado: plataforma, id_externo, nombre


@router.post("/conexiones/{conexion_id}/activar")
async def activar(
    conexion_id: int, cuerpo: Activar, _: Equipo, repo: Repo, config: Config
) -> dict[str, Any]:
    c = await repo.conexion(conexion_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conexión no encontrada")
    permitidos = {(a["plataforma"], a["id_externo"]): a for a in c["activos"]}
    elegidos = []
    for a in cuerpo.activos:
        base = permitidos.get((a.get("plataforma"), a.get("id_externo")))
        if base is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Activo no ofrecido por esta conexión")
        elegidos.append(base)
    if not elegidos:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige al menos un activo")
    try:
        ids = await repo.activar_conexion(conexion_id, elegidos, config.clave_cifrado)
    except LookupError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return {"cuentas": ids}


def _url(texto: str) -> str:
    from urllib.parse import quote

    return quote(texto[:200])

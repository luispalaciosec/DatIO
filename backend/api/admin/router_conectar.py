"""Endpoints de los botones "Conectar con ...". Ver api/admin/conectar.py."""

from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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


def _config_con_api_url(config: Configuracion, request: Request) -> Configuracion:
    """Seguro: si API_URL quedó en localhost pero la petición llega por un dominio real
    (Railway detrás de proxy), usa ese dominio con https."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    if "localhost" in config.api_url and host and "localhost" not in host:
        return config.model_copy(update={"api_url": f"https://{host}"})
    return config


@router.get("/conectar/{proveedor}/iniciar")
async def iniciar(
    proveedor: str, cliente_id: int, usuario: Equipo, repo: Repo, config: Config, request: Request
) -> dict[str, str]:
    _validar_proveedor(proveedor)
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    config = _config_con_api_url(config, request)
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
    request: Request,
    state: str = Query(default=""),
    code: str = Query(default=""),
    error: str = Query(default=""),
    error_description: str = Query(default=""),
) -> RedirectResponse:
    """Llega el navegador desde el proveedor. Sin token de usuario: el `state` es la prueba."""
    _validar_proveedor(proveedor)
    config = _config_con_api_url(config, request)  # el redirect_uri del canje debe coincidir
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


@router.post("/conectar/meta/business")
async def importar_business_manager(
    cliente_id: int, usuario: Equipo, repo: Repo, config: Config
) -> dict[str, Any]:
    """Atajo sin diálogo OAuth: lista lo que administra el Business Manager de la agencia con el
    token del System User y lo ofrece en el mismo selector. Las cuentas quedan con ese token."""
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    if not (config.meta_system_user_token and config.meta_business_id and config.clave_cifrado):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Faltan META_SYSTEM_USER_TOKEN, META_BUSINESS_ID o CLAVE_CIFRADO",
        )
    activos = await conectar.activos_business_manager(
        config, config.meta_system_user_token, config.meta_business_id
    )
    conexion_id = await repo.crear_conexion(
        cliente_id,
        "meta",
        usuario.email,
        config.meta_system_user_token,
        config.clave_cifrado,
        None,
        [a.como_dict() for a in activos],
    )
    return {"conexion_id": conexion_id, "activos": len(activos)}


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
        if base is None or base["plataforma"] == conectar.AVISO:
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

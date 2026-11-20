"""Endpoints del administrador. Todos exigen rol equipo (403 para clientes)."""

import logging
import re
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from api.admin.repositorio import RepositorioAdmin, UsuarioDeOtroClienteError
from api.alertas.repositorio import RepositorioAlertas
from api.auth.admin_supabase import asegurar_usuario_auth
from api.config import Configuracion
from api.deps import (
    UsuarioActual,
    obtener_config_app,
    obtener_pool,
    usuario_actual,
    vaciar_cache_tras_escritura,
)

log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    # B-7: las ediciones se ven en /consulta en la petición siguiente
    dependencies=[Depends(vaciar_cache_tras_escritura)],
)
RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def usuario_equipo(usuario: Annotated[UsuarioActual, Depends(usuario_actual)]) -> UsuarioActual:
    if not usuario.es_equipo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el equipo puede administrar")
    return usuario


def _repo(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioAdmin:
    return RepositorioAdmin(pool)


Equipo = Annotated[UsuarioActual, Depends(usuario_equipo)]
Repo = Annotated[RepositorioAdmin, Depends(_repo)]


# ---- clientes ---------------------------------------------------------------


# #14: validación de entradas del admin --------------------------------------------------

# Logo/banner: una URL https o una ruta relativa a archivos del propio frontend (p. ej.
# /clientes/logo.png). Vacío borra la imagen.
PATRON_IMAGEN = r"^$|^https://[^\s\"'<>]{1,500}$|^/[A-Za-z0-9._/-]{1,200}$"
# Nombre de una fuente de Google Fonts o del sistema: letras, números, espacios y guiones.
PATRON_FUENTE = r"^[A-Za-z0-9 -]{1,60}$"


class ClienteNuevo(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=60)  # formato: RE_SLUG en crear_cliente
    sector: str | None = Field(default=None, max_length=60)
    plantilla_id: int | None = None


class ClienteCambios(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    sector: str | None = Field(default=None, max_length=60)
    activo: bool | None = None


@router.get("/clientes")
async def listar_clientes(_: Equipo, repo: Repo) -> list[dict[str, Any]]:
    return await repo.clientes()


@router.post("/clientes", status_code=status.HTTP_201_CREATED)
async def crear_cliente(cuerpo: ClienteNuevo, _: Equipo, repo: Repo) -> dict[str, Any]:
    if not RE_SLUG.match(cuerpo.slug):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Slug inválido: usa minúsculas, números y guiones"
        )
    try:
        cliente_id = await repo.crear_cliente(
            cuerpo.nombre, cuerpo.slug, cuerpo.sector, cuerpo.plantilla_id
        )
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un cliente con ese slug") from e
    return {"id": cliente_id, "slug": cuerpo.slug}


@router.get("/clientes/{cliente_id}")
async def ver_cliente(cliente_id: int, _: Equipo, repo: Repo) -> dict[str, Any]:
    cliente = await repo.cliente(cliente_id)
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    return {
        **cliente,
        "tema": await repo.tema(cliente_id),
        "cuentas": await repo.cuentas(cliente_id),
        "usuarios": await repo.usuarios(cliente_id),
        "competidores": await repo.competidores(cliente_id),
    }


@router.patch("/clientes/{cliente_id}")
async def editar_cliente(
    cliente_id: int, cuerpo: ClienteCambios, _: Equipo, repo: Repo
) -> dict[str, Any]:
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    await repo.actualizar_cliente(cliente_id, cuerpo.model_dump(exclude_none=True))
    return await repo.cliente(cliente_id) or {}


class EliminarCliente(BaseModel):
    confirmar: str = Field(min_length=1, max_length=60)  # el slug del cliente, escrito a mano


@router.delete("/clientes/{cliente_id}")
async def eliminar_cliente(
    cliente_id: int, cuerpo: EliminarCliente, usuario: Equipo, repo: Repo
) -> dict[str, Any]:
    """Elimina el cliente y todos sus datos. Irreversible: exige escribir el slug."""
    cliente = await repo.cliente(cliente_id)
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    if cuerpo.confirmar.strip() != cliente["slug"]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Para eliminar, escribe exactamente el slug del cliente"
        )
    borradas = await repo.eliminar_cliente(cliente_id)
    log.warning(
        "cliente eliminado: id=%s slug=%s por=%s filas=%s",
        cliente_id,
        cliente["slug"],
        usuario.email,
        borradas,
    )
    return {"eliminado": cliente["slug"], "filas": borradas}


# ---- tema -------------------------------------------------------------------


class TemaCambios(BaseModel):
    logo_url: str | None = Field(default=None, pattern=PATRON_IMAGEN)
    banner_url: str | None = Field(default=None, pattern=PATRON_IMAGEN)
    color_primario: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_secundario: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    color_acento: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    fuente_titulos: str | None = Field(default=None, pattern=PATRON_FUENTE)
    fuente_cuerpo: str | None = Field(default=None, pattern=PATRON_FUENTE)
    modo_oscuro: bool | None = None


@router.put("/clientes/{cliente_id}/tema")
async def guardar_tema(
    cliente_id: int, cuerpo: TemaCambios, _: Equipo, repo: Repo
) -> dict[str, Any]:
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    return await repo.guardar_tema(cliente_id, cuerpo.model_dump(exclude_unset=True))


# ---- cuentas ----------------------------------------------------------------


class CuentaNueva(BaseModel):
    # Además se valida contra la tabla plataformas en crear_cuenta
    plataforma: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9_]+$")
    id_externo: str = Field(min_length=1, max_length=300)
    nombre_cuenta: str | None = Field(default=None, max_length=200)
    # token o JSON de credenciales; se cifra en el servidor y no se devuelve nunca
    credencial: str | None = Field(default=None, max_length=20_000)


class CuentaCambios(BaseModel):
    nombre_cuenta: str | None = Field(default=None, max_length=200)
    activo: bool | None = None
    credencial: str | None = None


@router.post("/clientes/{cliente_id}/cuentas", status_code=status.HTTP_201_CREATED)
async def crear_cuenta(
    cliente_id: int,
    cuerpo: CuentaNueva,
    _: Equipo,
    repo: Repo,
    config: Annotated[Configuracion, Depends(obtener_config_app)],
) -> dict[str, Any]:
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    if cuerpo.plataforma not in {p["codigo"] for p in await repo.plataformas()}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Plataforma desconocida")
    try:
        cuenta_id = await repo.crear_cuenta(
            cliente_id, cuerpo.plataforma, cuerpo.id_externo.strip(), cuerpo.nombre_cuenta
        )
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esa cuenta ya está conectada a un cliente"
        ) from e
    if cuerpo.credencial:
        if not config.clave_cifrado:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CLAVE_CIFRADO no configurada")
        await repo.guardar_credencial(cuenta_id, cuerpo.credencial, config.clave_cifrado)
    return {"id": cuenta_id}


@router.patch("/cuentas/{cuenta_id}")
async def editar_cuenta(
    cuenta_id: int,
    cuerpo: CuentaCambios,
    _: Equipo,
    repo: Repo,
    config: Annotated[Configuracion, Depends(obtener_config_app)],
) -> dict[str, str]:
    if await repo.cuenta_cliente(cuenta_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuenta no encontrada")
    await repo.actualizar_cuenta(
        cuenta_id, cuerpo.model_dump(exclude_none=True, exclude={"credencial"})
    )
    if cuerpo.credencial:
        if not config.clave_cifrado:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "CLAVE_CIFRADO no configurada")
        await repo.guardar_credencial(cuenta_id, cuerpo.credencial, config.clave_cifrado)
    return {"estado": "ok"}


# ---- usuarios ---------------------------------------------------------------


class UsuarioNuevo(BaseModel):
    email: EmailStr
    rol: str = Field(pattern="^(cliente|equipo)$")
    cliente_id: int | None = None


@router.get("/usuarios")
async def listar_usuarios(_: Equipo, repo: Repo) -> list[dict[str, Any]]:
    return await repo.usuarios()


@router.post("/usuarios", status_code=status.HTTP_201_CREATED)
async def guardar_usuario(
    cuerpo: UsuarioNuevo,
    _: Equipo,
    repo: Repo,
    config: Annotated[Configuracion, Depends(obtener_config_app)],
) -> dict[str, str]:
    if cuerpo.rol == "cliente" and cuerpo.cliente_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un usuario cliente necesita cliente_id")
    if cuerpo.rol == "equipo" and cuerpo.cliente_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Un usuario de equipo no lleva cliente_id")
    if cuerpo.cliente_id is not None and await repo.cliente(cuerpo.cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    try:
        await repo.guardar_usuario(cuerpo.email.lower(), cuerpo.rol, cuerpo.cliente_id)
    except UsuarioDeOtroClienteError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ese correo ya pertenece a otro cliente o al equipo"
        ) from e
    # #12: también en Supabase Auth, para que pueda entrar con enlace mágico
    auth = await asegurar_usuario_auth(config, cuerpo.email.lower())
    return {"email": cuerpo.email.lower(), "auth": auth}


@router.delete("/usuarios/{email}")
async def desactivar_usuario(email: str, usuario: Equipo, repo: Repo) -> dict[str, str]:
    if email.lower() == usuario.email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No puedes desactivarte a ti mismo")
    await repo.desactivar_usuario(email.lower())
    return {"estado": "ok"}


# ---- competidores (PT-15) ---------------------------------------------------


class CompetidorNuevo(BaseModel):
    plataforma: str = Field(pattern="^(meta_ig|meta_fb|tiktok|linkedin|youtube)$")
    nombre: str = Field(min_length=2, max_length=120)
    handle: str = Field(min_length=1, max_length=200)
    logo_url: str | None = Field(default=None, pattern=PATRON_IMAGEN)
    orden: int = Field(default=0, ge=0, le=1000)


class CompetidorCambios(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    handle: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = Field(default=None, pattern=PATRON_IMAGEN)
    orden: int | None = Field(default=None, ge=0, le=1000)


def _normalizar_handle(plataforma: str, handle: str) -> str:
    h = handle.strip()
    if plataforma in ("meta_ig", "tiktok"):
        h = h.lstrip("@")
        for prefijo in (
            "https://www.instagram.com/",
            "https://instagram.com/",
            "https://www.tiktok.com/@",
            "https://tiktok.com/@",
        ):
            if h.startswith(prefijo):
                h = h[len(prefijo) :]
        h = h.strip("/").split("/")[0].split("?")[0]
    if plataforma == "meta_fb":
        for prefijo in ("https://www.facebook.com/", "https://facebook.com/"):
            if h.startswith(prefijo):
                h = h[len(prefijo) :]
        h = h.strip("/").split("?")[0]
    return h


@router.get("/clientes/{cliente_id}/competidores")
async def listar_competidores(cliente_id: int, _: Equipo, repo: Repo) -> list[dict[str, Any]]:
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    return await repo.competidores(cliente_id)


@router.post("/clientes/{cliente_id}/competidores", status_code=status.HTTP_201_CREATED)
async def crear_competidor(
    cliente_id: int, cuerpo: CompetidorNuevo, _: Equipo, repo: Repo
) -> dict[str, Any]:
    if await repo.cliente(cliente_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    handle = _normalizar_handle(cuerpo.plataforma, cuerpo.handle)
    try:
        cid = await repo.crear_competidor(
            cliente_id,
            cuerpo.plataforma,
            cuerpo.nombre.strip(),
            handle,
            cuerpo.logo_url,
            cuerpo.orden,
        )
    except asyncpg.UniqueViolationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese competidor ya está en esta red") from e
    return {"id": cid, "handle": handle}


@router.patch("/competidores/{competidor_id}")
async def editar_competidor(
    competidor_id: int, cuerpo: CompetidorCambios, _: Equipo, repo: Repo
) -> dict[str, str]:
    await repo.actualizar_competidor(competidor_id, cuerpo.model_dump(exclude_none=True))
    return {"estado": "ok"}


@router.delete("/competidores/{competidor_id}")
async def borrar_competidor(competidor_id: int, _: Equipo, repo: Repo) -> dict[str, str]:
    if await repo.borrar_competidor(competidor_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Competidor no encontrado")
    return {"estado": "ok"}


# ---- catálogos y capturas ----------------------------------------------------


# ---- alertas (PT-14) ----------------------------------------------------------------


@router.get("/alertas")
async def listar_alertas(
    _: Equipo, pool: Annotated[asyncpg.Pool, Depends(obtener_pool)], abiertas: bool = True
) -> list[dict[str, Any]]:
    return await RepositorioAlertas(pool).listar(solo_abiertas=abiertas)


class AlertaCambios(BaseModel):
    resuelta: bool = True


@router.patch("/alertas/{alerta_id}")
async def resolver_alerta(
    alerta_id: int,
    cuerpo: AlertaCambios,
    _: Equipo,
    pool: Annotated[asyncpg.Pool, Depends(obtener_pool)],
) -> dict[str, str]:
    if not await RepositorioAlertas(pool).resolver(alerta_id, cuerpo.resuelta):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    return {"estado": "resuelta" if cuerpo.resuelta else "abierta"}


@router.get("/catalogos")
async def catalogos(_: Equipo, repo: Repo) -> dict[str, Any]:
    return {
        "plataformas": await repo.plataformas(),
        "plantillas": await repo.plantillas(),
        "sectores": ["banca", "retail", "salud", "educacion", "agencia", "veterinaria", "otro"],
    }


@router.get("/capturas")
async def capturas(_: Equipo, repo: Repo, limite: int = 50) -> list[dict[str, Any]]:
    return await repo.jobs_recientes(min(limite, 200))

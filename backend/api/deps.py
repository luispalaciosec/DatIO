"""Dependencias de FastAPI (PT-07). cliente_id se deriva SIEMPRE del token."""

import logging
from dataclasses import dataclass
from typing import Annotated

import asyncpg
from fastapi import Depends, Header, HTTPException, Request, status

from api.auth.repositorio import RepositorioAuth
from api.auth.supabase import TokenInvalidoError, verificar_token
from api.config import Configuracion
from api.consulta.repositorio import Instancia, RepositorioConsulta
from api.pdf.render import RenderInvalidoError, verificar_token_render

log = logging.getLogger(__name__)


def obtener_config_app(request: Request) -> Configuracion:
    config: Configuracion = request.app.state.config
    return config


def obtener_pool(request: Request) -> asyncpg.Pool:
    pool: asyncpg.Pool = request.app.state.pool
    return pool


def obtener_repo_auth(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioAuth:
    return RepositorioAuth(pool)


@dataclass(frozen=True)
class UsuarioActual:
    email: str
    rol: str  # 'cliente' | 'equipo'
    cliente_id: int | None

    @property
    def es_equipo(self) -> bool:
        return self.rol == "equipo"


async def usuario_actual(
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
    authorization: Annotated[str | None, Header()] = None,
) -> UsuarioActual:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token de acceso")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verificar_token(token, config)
    except TokenInvalidoError as e:
        # Token de render (PT-11): lo emitió la propia API para Playwright, dura 5 minutos.
        if config.pdf_secret:
            try:
                principal = verificar_token_render(token, config)
                return UsuarioActual(
                    email="render@datio", rol="cliente", cliente_id=principal.cliente_id
                )
            except RenderInvalidoError:
                pass
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    email = str(claims.get("email") or "").lower()
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El token no contiene email")

    usuario = await repo.usuario_por_email(email)
    if usuario is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario no autorizado en la plataforma")
    return UsuarioActual(email=usuario.email, rol=usuario.rol, cliente_id=usuario.cliente_id)


async def cliente_id_actual(
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
) -> int:
    """cliente_id inyectado en el servidor. Solo válido para usuarios de rol cliente."""
    if usuario.cliente_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El usuario de equipo debe indicar el cliente por slug en la ruta",
        )
    return usuario.cliente_id


async def cliente_autorizado(
    slug: str,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
) -> int:
    """Resuelve el cliente de la ruta y verifica que el usuario pueda verlo (403 si no)."""
    cliente = await repo.cliente_por_slug(slug)
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    if not usuario.es_equipo and usuario.cliente_id != cliente.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin acceso a este cliente")
    return cliente.id


# ---- acceso a un reporte (S-1): UNA regla para /reportes/{slug}, /consulta y el PDF -------


def autorizar_instancia(
    usuario: UsuarioActual, instancia: Instancia | None, pedida: str
) -> Instancia:
    """404 si el reporte no existe; 403 si es de otro cliente o si su cliente está desactivado
    (Términos §9: al desactivar se revocan los accesos). Cada 403 queda en el log, sin token."""
    if instancia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte no encontrado")
    ajeno = not usuario.es_equipo and usuario.cliente_id != instancia.cliente_id
    if ajeno or not instancia.cliente_activo:
        log.warning(
            "acceso denegado a reporte: usuario=%s rol=%s instancia=%s motivo=%s",
            usuario.email,
            usuario.rol,
            pedida,
            "cliente_inactivo" if not instancia.cliente_activo else "otro_cliente",
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin acceso a este reporte")
    return instancia


async def instancia_autorizada(
    slug_publico: str,
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    pool: Annotated[asyncpg.Pool, Depends(obtener_pool)],
) -> Instancia:
    """Instancia de la ruta /reportes/{slug_publico}..., ya autorizada para el usuario."""
    instancia = await RepositorioConsulta(pool).instancia_por_slug(slug_publico)
    return autorizar_instancia(usuario, instancia, f"slug:{slug_publico}")


async def instancia_autorizada_por_id(
    instancia_id: int, usuario: UsuarioActual, pool: asyncpg.Pool
) -> Instancia:
    """Igual que instancia_autorizada, para POST /consulta (el id viene en el cuerpo)."""
    instancia = await RepositorioConsulta(pool).instancia_por_id(instancia_id)
    return autorizar_instancia(usuario, instancia, f"id:{instancia_id}")

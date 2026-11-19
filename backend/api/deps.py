"""Dependencias de FastAPI (PT-07). cliente_id se deriva SIEMPRE del token."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any

import asyncpg
from fastapi import Depends, Header, HTTPException, Request, status

from api.auth.repositorio import RepositorioAuth
from api.auth.supabase import TokenInvalidoError, correo_verificado, verificar_token
from api.config import Configuracion
from api.consulta.repositorio import Instancia, RepositorioConsulta
from api.pdf.render import RenderInvalidoError, verificar_token_render
from api.seguridad import LimiteVentana

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
    es_render: bool = False  # token de render de Playwright (PT-11), no una persona
    instancia_render: int | None = None  # la única instancia que ese token puede leer

    @property
    def es_equipo(self) -> bool:
        return self.rol == "equipo"


def _token_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token de acceso")
    return authorization.split(" ", 1)[1].strip()


async def _usuario_de_supabase(
    token: str, config: Configuracion, repo: RepositorioAuth
) -> UsuarioActual:
    try:
        claims = verificar_token(token, config)
    except TokenInvalidoError as e:
        # B-11: al cliente, mensaje genérico; el motivo concreto solo al log.
        log.info("token rechazado: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o vencido") from e

    email = str(claims.get("email") or "").lower()
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El token no contiene email")
    # S-2: toda la autorización (incluido el rol 'equipo') depende del correo: tiene que estar
    # verificado por Supabase.
    if not correo_verificado(claims):
        log.warning("token con correo no verificado rechazado: %s", email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "El correo no está verificado")

    usuario = await repo.usuario_por_email(email)
    if usuario is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario no autorizado en la plataforma")
    return UsuarioActual(email=usuario.email, rol=usuario.rol, cliente_id=usuario.cliente_id)


async def usuario_actual(
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
    authorization: Annotated[str | None, Header()] = None,
) -> UsuarioActual:
    """Usuario de Supabase. El token de render NO vale aquí (S-5): solo lo aceptan las rutas
    de la vista de impresión, vía usuario_o_render."""
    return await _usuario_de_supabase(_token_bearer(authorization), config, repo)


async def usuario_o_render(
    config: Annotated[Configuracion, Depends(obtener_config_app)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
    authorization: Annotated[str | None, Header()] = None,
) -> UsuarioActual:
    """Para GET /reportes/{slug} y POST /consulta: además de un usuario de Supabase acepta el
    token de render (PT-11) que la API emite para Playwright. Ese principal queda atado a SU
    instancia: autorizar_instancia rechaza cualquier otra (S-5)."""
    token = _token_bearer(authorization)
    if config.pdf_secret:
        try:
            principal = verificar_token_render(token, config)
        except RenderInvalidoError:
            pass
        else:
            return UsuarioActual(
                email="render@datio",
                rol="cliente",
                cliente_id=principal.cliente_id,
                es_render=True,
                instancia_render=principal.instancia_id,
            )
    return await _usuario_de_supabase(token, config, repo)


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
    # S-5: el token de render solo abre la instancia para la que se emitió
    ajeno = ajeno or (usuario.es_render and usuario.instancia_render != instancia.id)
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


async def instancia_autorizada_impresion(
    slug_publico: str,
    usuario: Annotated[UsuarioActual, Depends(usuario_o_render)],
    pool: Annotated[asyncpg.Pool, Depends(obtener_pool)],
) -> Instancia:
    """Como instancia_autorizada, pero acepta también el token de render (vista de impresión)."""
    instancia = await RepositorioConsulta(pool).instancia_por_slug(slug_publico)
    return autorizar_instancia(usuario, instancia, f"slug:{slug_publico}")


async def instancia_autorizada_por_id(
    instancia_id: int, usuario: UsuarioActual, pool: asyncpg.Pool
) -> Instancia:
    """Igual que instancia_autorizada, para POST /consulta (el id viene en el cuerpo)."""
    instancia = await RepositorioConsulta(pool).instancia_por_id(instancia_id)
    return autorizar_instancia(usuario, instancia, f"id:{instancia_id}")


async def vaciar_cache_tras_escritura(request: Request) -> AsyncIterator[None]:
    """Dependencia de los routers del admin: tras cualquier escritura (no GET) vacía la cache
    de /consulta de este proceso para que la edición se vea en la petición siguiente (B-7).
    Los demás procesos la ven por config_version (sql/015) en <= 60 s."""
    yield
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        cache = getattr(request.app.state, "cache", None)
        if cache is not None:
            cache.vaciar()


# ---- límites por usuario para acciones caras (#11) -------------------------------------


def limite_por_usuario(nombre: str, maximo: int, segundos: float = 60.0) -> Any:
    """Dependencia: como mucho `maximo` peticiones de la acción `nombre` por usuario en la
    ventana. En memoria y por proceso, como el límite por IP de api/seguridad.py."""
    ventana = LimiteVentana(maximo, segundos)

    async def _limitar(usuario: Annotated[UsuarioActual, Depends(usuario_actual)]) -> None:
        if not ventana.permitir(usuario.email):
            log.warning("límite de %s alcanzado por %s", nombre, usuario.email)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Demasiadas solicitudes seguidas, intenta en un minuto",
                headers={"Retry-After": str(int(segundos))},
            )

    return Depends(_limitar)

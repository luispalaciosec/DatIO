"""Rutas autenticadas (PT-07)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from api.auth.repositorio import RepositorioAuth
from api.deps import (
    UsuarioActual,
    cliente_autorizado,
    cliente_id_actual,
    obtener_repo_auth,
    usuario_actual,
)

router = APIRouter(tags=["auth"])


@router.get("/yo")
async def yo(
    usuario: Annotated[UsuarioActual, Depends(usuario_actual)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
) -> dict[str, Any]:
    cliente = await repo.cliente_por_id(usuario.cliente_id) if usuario.cliente_id else None
    return {
        "email": usuario.email,
        "rol": usuario.rol,
        "cliente_id": usuario.cliente_id,
        "slug": cliente.slug if cliente else None,
    }


@router.get("/mi/cuentas")
async def mis_cuentas(
    cliente_id: Annotated[int, Depends(cliente_id_actual)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
) -> list[dict[str, Any]]:
    """Cuentas del cliente del token. El cliente_id nunca viene del request."""
    return [c.__dict__ for c in await repo.cuentas_de_cliente(cliente_id)]


@router.get("/clientes/{slug}/cuentas")
async def cuentas_de_cliente(
    cliente_id: Annotated[int, Depends(cliente_autorizado)],
    repo: Annotated[RepositorioAuth, Depends(obtener_repo_auth)],
) -> list[dict[str, Any]]:
    """Para el equipo: cualquier cliente. Para un cliente: solo el suyo (403 si no)."""
    return [c.__dict__ for c in await repo.cuentas_de_cliente(cliente_id)]

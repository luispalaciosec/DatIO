"""Admin: invitar usuarios del cliente, editar su reporte (ocultar bloques y páginas, textos,
objetivos) y enviar el reporte mensual a demanda."""

from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from api.admin.router import usuario_equipo
from api.config import Configuracion
from api.deps import UsuarioActual, obtener_config_app, obtener_pool
from api.etl.conector_base import hoy_en
from api.reportes.correo import enviar, html_invitacion
from api.reportes.envio import COLOR_DEFECTO, enviar_reporte, mes_anterior
from api.reportes.repositorio import RepositorioReportes

router = APIRouter(prefix="/admin", tags=["admin-reporte"])

# Claves de config que el editor puede sobreescribir por cliente (lista blanca)
EDITABLES = {"titulo", "bajada", "etiqueta", "etiqueta_propio", "objetivo", "limite", "ia", "items"}


def _repo(pool: Annotated[asyncpg.Pool, Depends(obtener_pool)]) -> RepositorioReportes:
    return RepositorioReportes(pool)


Equipo = Annotated[UsuarioActual, Depends(usuario_equipo)]
Repo = Annotated[RepositorioReportes, Depends(_repo)]
Config = Annotated[Configuracion, Depends(obtener_config_app)]
Pool = Annotated[asyncpg.Pool, Depends(obtener_pool)]


async def _instancia(repo: RepositorioReportes, cliente_id: int) -> dict[str, Any]:
    inst = await repo.instancia_de_cliente(cliente_id)
    if inst is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El cliente no tiene reporte activo")
    return inst


class Invitacion(BaseModel):
    emails: list[EmailStr] = Field(min_length=1, max_length=20)
    enviar_correo: bool = True


@router.post("/clientes/{cliente_id}/invitar")
async def invitar(
    cliente_id: int, cuerpo: Invitacion, _: Equipo, repo: Repo, config: Config
) -> dict[str, Any]:
    """Habilita a cada correo como usuario del cliente y le envía la invitación."""
    inst = await _instancia(repo, cliente_id)
    url = f"{config.frontend_url.rstrip('/')}/{inst['slug_publico']}"
    color = inst.get("color_primario") or COLOR_DEFECTO
    resultados: list[dict[str, str | None]] = []
    for crudo in cuerpo.emails:
        email = crudo.lower()
        if await repo.rol_de(email) == "equipo":
            resultados.append({"email": email, "estado": "omitido", "detalle": "es del equipo"})
            continue
        await repo.invitar(cliente_id, email)
        if not cuerpo.enviar_correo:
            resultados.append({"email": email, "estado": "habilitado", "detalle": None})
            continue
        ok, error = await enviar(
            config,
            [email],
            f"Tu reporte de {inst['cliente']} está listo",
            html_invitacion(str(inst["cliente"]), url, color),
        )
        resultados.append(
            {
                "email": email,
                "estado": "invitado" if ok else "habilitado_sin_correo",
                "detalle": error,
            }
        )
    return {"url": url, "resultados": resultados}


@router.get("/clientes/{cliente_id}/reporte")
async def estructura(cliente_id: int, _: Equipo, repo: Repo) -> dict[str, Any]:
    inst = await _instancia(repo, cliente_id)
    return {
        "instancia_id": inst["id"],
        "slug": inst["slug_publico"],
        "paginas": await repo.estructura(inst["id"], inst["plantilla_id"], cliente_id),
        "envios": await repo.envios(cliente_id),
    }


class Override(BaseModel):
    oculto: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


@router.put("/clientes/{cliente_id}/reporte/bloques/{bloque_id}")
async def guardar_bloque(
    cliente_id: int, bloque_id: int, cuerpo: Override, _: Equipo, repo: Repo
) -> dict[str, str]:
    inst = await _instancia(repo, cliente_id)
    if not await repo.bloque_pertenece(inst["id"], bloque_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bloque no encontrado en este reporte")
    ajenas = set(cuerpo.config) - EDITABLES
    if ajenas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Campos no editables: {sorted(ajenas)}")
    limpio = {k: v for k, v in cuerpo.config.items() if v not in (None, "")}
    await repo.guardar_override(inst["id"], bloque_id, cuerpo.oculto, limpio)
    return {"estado": "guardado"}


class PaginaOculta(BaseModel):
    oculto: bool


@router.put("/clientes/{cliente_id}/reporte/paginas/{pagina_id}")
async def ocultar_pagina(
    cliente_id: int, pagina_id: int, cuerpo: PaginaOculta, _: Equipo, repo: Repo
) -> dict[str, int]:
    inst = await _instancia(repo, cliente_id)
    return {"bloques": await repo.ocultar_pagina(inst["id"], pagina_id, cuerpo.oculto)}


class EnvioManual(BaseModel):
    destinatarios: list[EmailStr] | None = None  # None = usuarios del cliente
    mes: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")  # None = mes anterior


@router.post("/clientes/{cliente_id}/reporte/enviar")
async def enviar_ahora(
    cliente_id: int, cuerpo: EnvioManual, _: Equipo, config: Config, pool: Pool
) -> dict[str, Any]:
    if not config.resend_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "RESEND_API_KEY no configurada")
    if cuerpo.mes:
        periodo = date.fromisoformat(f"{cuerpo.mes}-01")
    else:
        periodo, _fin = mes_anterior(hoy_en(config.zona_horaria))
    para = [e.lower() for e in cuerpo.destinatarios] if cuerpo.destinatarios else None
    r = await enviar_reporte(pool, config, cliente_id, periodo, para, automatico=False)
    if r.estado != "enviado":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, r.error or r.estado)
    return {"estado": r.estado, "destinatarios": r.destinatarios, "periodo": periodo.isoformat()}

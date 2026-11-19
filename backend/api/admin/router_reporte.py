"""Admin: invitar usuarios del cliente, editar su reporte (ocultar bloques y páginas, textos,
objetivos) y enviar el reporte mensual a demanda."""

from datetime import date
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from api.admin.router import usuario_equipo
from api.auth.admin_supabase import asegurar_usuario_auth
from api.config import Configuracion
from api.deps import (
    UsuarioActual,
    limite_por_usuario,
    obtener_config_app,
    obtener_pool,
    vaciar_cache_tras_escritura,
)
from api.etl.conector_base import hoy_en
from api.reportes.correo import enviar, html_invitacion
from api.reportes.envio import COLOR_DEFECTO, enviar_reporte, mes_anterior
from api.reportes.repositorio import RepositorioReportes

router = APIRouter(
    prefix="/admin",
    tags=["admin-reporte"],
    # B-7: las ediciones se ven en /consulta en la petición siguiente
    dependencies=[Depends(vaciar_cache_tras_escritura)],
)

# Claves de config que el editor puede sobreescribir por cliente (lista blanca)
EDITABLES = {"titulo", "bajada", "etiqueta", "etiqueta_propio", "objetivo", "limite", "ia", "items"}
TEXTOS = {"titulo": 200, "bajada": 500, "etiqueta": 120, "etiqueta_propio": 120}
MAX_ITEMS = 12


def errores_override(config: dict[str, Any]) -> list[str]:
    """#14: tipos y rangos de cada valor editable (además de la lista blanca de claves)."""
    errores: list[str] = []
    for clave, maximo in TEXTOS.items():
        v = config.get(clave)
        if v is not None and (not isinstance(v, str) or len(v) > maximo):
            errores.append(f"{clave}: texto de hasta {maximo} caracteres")
    if "limite" in config:
        v = config["limite"]
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 100:
            errores.append("limite: entero entre 1 y 100")
    if "objetivo" in config:
        v = config["objetivo"]
        if isinstance(v, bool) or not isinstance(v, int | float) or not 0 <= v <= 1e12:
            errores.append("objetivo: número entre 0 y 1e12")
    if "ia" in config and not isinstance(config["ia"], bool):
        errores.append("ia: verdadero o falso")
    if "items" in config:
        items = config["items"]
        validos = isinstance(items, list) and len(items) <= MAX_ITEMS
        for i in items if isinstance(items, list) else []:
            validos = validos and (
                isinstance(i, dict)
                and isinstance(i.get("metrica"), str)
                and len(i) <= 8
                and all(isinstance(k, str) and len(k) <= 40 for k in i)
                and all(
                    v is None
                    or isinstance(v, bool | int | float)
                    or (isinstance(v, str) and len(v) <= 120)
                    for v in i.values()
                )
            )
        if not validos:
            errores.append(
                f"items: lista de hasta {MAX_ITEMS} objetos con 'metrica' y valores simples"
            )
    return errores


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


NO_INVITABLES = {
    "pertenece_a_otro_cliente": "ya es usuario de otro cliente; no se cambió",
    "es_equipo": "es del equipo",
}


class Invitacion(BaseModel):
    emails: list[EmailStr] = Field(min_length=1, max_length=20)
    enviar_correo: bool = True


@router.post("/clientes/{cliente_id}/invitar", dependencies=[limite_por_usuario("invitar", 10)])
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
        estado = await repo.invitar(cliente_id, email)
        if estado in NO_INVITABLES:
            # N-1: nunca se mueve un usuario de cliente ni se toca uno del equipo. No se dice
            # a qué cliente pertenece.
            resultados.append({"email": email, "estado": estado, "detalle": NO_INVITABLES[estado]})
            continue
        # #12: el enlace mágico no crea usuarios; hay que darlo de alta en Supabase Auth.
        auth = await asegurar_usuario_auth(config, email)
        if auth in ("sin_clave_auth", "error_auth"):
            resultados.append(
                {
                    "email": email,
                    "estado": "habilitado_sin_auth",
                    "detalle": "habilitado en DatIO, pero no se pudo crear su acceso en Supabase "
                    f"Auth ({auth}); no podrá pedir el enlace hasta resolverlo",
                }
            )
            continue
        if not cuerpo.enviar_correo:
            resultados.append({"email": email, "estado": "habilitado", "detalle": estado})
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
                "detalle": error if not ok else (estado if estado != "creado" else None),
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
    errores = errores_override(limpio)
    if errores:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "; ".join(errores))
    # "No inventes métricas": toda métrica de items tiene que existir en dim_metrica
    codigos = [str(i["metrica"]) for i in limpio.get("items", [])]
    desconocidas = sorted(set(codigos) - await repo.metricas_existentes(codigos))
    if desconocidas:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Métricas desconocidas: {', '.join(desconocidas)}"
        )
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


@router.post(
    "/clientes/{cliente_id}/reporte/enviar", dependencies=[limite_por_usuario("enviar", 3)]
)
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

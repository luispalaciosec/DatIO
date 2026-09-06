"""Radar competitivo (PT-15): snapshot semanal de perfiles de la competencia vía Apify.

Errata E-02: cadencia SEMANAL. Cada corrida guarda el payload de Apify en raw_payloads
(referenciando al competidor) antes de normalizar a fct_competidor_snapshot.

Métricas por competidor (códigos de dim_metrica):
  seguidores, publicaciones (totales del perfil), y sobre las últimas 12 publicaciones que
  Apify devuelve: me_gusta, comentarios, interacciones (suma de ambas).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from api.config import Configuracion
from api.etl.conector_base import hoy_en
from api.etl.repositorio import RepositorioETL

log = logging.getLogger(__name__)

ACTORES = {"meta_ig": "apify~instagram-profile-scraper", "meta_fb": "apify~facebook-pages-scraper"}
API = "https://api.apify.com/v2"


@dataclass
class ResumenRadar:
    competidores: int = 0
    snapshots: int = 0
    costo_usd: float = 0.0
    errores: dict[int, str] = field(default_factory=dict)
    omitidos: list[str] = field(default_factory=list)


def normalizar_instagram(perfil: dict[str, Any]) -> dict[str, Decimal]:
    posts = perfil.get("latestPosts") or []
    likes = sum(int(p.get("likesCount") or 0) for p in posts)
    comentarios = sum(int(p.get("commentsCount") or 0) for p in posts)
    valores: dict[str, Decimal] = {}
    if perfil.get("followersCount") is not None:
        valores["seguidores"] = Decimal(int(perfil["followersCount"]))
    if perfil.get("postsCount") is not None:
        valores["publicaciones"] = Decimal(int(perfil["postsCount"]))
    if posts:
        valores["me_gusta"] = Decimal(likes)
        valores["comentarios"] = Decimal(comentarios)
        valores["interacciones"] = Decimal(likes + comentarios)
    return valores


def normalizar_facebook(pagina: dict[str, Any]) -> dict[str, Decimal]:
    valores: dict[str, Decimal] = {}
    seguidores = pagina.get("followers") or pagina.get("likes")
    if seguidores is not None:
        valores["seguidores"] = Decimal(int(seguidores))
    return valores


NORMALIZADORES = {"meta_ig": normalizar_instagram, "meta_fb": normalizar_facebook}


def entrada_actor(plataforma: str, handles: list[str]) -> dict[str, Any]:
    if plataforma == "meta_ig":
        return {"usernames": handles}
    return {"startUrls": [{"url": f"https://www.facebook.com/{h}"} for h in handles]}


def clave_perfil(plataforma: str, item: dict[str, Any]) -> str:
    """Con qué handle (en minúsculas) casar cada ítem devuelto por Apify."""
    if plataforma == "meta_ig":
        return str(item.get("username") or "").lower()
    url = str(item.get("pageUrl") or item.get("facebookUrl") or item.get("url") or "")
    return url.rstrip("/").split("/")[-1].lower()


async def ejecutar_actor(
    config: Configuracion, actor: str, entrada: dict[str, Any], timeout_seg: int = 300
) -> tuple[list[dict[str, Any]], float, str]:
    """Corre el actor y espera. Devuelve (items, costo_usd, run_id)."""
    cab = {"Authorization": f"Bearer {config.apify_token}"}
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(f"{API}/acts/{actor}/runs", headers=cab, json=entrada)
        r.raise_for_status()
        run = r.json()["data"]
        run_id = str(run["id"])
        esperado = 0
        while run["status"] not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            await asyncio.sleep(5)
            esperado += 5
            if esperado > timeout_seg:
                raise TimeoutError(f"Apify run {run_id} no terminó en {timeout_seg}s")
            run = (await http.get(f"{API}/actor-runs/{run_id}", headers=cab)).json()["data"]
        if run["status"] != "SUCCEEDED":
            raise RuntimeError(f"Apify run {run_id} terminó en {run['status']}")
        items = (
            await http.get(f"{API}/datasets/{run['defaultDatasetId']}/items", headers=cab)
        ).json()
    return list(items), float(run.get("usageTotalUsd") or 0), run_id


async def correr_radar(
    repo: RepositorioETL,
    config: Configuracion,
    cliente_id: int | None = None,
    forzar: bool = False,
    dias_minimos: int = 7,
) -> ResumenRadar:
    resumen = ResumenRadar()
    if not config.apify_token:
        resumen.omitidos.append("APIFY_TOKEN no configurado")
        return resumen
    pendientes = await repo.competidores_para_radar(dias_minimos, cliente_id, forzar)
    fecha = hoy_en(config.zona_horaria)
    por_plataforma: dict[str, list[dict[str, Any]]] = {}
    for c in pendientes:
        por_plataforma.setdefault(c["plataforma"], []).append(c)

    for plataforma, comps in por_plataforma.items():
        actor = ACTORES.get(plataforma)
        if actor is None:
            resumen.omitidos.append(f"{plataforma}: sin actor de Apify todavía")
            continue
        handles = [c["handle"] for c in comps]
        try:
            items, costo, run_id = await ejecutar_actor(
                config, actor, entrada_actor(plataforma, handles)
            )
        except Exception as e:
            log.exception("Radar %s falló", plataforma)
            for c in comps:
                resumen.errores[c["id"]] = f"{type(e).__name__}: {e}"
            continue
        resumen.costo_usd += costo
        por_handle = {clave_perfil(plataforma, it): it for it in items}
        for c in comps:
            item = por_handle.get(c["handle"].lower())
            if item is None:
                resumen.errores[c["id"]] = "Apify no devolvió este perfil (¿usuario incorrecto?)"
                continue
            await repo.guardar_raw_competidor(
                c["id"], actor, {"run_id": run_id, "handle": c["handle"]}, item
            )
            valores = NORMALIZADORES[plataforma](item)
            resumen.snapshots += await repo.upsert_snapshot_competidor(c["id"], fecha, valores)
            resumen.competidores += 1
            foto = (
                item.get("profilePicUrlHD")
                or item.get("profilePicUrl")
                or item.get("profilePictureUrl")
            )
            if foto:
                await repo.actualizar_logo_competidor(c["id"], str(foto))
    return resumen

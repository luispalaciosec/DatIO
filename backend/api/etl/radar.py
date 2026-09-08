"""Radar competitivo (PT-15): snapshot semanal de perfiles de la competencia vía Apify.

Errata E-02: cadencia SEMANAL. Cada corrida guarda el payload de Apify en raw_payloads
(referenciando al competidor) antes de normalizar a fct_competidor_snapshot.

Métricas por competidor (códigos de dim_metrica):
  seguidores, publicaciones (totales del perfil), y sobre las últimas 12 publicaciones que
  Apify devuelve: me_gusta, comentarios, interacciones (sumas), *_promedio por publicación,
  tasa_engagement (interacciones promedio / seguidores) y publicaciones_semana (ritmo).
Las publicaciones en sí se guardan en competidor_publicaciones (sql/007).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from api.config import Configuracion
from api.etl.conector_base import hoy_en
from api.etl.imagenes import descargar_reducida
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


def _fecha_post(p: dict[str, Any]) -> datetime | None:
    t = p.get("timestamp")
    if not t:
        return None
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalizar_instagram(perfil: dict[str, Any]) -> dict[str, Decimal]:
    """Seguidores y publicaciones totales del perfil, y sobre las últimas publicaciones que
    Apify devuelve (hasta 12): promedios por publicación, tasa de engagement y ritmo semanal."""
    posts = perfil.get("latestPosts") or []
    n = len(posts)
    likes = sum(int(p.get("likesCount") or 0) for p in posts)
    comentarios = sum(int(p.get("commentsCount") or 0) for p in posts)
    valores: dict[str, Decimal] = {}
    seguidores = perfil.get("followersCount")
    if seguidores is not None:
        valores["seguidores"] = Decimal(int(seguidores))
    if perfil.get("postsCount") is not None:
        valores["publicaciones"] = Decimal(int(perfil["postsCount"]))
    if n:
        valores["me_gusta_promedio"] = Decimal(likes) / n
        valores["comentarios_promedio"] = Decimal(comentarios) / n
        valores["interacciones_promedio"] = Decimal(likes + comentarios) / n
        valores["me_gusta"] = Decimal(likes)
        valores["comentarios"] = Decimal(comentarios)
        valores["interacciones"] = Decimal(likes + comentarios)
        if seguidores:
            valores["tasa_engagement"] = (
                Decimal(likes + comentarios) / n / Decimal(int(seguidores)) * 100
            )
        fechas = sorted(f for f in (_fecha_post(p) for p in posts) if f)
        if len(fechas) >= 2:
            dias = max((fechas[-1] - fechas[0]).days, 1)
            valores["publicaciones_semana"] = Decimal(len(fechas)) / dias * 7
    return valores


TIPOS_IG = {"Sidecar": "carrusel", "Video": "reel", "Image": "imagen"}


def publicaciones_instagram(perfil: dict[str, Any]) -> list[dict[str, Any]]:
    """Últimas publicaciones del perfil (hasta 12) en el formato de competidor_publicaciones."""
    salida = []
    for p in perfil.get("latestPosts") or []:
        id_externo = p.get("id") or p.get("shortCode")
        if not id_externo:
            continue
        salida.append(
            {
                "id_externo": str(id_externo),
                "tipo": TIPOS_IG.get(str(p.get("type")), str(p.get("type") or "").lower() or None),
                "publicado_en": _fecha_post(p),
                "permalink": p.get("url"),
                "caption": (p.get("caption") or None),
                "thumbnail_url": p.get("displayUrl") or (p.get("images") or [None])[0],
                "me_gusta": Decimal(int(p["likesCount"]))
                if p.get("likesCount") is not None
                else None,
                "comentarios": (
                    Decimal(int(p["commentsCount"])) if p.get("commentsCount") is not None else None
                ),
                "reproducciones": (
                    Decimal(int(p["videoViewCount"])) if p.get("videoViewCount") else None
                ),
            }
        )
    return salida


def normalizar_facebook(pagina: dict[str, Any]) -> dict[str, Decimal]:
    valores: dict[str, Decimal] = {}
    seguidores = pagina.get("followers") or pagina.get("likes")
    if seguidores is not None:
        valores["seguidores"] = Decimal(int(seguidores))
    return valores


NORMALIZADORES = {"meta_ig": normalizar_instagram, "meta_fb": normalizar_facebook}
PUBLICACIONES = {"meta_ig": publicaciones_instagram}


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
            extractor = PUBLICACIONES.get(plataforma)
            publicaciones = extractor(item) if extractor is not None else []
            if publicaciones:
                await repo.upsert_publicaciones_competidor(c["id"], fecha, publicaciones)
            resumen.competidores += 1
            foto = (
                item.get("profilePicUrlHD")
                or item.get("profilePicUrl")
                or item.get("profilePictureUrl")
            )
            if foto:
                await repo.actualizar_logo_competidor(c["id"], str(foto))
            await guardar_imagenes(repo, c["id"], str(foto) if foto else None, publicaciones)
    return resumen


async def guardar_imagenes(
    repo: RepositorioETL,
    competidor_id: int,
    foto_url: str | None,
    publicaciones: list[dict[str, Any]],
) -> int:
    """Copia local (reducida) de la foto de perfil y de las miniaturas nuevas. Best effort:
    una imagen que falle no detiene el radar. Devuelve cuántas se guardaron."""
    existentes = await repo.imagenes_existentes(competidor_id)
    pendientes: list[tuple[str, str]] = []
    if foto_url:
        pendientes.append(("perfil", foto_url))  # el perfil se refresca en cada corrida
    for p in publicaciones:
        if p.get("thumbnail_url") and p["id_externo"] not in existentes:
            pendientes.append((p["id_externo"], str(p["thumbnail_url"])))
    guardadas = 0
    async with httpx.AsyncClient(timeout=30) as http:
        for clave, url in pendientes:
            imagen = await descargar_reducida(http, url)
            if imagen is None:
                continue
            await repo.guardar_imagen_competidor(competidor_id, clave, imagen[1], imagen[0])
            guardadas += 1
    return guardadas

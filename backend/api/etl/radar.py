"""Radar competitivo (PT-15 / PT-15b): snapshot semanal de perfiles de la competencia vía Apify
y radar de pauta (Meta Ad Library).

Errata E-02: cadencia SEMANAL. Cada corrida guarda el payload crudo en raw_payloads
(referenciando al competidor) antes de normalizar.

Por red:
  meta_ig  → apify~instagram-profile-scraper (perfil + últimas 12 publicaciones)
  meta_fb  → apify~facebook-pages-scraper (seguidores, foto) + apify~facebook-posts-scraper
  tiktok   → clockworks~tiktok-profile-scraper (los ítems son videos; el perfil viene en cada uno)
  pauta    → curious_coder~facebook-ads-library-scraper sobre la página de Facebook de cada
             competidor: anuncios activos en Ecuador → dim_anuncio_competencia. La antigüedad
             (total_active_time) es la señal: un anuncio que lleva 90 días es uno que funciona.

Métricas por competidor (códigos de dim_metrica): seguidores, publicaciones (totales), y sobre
las últimas publicaciones: me_gusta, comentarios, interacciones (sumas), *_promedio,
tasa_engagement (interacciones promedio / seguidores) y publicaciones_semana (ritmo).
Las publicaciones se guardan en competidor_publicaciones y sus imágenes en competidor_imagenes.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from api.config import Configuracion
from api.etl.conector_base import hoy_en
from api.etl.imagenes import descargar_reducida
from api.etl.repositorio import RepositorioETL

log = logging.getLogger(__name__)

ACTORES = {
    "meta_ig": "apify~instagram-profile-scraper",
    "meta_fb": "apify~facebook-pages-scraper",
    "meta_fb_publicaciones": "apify~facebook-posts-scraper",
    "tiktok": "clockworks~tiktok-profile-scraper",
    "pauta": "curious_coder~facebook-ads-library-scraper",
}
API = "https://api.apify.com/v2"
ULTIMAS_PUBLICACIONES = 12
PAIS_PAUTA = "EC"
MAX_ANUNCIOS_POR_PAGINA = 100


@dataclass
class ResumenRadar:
    competidores: int = 0
    snapshots: int = 0
    costo_usd: float = 0.0
    errores: dict[int, str] = field(default_factory=dict)
    omitidos: list[str] = field(default_factory=list)
    anuncios: int = 0


@dataclass
class Perfil:
    """Lo que el radar necesita de un competidor, venga del actor que venga."""

    seguidores: int | None
    publicaciones_totales: int | None
    publicaciones: list[dict[str, Any]]  # formato de competidor_publicaciones
    foto_url: str | None
    crudo: Any


# ---- utilidades ----------------------------------------------------------------------


def _fecha(valor: Any) -> datetime | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, int | float):
        return datetime.fromtimestamp(float(valor), tz=UTC)
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None


def _fecha_post(p: dict[str, Any]) -> datetime | None:
    return _fecha(p.get("timestamp") or p.get("time") or p.get("createTimeISO"))


def _entero(v: Any) -> Decimal | None:
    return Decimal(int(v)) if v is not None and v != "" else None


def metricas_de_perfil(perfil: Perfil) -> dict[str, Decimal]:
    """Misma definición para todas las redes: promedios sobre las últimas publicaciones,
    engagement = interacciones promedio / seguidores, ritmo = publicaciones por semana."""
    valores: dict[str, Decimal] = {}
    if perfil.seguidores is not None:
        valores["seguidores"] = Decimal(perfil.seguidores)
    if perfil.publicaciones_totales is not None:
        valores["publicaciones"] = Decimal(perfil.publicaciones_totales)
    posts = perfil.publicaciones
    n = len(posts)
    if not n:
        return valores
    likes = sum(int(p.get("me_gusta") or 0) for p in posts)
    comentarios = sum(int(p.get("comentarios") or 0) for p in posts)
    compartidos = sum(int(p.get("compartidos") or 0) for p in posts)
    interacciones = likes + comentarios + compartidos
    valores["me_gusta"] = Decimal(likes)
    valores["comentarios"] = Decimal(comentarios)
    valores["interacciones"] = Decimal(interacciones)
    valores["me_gusta_promedio"] = Decimal(likes) / n
    valores["comentarios_promedio"] = Decimal(comentarios) / n
    valores["interacciones_promedio"] = Decimal(interacciones) / n
    if perfil.seguidores:
        valores["tasa_engagement"] = Decimal(interacciones) / n / Decimal(perfil.seguidores) * 100
    fechas = sorted(p["publicado_en"] for p in posts if p.get("publicado_en"))
    if len(fechas) >= 2:
        dias = max((fechas[-1] - fechas[0]).days, 1)
        valores["publicaciones_semana"] = Decimal(len(fechas)) / dias * 7
    return valores


# ---- Instagram -------------------------------------------------------------------------

TIPOS_IG = {"Sidecar": "carrusel", "Video": "reel", "Image": "imagen"}


def publicaciones_instagram(perfil: dict[str, Any]) -> list[dict[str, Any]]:
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
                "caption": p.get("caption") or None,
                "thumbnail_url": p.get("displayUrl") or (p.get("images") or [None])[0],
                "me_gusta": _entero(p.get("likesCount")),
                "comentarios": _entero(p.get("commentsCount")),
                "reproducciones": _entero(p.get("videoViewCount"))
                if p.get("videoViewCount")
                else None,
            }
        )
    return salida


def perfil_instagram(item: dict[str, Any]) -> Perfil:
    return Perfil(
        seguidores=int(item["followersCount"]) if item.get("followersCount") is not None else None,
        publicaciones_totales=int(item["postsCount"])
        if item.get("postsCount") is not None
        else None,
        publicaciones=publicaciones_instagram(item),
        foto_url=item.get("profilePicUrlHD") or item.get("profilePicUrl"),
        crudo=item,
    )


def normalizar_instagram(perfil: dict[str, Any]) -> dict[str, Decimal]:
    return metricas_de_perfil(perfil_instagram(perfil))


# ---- Facebook --------------------------------------------------------------------------


def publicaciones_facebook(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    salida = []
    for p in posts:
        id_externo = p.get("postId") or p.get("url")
        if not id_externo:
            continue
        media = p.get("media") or {}
        if isinstance(media, list):
            media = media[0] if media else {}
        miniatura = (
            (media.get("thumbnail") if isinstance(media, dict) else None)
            or ((media.get("image") or {}).get("uri") if isinstance(media, dict) else None)
            or ((media.get("thumbnailImage") or {}).get("uri") if isinstance(media, dict) else None)
        )
        salida.append(
            {
                "id_externo": str(id_externo),
                "tipo": "video" if p.get("isVideo") else "publicacion",
                "publicado_en": _fecha_post(p),
                "permalink": p.get("url") or p.get("topLevelUrl"),
                "caption": p.get("text") or None,
                "thumbnail_url": miniatura,
                "me_gusta": _entero(p.get("likes")),
                "comentarios": _entero(p.get("comments")),
                "compartidos": _entero(p.get("shares")),
                "reproducciones": _entero(p.get("viewsCount") or p.get("videoPostViewCount"))
                if (p.get("viewsCount") or p.get("videoPostViewCount"))
                else None,
            }
        )
    return salida


def perfil_facebook(pagina: dict[str, Any] | None, posts: list[dict[str, Any]]) -> Perfil:
    pagina = pagina or {}
    seguidores = pagina.get("followers") or pagina.get("likes")
    return Perfil(
        seguidores=int(seguidores) if seguidores is not None else None,
        publicaciones_totales=None,
        publicaciones=publicaciones_facebook(posts),
        foto_url=pagina.get("profilePictureUrl")
        or pagina.get("profilePhoto")
        or ((posts[0].get("user") or {}).get("profilePic") if posts else None),
        crudo={"pagina": pagina, "publicaciones": posts},
    )


def normalizar_facebook(pagina: dict[str, Any]) -> dict[str, Decimal]:
    return metricas_de_perfil(perfil_facebook(pagina, []))


# ---- TikTok ----------------------------------------------------------------------------


def perfil_tiktok(videos: list[dict[str, Any]]) -> Perfil:
    autor = (videos[0].get("authorMeta") or {}) if videos else {}
    publicaciones = []
    for v in videos:
        if not v.get("id"):
            continue
        meta = v.get("videoMeta") or {}
        publicaciones.append(
            {
                "id_externo": str(v["id"]),
                "tipo": "video",
                "publicado_en": _fecha(v.get("createTimeISO")) or _fecha(v.get("createTime")),
                "permalink": v.get("webVideoUrl"),
                "caption": v.get("text") or None,
                "thumbnail_url": meta.get("coverUrl") or meta.get("originalCoverUrl"),
                "me_gusta": _entero(v.get("diggCount")),
                "comentarios": _entero(v.get("commentCount")),
                "compartidos": _entero(v.get("shareCount")),
                "reproducciones": _entero(v.get("playCount")),
            }
        )
    return Perfil(
        seguidores=int(autor["fans"]) if autor.get("fans") is not None else None,
        publicaciones_totales=int(autor["video"]) if autor.get("video") is not None else None,
        publicaciones=publicaciones,
        foto_url=autor.get("avatar") or autor.get("originalAvatarUrl"),
        crudo={"autor": autor, "videos": videos},
    )


NORMALIZADORES = {"meta_ig": normalizar_instagram, "meta_fb": normalizar_facebook}


# ---- Apify ----------------------------------------------------------------------------


def entrada_actor(plataforma: str, handles: list[str]) -> dict[str, Any]:
    if plataforma == "meta_ig":
        return {"usernames": handles}
    if plataforma == "tiktok":
        return {
            "profiles": handles,
            "resultsPerPage": ULTIMAS_PUBLICACIONES,
            "profileSorting": "latest",
            "excludePinnedPosts": False,
        }
    if plataforma == "meta_fb_publicaciones":
        return {
            "startUrls": [{"url": f"https://www.facebook.com/{h}"} for h in handles],
            "resultsLimit": ULTIMAS_PUBLICACIONES,
        }
    if plataforma == "pauta":
        return {
            "urls": [{"url": f"https://www.facebook.com/{h}"} for h in handles],
            "limitPerSource": MAX_ANUNCIOS_POR_PAGINA,
            "scrapePageAds.activeStatus": "active",
            "scrapePageAds.countryCode": PAIS_PAUTA,
            "scrapePageAds.sortBy": "impressions_desc",
            "scrapeAdDetails": False,
        }
    return {"startUrls": [{"url": f"https://www.facebook.com/{h}"} for h in handles]}


def _ultimo_segmento(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0].lower()


def clave_perfil(plataforma: str, item: dict[str, Any]) -> str:
    """Con qué handle (en minúsculas) casar cada ítem devuelto por Apify."""
    if plataforma == "meta_ig":
        return str(item.get("username") or "").lower()
    if plataforma == "tiktok":
        return str(item.get("input") or (item.get("authorMeta") or {}).get("name") or "").lower()
    if plataforma == "meta_fb_publicaciones":
        return _ultimo_segmento(str(item.get("inputUrl") or item.get("facebookUrl") or ""))
    if plataforma == "pauta":
        return _ultimo_segmento(str(item.get("url") or ""))
    return _ultimo_segmento(
        str(item.get("pageUrl") or item.get("facebookUrl") or item.get("url") or "")
    )


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


def _agrupar(plataforma: str, items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    salida: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        salida.setdefault(clave_perfil(plataforma, it), []).append(it)
    return salida


async def perfiles_de_red(
    config: Configuracion, plataforma: str, handles: list[str], resumen: ResumenRadar
) -> tuple[dict[str, Perfil], dict[str, str]]:
    """Corre el/los actores de la red y devuelve {handle: Perfil} y {actor: run_id}."""
    corridas: dict[str, str] = {}
    if plataforma == "meta_ig":
        items, costo, run_id = await ejecutar_actor(
            config, ACTORES["meta_ig"], entrada_actor("meta_ig", handles)
        )
        resumen.costo_usd += costo
        corridas[ACTORES["meta_ig"]] = run_id
        return {
            h: perfil_instagram(its[0]) for h, its in _agrupar("meta_ig", items).items()
        }, corridas
    if plataforma == "tiktok":
        items, costo, run_id = await ejecutar_actor(
            config, ACTORES["tiktok"], entrada_actor("tiktok", handles)
        )
        resumen.costo_usd += costo
        corridas[ACTORES["tiktok"]] = run_id
        return {h: perfil_tiktok(its) for h, its in _agrupar("tiktok", items).items()}, corridas
    if plataforma == "meta_fb":
        paginas, costo1, run1 = await ejecutar_actor(
            config, ACTORES["meta_fb"], entrada_actor("meta_fb", handles)
        )
        posts, costo2, run2 = await ejecutar_actor(
            config,
            ACTORES["meta_fb_publicaciones"],
            entrada_actor("meta_fb_publicaciones", handles),
        )
        resumen.costo_usd += costo1 + costo2
        corridas[ACTORES["meta_fb"]] = run1
        corridas[ACTORES["meta_fb_publicaciones"]] = run2
        por_pagina = _agrupar("meta_fb", paginas)
        por_posts = _agrupar("meta_fb_publicaciones", posts)
        salida: dict[str, Perfil] = {}
        for h in set(por_pagina) | set(por_posts):
            pagina = por_pagina.get(h, [None])[0]
            salida[h] = perfil_facebook(pagina, por_posts.get(h, []))
        return salida, corridas
    raise LookupError(f"{plataforma}: sin actor de Apify todavía")


async def correr_radar(
    repo: RepositorioETL,
    config: Configuracion,
    cliente_id: int | None = None,
    forzar: bool = False,
    dias_minimos: int = 7,
    pauta: bool = True,
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
        handles = [c["handle"] for c in comps]
        try:
            perfiles, corridas = await perfiles_de_red(config, plataforma, handles, resumen)
        except LookupError as e:
            resumen.omitidos.append(str(e))
            continue
        except Exception as e:
            log.exception("Radar %s falló", plataforma)
            for c in comps:
                resumen.errores[c["id"]] = f"{type(e).__name__}: {e}"
            continue
        for c in comps:
            perfil = perfiles.get(c["handle"].lower())
            if perfil is None:
                resumen.errores[c["id"]] = "Apify no devolvió este perfil (¿usuario incorrecto?)"
                continue
            await repo.guardar_raw_competidor(
                c["id"], ",".join(corridas), {"runs": corridas, "handle": c["handle"]}, perfil.crudo
            )
            valores = metricas_de_perfil(perfil)
            resumen.snapshots += await repo.upsert_snapshot_competidor(c["id"], fecha, valores)
            if perfil.publicaciones:
                await repo.upsert_publicaciones_competidor(c["id"], fecha, perfil.publicaciones)
            resumen.competidores += 1
            if perfil.foto_url:
                await repo.actualizar_logo_competidor(c["id"], str(perfil.foto_url))
            await guardar_imagenes(repo, c["id"], perfil.foto_url, perfil.publicaciones)

    if pauta:
        await correr_radar_pauta(repo, config, resumen, por_plataforma.get("meta_fb", []), fecha)
    return resumen


# ---- Radar de pauta (Meta Ad Library) --------------------------------------------------


def normalizar_anuncio(item: dict[str, Any], hoy: date) -> dict[str, Any] | None:
    """Un anuncio del actor → fila de dim_anuncio_competencia (+ imagen de la creatividad)."""
    ad_id = item.get("ad_archive_id")
    if not ad_id:
        return None
    snap = item.get("snapshot") or {}
    tarjetas = snap.get("cards") or []
    tarjeta = tarjetas[0] if tarjetas else {}
    cuerpo = (snap.get("body") or {}).get("text") if isinstance(snap.get("body"), dict) else None
    activo_seg = item.get("total_active_time")
    inicio = _fecha(item.get("start_date"))
    if activo_seg:
        primera = hoy - timedelta(days=int(activo_seg) // 86400)
    elif inicio is not None:
        primera = inicio.date()
    else:
        primera = hoy
    creatividad = (
        tarjeta.get("resized_image_url")
        or tarjeta.get("original_image_url")
        or tarjeta.get("video_preview_image_url")
        or snap.get("image_url")
    )
    copia = cuerpo or tarjeta.get("body") or snap.get("title")
    titulo = snap.get("title") or tarjeta.get("title")
    if copia and "{{" in str(copia):  # plantillas de catálogo dinámico: no hay copy real
        copia = "Anuncio dinámico de catálogo (creatividad generada por producto)"
    if titulo and "{{" in str(titulo):
        titulo = None
    return {
        "ad_archive_id": str(ad_id),
        "primera_vez_visto": primera,
        "ultima_vez_visto": hoy,
        "plataformas": [str(p).lower() for p in (item.get("publisher_platform") or [])],
        "creatividad_url": creatividad,
        "copy_texto": copia,
        "formato": str(snap.get("display_format") or "").lower() or None,
        "oferta": snap.get("cta_text") or tarjeta.get("cta_text"),
        "titulo": titulo,
        "enlace": snap.get("link_url") or tarjeta.get("link_url"),
        "url_biblioteca": item.get("ad_library_url"),
        "activo": bool(item.get("is_active", True)),
    }


async def correr_radar_pauta(
    repo: RepositorioETL,
    config: Configuracion,
    resumen: ResumenRadar,
    competidores_fb: list[dict[str, Any]],
    hoy: date,
) -> None:
    if not competidores_fb:
        return
    handles = [c["handle"] for c in competidores_fb]
    try:
        items, costo, run_id = await ejecutar_actor(
            config, ACTORES["pauta"], entrada_actor("pauta", handles)
        )
    except Exception as e:
        log.exception("Radar de pauta falló")
        for c in competidores_fb:
            resumen.errores[c["id"]] = f"pauta: {type(e).__name__}: {e}"
        return
    resumen.costo_usd += costo
    por_pagina = _agrupar("pauta", items)
    for c in competidores_fb:
        crudos = por_pagina.get(c["handle"].lower(), [])
        await repo.guardar_raw_competidor(
            c["id"], ACTORES["pauta"], {"run_id": run_id, "handle": c["handle"]}, crudos
        )
        anuncios = [a for a in (normalizar_anuncio(it, hoy) for it in crudos) if a]
        resumen.anuncios += await repo.upsert_anuncios_competidor(c["id"], anuncios)
        existentes = await repo.imagenes_existentes(c["id"])
        pendientes = [
            (f"ad:{a['ad_archive_id']}", str(a["creatividad_url"]))
            for a in anuncios
            if a.get("creatividad_url") and f"ad:{a['ad_archive_id']}" not in existentes
        ]
        async with httpx.AsyncClient(timeout=30) as http:
            for clave, url in pendientes:
                imagen = await descargar_reducida(http, url)
                if imagen is not None:
                    await repo.guardar_imagen_competidor(c["id"], clave, imagen[1], imagen[0])


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

"""Publicaciones de Instagram y Facebook (métricas por post, Graph API v21)."""

from datetime import date, datetime, timedelta
from typing import Any

from api.etl.conector_publicaciones import ConectorPublicacionesBase, Publicacion
from api.etl.conectores.meta_base import ConectorMetaBase
from api.etl.registro import registrar_publicaciones

TIPOS_IG = {"IMAGE": "imagen", "VIDEO": "video", "CAROUSEL_ALBUM": "carrusel"}


def _fecha(texto: str | None) -> datetime | None:
    if not texto:
        return None
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%S%z")


@registrar_publicaciones
class ConectorMetaIGPublicaciones(ConectorMetaBase, ConectorPublicacionesBase):
    codigo = "meta_ig_publicaciones"
    plataforma = "meta_ig"

    CAMPOS = "id,caption,media_type,media_product_type,permalink,timestamp,thumbnail_url,media_url"
    # Métricas por media vigentes en v21 (impressions/plays retiradas). Todas en el seed.
    METRICAS_NATIVAS = (
        "reach",
        "views",
        "likes",
        "comments",
        "shares",
        "saved",
        "total_interactions",
        "profile_visits",
        "follows",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self.token_acceso()
        ig = self.cuenta.id_externo
        medios = await self.get_paginado(
            f"{ig}/media",
            token,
            fields=self.CAMPOS,
            limit=50,
            since=int(datetime.combine(desde, datetime.min.time()).timestamp()),
            until=int(datetime.combine(hasta + timedelta(days=1), datetime.min.time()).timestamp()),
        )
        salida = []
        for m in medios:
            try:
                ins = await self.get(
                    f"{m['id']}/insights", token, metric=",".join(self.METRICAS_NATIVAS)
                )
                datos = ins.get("data", [])
            except Exception as e:  # algunas métricas no aplican a ciertos tipos de media
                datos = []
                m["insights_error"] = str(e)[:200]
                for metrica in self.METRICAS_NATIVAS:
                    try:
                        ins = await self.get(f"{m['id']}/insights", token, metric=metrica)
                        datos.extend(ins.get("data", []))
                    except Exception:
                        continue
            m["insights"] = datos
            salida.append(m)
        return [{"tipo": "media", "data": salida}]

    def normalizar_publicaciones(self, payload: list[dict[str, Any]]) -> list[Publicacion]:
        salida = []
        for bloque in payload:
            for m in bloque.get("data", []):
                nativas = {
                    s["name"]: s["values"][0]["value"]
                    for s in m.get("insights", [])
                    if s.get("values")
                }
                tipo = (
                    "reel"
                    if m.get("media_product_type") == "REELS"
                    else TIPOS_IG.get(m.get("media_type"), None)
                )
                salida.append(
                    Publicacion(
                        id_externo=m["id"],
                        tipo=tipo,
                        publicado_en=_fecha(m.get("timestamp")),
                        permalink=m.get("permalink"),
                        caption=m.get("caption"),
                        thumbnail_url=m.get("thumbnail_url") or m.get("media_url"),
                        metricas=self.metricas_canonicas(nativas),
                    )
                )
        return salida


@registrar_publicaciones
class ConectorMetaFBPublicaciones(ConectorMetaBase, ConectorPublicacionesBase):
    codigo = "meta_fb_publicaciones"
    plataforma = "meta_fb"

    # Meta retiró post_impressions* en v21; queda engagement por post.
    CAMPOS = (
        "id,message,created_time,permalink_url,full_picture,attachments{media_type},"
        "shares,comments.summary(true).limit(0),reactions.summary(true).limit(0),"
        "insights.metric(post_clicks,post_video_views)"
    )
    METRICAS_NATIVAS = (
        "post_reactions_total",
        "post_comments_total",
        "post_shares_total",
        "post_clicks",
        "post_video_views",
        "post_interacciones",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self.token_acceso()
        pagina = await self.get(self.cuenta.id_externo, token, fields="access_token")
        posts = await self.get_paginado(
            f"{self.cuenta.id_externo}/posts",
            str(pagina["access_token"]),
            fields=self.CAMPOS,
            limit=50,
            since=desde.isoformat(),
            until=(hasta + timedelta(days=1)).isoformat(),
        )
        return [{"tipo": "posts", "data": posts}]

    def normalizar_publicaciones(self, payload: list[dict[str, Any]]) -> list[Publicacion]:
        salida = []
        for bloque in payload:
            for p in bloque.get("data", []):
                reacciones = (p.get("reactions") or {}).get("summary", {}).get("total_count", 0)
                comentarios = (p.get("comments") or {}).get("summary", {}).get("total_count", 0)
                compartidos = (p.get("shares") or {}).get("count", 0)
                nativas: dict[str, Any] = {
                    "post_reactions_total": reacciones,
                    "post_comments_total": comentarios,
                    "post_shares_total": compartidos,
                    "post_interacciones": reacciones + comentarios + compartidos,
                }
                for s in (p.get("insights") or {}).get("data", []):
                    if s.get("values"):
                        nativas[s["name"]] = s["values"][0]["value"]
                adj = ((p.get("attachments") or {}).get("data") or [{}])[0].get("media_type")
                tipo = {
                    "photo": "imagen",
                    "video_inline": "video",
                    "video": "video",
                    "album": "carrusel",
                }.get(adj or "", adj)
                salida.append(
                    Publicacion(
                        id_externo=p["id"],
                        tipo=tipo,
                        publicado_en=_fecha(p.get("created_time")),
                        permalink=p.get("permalink_url"),
                        caption=p.get("message"),
                        thumbnail_url=p.get("full_picture"),
                        metricas=self.metricas_canonicas(nativas),
                    )
                )
        return salida

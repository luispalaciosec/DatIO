"""Conector nativo de LinkedIn (Community Management API, aprobada 2026-10): estadísticas de
página de empresa y publicaciones. Reemplaza al puente de Metricool para las cuentas que se
conecten con el botón «Conectar con LinkedIn» (token OAuth del administrador de la página,
60 días; con refresh token si la app tiene renovación programática).

id_externo = urn:li:organization:NNN. Credencial cifrada: el access token (texto) o un JSON
{"access_token", "refresh_token"}. Métricas nativas → seed 'linkedin' (nombres de la API).
"""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from api.etl.conector_base import ConectorBase, Fila
from api.etl.conector_publicaciones import ConectorPublicacionesBase, Publicacion
from api.etl.registro import registrar, registrar_publicaciones

API = "https://api.linkedin.com/rest"


class LinkedInError(RuntimeError):
    pass


def _ms(d: date) -> int:
    return int(datetime.combine(d, datetime.min.time(), UTC).timestamp() * 1000)


def _dia(ms: int | None) -> date | None:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).date() if ms else None


def intervalo(desde: date, hasta: date) -> str:
    """timeIntervals en formato Rest.li: desde el inicio del día `desde` al fin de `hasta`."""
    return (
        f"(timeRange:(start:{_ms(desde)},end:{_ms(hasta + timedelta(days=1))}),"
        "timeGranularityType:DAY)"
    )


class LinkedInBase(ConectorBase):
    timeout_seg: float = 60

    async def _token(self) -> str:
        if not self.config.clave_cifrado:
            raise LinkedInError("CLAVE_CIFRADO no configurada")
        cruda = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
        if not cruda:
            raise LinkedInError(
                "La cuenta no tiene token de LinkedIn: conéctala con «Conectar con LinkedIn» "
                "desde el admin (esta cuenta venía del puente Metricool)"
            )
        if cruda.startswith("{"):
            datos = json.loads(cruda)
            return str(datos["access_token"])
        return cruda

    def _cab(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "LinkedIn-Version": self.config.linkedin_api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    async def get(self, http: httpx.AsyncClient, token: str, ruta: str, **params: Any) -> Any:
        """Rest.li 2.0: la sintaxis estructurada ((), List(...), ':') va sin codificar y los
        URN dentro van codificados. httpx codificaría los paréntesis, así que la query se arma
        a mano; los valores llegan ya con los URN codificados (ver urn_codificado)."""
        query = "&".join(f"{k}={quote(str(v), safe='(),:%=')}" for k, v in params.items())
        # raw_path evita que httpx vuelva a codificar los %3A de los URN (→ %253A)
        ruta_cruda = f"/rest/{ruta}" + (f"?{query}" if query else "")
        url = httpx.URL(scheme="https", host="api.linkedin.com", raw_path=ruta_cruda.encode())
        r = await http.get(url, headers=self._cab(token))
        if r.status_code >= 400:
            raise LinkedInError(f"LinkedIn {ruta} → {r.status_code}: {r.text[:300]}")
        return r.json()


def urn_codificado(urn: str) -> str:
    return quote(urn, safe="")


@registrar
class ConectorLinkedIn(LinkedInBase):
    codigo = "linkedin"
    plataforma = "linkedin"
    METRICAS_NATIVAS = (
        "followerCount",
        "followerGains",
        "impressionCount",
        "uniqueImpressionsCount",
        "likeCount",
        "commentCount",
        "shareCount",
        "clickCount",
        "engagement",
        "interactions",
        "allPageViews",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self._token()
        urn = urn_codificado(self.cuenta.id_externo)
        ti = intervalo(desde, hasta)
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            # Rest.li 2.0: los URN en la ruta y dentro de List(...) van codificados (%3A)
            red = await self.get(
                http,
                token,
                f"networkSizes/{urn}",
                edgeType="COMPANY_FOLLOWED_BY_MEMBER",
            )
            seguidores = await self.get(
                http,
                token,
                "organizationalEntityFollowerStatistics",
                q="organizationalEntity",
                organizationalEntity=urn,
                timeIntervals=ti,
            )
            compartidos = await self.get(
                http,
                token,
                "organizationalEntityShareStatistics",
                q="organizationalEntity",
                organizationalEntity=urn,
                timeIntervals=ti,
            )
            try:
                pagina = await self.get(
                    http,
                    token,
                    "organizationPageStatistics",
                    q="organization",
                    organization=urn,
                    timeIntervals=ti,
                )
            except LinkedInError as e:  # las vistas de página no bloquean el resto
                pagina = {"error": str(e)[:200], "elements": []}
        return [
            {"tipo": "seguidores_total", "fecha": hasta.isoformat(), **red},
            {"tipo": "seguidores", **seguidores},
            {"tipo": "compartidos", **compartidos},
            {"tipo": "pagina", **pagina},
        ]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []

        def emitir(fecha: date, nativa: str, valor: Any) -> None:
            m = self.mapear(nativa, valor)
            if m is not None:
                salida.append((fecha, m[0], m[1]))

        for bloque in payload:
            tipo = bloque.get("tipo")
            if tipo == "seguidores_total" and bloque.get("firstDegreeSize") is not None:
                emitir(
                    date.fromisoformat(bloque["fecha"]), "followerCount", bloque["firstDegreeSize"]
                )
            elif tipo == "seguidores":
                for e in bloque.get("elements", []):
                    f = _dia((e.get("timeRange") or {}).get("start"))
                    g = e.get("followerGains") or {}
                    if f:
                        emitir(
                            f,
                            "followerGains",
                            int(g.get("organicFollowerGain", 0))
                            + int(g.get("paidFollowerGain", 0)),
                        )
            elif tipo == "compartidos":
                for e in bloque.get("elements", []):
                    f = _dia((e.get("timeRange") or {}).get("start"))
                    s = e.get("totalShareStatistics") or {}
                    if not f:
                        continue
                    for nativa in (
                        "impressionCount",
                        "uniqueImpressionsCount",
                        "likeCount",
                        "commentCount",
                        "shareCount",
                        "clickCount",
                        "engagement",
                    ):
                        if nativa in s:
                            emitir(f, nativa, s[nativa])
                    emitir(
                        f,
                        "interactions",
                        sum(
                            int(s.get(k, 0))
                            for k in ("likeCount", "commentCount", "shareCount", "clickCount")
                        ),
                    )
            elif tipo == "pagina":
                for e in bloque.get("elements", []):
                    f = _dia((e.get("timeRange") or {}).get("start"))
                    vistas = (
                        ((e.get("totalPageStatistics") or {}).get("views") or {}).get(
                            "allPageViews"
                        )
                        or {}
                    ).get("pageViews")
                    if f and vistas is not None:
                        emitir(f, "allPageViews", vistas)
        return salida


@registrar_publicaciones
class ConectorLinkedInPublicaciones(LinkedInBase, ConectorPublicacionesBase):
    codigo = "linkedin_publicaciones"
    plataforma = "linkedin"
    METRICAS_NATIVAS = (
        "impressionCount",
        "uniqueImpressionsCount",
        "likeCount",
        "commentCount",
        "shareCount",
        "clickCount",
        "engagement",
        "interactions",
    )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self._token()
        urn = urn_codificado(self.cuenta.id_externo)
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            cuerpo = await self.get(
                http, token, "posts", q="author", author=urn, count=50, sortBy="LAST_MODIFIED"
            )
            posts = [
                p
                for p in cuerpo.get("elements", [])
                if (f := _dia(p.get("publishedAt") or p.get("createdAt"))) and f >= desde
            ]
            stats: dict[str, Any] = {}
            # Las estadísticas se piden por tipo de URN: shares=List(...) o ugcPosts=List(...)
            grupos = {
                "ugcPosts": [p for p in posts if p["id"].startswith("urn:li:ugcPost")],
                "shares": [p for p in posts if p["id"].startswith("urn:li:share")],
            }
            lotes = [
                (campo, lista[i : i + 20])
                for campo, lista in grupos.items()
                for i in range(0, len(lista), 20)
            ]
            for campo, lote in lotes:
                urns = ",".join(urn_codificado(p["id"]) for p in lote)
                try:
                    rs = await self.get(
                        http,
                        token,
                        "organizationalEntityShareStatistics",
                        q="organizationalEntity",
                        organizationalEntity=urn,
                        **{campo: f"List({urns})"},
                    )
                    for e in rs.get("elements", []):
                        clave = e.get("share") or e.get("ugcPost")
                        if clave:
                            stats[str(clave)] = e.get("totalShareStatistics") or {}
                except LinkedInError as e:
                    stats.setdefault("_errores", []).append(str(e)[:200])
        return [{"tipo": "posts", "posts": posts, "stats": stats}]

    def normalizar_publicaciones(self, payload: list[dict[str, Any]]) -> list[Publicacion]:
        salida = []
        for bloque in payload:
            stats = bloque.get("stats", {})
            for p in bloque.get("posts", []):
                s = dict(stats.get(p["id"], {}))
                if s:
                    s["interactions"] = sum(
                        int(s.get(k, 0))
                        for k in ("likeCount", "commentCount", "shareCount", "clickCount")
                    )
                contenido = p.get("content") or {}
                tipo = (
                    "articulo"
                    if "article" in contenido
                    else (
                        "video"
                        if "media" in contenido
                        and str(contenido["media"].get("id", "")).startswith("urn:li:video")
                        else "imagen"
                        if "media" in contenido or "multiImage" in contenido
                        else "texto"
                    )
                )
                pub_ms = p.get("publishedAt") or p.get("createdAt")
                salida.append(
                    Publicacion(
                        id_externo=str(p["id"]),
                        tipo=tipo,
                        publicado_en=datetime.fromtimestamp(pub_ms / 1000, tz=UTC)
                        if pub_ms
                        else None,
                        permalink=f"https://www.linkedin.com/feed/update/{p['id']}",
                        caption=p.get("commentary"),
                        thumbnail_url=None,
                        metricas=self.metricas_canonicas(s),
                    )
                )
        return salida

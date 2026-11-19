"""Conector nativo de TikTok (TikTok for Developers: Login Kit + Display API v2).

Reemplaza al puente de Metricool para las cuentas conectadas con «Conectar con TikTok».
id_externo = open_id de la cuenta. Credencial cifrada: JSON con access_token (24 h),
refresh_token (365 días), access_expira_en y open_id (ver conectar.credencial_tiktok).

Qué entrega Display API y cómo se guarda:
- Cuenta: solo totales "de por vida" (seguidores, me gusta acumulados, número de videos).
  No hay series diarias: cada corrida guarda la foto del día en la fecha `hasta` (ayer), igual
  que el total de seguidores de LinkedIn. La ventana de re-sync de 28 días no aplica a una foto:
  no se puede reconstruir el pasado, por eso el histórico empieza el día que se conecta.
- Publicaciones: los videos recientes con vistas, me gusta, comentarios y compartidos.
No entrega alcance, impresiones de cuenta ni visitas al perfil (eso es TikTok API for Business).
Métricas nativas → seed 'tiktok' (nombres de la API).
"""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from api.etl.conector_base import ConectorBase, Fila
from api.etl.conector_publicaciones import ConectorPublicacionesBase, Publicacion
from api.etl.registro import registrar, registrar_publicaciones

API = "https://open.tiktokapis.com/v2"
TOKEN = f"{API}/oauth/token/"
CAMPOS_CUENTA = (
    "open_id,display_name,username,follower_count,following_count,likes_count,video_count"
)
CAMPOS_VIDEO = (
    "id,create_time,cover_image_url,share_url,video_description,title,duration,"
    "view_count,like_count,comment_count,share_count"
)
MAX_PAGINAS_VIDEOS = 10  # 20 videos por página
MARGEN_RENOVACION = timedelta(minutes=10)


class TikTokError(RuntimeError):
    pass


def _verificar(r: httpx.Response, que: str) -> dict[str, Any]:
    """TikTok responde {"data": ..., "error": {"code": "ok", ...}}; cualquier otro code es error."""
    try:
        cuerpo: dict[str, Any] = r.json()
    except ValueError as e:
        raise TikTokError(f"TikTok {que} → HTTP {r.status_code} sin JSON") from e
    error = cuerpo.get("error") or {}
    if r.status_code >= 400 or error.get("code") not in (None, "ok"):
        raise TikTokError(
            f"TikTok {que} → {r.status_code}: {error.get('code')} {error.get('message', '')}"[:300]
        )
    return cuerpo


class TikTokBase(ConectorBase):
    timeout_seg: float = 60

    async def _credencial(self) -> dict[str, Any]:
        if not self.config.clave_cifrado:
            raise TikTokError("CLAVE_CIFRADO no configurada")
        cruda = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
        if not cruda or not cruda.startswith("{"):
            raise TikTokError(
                "La cuenta no tiene token de TikTok: conéctala con «Conectar con TikTok» "
                "desde el admin (esta cuenta venía del puente Metricool)"
            )
        datos: dict[str, Any] = json.loads(cruda)
        return datos

    async def _token(self, http: httpx.AsyncClient) -> str:
        """Access token vigente. Si vence en menos de 10 minutos lo renueva y guarda la
        credencial nueva ANTES de usarla: TikTok puede rotar el refresh token y el conector de
        publicaciones corre después con lo que quedó guardado."""
        cred = await self._credencial()
        expira = cred.get("access_expira_en")
        if expira and datetime.fromisoformat(expira) - MARGEN_RENOVACION > datetime.now(UTC):
            return str(cred["access_token"])
        if not self.config.tiktok_client_key or not self.config.tiktok_client_secret:
            raise TikTokError("TIKTOK_CLIENT_KEY o TIKTOK_CLIENT_SECRET no configurados")
        r = await http.post(
            TOKEN,
            data={
                "client_key": self.config.tiktok_client_key,
                "client_secret": self.config.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": cred["refresh_token"],
            },
        )
        try:
            nuevo: dict[str, Any] = r.json()
        except ValueError as e:
            raise TikTokError(f"TikTok renovar token → HTTP {r.status_code}") from e
        if r.status_code >= 400 or "access_token" not in nuevo:
            raise TikTokError(
                f"TikTok no renovó el token ({nuevo.get('error')}): reconecta la cuenta "
                "con «Conectar con TikTok»"
            )
        from api.admin.conectar import credencial_tiktok  # evita import circular

        guardar = credencial_tiktok({**cred, **nuevo})
        await self.repo.guardar_credencial(
            self.cuenta.id, json.dumps(guardar), self.config.clave_cifrado
        )
        return str(guardar["access_token"])

    @staticmethod
    def _cab(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


@registrar
class ConectorTikTok(TikTokBase):
    codigo = "tiktok"
    plataforma = "tiktok"
    METRICAS_NATIVAS = ("follower_count", "likes_count", "video_count")

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            token = await self._token(http)
            r = await http.get(
                f"{API}/user/info/", params={"fields": CAMPOS_CUENTA}, headers=self._cab(token)
            )
        usuario = (_verificar(r, "user/info").get("data") or {}).get("user") or {}
        return [{"tipo": "cuenta", "fecha": hasta.isoformat(), "user": usuario}]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            if bloque.get("tipo") != "cuenta":
                continue
            fecha = date.fromisoformat(bloque["fecha"])
            usuario = bloque.get("user") or {}
            for nativa in self.METRICAS_NATIVAS:
                if usuario.get(nativa) is None:
                    continue
                m = self.mapear(nativa, usuario[nativa])
                if m is not None:
                    salida.append((fecha, m[0], m[1]))
        return salida


@registrar_publicaciones
class ConectorTikTokPublicaciones(TikTokBase, ConectorPublicacionesBase):
    codigo = "tiktok_publicaciones"
    plataforma = "tiktok"
    METRICAS_NATIVAS = ("view_count", "like_count", "comment_count", "share_count", "engagement")

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        limite = int(datetime.combine(desde, datetime.min.time(), UTC).timestamp())
        videos: list[dict[str, Any]] = []
        cursor: int | None = None
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            token = await self._token(http)
            for _ in range(MAX_PAGINAS_VIDEOS):
                cuerpo: dict[str, Any] = {"max_count": 20}
                if cursor is not None:
                    cuerpo["cursor"] = cursor
                r = await http.post(
                    f"{API}/video/list/",
                    params={"fields": CAMPOS_VIDEO},
                    json=cuerpo,
                    headers=self._cab(token),
                )
                datos = _verificar(r, "video/list").get("data") or {}
                pagina = datos.get("videos") or []
                videos.extend(pagina)
                # Vienen del más nuevo al más viejo: se corta al pasar la ventana de re-sync
                viejo = min((int(v.get("create_time") or 0) for v in pagina), default=0)
                if not datos.get("has_more") or viejo < limite:
                    break
                cursor = datos.get("cursor")
        return [{"tipo": "videos", "videos": videos, "desde": desde.isoformat()}]

    def normalizar_publicaciones(self, payload: list[dict[str, Any]]) -> list[Publicacion]:
        salida: list[Publicacion] = []
        for bloque in payload:
            desde = date.fromisoformat(bloque.get("desde") or "1970-01-01")
            for v in bloque.get("videos", []):
                creado = (
                    datetime.fromtimestamp(int(v["create_time"]), tz=UTC)
                    if v.get("create_time")
                    else None
                )
                if creado is not None and creado.date() < desde:
                    continue
                nativas = {
                    k: v[k]
                    for k in ("view_count", "like_count", "comment_count", "share_count")
                    if v.get(k) is not None
                }
                if nativas:
                    nativas["engagement"] = sum(
                        int(nativas.get(k, 0))
                        for k in ("like_count", "comment_count", "share_count")
                    )
                salida.append(
                    Publicacion(
                        id_externo=str(v["id"]),
                        tipo="video",
                        publicado_en=creado,
                        permalink=v.get("share_url"),
                        caption=v.get("title") or v.get("video_description"),
                        thumbnail_url=v.get("cover_image_url"),
                        metricas=self.metricas_canonicas(nativas),
                    )
                )
        return salida

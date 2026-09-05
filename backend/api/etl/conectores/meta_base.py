"""Base común para los conectores de Meta (Graph API): FB orgánico, IG orgánico y Meta Ads.

Decisiones (PT-05):
  * El token del System User (no expira) vive cifrado en `credencial_cifrada` de cada cuenta.
    META_SYSTEM_USER_TOKEN en el ambiente es solo respaldo.
  * Toda llamada lleva `appsecret_proof` (HMAC del token con el app secret), así el token no
    sirve fuera de nuestro servidor.
  * Los tokens NUNCA se guardan en raw_payloads: los payloads que devuelven `extraer` son solo
    las respuestas de insights.
"""

import hashlib
import hmac
from datetime import date, timedelta
from typing import Any

import httpx

from api.etl.conector_base import ConectorBase


class GraphAPIError(Exception):
    """Error devuelto por el Graph API de Meta."""


class ConectorMetaBase(ConectorBase):
    timeout_seg: float = 60

    @property
    def url_base(self) -> str:
        return f"https://graph.facebook.com/{self.config.meta_api_version}"

    async def token_acceso(self) -> str:
        if self.config.clave_cifrado:
            propio = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
            if propio:
                return propio
        if not self.config.meta_system_user_token:
            raise RuntimeError("La cuenta no tiene credencial y META_SYSTEM_USER_TOKEN está vacío")
        return self.config.meta_system_user_token

    def _prueba_secreto(self, token: str) -> dict[str, str]:
        if not self.config.meta_app_secret:
            return {}
        firma = hmac.new(
            self.config.meta_app_secret.encode(), token.encode(), hashlib.sha256
        ).hexdigest()
        return {"appsecret_proof": firma}

    async def get(self, ruta: str, token: str, **params: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            respuesta = await http.get(
                f"{self.url_base}/{ruta}",
                params={"access_token": token, **self._prueba_secreto(token), **params},
            )
        datos: dict[str, Any] = respuesta.json()
        if respuesta.status_code >= 400 or "error" in datos:
            err = datos.get("error", {})
            raise GraphAPIError(
                f"{ruta}: ({err.get('code')}) {err.get('message', respuesta.text[:200])}"
            )
        return datos

    async def get_paginado(self, ruta: str, token: str, **params: Any) -> list[dict[str, Any]]:
        """Sigue `paging.next` hasta agotar. Devuelve la lista de `data` concatenada."""
        filas: list[dict[str, Any]] = []
        datos = await self.get(ruta, token, **params)
        filas.extend(datos.get("data", []))
        siguiente = datos.get("paging", {}).get("next")
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            while siguiente:
                r = await http.get(siguiente)
                pagina: dict[str, Any] = r.json()
                if "error" in pagina:
                    raise GraphAPIError(pagina["error"].get("message", ""))
                filas.extend(pagina.get("data", []))
                siguiente = pagina.get("paging", {}).get("next")
        return filas

    @staticmethod
    def dias(desde: date, hasta: date) -> list[date]:
        return [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]

    @staticmethod
    def fecha_de_end_time(end_time: str) -> date:
        """Meta reporta el día con `end_time` = fin del período (07:00 UTC del día siguiente)."""
        return date.fromisoformat(end_time[:10]) - timedelta(days=1)

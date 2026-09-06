"""Base común para conectores de Google con Service Account (GA4, Search Console).

Decisión (PT-04): el Service Account es una credencial de la agencia, no del cliente, así
que vive en GOOGLE_SERVICE_ACCOUNT_JSON. El cliente solo otorga acceso de lectura a ese
correo en su propiedad. Si una cuenta tiene `credencial_cifrada`, esta tiene prioridad
(permite un SA distinto por cliente sin tocar código).
"""

import asyncio
import json
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from api.etl.conector_base import ConectorBase


def _token_sincrono(
    credencial: str, scopes: tuple[str, ...], client_id: str = "", client_secret: str = ""
) -> str:
    """Acepta un Service Account (JSON de Google) o {"tipo":"oauth","refresh_token":...}."""
    datos = json.loads(credencial)
    if datos.get("tipo") == "oauth":
        from google.oauth2.credentials import Credentials

        credenciales = Credentials(  # type: ignore[no-untyped-call]
            None,
            refresh_token=datos["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=list(scopes),
        )
    else:
        credenciales = service_account.Credentials.from_service_account_info(  # type: ignore[no-untyped-call]
            datos, scopes=list(scopes)
        )
    credenciales.refresh(Request())  # type: ignore[no-untyped-call]
    return str(credenciales.token)


class ConectorGoogleBase(ConectorBase):
    scopes: tuple[str, ...] = ()
    timeout_seg: float = 60

    async def _service_account_json(self) -> str:
        if self.config.clave_cifrado:
            propia = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
            if propia:
                return propia
        if not self.config.google_service_account_json:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON no configurado")
        return self.config.google_service_account_json

    async def token_acceso(self) -> str:
        credencial = await self._service_account_json()
        return await asyncio.to_thread(
            _token_sincrono,
            credencial,
            self.scopes,
            self.config.google_oauth_client_id,
            self.config.google_oauth_client_secret,
        )

    async def post_json(self, url: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
        token = await self.token_acceso()
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            respuesta = await http.post(
                url, json=cuerpo, headers={"Authorization": f"Bearer {token}"}
            )
        respuesta.raise_for_status()
        datos: dict[str, Any] = respuesta.json()
        return datos

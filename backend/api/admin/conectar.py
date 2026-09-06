"""Botones "Conectar con Meta / Google" del admin.

Flujo:
  1. GET /admin/conectar/{proveedor}/iniciar?cliente_id → URL del proveedor con `state` firmado.
  2. El proveedor vuelve a GET /admin/conectar/{proveedor}/retorno?code&state (sin cabecera de
     autorización: es el navegador quien llega). Se valida el state, se cambia el código por
     token, se listan los activos visibles y se guarda todo cifrado en conexiones_oauth.
  3. El navegador vuelve al admin con ?conexion=ID; el equipo elige activos y
     POST /admin/conexiones/{id}/activar crea las cuentas_conectadas con el token cifrado.

Los tokens jamás salen al navegador. El `state` va firmado con PDF_SECRET (HS256, 10 min)
y ata la conexión al cliente y al usuario que la inició.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from api.config import Configuracion

DURACION_ESTADO = timedelta(minutes=10)
PROVEEDORES = ("meta", "google", "linkedin")

# Community Management API: lectura de páginas de empresa que el usuario administra.
SCOPES_LINKEDIN = ("r_organization_admin", "r_organization_social", "rw_organization_admin")

SCOPES_GOOGLE = (
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)


class ConexionError(Exception):
    pass


@dataclass(frozen=True)
class Activo:
    """Algo que se puede convertir en una cuenta_conectada."""

    plataforma: str
    id_externo: str
    nombre: str
    extra: dict[str, Any]

    def como_dict(self) -> dict[str, Any]:
        return {
            "plataforma": self.plataforma,
            "id_externo": self.id_externo,
            "nombre": self.nombre,
            "extra": self.extra,
        }


# ---- state ------------------------------------------------------------------


def emitir_estado(config: Configuracion, proveedor: str, cliente_id: int, email: str) -> str:
    if not config.pdf_secret:
        raise ConexionError("PDF_SECRET no configurado (firma del state)")
    ahora = datetime.now(UTC)
    return jwt.encode(
        {
            "tipo": "oauth",
            "proveedor": proveedor,
            "cliente_id": cliente_id,
            "email": email,
            "iat": ahora,
            "exp": ahora + DURACION_ESTADO,
        },
        config.pdf_secret,
        algorithm="HS256",
    )


def verificar_estado(config: Configuracion, estado: str, proveedor: str) -> tuple[int, str]:
    try:
        claims: dict[str, Any] = jwt.decode(estado, config.pdf_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise ConexionError(f"state inválido o vencido: {e}") from e
    if claims.get("tipo") != "oauth" or claims.get("proveedor") != proveedor:
        raise ConexionError("state no corresponde a este proveedor")
    return int(claims["cliente_id"]), str(claims["email"])


def url_retorno(config: Configuracion, proveedor: str) -> str:
    return f"{config.api_url.rstrip('/')}/admin/conectar/{proveedor}/retorno"


# ---- URLs de inicio ------------------------------------------------------------


def url_inicio(config: Configuracion, proveedor: str, estado: str) -> str:
    if proveedor == "meta":
        if not config.meta_app_id or not config.meta_login_config_id:
            raise ConexionError("META_APP_ID o META_LOGIN_CONFIG_ID no configurados")
        return (
            "https://www.facebook.com/"
            + config.meta_api_version
            + "/dialog/oauth?"
            + urlencode(
                {
                    "client_id": config.meta_app_id,
                    "config_id": config.meta_login_config_id,
                    "redirect_uri": url_retorno(config, "meta"),
                    "state": estado,
                    "response_type": "code",
                    "override_default_response_type": "true",
                }
            )
        )
    if proveedor == "google":
        if not config.google_oauth_client_id:
            raise ConexionError("GOOGLE_OAUTH_CLIENT_ID no configurado")
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
            {
                "client_id": config.google_oauth_client_id,
                "redirect_uri": url_retorno(config, "google"),
                "response_type": "code",
                "scope": " ".join(SCOPES_GOOGLE),
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "state": estado,
            }
        )
    if proveedor == "linkedin":
        if not config.linkedin_client_id:
            raise ConexionError("LINKEDIN_CLIENT_ID no configurado")
        return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(
            {
                "response_type": "code",
                "client_id": config.linkedin_client_id,
                "redirect_uri": url_retorno(config, "linkedin"),
                "state": estado,
                "scope": " ".join(SCOPES_LINKEDIN),
            }
        )
    raise ConexionError(f"Proveedor desconocido: {proveedor}")


# ---- intercambio de código y listado de activos ---------------------------------


async def intercambiar_codigo(config: Configuracion, proveedor: str, codigo: str) -> dict[str, Any]:
    """Devuelve el token tal como lo entrega el proveedor (dict con access_token, etc.)."""
    async with httpx.AsyncClient(timeout=30) as http:
        if proveedor == "meta":
            r = await http.get(
                f"https://graph.facebook.com/{config.meta_api_version}/oauth/access_token",
                params={
                    "client_id": config.meta_app_id,
                    "client_secret": config.meta_app_secret,
                    "redirect_uri": url_retorno(config, "meta"),
                    "code": codigo,
                },
            )
        elif proveedor == "linkedin":
            r = await http.post(
                "https://www.linkedin.com/oauth/v2/accessToken",
                data={
                    "grant_type": "authorization_code",
                    "code": codigo,
                    "client_id": config.linkedin_client_id,
                    "client_secret": config.linkedin_client_secret,
                    "redirect_uri": url_retorno(config, "linkedin"),
                },
            )
        else:
            r = await http.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": config.google_oauth_client_id,
                    "client_secret": config.google_oauth_client_secret,
                    "redirect_uri": url_retorno(config, "google"),
                    "grant_type": "authorization_code",
                    "code": codigo,
                },
            )
    datos: dict[str, Any] = r.json()
    if r.status_code >= 400 or "access_token" not in datos:
        raise ConexionError(f"{proveedor} rechazó el código: {json.dumps(datos)[:300]}")
    return datos


async def listar_activos(
    config: Configuracion, proveedor: str, token: dict[str, Any]
) -> list[Activo]:
    acceso = str(token["access_token"])
    if proveedor == "meta":
        return await _activos_meta(config, acceso)
    if proveedor == "linkedin":
        return await _activos_linkedin(acceso)
    return await _activos_google(acceso)


async def _activos_linkedin(acceso: str) -> list[Activo]:
    """Páginas de empresa donde el usuario es administrador (organizationAcls)."""
    cab = {
        "Authorization": f"Bearer {acceso}",
        "LinkedIn-Version": "202409",
        "X-Restli-Protocol-Version": "2.0.0",
    }
    activos: list[Activo] = []
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(
            "https://api.linkedin.com/rest/organizationAcls",
            params={
                "q": "roleAssignee",
                "role": "ADMINISTRATOR",
                "state": "APPROVED",
                "projection": "(elements*(organization~(localizedName)))",
            },
            headers=cab,
        )
        if r.status_code >= 400:
            raise ConexionError(f"LinkedIn no permitió listar páginas: {r.text[:200]}")
        for e in r.json().get("elements", []):
            urn = e.get("organization")
            nombre = (e.get("organization~") or {}).get("localizedName", urn)
            if urn:
                activos.append(Activo("linkedin", urn, nombre, {}))
    return activos


async def _activos_meta(config: Configuracion, acceso: str) -> list[Activo]:
    base = f"https://graph.facebook.com/{config.meta_api_version}"
    activos: list[Activo] = []
    async with httpx.AsyncClient(timeout=30) as http:
        paginas = (
            await http.get(
                f"{base}/me/accounts",
                params={
                    "access_token": acceso,
                    "limit": 100,
                    "fields": "id,name,instagram_business_account{id,username}",
                },
            )
        ).json()
        for p in paginas.get("data", []):
            activos.append(Activo("meta_fb", p["id"], p["name"], {}))
            ig = p.get("instagram_business_account")
            if ig:
                activos.append(
                    Activo(
                        "meta_ig", ig["id"], f"@{ig.get('username', ig['id'])}", {"pagina": p["id"]}
                    )
                )
        anuncios = (
            await http.get(
                f"{base}/me/adaccounts",
                params={"access_token": acceso, "limit": 100, "fields": "id,name"},
            )
        ).json()
        for a in anuncios.get("data", []):
            activos.append(Activo("meta_ads", a["id"], a.get("name", a["id"]), {}))
    return activos


async def _activos_google(acceso: str) -> list[Activo]:
    cab = {"Authorization": f"Bearer {acceso}"}
    activos: list[Activo] = []
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(
            "https://analyticsadmin.googleapis.com/v1beta/accountSummaries", headers=cab
        )
        for cuenta in r.json().get("accountSummaries", []):
            for prop in cuenta.get("propertySummaries", []):
                activos.append(
                    Activo(
                        "ga4",
                        prop["property"].split("/")[-1],
                        f"{prop.get('displayName')} ({cuenta.get('displayName')})",
                        {},
                    )
                )
        r = await http.get("https://www.googleapis.com/webmasters/v3/sites", headers=cab)
        for sitio in r.json().get("siteEntry", []):
            if sitio.get("permissionLevel") != "siteUnverifiedUser":
                activos.append(Activo("gsc", sitio["siteUrl"], sitio["siteUrl"], {}))
        r = await http.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "snippet", "mine": "true"},
            headers=cab,
        )
        for canal in r.json().get("items", []):
            activos.append(Activo("youtube", canal["id"], canal["snippet"]["title"], {}))
    return activos


def credencial_para_guardar(proveedor: str, token: dict[str, Any]) -> str:
    """Lo que se cifra en cuentas_conectadas. Meta: el token. Google: JSON con refresh_token."""
    if proveedor in ("meta", "linkedin"):
        return str(token["access_token"])
    if not token.get("refresh_token"):
        raise ConexionError("Google no devolvió refresh_token; repite la conexión")
    return json.dumps({"tipo": "oauth", "refresh_token": token["refresh_token"]})


def expiracion(proveedor: str, token: dict[str, Any]) -> datetime | None:
    seg = token.get("expires_in")
    if proveedor == "google" or not seg:
        return None  # refresh token: no expira; Meta business token: según respuesta
    return datetime.now(UTC) + timedelta(seconds=int(seg))

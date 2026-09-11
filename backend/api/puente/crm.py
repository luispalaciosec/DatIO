"""Adaptadores de CRM (PT-16). Una interfaz, dos implementaciones:

- PrometIO (CRM propio de Geeks): API FastAPI autenticada con JWT de Supabase. DatIO entra
  con un usuario de servicio (PROMETIO_EMAIL / PROMETIO_PASSWORD, equipo 'ventas') y crea la
  oportunidad (contacto + empresa) y una actividad programada con la evidencia.
- HubSpot: token de app privada por cliente (cifrado). Crea un deal asociado a la company y
  una task con la evidencia.

Ningún adaptador decide cuándo disparar: eso es de disparadores.py.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from api.config import Configuracion

log = logging.getLogger(__name__)


class CrmError(RuntimeError):
    pass


@dataclass
class Accion:
    """Lo que un disparador quiere crear en el CRM."""

    codigo: str
    tipo: str  # 'oportunidad' | 'tarea'
    titulo: str
    evidencia: str
    valor: float | None = None
    prioridad: str = "media"


@dataclass
class ResultadoCrm:
    objeto_ref: str
    url: str | None = None


class CrmBase:
    proveedor = ""

    async def probar(self) -> dict[str, Any]:
        raise NotImplementedError

    async def ejecutar(
        self, accion: Accion, empresa_ref: str, contacto_ref: str | None
    ) -> ResultadoCrm:
        raise NotImplementedError


# ---- PrometIO ---------------------------------------------------------------------------


class CrmPrometio(CrmBase):
    proveedor = "prometio"

    def __init__(self, config: Configuracion) -> None:
        self.config = config
        self._jwt: str | None = None
        self._expira: datetime = datetime.min.replace(tzinfo=UTC)

    def configurado(self) -> bool:
        c = self.config
        return bool(
            c.prometio_url
            and c.prometio_supabase_url
            and c.prometio_supabase_anon_key
            and c.prometio_email
            and c.prometio_password
        )

    async def _token(self, http: httpx.AsyncClient) -> str:
        if self._jwt and datetime.now(UTC) < self._expira:
            return self._jwt
        if not self.configurado():
            raise CrmError("PrometIO no configurado (PROMETIO_URL, SUPABASE y usuario de servicio)")
        r = await http.post(
            f"{self.config.prometio_supabase_url.rstrip('/')}/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": self.config.prometio_supabase_anon_key},
            json={"email": self.config.prometio_email, "password": self.config.prometio_password},
        )
        if r.status_code >= 400:
            raise CrmError(f"PrometIO: login rechazado ({r.status_code}): {r.text[:200]}")
        datos = r.json()
        self._jwt = str(datos["access_token"])
        self._expira = datetime.now(UTC) + timedelta(
            seconds=int(datos.get("expires_in", 3600)) - 60
        )
        return self._jwt

    async def _llamar(self, http: httpx.AsyncClient, metodo: str, ruta: str, **kw: Any) -> Any:
        cab = {"Authorization": f"Bearer {await self._token(http)}"}
        r = await http.request(
            metodo, f"{self.config.prometio_url.rstrip('/')}{ruta}", headers=cab, **kw
        )
        if r.status_code >= 400:
            raise CrmError(f"PrometIO {metodo} {ruta} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    async def probar(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as http:
            empresas = await self._llamar(http, "GET", "/empresas")
        return {"ok": True, "empresas": len(empresas or [])}

    async def empresas(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as http:
            empresas = await self._llamar(http, "GET", "/empresas") or []
            contactos = await self._llamar(http, "GET", "/contactos") or []
        por_empresa: dict[str, list[dict[str, Any]]] = {}
        for c in contactos:
            if c.get("empresa_id"):
                por_empresa.setdefault(str(c["empresa_id"]), []).append(
                    {
                        "id": str(c["id"]),
                        "nombre": c.get("nombre_completo"),
                        "email": c.get("email_trabajo"),
                    }
                )
        return [
            {
                "id": str(e["id"]),
                "nombre": e.get("nombre"),
                "contactos": por_empresa.get(str(e["id"]), []),
            }
            for e in empresas
        ]

    async def ejecutar(
        self, accion: Accion, empresa_ref: str, contacto_ref: str | None
    ) -> ResultadoCrm:
        if not contacto_ref:
            raise CrmError("PrometIO exige un contacto para crear la oportunidad")
        manana = (datetime.now(UTC) + timedelta(days=1)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        async with httpx.AsyncClient(timeout=30) as http:
            if accion.tipo == "oportunidad":
                op = await self._llamar(
                    http,
                    "POST",
                    "/oportunidades",
                    json={
                        "contacto_id": contacto_ref,
                        "empresa_id": empresa_ref,
                        "valor_referencial": accion.valor,
                    },
                )
                ref = str(op["id"])
                await self._llamar(
                    http,
                    "POST",
                    "/actividades",
                    json={
                        "tipo": "tarea_interna",
                        "oportunidad_id": ref,
                        "programada_para": manana.isoformat(),
                        "feedback": f"[DatIO] {accion.titulo}\n\n{accion.evidencia}",
                    },
                )
                return ResultadoCrm(
                    ref,
                    f"{self.config.prometio_frontend_url}/oportunidades/{ref}"
                    if self.config.prometio_frontend_url
                    else None,
                )
            act = await self._llamar(
                http,
                "POST",
                "/actividades",
                json={
                    "tipo": "tarea_interna",
                    "contacto_id": contacto_ref,
                    "programada_para": manana.isoformat(),
                    "feedback": f"[DatIO] {accion.titulo}\n\n{accion.evidencia}",
                },
            )
            return ResultadoCrm(str(act["id"]))


# ---- HubSpot ----------------------------------------------------------------------------

HUBSPOT = "https://api.hubapi.com"
ASOC_DEAL_COMPANY = 5
ASOC_TASK_COMPANY = 192


class CrmHubspot(CrmBase):
    proveedor = "hubspot"

    def __init__(self, token: str, config_cliente: dict[str, Any] | None = None) -> None:
        self.token = token
        self.cfg = config_cliente or {}

    def _cab(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def _post(
        self, http: httpx.AsyncClient, ruta: str, cuerpo: dict[str, Any]
    ) -> dict[str, Any]:
        r = await http.post(f"{HUBSPOT}{ruta}", headers=self._cab(), json=cuerpo)
        if r.status_code >= 400:
            raise CrmError(f"HubSpot {ruta} → {r.status_code}: {r.text[:300]}")
        return dict(r.json())

    async def probar(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(
                f"{HUBSPOT}/crm/v3/objects/companies", headers=self._cab(), params={"limit": 1}
            )
            if r.status_code >= 400:
                raise CrmError(f"HubSpot rechazó el token ({r.status_code}): {r.text[:200]}")
            p = await http.get(f"{HUBSPOT}/crm/v3/pipelines/deals", headers=self._cab())
        pipelines = [
            {
                "id": x["id"],
                "label": x["label"],
                "etapas": [{"id": s["id"], "label": s["label"]} for s in x.get("stages", [])],
            }
            for x in (p.json().get("results", []) if p.status_code < 400 else [])
        ]
        return {"ok": True, "pipelines": pipelines}

    async def empresas(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(
                f"{HUBSPOT}/crm/v3/objects/companies",
                headers=self._cab(),
                params={"limit": 100, "properties": "name,domain"},
            )
            if r.status_code >= 400:
                raise CrmError(f"HubSpot companies → {r.status_code}")
        return [
            {
                "id": str(c["id"]),
                "nombre": c["properties"].get("name") or c["properties"].get("domain"),
                "contactos": [],
            }
            for c in r.json().get("results", [])
        ]

    async def ejecutar(
        self, accion: Accion, empresa_ref: str, contacto_ref: str | None
    ) -> ResultadoCrm:
        ahora_ms = int(datetime.now(UTC).timestamp() * 1000)
        async with httpx.AsyncClient(timeout=30) as http:
            if accion.tipo == "oportunidad":
                props: dict[str, Any] = {
                    "dealname": accion.titulo,
                    "description": accion.evidencia,
                    "dealstage": self.cfg.get("dealstage", "appointmentscheduled"),
                    "pipeline": self.cfg.get("pipeline", "default"),
                }
                if accion.valor is not None:
                    props["amount"] = str(round(accion.valor, 2))
                deal = await self._post(
                    http,
                    "/crm/v3/objects/deals",
                    {
                        "properties": props,
                        "associations": [
                            {
                                "to": {"id": empresa_ref},
                                "types": [
                                    {
                                        "associationCategory": "HUBSPOT_DEFINED",
                                        "associationTypeId": ASOC_DEAL_COMPANY,
                                    }
                                ],
                            }
                        ],
                    },
                )
                ref = str(deal["id"])
                return ResultadoCrm(
                    ref,
                    f"https://app.hubspot.com/contacts/{self.cfg.get('portal_id', '')}/deal/{ref}"
                    if self.cfg.get("portal_id")
                    else None,
                )
            tarea = await self._post(
                http,
                "/crm/v3/objects/tasks",
                {
                    "properties": {
                        "hs_task_subject": accion.titulo,
                        "hs_task_body": accion.evidencia,
                        "hs_task_status": "NOT_STARTED",
                        "hs_task_priority": "HIGH" if accion.prioridad == "alta" else "MEDIUM",
                        "hs_timestamp": str(ahora_ms + 86_400_000),
                    },
                    "associations": [
                        {
                            "to": {"id": empresa_ref},
                            "types": [
                                {
                                    "associationCategory": "HUBSPOT_DEFINED",
                                    "associationTypeId": ASOC_TASK_COMPANY,
                                }
                            ],
                        }
                    ],
                },
            )
            return ResultadoCrm(str(tarea["id"]))


def adaptador(
    config: Configuracion, proveedor: str | None, token: str | None, cfg: dict[str, Any] | None
) -> CrmBase | None:
    if proveedor == "prometio":
        return CrmPrometio(config)
    if proveedor == "hubspot":
        if not token:
            return None
        return CrmHubspot(token, cfg)
    return None

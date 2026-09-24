"""Conector Zoho CRM como fuente de datos (mismas métricas que PrometIO y HubSpot).

Credencial por cuenta (JSON cifrado): {"client_id", "client_secret", "refresh_token",
"dominio": "com" | "eu" | "in" | "com.au" | "jp"}. id_externo = id de la organización (informativo).
Refresh token → access token en accounts.zoho.{dominio}; datos en www.zohoapis.{dominio}
(API v6, requiere `fields`). Deals: Created_Time, Closing_Date, Stage, Amount; Contacts:
Created_Time. Etapas ganadas/perdidas se detectan por el nombre ("Closed Won", "Closed Lost",
"Ganado", "Perdido") o por la lista `etapas_ganadas`/`etapas_perdidas` de la credencial.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import httpx

from api.etl.conector_base import Fila
from api.etl.conectores.crm import ConectorCrmBase, _fecha
from api.etl.registro import registrar

GANADAS = ("closed won", "ganad", "won")
PERDIDAS = ("closed lost", "perdid", "lost")


def etapa_es(etapa: str, patrones: tuple[str, ...], lista: list[str] | None) -> bool:
    e = (etapa or "").strip().lower()
    if lista:
        return e in {x.strip().lower() for x in lista}
    return any(p in e for p in patrones)


@registrar
class ConectorZoho(ConectorCrmBase):
    codigo = "zoho"
    plataforma = "zoho"

    async def _credencial(self) -> dict[str, Any]:
        if not self.config.clave_cifrado:
            raise RuntimeError("CLAVE_CIFRADO no configurada")
        cruda = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
        if not cruda:
            raise RuntimeError("La cuenta de Zoho no tiene credencial (client, secret, refresh)")
        datos: dict[str, Any] = json.loads(cruda)
        faltan = {"client_id", "client_secret", "refresh_token"} - set(datos)
        if faltan:
            raise RuntimeError(f"Credencial de Zoho incompleta: faltan {sorted(faltan)}")
        datos.setdefault("dominio", "com")
        return datos

    async def _token(self, http: httpx.AsyncClient, cred: dict[str, Any]) -> str:
        r = await http.post(
            f"https://accounts.zoho.{cred['dominio']}/oauth/v2/token",
            params={
                "grant_type": "refresh_token",
                "client_id": cred["client_id"],
                "client_secret": cred["client_secret"],
                "refresh_token": cred["refresh_token"],
            },
        )
        r.raise_for_status()
        datos = r.json()
        if "access_token" not in datos:
            raise RuntimeError(f"Zoho rechazó el refresh token: {datos}")
        return str(datos["access_token"])

    async def _listar(
        self,
        http: httpx.AsyncClient,
        cred: dict[str, Any],
        token: str,
        modulo: str,
        campos: list[str],
        desde: date,
    ) -> list[dict[str, Any]]:
        base = f"https://www.zohoapis.{cred['dominio']}/crm/v6/{modulo}"
        cab = {"Authorization": f"Zoho-oauthtoken {token}"}
        salida: list[dict[str, Any]] = []
        pagina = 1
        limite = desde - timedelta(days=400)
        while pagina <= 25:
            r = await http.get(
                base,
                headers=cab,
                params={
                    "fields": ",".join(campos),
                    "per_page": 200,
                    "page": pagina,
                    "sort_by": "Created_Time",
                    "sort_order": "desc",
                },
            )
            if r.status_code == 204:
                break
            r.raise_for_status()
            cuerpo = r.json()
            lote = cuerpo.get("data", [])
            salida.extend(lote)
            ultimo = _fecha(lote[-1].get("Created_Time")) if lote else None
            if not cuerpo.get("info", {}).get("more_records") or (ultimo and ultimo < limite):
                break
            pagina += 1
        return salida

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        cred = await self._credencial()
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            token = await self._token(http, cred)
            deals = await self._listar(
                http,
                cred,
                token,
                "Deals",
                ["Created_Time", "Closing_Date", "Stage", "Amount"],
                desde,
            )
            contactos = await self._listar(http, cred, token, "Contacts", ["Created_Time"], desde)
        return [
            {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
                "deals": deals,
                "contactos": contactos,
                "etapas_ganadas": cred.get("etapas_ganadas"),
                "etapas_perdidas": cred.get("etapas_perdidas"),
            }
        ]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        b = payload[0]
        desde, hasta = date.fromisoformat(b["desde"]), date.fromisoformat(b["hasta"])
        contactos = [{"creado": _fecha(c.get("Created_Time"))} for c in b["contactos"]]
        ops = []
        for d in b["deals"]:
            etapa = str(d.get("Stage") or "")
            ganada = etapa_es(etapa, GANADAS, b.get("etapas_ganadas"))
            perdida = etapa_es(etapa, PERDIDAS, b.get("etapas_perdidas"))
            ops.append(
                {
                    "creado": _fecha(d.get("Created_Time")),
                    "cerrado": _fecha(d.get("Closing_Date")) if (ganada or perdida) else None,
                    "ganada": ganada,
                    "perdida": perdida,
                    "abierta": not (ganada or perdida),
                    "valor": Decimal(str(d.get("Amount") or 0)),
                }
            )
        return self._emitir(desde, hasta, contactos, ops)

"""Conectores CRM como fuente de datos: PrometIO y HubSpot.

Métricas diarias calculadas por el conector: contactos_nuevos, oportunidades_creadas,
oportunidades_ganadas/perdidas y valor_ganado (por fecha del evento), más dos de nivel
al día `hasta`: oportunidades_abiertas y valor_pipeline. El payload crudo son las listas de
objetos del CRM tal como llegaron.

PrometIO: usuario de servicio de la agencia (config PROMETIO_*); id_externo = organización
(informativo). HubSpot: token de app privada en la credencial cifrada de la cuenta;
id_externo = portal id (informativo).
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from api.etl.conector_base import ConectorBase, Fila
from api.etl.registro import registrar
from api.puente.crm import HUBSPOT, CrmPrometio

NATIVAS = (
    "contactos_nuevos",
    "oportunidades_creadas",
    "oportunidades_ganadas",
    "oportunidades_perdidas",
    "oportunidades_abiertas",
    "valor_ganado",
    "valor_pipeline",
)


def _fecha(v: Any) -> date | None:
    if not v:
        return None
    try:
        if isinstance(v, int | float):
            return datetime.fromtimestamp(v / 1000, tz=UTC).date()
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        return None


class ConectorCrmBase(ConectorBase):
    METRICAS_NATIVAS = NATIVAS
    timeout_seg: float = 60

    def _emitir(
        self,
        desde: date,
        hasta: date,
        contactos: list[dict[str, Any]],
        oportunidades: list[dict[str, Any]],
    ) -> list[Fila]:
        """contactos: [{creado}]; oportunidades: [{creado, cerrado, ganada, perdida, abierta,
        valor}]."""
        por_dia: dict[tuple[date, str], Decimal] = defaultdict(Decimal)
        for c in contactos:
            if c["creado"] and desde <= c["creado"] <= hasta:
                por_dia[(c["creado"], "contactos_nuevos")] += 1
        abiertas = Decimal(0)
        pipeline = Decimal(0)
        for o in oportunidades:
            if o["creado"] and desde <= o["creado"] <= hasta:
                por_dia[(o["creado"], "oportunidades_creadas")] += 1
            if o["cerrado"] and desde <= o["cerrado"] <= hasta:
                if o["ganada"]:
                    por_dia[(o["cerrado"], "oportunidades_ganadas")] += 1
                    por_dia[(o["cerrado"], "valor_ganado")] += o["valor"]
                elif o["perdida"]:
                    por_dia[(o["cerrado"], "oportunidades_perdidas")] += 1
            if o["abierta"]:
                abiertas += 1
                pipeline += o["valor"]
        # Contadores a cero los días sin eventos, para que las series no tengan huecos
        dia = desde
        while dia <= hasta:
            for nativa in (
                "contactos_nuevos",
                "oportunidades_creadas",
                "oportunidades_ganadas",
                "oportunidades_perdidas",
                "valor_ganado",
            ):
                por_dia.setdefault((dia, nativa), Decimal(0))
            dia += timedelta(days=1)
        por_dia[(hasta, "oportunidades_abiertas")] = abiertas
        por_dia[(hasta, "valor_pipeline")] = pipeline
        salida: list[Fila] = []
        for (fecha, nativa), valor in sorted(por_dia.items()):
            m = self.mapear(nativa, valor)
            if m:
                salida.append((fecha, m[0], m[1]))
        return salida


@registrar
class ConectorPrometio(ConectorCrmBase):
    codigo = "prometio"
    plataforma = "prometio"

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        crm = CrmPrometio(self.config)
        if not crm.configurado():
            raise RuntimeError("PrometIO no configurado (PROMETIO_URL y usuario de servicio)")
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            oportunidades = await crm._llamar(http, "GET", "/oportunidades?incluir_inactivas=true")
            contactos = await crm._llamar(http, "GET", "/contactos?incluir_inactivos=true")
        return [
            {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
                "oportunidades": oportunidades or [],
                "contactos": contactos or [],
            }
        ]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        b = payload[0]
        desde, hasta = date.fromisoformat(b["desde"]), date.fromisoformat(b["hasta"])
        contactos = [{"creado": _fecha(c.get("created_at"))} for c in b["contactos"]]
        ops = []
        for o in b["oportunidades"]:
            etapa = str(o.get("etapa") or "")
            valor = o.get("valor_cotizado") or o.get("valor_referencial") or 0
            ops.append(
                {
                    "creado": _fecha(o.get("created_at")),
                    "cerrado": _fecha(o.get("fecha_cierre")),
                    "ganada": etapa == "cierre_ganado",
                    "perdida": etapa == "cierre_perdido",
                    "abierta": bool(o.get("activo", True))
                    and etapa not in ("cierre_ganado", "cierre_perdido"),
                    "valor": Decimal(str(valor)),
                }
            )
        return self._emitir(desde, hasta, contactos, ops)


@registrar
class ConectorHubspot(ConectorCrmBase):
    codigo = "hubspot"
    plataforma = "hubspot"

    async def _token(self) -> str:
        if not self.config.clave_cifrado:
            raise RuntimeError("CLAVE_CIFRADO no configurada")
        t = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
        if not t:
            raise RuntimeError("La cuenta de HubSpot no tiene token de app privada")
        return t

    async def _buscar(
        self, http: httpx.AsyncClient, token: str, objeto: str, propiedades: list[str], desde: date
    ) -> list[dict[str, Any]]:
        salida: list[dict[str, Any]] = []
        despues: str | None = None
        inicio_ms = int(
            datetime.combine(desde - timedelta(days=400), datetime.min.time(), UTC).timestamp()
            * 1000
        )
        while True:
            cuerpo: dict[str, Any] = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "createdate",
                                "operator": "GTE",
                                "value": str(inicio_ms),
                            }
                        ]
                    }
                ],
                "properties": propiedades,
                "limit": 100,
                "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
            }
            if despues:
                cuerpo["after"] = despues
            r = await http.post(
                f"{HUBSPOT}/crm/v3/objects/{objeto}/search",
                json=cuerpo,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            datos = r.json()
            salida.extend(datos.get("results", []))
            despues = (datos.get("paging") or {}).get("next", {}).get("after")
            if not despues or len(salida) >= 10_000:
                break
        return salida

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            deals = await self._buscar(
                http,
                token,
                "deals",
                [
                    "createdate",
                    "closedate",
                    "amount",
                    "dealstage",
                    "hs_is_closed_won",
                    "hs_is_closed",
                ],
                desde,
            )
            contactos = await self._buscar(http, token, "contacts", ["createdate"], desde)
        return [
            {
                "desde": desde.isoformat(),
                "hasta": hasta.isoformat(),
                "deals": deals,
                "contactos": contactos,
            }
        ]

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        b = payload[0]
        desde, hasta = date.fromisoformat(b["desde"]), date.fromisoformat(b["hasta"])
        contactos = [
            {"creado": _fecha((c.get("properties") or {}).get("createdate"))}
            for c in b["contactos"]
        ]
        ops = []
        for d in b["deals"]:
            p = d.get("properties") or {}
            ganada = str(p.get("hs_is_closed_won")).lower() == "true"
            cerrada = str(p.get("hs_is_closed")).lower() == "true" or ganada
            ops.append(
                {
                    "creado": _fecha(p.get("createdate")),
                    "cerrado": _fecha(p.get("closedate")) if cerrada else None,
                    "ganada": ganada,
                    "perdida": cerrada and not ganada,
                    "abierta": not cerrada,
                    "valor": Decimal(str(p.get("amount") or 0)),
                }
            )
        return self._emitir(desde, hasta, contactos, ops)

"""Conector App Store Connect: informes de ventas diarios (descargas, actualizaciones,
compras y proceeds) y reseñas (calificaciones) de una app.

Credencial por cuenta (JSON cifrado): {"issuer_id", "key_id", "private_key" (.p8),
"vendor_number"}. id_externo = Apple ID de la app (adamId). Autenticación con JWT ES256 de
20 minutos, audiencia appstoreconnect-v1. El informe SALES/SUMMARY/DAILY viene como TSV gzip
con una fila por (producto, país); se filtra por el Apple ID de la app.
"""

import csv
import gzip
import io
import json
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import jwt

from api.etl.conector_base import ConectorBase, Fila, FilaDimension
from api.etl.registro import registrar

API = "https://api.appstoreconnect.apple.com/v1"
AUDIENCIA = "appstoreconnect-v1"
# Product Type Identifier del informe de ventas → clave nativa del conector
TIPOS_DESCARGA = {"1", "1F", "1T", "1E", "1EP", "1EU", "F1", "F1-B", "3", "3F"}
TIPOS_ACTUALIZACION = {"7", "7F", "7T", "7E", "7EP", "7EU", "F7"}
TIPOS_IAP = {"IA1", "IA1-M", "IA9", "IA9-M", "IAY", "IAY-M", "IAC", "IAC-M", "FI1"}


def token_app_store(
    issuer_id: str, key_id: str, private_key: str, ahora: float | None = None
) -> str:
    t = int(ahora if ahora is not None else time.time())
    return jwt.encode(
        {"iss": issuer_id, "iat": t, "exp": t + 20 * 60, "aud": AUDIENCIA},
        private_key,
        algorithm="ES256",
        headers={"kid": key_id, "typ": "JWT"},
    )


def leer_informe_ventas(contenido: bytes) -> list[dict[str, str]]:
    """TSV (gzip o plano) → lista de dicts por fila."""
    try:
        texto = gzip.decompress(contenido).decode("utf-8")
    except (OSError, gzip.BadGzipFile):
        texto = contenido.decode("utf-8")
    lector = csv.DictReader(io.StringIO(texto), delimiter="\t")
    return [dict(f) for f in lector if f.get("Apple Identifier")]


@registrar
class ConectorAppStore(ConectorBase):
    codigo = "app_store"
    plataforma = "app_store"
    timeout_seg: float = 90
    METRICAS_NATIVAS = (
        "descargas",
        "actualizaciones",
        "compras_in_app",
        "ingresos",
        "calificaciones",
        "calificacion_promedio",
    )

    async def _credencial(self) -> dict[str, str]:
        if not self.config.clave_cifrado:
            raise RuntimeError("CLAVE_CIFRADO no configurada")
        cruda = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
        if not cruda:
            raise RuntimeError("La cuenta de App Store no tiene credencial (issuer, key, .p8)")
        datos: dict[str, str] = json.loads(cruda)
        faltan = {"issuer_id", "key_id", "private_key", "vendor_number"} - set(datos)
        if faltan:
            raise RuntimeError(f"Credencial de App Store incompleta: faltan {sorted(faltan)}")
        return datos

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        cred = await self._credencial()
        token = token_app_store(cred["issuer_id"], cred["key_id"], cred["private_key"])
        cab = {"Authorization": f"Bearer {token}"}
        payload: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            dia = desde
            while dia <= hasta:
                r = await http.get(
                    f"{API}/salesReports",
                    headers={**cab, "Accept": "application/a-gzip"},
                    params={
                        "filter[frequency]": "DAILY",
                        "filter[reportDate]": dia.isoformat(),
                        "filter[reportSubType]": "SUMMARY",
                        "filter[reportType]": "SALES",
                        "filter[vendorNumber]": cred["vendor_number"],
                    },
                )
                if r.status_code == 404:  # sin ventas ese día: Apple responde 404
                    payload.append({"tipo": "ventas", "fecha": dia.isoformat(), "filas": []})
                else:
                    r.raise_for_status()
                    payload.append(
                        {
                            "tipo": "ventas",
                            "fecha": dia.isoformat(),
                            "filas": leer_informe_ventas(r.content),
                        }
                    )
                dia += timedelta(days=1)
            resenas: list[dict[str, Any]] = []
            url: str | None = (
                f"{API}/apps/{self.cuenta.id_externo}/customerReviews?limit=200&sort=-createdDate"
            )
            while url:
                r = await http.get(url, headers=cab)
                r.raise_for_status()
                cuerpo = r.json()
                lote = cuerpo.get("data", [])
                resenas.extend(lote)
                mas_antigua = min(
                    (datetime.fromisoformat(x["attributes"]["createdDate"]).date() for x in lote),
                    default=desde,
                )
                url = cuerpo.get("links", {}).get("next") if mas_antigua >= desde else None
            payload.append({"tipo": "resenas", "data": resenas})
        return payload

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        app_id = str(self.cuenta.id_externo)
        salida: list[Fila] = []
        for bloque in payload:
            if bloque.get("tipo") == "ventas":
                fecha = date.fromisoformat(bloque["fecha"])
                acumulado: dict[str, Decimal] = defaultdict(Decimal)
                for f in bloque["filas"]:
                    if str(f.get("Apple Identifier")) != app_id:
                        continue
                    tipo = str(f.get("Product Type Identifier", ""))
                    unidades = Decimal(str(f.get("Units") or 0))
                    proceeds = Decimal(str(f.get("Developer Proceeds") or 0))
                    if tipo in TIPOS_DESCARGA:
                        acumulado["descargas"] += unidades
                    elif tipo in TIPOS_ACTUALIZACION:
                        acumulado["actualizaciones"] += unidades
                    elif tipo in TIPOS_IAP:
                        acumulado["compras_in_app"] += unidades
                    acumulado["ingresos"] += unidades * proceeds
                for nativa in ("descargas", "actualizaciones", "compras_in_app", "ingresos"):
                    m = self.mapear(nativa, acumulado.get(nativa, Decimal(0)))
                    if m:
                        salida.append((fecha, m[0], m[1]))
            elif bloque.get("tipo") == "resenas":
                por_dia: dict[date, list[int]] = defaultdict(list)
                for r in bloque.get("data", []):
                    a = r.get("attributes", {})
                    if a.get("createdDate") and a.get("rating") is not None:
                        por_dia[datetime.fromisoformat(a["createdDate"]).date()].append(
                            int(a["rating"])
                        )
                for fecha, notas in por_dia.items():
                    for nativa, valor in (
                        ("calificaciones", Decimal(len(notas))),
                        ("calificacion_promedio", Decimal(sum(notas)) / len(notas)),
                    ):
                        m = self.mapear(nativa, valor)
                        if m:
                            salida.append((fecha, m[0], m[1]))
        return salida

    def normalizar_dimensiones(self, payload: list[dict[str, Any]]) -> list[FilaDimension]:
        """Descargas por país (Country Code del informe de ventas)."""
        app_id = str(self.cuenta.id_externo)
        salida: list[FilaDimension] = []
        for bloque in payload:
            if bloque.get("tipo") != "ventas":
                continue
            fecha = date.fromisoformat(bloque["fecha"])
            por_pais: dict[str, Decimal] = defaultdict(Decimal)
            for f in bloque["filas"]:
                if (
                    str(f.get("Apple Identifier")) == app_id
                    and str(f.get("Product Type Identifier", "")) in TIPOS_DESCARGA
                ):
                    por_pais[str(f.get("Country Code") or "(sin dato)")] += Decimal(
                        str(f.get("Units") or 0)
                    )
            for pais, unidades in por_pais.items():
                m = self.mapear("descargas", unidades)
                if m:
                    salida.append((fecha, m[0], "pais", pais, m[1]))
        return salida

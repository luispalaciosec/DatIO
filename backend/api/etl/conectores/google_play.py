"""Conector Google Play Console: informes CSV que Play deja en Cloud Storage
(pubsite_prod_rev_XXXX/stats/...). Instalaciones, desinstalaciones, actualizaciones,
dispositivos activos, calificación diaria, fallos y ANR; descargas por país como dimensión.

id_externo = nombre del paquete (com.empresa.app). Credencial por cuenta (JSON cifrado,
opcional): {"bucket": "pubsite_prod_rev_...", "service_account": {...}}. Sin bucket se usa
GOOGLE_PLAY_BUCKET; sin service_account se usa el de la agencia (que Play debe tener invitado
con permiso "Ver información de la app" y "Ver datos de estadísticas").
Los CSV de Play vienen en UTF-16 con BOM.
"""

import csv
import io
import json
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from api.etl.conector_base import Fila, FilaDimension
from api.etl.conectores.google_base import ConectorGoogleBase, _token_sincrono
from api.etl.registro import registrar

GCS = "https://storage.googleapis.com/storage/v1/b"
INFORMES = {  # carpeta → sufijo del archivo
    "installs": "overview",
    "ratings": "overview",
    "crashes": "overview",
    "installs_pais": "country",
}


def leer_csv_play(contenido: bytes) -> list[dict[str, str]]:
    for codificacion in ("utf-16", "utf-8-sig"):
        try:
            texto = contenido.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        return []
    texto = texto.lstrip("\ufeff")  # BOM residual (Play escribe UTF-16 con BOM, a veces doble)
    return [dict(f) for f in csv.DictReader(io.StringIO(texto)) if f.get("Date")]


def meses(desde: date, hasta: date) -> list[str]:
    salida = []
    a, m = desde.year, desde.month
    while (a, m) <= (hasta.year, hasta.month):
        salida.append(f"{a}{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return salida


@registrar
class ConectorGooglePlay(ConectorGoogleBase):
    codigo = "google_play"
    plataforma = "google_play"
    scopes = ("https://www.googleapis.com/auth/devstorage.read_only",)
    METRICAS_NATIVAS = (
        "Daily Device Installs",
        "Daily Device Uninstalls",
        "Daily Device Upgrades",
        "Active Device Installs",
        "Daily Average Rating",
        "Daily Crashes",
        "Daily ANRs",
    )

    async def _config_play(self) -> tuple[str, str | None]:
        bucket = self.config.google_play_bucket or None
        sa: str | None = None
        if self.config.clave_cifrado:
            cruda = await self.repo.credencial(self.cuenta.id, self.config.clave_cifrado)
            if cruda:
                datos = json.loads(cruda)
                bucket = datos.get("bucket") or bucket
                if datos.get("service_account"):
                    sa = json.dumps(datos["service_account"])
        if not bucket:
            raise RuntimeError(
                "Falta el bucket de Google Play (credencial.bucket o GOOGLE_PLAY_BUCKET)"
            )
        return bucket, sa

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        bucket, sa = await self._config_play()
        credencial = sa or await self._service_account_json()
        import asyncio

        token = await asyncio.to_thread(_token_sincrono, credencial, self.scopes)
        paquete = self.cuenta.id_externo
        payload: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            for mes in meses(desde, hasta):
                for carpeta, sufijo in INFORMES.items():
                    carpeta_real = carpeta.split("_")[0]
                    objeto = f"stats/{carpeta_real}/{carpeta_real}_{paquete}_{mes}_{sufijo}.csv"
                    r = await http.get(
                        f"{GCS}/{bucket}/o/{quote(objeto, safe='')}",
                        params={"alt": "media"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if r.status_code == 404:
                        continue
                    r.raise_for_status()
                    payload.append(
                        {"informe": carpeta, "mes": mes, "filas": leer_csv_play(r.content)}
                    )
        return payload

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            if bloque["informe"] not in ("installs", "ratings", "crashes"):
                continue
            for f in bloque["filas"]:
                fecha = datetime.strptime(f["Date"], "%Y-%m-%d").date()
                for nativa in self.METRICAS_NATIVAS:
                    if nativa in f and f[nativa] not in ("", None):
                        m = self.mapear(nativa, f[nativa])
                        if m:
                            salida.append((fecha, m[0], m[1]))
        return salida

    def normalizar_dimensiones(self, payload: list[dict[str, Any]]) -> list[FilaDimension]:
        salida: list[FilaDimension] = []
        for bloque in payload:
            if bloque["informe"] != "installs_pais":
                continue
            for f in bloque["filas"]:
                fecha = datetime.strptime(f["Date"], "%Y-%m-%d").date()
                pais = f.get("Country") or "(sin dato)"
                m = self.mapear("Daily Device Installs", f.get("Daily Device Installs"))
                if m:
                    salida.append((fecha, m[0], "pais", pais, m[1]))
        return salida

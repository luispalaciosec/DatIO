"""Conector Google Business Profile (antes Google My Business): métricas diarias de la ficha
(vistas en Maps y Búsqueda, llamadas, indicaciones, clics al sitio, conversaciones, reservas)
vía Business Profile Performance API, y reseñas (calificaciones por día) vía la API v4.

id_externo = "accounts/{cuenta}/locations/{ficha}" (lo entrega el selector de "Conectar con
Google"). Credencial: refresh token OAuth del usuario que administra la ficha (mismo formato que
GA4 por OAuth). Google exige aprobar el acceso a estas APIs por proyecto (formulario de
Business Profile APIs); hasta entonces responde 403 PERMISSION_DENIED.
"""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from api.etl.conector_base import Fila
from api.etl.conectores.google_base import ConectorGoogleBase
from api.etl.registro import registrar

PERFORMANCE = "https://businessprofileperformance.googleapis.com/v1"
RESENAS = "https://mybusiness.googleapis.com/v4"
ESTRELLAS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


@registrar
class ConectorGoogleNegocio(ConectorGoogleBase):
    codigo = "google_negocio"
    plataforma = "google_negocio"
    scopes = ("https://www.googleapis.com/auth/business.manage",)
    METRICAS_NATIVAS = (
        "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
        "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
        "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
        "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
        "CALL_CLICKS",
        "BUSINESS_DIRECTION_REQUESTS",
        "WEBSITE_CLICKS",
        "BUSINESS_CONVERSATIONS",
        "BUSINESS_BOOKINGS",
        "calificaciones",
        "calificacion_promedio",
    )
    DIARIAS = METRICAS_NATIVAS[:9]

    def _ficha(self) -> str:
        """'accounts/A/locations/L' → 'locations/L' (Performance API no lleva la cuenta)."""
        partes = self.cuenta.id_externo.split("/")
        return (
            "/".join(partes[-2:])
            if "locations" in partes
            else f"locations/{self.cuenta.id_externo}"
        )

    async def extraer(self, desde: date, hasta: date) -> list[dict[str, Any]]:
        token = await self.token_acceso()
        cab = {"Authorization": f"Bearer {token}"}
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("dailyMetrics", m) for m in self.DIARIAS
        ]
        params += [
            ("dailyRange.start_date.year", str(desde.year)),
            ("dailyRange.start_date.month", str(desde.month)),
            ("dailyRange.start_date.day", str(desde.day)),
            ("dailyRange.end_date.year", str(hasta.year)),
            ("dailyRange.end_date.month", str(hasta.month)),
            ("dailyRange.end_date.day", str(hasta.day)),
        ]
        async with httpx.AsyncClient(timeout=self.timeout_seg) as http:
            r = await http.get(
                f"{PERFORMANCE}/{self._ficha()}:fetchMultiDailyMetricsTimeSeries",
                params=params,
                headers=cab,
            )
            r.raise_for_status()
            payload: list[dict[str, Any]] = [{"tipo": "metricas", **r.json()}]
            if self.cuenta.id_externo.startswith("accounts/"):
                resenas: list[dict[str, Any]] = []
                url: str | None = f"{RESENAS}/{self.cuenta.id_externo}/reviews?pageSize=200"
                while url:
                    rr = await http.get(url, headers=cab)
                    if rr.status_code == 403:  # reseñas sin permiso: no bloquea las métricas
                        payload.append({"tipo": "resenas", "error": rr.text[:200], "reviews": []})
                        break
                    rr.raise_for_status()
                    cuerpo = rr.json()
                    lote = cuerpo.get("reviews", [])
                    resenas.extend(lote)
                    mas_antigua = min(
                        (
                            datetime.fromisoformat(x["createTime"].replace("Z", "+00:00")).date()
                            for x in lote
                            if x.get("createTime")
                        ),
                        default=desde,
                    )
                    sig = cuerpo.get("nextPageToken")
                    url = (
                        f"{RESENAS}/{self.cuenta.id_externo}/reviews?pageSize=200&pageToken={sig}"
                        if sig and mas_antigua >= desde
                        else None
                    )
                else:
                    payload.append({"tipo": "resenas", "reviews": resenas})
                if payload[-1].get("tipo") != "resenas":
                    payload.append({"tipo": "resenas", "reviews": resenas})
        return payload

    def normalizar(self, payload: list[dict[str, Any]]) -> list[Fila]:
        salida: list[Fila] = []
        for bloque in payload:
            if bloque.get("tipo") == "metricas":
                for serie in bloque.get("multiDailyMetricTimeSeries", []):
                    for dm in serie.get("dailyMetricTimeSeries", []):
                        nativa = str(dm.get("dailyMetric"))
                        for punto in (dm.get("timeSeries") or {}).get("datedValues", []):
                            d = punto.get("date") or {}
                            fecha = date(int(d["year"]), int(d["month"]), int(d["day"]))
                            m = self.mapear(nativa, punto.get("value", 0))
                            if m:
                                salida.append((fecha, m[0], m[1]))
            elif bloque.get("tipo") == "resenas":
                por_dia: dict[date, list[int]] = defaultdict(list)
                for r in bloque.get("reviews", []):
                    if r.get("createTime") and r.get("starRating") in ESTRELLAS:
                        f = datetime.fromisoformat(r["createTime"].replace("Z", "+00:00")).date()
                        por_dia[f].append(ESTRELLAS[r["starRating"]])
                for fecha, notas in por_dia.items():
                    for nativa, valor in (
                        ("calificaciones", Decimal(len(notas))),
                        ("calificacion_promedio", Decimal(sum(notas)) / len(notas)),
                    ):
                        m = self.mapear(nativa, valor)
                        if m:
                            salida.append((fecha, m[0], m[1]))
        return salida

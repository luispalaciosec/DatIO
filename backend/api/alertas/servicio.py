"""Corrida de alertas (PT-14): anomalías de ayer + condiciones operativas, sin duplicar las
abiertas. Devuelve las alertas nuevas para el resumen por correo."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from api.alertas.detector import VENTANA_DIAS, detectar
from api.alertas.repositorio import METRICAS_VIGILADAS, REDES_CON_PUBLICACIONES, RepositorioAlertas

log = logging.getLogger(__name__)

DIAS_SIN_PUBLICAR = 14
DIAS_AVISO_TOKEN = 7
DIAS_DEDUPE = 3
NOMBRES_RED = {
    "meta_ig": "Instagram",
    "meta_fb": "Facebook",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "ga4": "Sitio web",
    "gsc": "Search Console",
    "meta_ads": "Meta Ads",
}


@dataclass
class AlertaNueva:
    id: int
    cliente: str
    cliente_id: int | None
    red: str
    tipo: str
    severidad: str
    titulo: str
    detalle: dict[str, Any]


@dataclass
class ResumenAlertas:
    nuevas: list[AlertaNueva] = field(default_factory=list)
    cuentas_revisadas: int = 0
    metricas_evaluadas: int = 0


def _pct(x: float) -> str:
    return f"{abs(x) * 100:.0f} %"


async def correr_alertas(repo: RepositorioAlertas, hoy: date) -> ResumenAlertas:
    resumen = ResumenAlertas()
    ayer = hoy - timedelta(days=1)
    cuentas = await repo.cuentas_vigiladas()
    codigos_todos = sorted({c for cs in METRICAS_VIGILADAS.values() for c in cs})
    agregaciones = await repo.agregaciones(codigos_todos)
    errores = {
        (e["cuenta_id"], e["conector"]): e
        for e in await repo.jobs_con_error(datetime.now(UTC) - timedelta(hours=26))
    }

    async def emitir(
        cuenta: dict[str, Any],
        tipo: str,
        severidad: str,
        titulo: str,
        clave: str,
        detalle: dict[str, Any],
    ) -> None:
        if await repo.existe_abierta(cuenta["id"], tipo, clave, DIAS_DEDUPE):
            return
        detalle = {
            "clave": clave,
            "red": cuenta["plataforma"],
            "cliente_id": cuenta["cliente_id"],
            **detalle,
        }
        alerta_id = await repo.crear(cuenta["id"], tipo, severidad, titulo, detalle)
        resumen.nuevas.append(
            AlertaNueva(
                alerta_id,
                cuenta["cliente"],
                cuenta["cliente_id"],
                NOMBRES_RED.get(cuenta["plataforma"], cuenta["plataforma"]),
                tipo,
                severidad,
                titulo,
                detalle,
            )
        )

    for cuenta in cuentas:
        resumen.cuentas_revisadas += 1
        red = NOMBRES_RED.get(cuenta["plataforma"], cuenta["plataforma"])

        # --- anomalías de ayer -------------------------------------------------------
        codigos = METRICAS_VIGILADAS.get(cuenta["plataforma"], [])
        if codigos:
            series = await repo.series(
                cuenta["id"], codigos, ayer - timedelta(days=VENTANA_DIAS + 1), ayer
            )
            for codigo, serie in series.items():
                resumen.metricas_evaluadas += 1
                a = detectar(serie, ayer, agregaciones.get(codigo, "suma"))
                if a is None:
                    continue
                verbo = "cayó" if a.tipo == "anomalia" else "subió"
                nombre = codigo.replace("_", " ")
                titulo = (
                    f"{cuenta['cliente']} · {red}: {nombre} {verbo} {_pct(a.cambio)} "
                    f"el {a.fecha.strftime('%d/%m')} "
                    f"(esperado {a.esperado:,.0f}, real {a.valor:,.0f})"
                )
                await emitir(
                    cuenta,
                    a.tipo,
                    a.severidad,
                    titulo,
                    codigo,
                    {
                        "metrica": codigo,
                        "fecha": a.fecha.isoformat(),
                        "valor": a.valor,
                        "esperado": a.esperado,
                        "z": a.z,
                        "cambio": a.cambio,
                    },
                )

        # --- operativas ----------------------------------------------------------------
        for (cuenta_id, conector), e in errores.items():
            if cuenta_id == cuenta["id"]:
                await emitir(
                    cuenta,
                    "operativa",
                    "alta",
                    f"{cuenta['cliente']} · {red}: la captura «{conector}» falló",
                    f"job:{conector}",
                    {"conector": conector, "error": (e["error_detalle"] or "")[:300]},
                )
        expira = cuenta.get("token_expira_en")
        if expira is not None:
            faltan = (expira.date() - hoy).days
            if faltan <= DIAS_AVISO_TOKEN:
                await emitir(
                    cuenta,
                    "operativa",
                    "alta" if faltan <= 2 else "media",
                    f"{cuenta['cliente']} · {red}: el acceso vence en {max(faltan, 0)} días. "
                    "Reconectar desde el admin",
                    "token",
                    {"vence": expira.isoformat(), "dias": faltan},
                )
        if cuenta["plataforma"] in REDES_CON_PUBLICACIONES:
            ultima = await repo.ultima_publicacion(cuenta["id"])
            antigua = (
                cuenta["creado_en"] is None
                or (hoy - cuenta["creado_en"].date()).days >= DIAS_SIN_PUBLICAR
            )
            if antigua and (ultima is None or (hoy - ultima.date()).days >= DIAS_SIN_PUBLICAR):
                dias = (hoy - ultima.date()).days if ultima else None
                cuantos = str(dias) if dias is not None else f"más de {DIAS_SIN_PUBLICAR}"
                await emitir(
                    cuenta,
                    "operativa",
                    "media",
                    f"{cuenta['cliente']} · {red}: {cuantos} días sin publicar",
                    "sin_publicar",
                    {"ultima_publicacion": ultima.isoformat() if ultima else None, "dias": dias},
                )
    return resumen

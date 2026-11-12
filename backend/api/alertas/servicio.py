"""Corrida de alertas (PT-14): anomalías de ayer + condiciones operativas, sin duplicar las
abiertas. Devuelve las alertas nuevas para el resumen por correo."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from api.alertas.detector import VENTANA_DIAS, Anomalia, detectar
from api.alertas.repositorio import METRICAS_VIGILADAS, REDES_CON_PUBLICACIONES, RepositorioAlertas

log = logging.getLogger(__name__)

DIAS_SIN_PUBLICAR = 14
DIAS_AVISO_TOKEN = 7
DIAS_DEDUPE = 3
DIAS_RADAR_ATRASADO = 10
DIAS_DATOS_ATRASADOS = 4
# Una anomalía o una oportunidad deja de ser accionable pasado este plazo: se cierra sola.
DIAS_VIGENCIA_ANOMALIA = 14
NOMBRES_RED = {
    "meta_ig": "Instagram",
    "meta_fb": "Facebook",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "ga4": "Sitio web",
    "gsc": "Search Console",
    "meta_ads": "Meta Ads",
    "radar": "Radar",
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
    cerradas: int = 0


def _pct(x: float) -> str:
    return f"{abs(x) * 100:.0f} %"


def _num(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def describir_anomalia(a: Anomalia, codigo: str, agregacion: str) -> str:
    """Frase legible para el gerente: seguidores en unidades, saltos grandes como múltiplo."""
    fecha = a.fecha.strftime("%d/%m")
    if agregacion == "ultimo":
        verbo = "ganó" if a.valor >= 0 else "perdió"
        nombre = codigo.replace("_", " ")
        return (
            f"{verbo} {_num(abs(a.valor))} {nombre} el {fecha} "
            f"(lo normal: {_num(a.esperado)} por día)"
        )
    nombre = codigo.replace("_", " ")
    if a.cambio >= 1.0 and a.esperado > 0:
        veces = a.valor / a.esperado
        cifra = f"×{veces:,.1f}".replace(",", ".") if veces < 10 else f"×{_num(veces)}"
        return (
            f"{nombre} se multiplicó {cifra} el {fecha} "
            f"(esperado {_num(a.esperado)}, real {_num(a.valor)})"
        )
    verbo = "cayó" if a.tipo == "anomalia" else "subió"
    return (
        f"{nombre} {verbo} {_pct(a.cambio)} el {fecha} "
        f"(esperado {_num(a.esperado)}, real {_num(a.valor)})"
    )


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

    vigentes: set[tuple[int | None, str]] = set()

    async def emitir(
        cuenta: dict[str, Any],
        tipo: str,
        severidad: str,
        titulo: str,
        clave: str,
        detalle: dict[str, Any],
    ) -> None:
        if tipo == "operativa":
            vigentes.add((cuenta["id"], clave))
            # Una operativa abierta con la misma clave no se repite: se cierra sola cuando
            # la condición desaparece (ver cerrar_operativas_no_vigentes).
            if await repo.existe_abierta_cualquiera(cuenta["id"], tipo, clave):
                return
        elif await repo.existe_abierta(cuenta["id"], tipo, clave, DIAS_DEDUPE):
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
                agregacion = agregaciones.get(codigo, "suma")
                a = detectar(serie, ayer, agregacion)
                if a is None:
                    continue
                titulo = f"{cuenta['cliente']} · {red}: {describir_anomalia(a, codigo, agregacion)}"
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

    # --- cuentas sin datos recientes (puente Metricool detenido, token muerto, etc.) ---------
    for cuenta in await repo.cuentas_sin_datos_recientes(DIAS_DATOS_ATRASADOS):
        red = NOMBRES_RED.get(cuenta["plataforma"], cuenta["plataforma"])
        ultima = cuenta["ultima"]
        detalle_txt = (
            f"sin datos desde el {ultima.strftime('%d/%m')} ({(hoy - ultima).days} días)"
            if ultima
            else "nunca ha traído datos"
        )
        await emitir(
            cuenta,
            "operativa",
            "alta" if ultima else "media",
            f"{cuenta['cliente']} · {red}: {detalle_txt}",
            "datos_atrasados",
            {"ultima": ultima.isoformat() if ultima else None},
        )

    # --- radar competitivo detenido (por cliente, no por cuenta) ---------------------------
    for atrasado in await repo.radar_atrasado(DIAS_RADAR_ATRASADO):
        clave = f"radar_atrasado:{atrasado['cliente_id']}"
        seudo = {
            "id": None,
            "cliente_id": atrasado["cliente_id"],
            "cliente": atrasado["cliente"],
            "plataforma": "radar",
        }
        desde = atrasado["ultimo"].strftime("%d/%m") if atrasado["ultimo"] else "nunca"
        await emitir(
            seudo,
            "operativa",
            "alta",
            f"{atrasado['cliente']} · Radar: sin captura de la competencia desde {desde}. "
            "Revisar APIFY_TOKEN en el servicio del cron",
            clave,
            {
                "ultimo": atrasado["ultimo"].isoformat() if atrasado["ultimo"] else None,
                "competidores": atrasado["competidores"],
            },
        )
    resumen.cerradas = await repo.cerrar_operativas_no_vigentes(vigentes)
    resumen.cerradas += await repo.cerrar_anomalias_vencidas(DIAS_VIGENCIA_ANOMALIA)
    return resumen

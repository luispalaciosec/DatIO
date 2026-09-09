"""pacing_mes (PT-13): acumulado del mes, cierre proyectado con banda y comparación con el
mes anterior. Se calcula sobre el mes de ctx.hasta (el mes en curso en el uso normal).

Cada cálculo del mes en curso se guarda en fct_proyeccion (modelo 'pacing') cuando el bloque
tiene una sola cuenta, para poder medir el error real cuando el mes cierre (backtest honesto).
"""

from datetime import date, timedelta
from typing import Any

from api.etl.conector_base import hoy_en
from api.prediccion.pacing import SEMANAS_REFERENCIA, calcular_pacing, limites_mes
from api.resolvedores import Contexto, Resultado, delta_porcentual, registrar

VERSION_MODELO = "pacing-1"


@registrar("pacing_mes")
async def resolver(ctx: Contexto) -> Resultado:
    metrica = str(ctx.config["metrica"])
    info = (await ctx.repo.metricas_info([metrica])).get(metrica, {})
    agregacion = str(info.get("agregacion", "suma"))
    zona = str(ctx.config.get("zona_horaria", "America/Guayaquil"))
    hoy = hoy_en(zona)
    mes_inicio, mes_fin = limites_mes(ctx.hasta)
    en_curso = mes_inicio <= hoy <= mes_fin

    # Serie diaria: mes anterior completo + referencia + mes objetivo.
    desde = mes_inicio - timedelta(days=max(7 * SEMANAS_REFERENCIA, 31))
    hasta = min(mes_fin, hoy)
    filas = await ctx.repo.serie_metricas(ctx.cuentas, [metrica], desde, hasta, "dia")
    serie: dict[date, float] = {
        f["periodo"]: float(f["valor"]) for f in filas if f["valor"] is not None
    }
    provisional = any(f.get("provisional") for f in filas)
    if not serie:
        return Resultado(None, meta={"sin_datos": True, "metrica": metrica})

    pacing = calcular_pacing(serie, hoy, agregacion, mes=None if en_curso else ctx.hasta)

    # Mes anterior: cierre real con la misma definición.
    ant_fin = mes_inicio - timedelta(days=1)
    ant_inicio, _ = limites_mes(ant_fin)
    anterior = {f: v for f, v in serie.items() if ant_inicio <= f <= ant_fin}
    # Sin datos desde el arranque del mes anterior no hay cierre comparable (historia corta).
    if anterior and min(anterior) > ant_inicio + timedelta(days=1):
        anterior = {}
    if agregacion == "ultimo":
        cierre_anterior = anterior[max(anterior)] if anterior else None
        mismo_dia_anterior = None
    else:
        cierre_anterior = sum(anterior.values()) if anterior else None
        mismo_corte = ant_inicio + timedelta(days=max(pacing.dias_transcurridos, 1) - 1)
        mismo_dia_anterior = (
            sum(v for f, v in anterior.items() if f <= mismo_corte)
            if anterior and pacing.dias_transcurridos
            else None
        )

    objetivo = ctx.config.get("objetivo")
    objetivo = float(objetivo) if objetivo not in (None, "") else None

    curva = _curva(serie, pacing, agregacion)
    datos: dict[str, Any] = {
        "metrica": metrica,
        "etiqueta": ctx.config.get("etiqueta") or info.get("nombre_es", metrica),
        "agregacion": agregacion,
        "mes_inicio": pacing.mes_inicio.isoformat(),
        "mes_fin": pacing.mes_fin.isoformat(),
        "corte": pacing.corte.isoformat(),
        "dias_transcurridos": pacing.dias_transcurridos,
        "dias_restantes": pacing.dias_restantes,
        "acumulado": pacing.acumulado,
        "proyeccion_p50": pacing.proyeccion_p50,
        "proyeccion_p10": pacing.proyeccion_p10,
        "proyeccion_p90": pacing.proyeccion_p90,
        "ritmo_diario": pacing.ritmo_diario,
        "cierre_anterior": cierre_anterior,
        "mismo_dia_anterior": mismo_dia_anterior,
        "delta_vs_anterior": delta_porcentual(pacing.proyeccion_p50, cierre_anterior),
        "delta_mismo_dia": delta_porcentual(pacing.acumulado, mismo_dia_anterior),
        "objetivo": objetivo,
        "avance_objetivo": (pacing.acumulado / objetivo * 100) if objetivo else None,
        "proyeccion_vs_objetivo": (
            (pacing.proyeccion_p50 / objetivo * 100)
            if objetivo and pacing.proyeccion_p50 is not None
            else None
        ),
        "curva": curva,
        "cerrado": not en_curso,
        "confiable": pacing.dias_referencia >= 14,
    }

    if en_curso and len(ctx.cuentas) == 1 and pacing.proyeccion_p50 is not None:
        await ctx.repo.guardar_proyeccion(
            ctx.cuentas[0],
            metrica,
            pacing.mes_fin,
            hoy,
            pacing.dias_restantes,
            pacing.proyeccion_p50,
            pacing.proyeccion_p10,
            pacing.proyeccion_p90,
            "pacing",
            VERSION_MODELO,
            {"acumulado": pacing.acumulado, "dias_referencia": pacing.dias_referencia},
        )
    return Resultado(
        datos,
        "provisional" if provisional else "consolidado",
        {"metrica": metrica, "en_curso": en_curso, "cuentas": len(ctx.cuentas)},
    )


def _curva(serie: dict[date, float], p: Any, agregacion: str) -> list[dict[str, Any]]:
    """Puntos diarios del mes: real acumulado hasta el corte y proyección después."""
    puntos: list[dict[str, Any]] = []
    acumulado = 0.0
    dia = p.mes_inicio
    while dia <= p.mes_fin:
        if dia <= p.corte:
            v = serie.get(dia)
            if agregacion == "ultimo":
                acumulado = v if v is not None else acumulado
            else:
                acumulado += v or 0.0
            puntos.append({"fecha": dia.isoformat(), "real": acumulado})
        else:
            if p.proyeccion_p50 is None or p.dias_restantes == 0:
                break
            avance = (dia - p.corte).days / p.dias_restantes
            puntos.append(
                {
                    "fecha": dia.isoformat(),
                    "proyeccion": p.acumulado + (p.proyeccion_p50 - p.acumulado) * avance,
                    "p10": p.acumulado + (p.proyeccion_p10 - p.acumulado) * avance,
                    "p90": p.acumulado + (p.proyeccion_p90 - p.acumulado) * avance,
                }
            )
        dia += timedelta(days=1)
    if puntos and p.dias_restantes and p.proyeccion_p50 is not None:
        # unir las dos líneas en el corte
        for q in puntos:
            if q["fecha"] == p.corte.isoformat():
                q["proyeccion"] = q["p10"] = q["p90"] = q["real"]
    return puntos

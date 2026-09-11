"""Disparadores del puente CRM (PT-16, spec/05 Ficha 6). Cada uno mira el contexto de un
cliente y, si aplica, describe la acción a crear en el CRM. La ventana anti-duplicado de 30
días es obligatoria (guardrail del spec). Las cifras salen de la base, nunca se inventan.

Códigos:
  bajo_meta          proyección de cierre del mes < 60 % del mes anterior → "Refuerzo de pauta"
  competencia_pauta  un competidor lanzó ≥ 3 anuncios nuevos en 7 días → tarea de contraataque
  organico_sin_pauta engagement orgánico alto y sin inversión en pauta → venta cruzada
  caida_sostenida    tres ventanas de 28 días cayendo ≥ 10 % cada una → riesgo de fuga
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from api.config import Configuracion
from api.prediccion.pacing import calcular_pacing, limites_mes
from api.puente.crm import Accion, CrmError, adaptador
from api.puente.repositorio import METRICA_PRINCIPAL, RepositorioPuente

log = logging.getLogger(__name__)

DIAS_DEDUPE = 30
UMBRAL_BAJO_META = 0.60
MIN_DIAS_MES = 10
ANUNCIOS_NUEVOS_MIN = 3
ENGAGEMENT_ALTO = 1.0  # % interacciones por publicación / seguidores
CAIDA_MIN = 0.10
VALOR_REFUERZO_MIN = 300.0
NOMBRE_RED = {
    "meta_ig": "Instagram",
    "meta_fb": "Facebook",
    "ga4": "Sitio web",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
}


@dataclass
class Disparo:
    cliente_id: int
    cliente: str
    cuenta_id: int | None
    accion: Accion
    contexto: dict[str, Any]
    objeto_ref: str | None = None
    error: str | None = None


@dataclass
class ResumenPuente:
    disparos: list[Disparo] = field(default_factory=list)
    clientes_evaluados: int = 0
    omitidos: list[str] = field(default_factory=list)


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


async def evaluar_cliente(
    repo: RepositorioPuente, cliente: dict[str, Any], hoy: date
) -> list[Disparo]:
    """Devuelve los disparos que aplican hoy para un cliente (sin ejecutarlos ni deduplicar)."""
    salida: list[Disparo] = []
    cuentas = await repo.cuentas(int(cliente["id"]))
    gasto_28 = await repo.gasto_ads(int(cliente["id"]), 28)

    for cuenta in cuentas:
        metrica = METRICA_PRINCIPAL.get(str(cuenta["plataforma"]))
        if not metrica:
            continue
        red = NOMBRE_RED.get(str(cuenta["plataforma"]), str(cuenta["plataforma"]))
        agregacion = await repo.agregacion(metrica)
        serie = await repo.serie(int(cuenta["id"]), metrica, hoy - timedelta(days=120), hoy)
        if not serie:
            continue

        # 1) bajo_meta: cierre proyectado muy por debajo del mes anterior
        pacing = calcular_pacing(serie, hoy, agregacion)
        ant_ini, ant_fin = limites_mes(pacing.mes_inicio - timedelta(days=1))
        anterior = [v for f, v in serie.items() if ant_ini <= f <= ant_fin]
        cierre_anterior = (
            (sum(anterior) if agregacion == "suma" else (anterior[-1] if anterior else 0))
            if anterior
            else None
        )
        dias_anterior = len(anterior)
        if (
            pacing.proyeccion_p50 is not None
            and pacing.dias_transcurridos >= MIN_DIAS_MES
            and cierre_anterior
            and dias_anterior >= 20
            and pacing.proyeccion_p50 < cierre_anterior * UMBRAL_BAJO_META
        ):
            brecha = 1 - pacing.proyeccion_p50 / cierre_anterior
            valor = max(VALOR_REFUERZO_MIN, (gasto_28 or 0) * 0.5)
            gasto_txt = "sin cuenta de pauta" if gasto_28 is None else f"USD {_fmt(gasto_28)}"
            evidencia_bajo_meta = (
                f"{red}: {metrica} va a cerrar {pacing.mes_inicio:%B} en "
                f"{_fmt(pacing.proyeccion_p50)} (rango {_fmt(pacing.proyeccion_p10 or 0)}–"
                f"{_fmt(pacing.proyeccion_p90 or 0)}), un {brecha * 100:.0f} % por debajo del "
                f"mes anterior ({_fmt(cierre_anterior)}). Llevamos {pacing.dias_transcurridos} "
                f"días del mes. Gasto en pauta últimos 28 días: {gasto_txt}. "
                f"Propuesta: refuerzo de pauta por USD {_fmt(valor)}/mes."
            )
            salida.append(
                Disparo(
                    int(cliente["id"]),
                    str(cliente["nombre"]),
                    int(cuenta["id"]),
                    Accion(
                        "bajo_meta",
                        "oportunidad",
                        f"Refuerzo de pauta · {cliente['nombre']} · {red}",
                        evidencia_bajo_meta,
                        valor=valor,
                        prioridad="alta",
                    ),
                    {
                        "metrica": metrica,
                        "proyeccion": pacing.proyeccion_p50,
                        "mes_anterior": cierre_anterior,
                        "brecha": brecha,
                        "gasto_28": gasto_28,
                    },
                )
            )

        # 4) caida_sostenida: tres ventanas de 28 días, cada una ≥ 10 % por debajo de la previa
        if agregacion == "suma":
            ventanas = []
            for k in range(3):
                fin = hoy - timedelta(days=1 + 28 * k)
                ini = fin - timedelta(days=27)
                puntos = [v for f, v in serie.items() if ini <= f <= fin]
                ventanas.append(sum(puntos) if len(puntos) >= 20 else None)
            v0, v1, v2 = ventanas
            if (
                v0 is not None
                and v1 is not None
                and v2 is not None
                and v0 < v1 * (1 - CAIDA_MIN)
                and v1 < v2 * (1 - CAIDA_MIN)
            ):
                evidencia_caida = (
                    f"{red}: {metrica} lleva tres períodos de 28 días cayendo: "
                    f"{_fmt(v2)} → {_fmt(v1)} → {_fmt(v0)}. Conviene una reunión de revisión "
                    "antes de que el cliente lo plantee."
                )
                salida.append(
                    Disparo(
                        int(cliente["id"]),
                        str(cliente["nombre"]),
                        int(cuenta["id"]),
                        Accion(
                            "caida_sostenida",
                            "tarea",
                            f"Riesgo de fuga · {cliente['nombre']} · {red}",
                            evidencia_caida,
                            prioridad="alta",
                        ),
                        {"metrica": metrica, "ventanas": ventanas},
                    )
                )

    # 2) competencia_pauta
    for comp in await repo.anuncios_nuevos_competencia(int(cliente["id"]), 7):
        if int(comp["nuevos"]) >= ANUNCIOS_NUEVOS_MIN:
            titulo_comp = (
                f"Alerta competitiva · {cliente['nombre']}: {comp['nombre']} lanzó "
                f"{comp['nuevos']} anuncios"
            )
            evidencia_comp = (
                f"{comp['nombre']} publicó {comp['nuevos']} anuncios nuevos en los últimos 7 días "
                f"({comp['activos_total']} activos en total). Revisar el radar de pauta en el "
                f"benchmark de Facebook de {cliente['nombre']} y preparar brief de contraataque."
            )
            salida.append(
                Disparo(
                    int(cliente["id"]),
                    str(cliente["nombre"]),
                    None,
                    Accion(
                        f"competencia_pauta:{comp['competidor_id']}",
                        "tarea",
                        titulo_comp,
                        evidencia_comp,
                        prioridad="media",
                    ),
                    {"competidor_id": comp["competidor_id"], "nuevos": comp["nuevos"]},
                )
            )

    # 3) organico_sin_pauta
    engagement = await repo.engagement_propio(int(cliente["id"]))
    sin_pauta = gasto_28 is None or gasto_28 == 0
    if engagement is not None and engagement >= ENGAGEMENT_ALTO and sin_pauta:
        pauta_txt = (
            "no hay cuenta de pauta conectada"
            if gasto_28 is None
            else "cero inversión en pauta en 28 días"
        )
        evidencia_org = (
            f"Instagram tiene {engagement:.2f} % de engagement por publicación (alto) y "
            f"{pauta_txt}. El contenido ya funciona orgánicamente: amplificarlo con pauta es la "
            "propuesta natural."
        )
        salida.append(
            Disparo(
                int(cliente["id"]),
                str(cliente["nombre"]),
                None,
                Accion(
                    "organico_sin_pauta",
                    "oportunidad",
                    f"Venta cruzada de pauta · {cliente['nombre']}",
                    evidencia_org,
                    valor=VALOR_REFUERZO_MIN,
                    prioridad="media",
                ),
                {"engagement": engagement, "gasto_28": gasto_28},
            )
        )
    return salida


async def correr_puente(
    repo: RepositorioPuente,
    config: Configuracion,
    hoy: date,
    cliente_id: int | None = None,
    simular: bool = False,
) -> ResumenPuente:
    resumen = ResumenPuente()
    for cliente in await repo.clientes_con_crm(cliente_id):
        resumen.clientes_evaluados += 1
        credencial = (
            await repo.credencial_crm(int(cliente["id"]), config.clave_cifrado)
            if config.clave_cifrado
            else None
        )
        crm = adaptador(config, cliente["crm_proveedor"], credencial, cliente["crm_config"])
        if crm is None:
            resumen.omitidos.append(
                f"{cliente['nombre']}: CRM {cliente['crm_proveedor']} sin credencial"
            )
            continue
        for d in await evaluar_cliente(repo, cliente, hoy):
            if await repo.disparo_reciente(d.cliente_id, d.accion.codigo, DIAS_DEDUPE):
                continue
            if simular:
                resumen.disparos.append(d)
                continue
            try:
                r = await crm.ejecutar(
                    d.accion, str(cliente["crm_empresa_ref"]), cliente.get("crm_contacto_ref")
                )
                d.objeto_ref = r.objeto_ref
                d.contexto["url"] = r.url
            except CrmError as e:
                d.error = str(e)
                log.warning("Puente CRM: %s falló: %s", d.accion.codigo, e)
            except Exception as e:  # red caída, etc.: se registra y se reintenta mañana
                d.error = f"{type(e).__name__}: {e}"
                log.exception("Puente CRM: %s falló", d.accion.codigo)
            await repo.registrar_disparo(
                d.cliente_id,
                d.cuenta_id,
                d.accion.codigo,
                d.accion.titulo,
                d.contexto,
                d.objeto_ref,
                d.error,
            )
            await repo.crear_alerta(
                d.cuenta_id,
                f"{'✓' if d.error is None else '✗'} CRM · {d.accion.titulo}",
                {
                    "clave": d.accion.codigo,
                    "cliente_id": d.cliente_id,
                    "crm": cliente["crm_proveedor"],
                    "objeto_ref": d.objeto_ref,
                    "error": d.error,
                    "evidencia": d.accion.evidencia,
                },
            )
            resumen.disparos.append(d)
    return resumen

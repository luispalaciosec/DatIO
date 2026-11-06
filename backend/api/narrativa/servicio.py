"""Construye los hechos de una red y devuelve la narrativa (cacheada por día)."""

import logging
from datetime import date, timedelta
from typing import Any

from api.config import Configuracion
from api.consulta.repositorio import RepositorioConsulta
from api.narrativa.hechos import Hecho, Hechos, redactar_base, validar_cifras

log = logging.getLogger(__name__)

NOMBRE_RED = {
    "meta_ig": "Instagram",
    "meta_fb": "Facebook",
    "linkedin": "LinkedIn",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "ga4": "el sitio web",
    "gsc": "la búsqueda de Google",
    "meta_ads": "Meta Ads",
    "google_ads": "Google Ads",
    "app_store": "la App Store",
    "google_play": "Google Play",
    "google_negocio": "la ficha de Google",
    "prometio": "el CRM",
    "hubspot": "el CRM",
    "zoho": "el CRM",
}
INSTRUCCIONES = (
    "Eres analista de marketing de una agencia en Ecuador. Reescribe el siguiente resumen en "
    "un solo párrafo de 3 o 4 frases, en español de Ecuador, tono profesional y directo, sin "
    "adjetivos de marketing ni relleno. REGLAS ESTRICTAS: usa únicamente las cifras que "
    "aparecen en el resumen, exactamente como están escritas; no calcules cifras nuevas, no "
    "redondees distinto, no inventes causas. Si no hay explicación en los datos, no la des. "
    "Devuelve solo el párrafo."
)


def periodo_anterior(desde: date, hasta: date) -> tuple[date, date]:
    dias = (hasta - desde).days + 1
    return desde - timedelta(days=dias), desde - timedelta(days=1)


def delta_porcentual(actual: Any, anterior: Any) -> float | None:
    if actual is None or anterior in (None, 0):
        return None
    return round((float(actual) - float(anterior)) / float(anterior) * 100, 2)


async def construir_hechos(
    repo: RepositorioConsulta,
    cuentas: list[int],
    plataforma: str,
    items: list[dict[str, Any]],
    desde: date,
    hasta: date,
) -> Hechos:
    h = Hechos(NOMBRE_RED.get(plataforma, plataforma), desde, hasta)
    codigos = [i["metrica"] for i in items]
    if not cuentas or not codigos:
        return h
    actual = await repo.agregar_metricas(cuentas, codigos, desde, hasta)
    d0, d1 = periodo_anterior(desde, hasta)
    anterior = await repo.agregar_metricas(cuentas, codigos, d0, d1)
    info = await repo.metricas_info(codigos)
    for item in items:
        c = item["metrica"]
        act = actual.get(c)
        if act is None or act.valor is None:
            continue
        ant = anterior.get(c)
        ant_v = float(ant.valor) if ant and ant.valor is not None else None
        comparable = info.get(c, {}).get("agregacion") != "ultimo"
        h.kpis.append(
            Hecho(
                c,
                item.get("etiqueta") or info.get(c, {}).get("nombre_es", c),
                float(act.valor),
                ant_v if comparable else None,
                delta_porcentual(act.valor, ant.valor if ant else None) if comparable else None,
                item.get("formato", "entero"),
            )
        )
    if h.kpis:
        principal = next((k for k in h.kpis if k.anterior is not None), h.kpis[0])
        serie = await repo.serie_metricas(cuentas, [principal.metrica], desde, hasta, "dia")
        puntos = [(p["periodo"], float(p["valor"])) for p in serie if p["valor"] is not None]
        if len(puntos) >= 7 and info.get(principal.metrica, {}).get("agregacion") == "suma":
            f, v = max(puntos, key=lambda x: x[1])
            if v > 0:
                h.mejor_dia = (f, v, principal.etiqueta)
    pubs = await repo.publicaciones(cuentas, desde, hasta, "interacciones", 1)
    if pubs:
        p = pubs[0]
        m = p["metricas"] if isinstance(p["metricas"], dict) else {}
        valor = m.get("interacciones")
        if valor and p.get("publicado_en"):
            h.top_publicacion = {
                "tipo": p.get("tipo"),
                "fecha": p["publicado_en"].date().isoformat(),
                "valor": float(valor),
                "metrica": "interacciones",
                "texto": (p.get("caption") or "")[:120],
            }
    return h


async def narrar(
    repo: RepositorioConsulta,
    config: Configuracion | None,
    cliente_id: int,
    cuentas: list[int],
    plataforma: str,
    items: list[dict[str, Any]],
    desde: date,
    hasta: date,
    usar_ia: bool = True,
) -> dict[str, Any]:
    en_cache = await repo.narrativa(cliente_id, plataforma, desde, hasta)
    if en_cache is not None:
        return en_cache
    h = await construir_hechos(repo, cuentas, plataforma, items, desde, hasta)
    base = redactar_base(h)
    if not base:
        return {"texto": "", "fuente": "sin_datos", "hechos": h.como_dict()}
    texto, fuente = base, "reglas"
    if usar_ia and config is not None and "narrativa" in config.llm_modelos:
        try:
            from api.llm.repositorio import RepositorioLLM
            from api.llm.router import completar

            salida = await completar(
                "narrativa",
                [{"role": "system", "content": INSTRUCCIONES}, {"role": "user", "content": base}],
                config,
                RepositorioLLM(repo.pool),
                cliente_id,
            )
            salida = (salida or "").strip()
            ajenas = validar_cifras(salida, h)
            if salida and not ajenas and len(salida) < 1200:
                texto, fuente = salida, "ia"
            else:
                log.warning("Narrativa IA descartada (cifras ajenas: %s)", ajenas[:5])
        except Exception as e:  # sin clave, sin red, modelo caído: queda la redacción base
            log.info("Narrativa sin IA: %s", str(e)[:120])
    resultado = {"texto": texto, "fuente": fuente, "hechos": h.como_dict()}
    await repo.guardar_narrativa(cliente_id, plataforma, desde, hasta, texto, fuente, h.como_dict())
    return resultado

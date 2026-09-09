"""benchmark_tabla: tabla comparativa completa del cliente frente a su competencia.

Por marca: seguidores (y variación vs. snapshot anterior), publicaciones por semana, me gusta,
comentarios e interacciones promedio por publicación, tasa de engagement y mezcla de formatos.
Los valores del cliente se calculan sobre sus últimas N publicaciones con la misma definición
que usa el radar, para que la comparación sea justa. Incluye posición en el ranking por métrica
y participación (share) de interacciones.
"""

from decimal import Decimal
from typing import Any

from api.resolvedores import Contexto, Resultado, delta_porcentual, registrar

ULTIMAS_PUBLICACIONES = 12
COLUMNAS = [
    ("seguidores", "Seguidores", "entero"),
    ("publicaciones_semana", "Posts / semana", "decimal"),
    ("me_gusta_promedio", "Me gusta / post", "entero"),
    ("comentarios_promedio", "Comentarios / post", "entero"),
    ("interacciones_promedio", "Interacciones / post", "entero"),
    ("tasa_engagement", "Engagement", "porcentaje"),
]
CODIGOS = [c for c, _, _ in COLUMNAS]


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None


def _formato_dominante(formatos: dict[str, int] | None) -> str | None:
    if not formatos:
        return None
    # Desempate por nombre para que el resultado sea estable
    return max(formatos.items(), key=lambda kv: (kv[1], kv[0]))[0]


async def valores_propios(
    ctx: Contexto, n: int = ULTIMAS_PUBLICACIONES
) -> tuple[dict[str, float | None], dict[str, int]]:
    """Métricas del cliente con la misma definición que el radar aplica a la competencia:
    seguidores actuales y, sobre sus últimas N publicaciones, promedios, ritmo y engagement.
    Devuelve (valores por código, publicaciones por formato)."""
    propio_agg = await ctx.repo.agregar_metricas(ctx.cuentas, ["seguidores"], ctx.desde, ctx.hasta)
    seg = propio_agg.get("seguidores")
    seguidores = _f(seg.valor) if seg is not None else None
    resumen = await ctx.repo.resumen_ultimas_publicaciones(ctx.cuentas, n)
    valores: dict[str, float | None] = {c: None for c in CODIGOS}
    valores["seguidores"] = seguidores
    formatos: dict[str, int] = {}
    if resumen:
        valores["me_gusta_promedio"] = _f(resumen["me_gusta"])
        valores["comentarios_promedio"] = _f(resumen["comentarios"])
        inter = resumen["interacciones"]
        if inter is None and resumen["me_gusta"] is not None:
            inter = Decimal(resumen["me_gusta"]) + Decimal(resumen["comentarios"] or 0)
        valores["interacciones_promedio"] = _f(inter)
        if resumen["primera"] and resumen["ultima"] and int(resumen["publicaciones"]) >= 2:
            dias = max((resumen["ultima"] - resumen["primera"]).days, 1)
            valores["publicaciones_semana"] = int(resumen["publicaciones"]) / dias * 7
        if inter is not None and seguidores:
            valores["tasa_engagement"] = float(inter) / seguidores * 100
        formatos = dict(resumen["formatos"] or {})
    return valores, formatos


@registrar("benchmark_tabla")
async def resolver(ctx: Contexto) -> Resultado:
    plataforma = ctx.config.get("plataforma")
    n = int(ctx.config.get("ultimas_publicaciones", ULTIMAS_PUBLICACIONES))
    valores_propio, formatos_propio = await valores_propios(ctx, n)

    # Variación del cliente: seguidores de hoy frente a los de hace 7 días (mismo ritmo del radar)
    delta_propio: float | None = None
    serie = await ctx.repo.serie_metricas(ctx.cuentas, ["seguidores"], ctx.desde, ctx.hasta, "dia")
    puntos = [p for p in serie if p["valor"] is not None]
    if len(puntos) >= 2:
        ultimo = puntos[-1]
        previos = [p for p in puntos if (ultimo["periodo"] - p["periodo"]).days >= 7]
        if previos:
            delta_propio = delta_porcentual(ultimo["valor"], previos[-1]["valor"])

    tema = await ctx.repo.tema(ctx.cliente_id)
    filas: list[dict[str, Any]] = [
        {
            "nombre": ctx.config.get("etiqueta_propio") or tema.get("nombre") or "Tu marca",
            "handle": None,
            "logo_url": tema.get("logo_url"),
            "propio": True,
            "valores": valores_propio,
            "delta_seguidores": delta_propio,
            "formatos": formatos_propio,
            "formato_dominante": _formato_dominante(formatos_propio),
            "fecha": ctx.hasta.isoformat(),
        }
    ]

    # --- competidores ----------------------------------------------------------------------
    competidores = await ctx.repo.competidores_con_snapshots(ctx.cliente_id, plataforma, CODIGOS)
    formatos_comp = await ctx.repo.formatos_competidores(ctx.cliente_id, plataforma)
    fechas: set[str] = set()
    for k in competidores:
        valores = {c: _f(k["actual"].get(c)) for c in CODIGOS}
        fmt = formatos_comp.get(int(k["id"]), {})
        if k["fecha_actual"]:
            fechas.add(k["fecha_actual"].isoformat())
        filas.append(
            {
                "nombre": k["nombre"],
                "handle": k["handle"],
                "logo_url": k["logo_url"],
                "propio": False,
                "valores": valores,
                "delta_seguidores": delta_porcentual(
                    k["actual"].get("seguidores"), k["anterior"].get("seguidores")
                ),
                "formatos": fmt,
                "formato_dominante": _formato_dominante(fmt),
                "fecha": k["fecha_actual"].isoformat() if k["fecha_actual"] else None,
            }
        )

    # --- ranking por columna y share de interacciones ---------------------------------------
    for c in CODIGOS:
        orden = sorted(
            (f for f in filas if f["valores"].get(c) is not None),
            key=lambda f: f["valores"][c],
            reverse=True,
        )
        for i, f in enumerate(orden, start=1):
            f.setdefault("posicion", {})[c] = i
    for f in filas:
        f.setdefault("posicion", {})
    total_inter = sum(f["valores"].get("interacciones_promedio") or 0 for f in filas)
    for f in filas:
        v = f["valores"].get("interacciones_promedio")
        f["share_interacciones"] = (
            (v / total_inter * 100) if v is not None and total_inter else None
        )

    lider_eng = next(
        (f["nombre"] for f in filas if f["posicion"].get("tasa_engagement") == 1), None
    )
    return Resultado(
        filas,
        meta={
            "columnas": [{"metrica": c, "etiqueta": e, "formato": fm} for c, e, fm in COLUMNAS],
            "ultimas_publicaciones": n,
            "snapshot": max(fechas) if fechas else None,
            "sin_competidores": len(competidores) == 0,
            "marcas": len(filas),
            "lider_engagement": lider_eng,
        },
    )

"""Hechos del período y su redacción.

Regla dura (CLAUDE.md): el LLM nunca genera cifras. Primero se calculan los hechos desde la
base; con ellos se escribe una redacción por reglas (siempre disponible, sin costo). Si hay LLM,
se le pide reescribirla y su salida solo se acepta si TODA cifra que contiene está entre las
cifras de los hechos (validar_cifras). Si no pasa, se usa la redacción por reglas.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
UMBRAL_ESTABLE = 3.0  # % por debajo del cual un cambio se describe como "estable"


@dataclass
class Hecho:
    metrica: str
    etiqueta: str
    valor: float
    anterior: float | None
    delta: float | None  # %
    formato: str = "entero"


@dataclass
class Hechos:
    red: str
    desde: date
    hasta: date
    kpis: list[Hecho] = field(default_factory=list)
    mejor_dia: tuple[date, float, str] | None = None  # fecha, valor, etiqueta de la métrica
    top_publicacion: dict[str, Any] | None = None  # tipo, fecha, valor, metrica, texto

    def como_dict(self) -> dict[str, Any]:
        return {
            "red": self.red,
            "desde": self.desde.isoformat(),
            "hasta": self.hasta.isoformat(),
            "kpis": [vars(k) for k in self.kpis],
            "mejor_dia": (
                {
                    "fecha": self.mejor_dia[0].isoformat(),
                    "valor": self.mejor_dia[1],
                    "metrica": self.mejor_dia[2],
                }
                if self.mejor_dia
                else None
            ),
            "top_publicacion": self.top_publicacion,
        }


def num(v: float, formato: str = "entero") -> str:
    if formato == "porcentaje":
        return f"{v:.1f}".replace(".", ",") + " %"
    if formato == "moneda":
        return "USD " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if abs(v) < 10 and v != int(v):
        return f"{v:.1f}".replace(".", ",")
    return f"{round(v):,}".replace(",", ".")


def fecha_corta(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]}"


def _cambio(delta: float | None) -> str:
    if delta is None:
        return ""
    if abs(delta) < UMBRAL_ESTABLE:
        return ", estable frente al período anterior"
    sentido = "más" if delta > 0 else "menos"
    return f", un {num(abs(delta))} % {sentido} que el período anterior"


def redactar_base(h: Hechos) -> str:
    """Redacción determinista. Cada cifra sale de los hechos."""
    if not h.kpis:
        return ""
    frases: list[str] = []
    principal = h.kpis[0]
    periodo = f"Entre el {fecha_corta(h.desde)} y el {fecha_corta(h.hasta)}"
    frases.append(
        f"{periodo}, {principal.etiqueta.lower()} en {h.red} fue de "
        f"{num(principal.valor, principal.formato)}{_cambio(principal.delta)}."
    )
    suben = [k for k in h.kpis[1:] if k.delta is not None and k.delta >= UMBRAL_ESTABLE]
    bajan = [k for k in h.kpis[1:] if k.delta is not None and k.delta <= -UMBRAL_ESTABLE]
    if suben:
        partes = [
            f"{k.etiqueta.lower()} ({num(k.valor, k.formato)}, +{num(k.delta or 0)} %)"
            for k in suben
        ]
        frases.append("También crecieron " + _lista(partes) + ".")
    if bajan:
        partes = [
            f"{k.etiqueta.lower()} ({num(k.valor, k.formato)}, −{num(abs(k.delta or 0))} %)"
            for k in bajan
        ]
        frases.append("En cambio bajaron " + _lista(partes) + ".")
    if h.mejor_dia:
        f, v, etiqueta = h.mejor_dia
        frases.append(f"El mejor día fue el {fecha_corta(f)}, con {num(v)} en {etiqueta.lower()}.")
    if h.top_publicacion:
        p = h.top_publicacion
        tipo = f" ({p['tipo']})" if p.get("tipo") else ""
        dia = fecha_corta(date.fromisoformat(p["fecha"]))
        frases.append(
            f"La publicación con mejor resultado fue la del {dia}{tipo}, "
            f"con {num(p['valor'])} {p['metrica'].lower()}."
        )
    return " ".join(frases)


def _lista(partes: list[str]) -> str:
    if len(partes) == 1:
        return partes[0]
    return ", ".join(partes[:-1]) + " y " + partes[-1]


# ---- validación de cifras de la salida del LLM -----------------------------------------

_RE_NUM = re.compile(r"\d[\d.,]*\d|\d")


def _normalizar(token: str) -> float | None:
    t = token.strip(".,")
    if not t:
        return None
    if "," in t:  # coma decimal española: 1.234,5
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") >= 1 and all(len(p) == 3 for p in t.split(".")[1:]):
        t = t.replace(".", "")  # punto de miles: 16.131
    try:
        return float(t)
    except ValueError:
        return None


def cifras_permitidas(h: Hechos) -> set[float]:
    """Toda cifra que puede aparecer legítimamente: valores, anteriores, deltas (con el
    redondeo de la redacción), días y años de las fechas."""
    permitidas: set[float] = set()

    def agregar(v: float | None) -> None:
        if v is None:
            return
        for r in (round(v), round(v, 1), round(abs(v)), round(abs(v), 1)):
            permitidas.add(float(r))

    for k in h.kpis:
        agregar(k.valor)
        agregar(k.anterior)
        agregar(k.delta)
    fechas = [h.desde, h.hasta]
    if h.mejor_dia:
        fechas.append(h.mejor_dia[0])
        agregar(h.mejor_dia[1])
    if h.top_publicacion:
        fechas.append(date.fromisoformat(h.top_publicacion["fecha"]))
        agregar(h.top_publicacion["valor"])
    for f in fechas:
        permitidas.update({float(f.day), float(f.year)})
    return permitidas


def validar_cifras(texto: str, h: Hechos) -> list[str]:
    """Devuelve las cifras del texto que NO están en los hechos (lista vacía = válido)."""
    permitidas = cifras_permitidas(h)
    ajenas = []
    for token in _RE_NUM.findall(texto):
        v = _normalizar(token)
        if v is None:
            continue
        if not any(abs(v - p) < 0.051 for p in permitidas):
            ajenas.append(token)
    return ajenas

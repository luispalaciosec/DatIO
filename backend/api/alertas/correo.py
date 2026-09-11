"""Resumen de alertas por correo (PT-14) vía Resend. Sin RESEND_API_KEY solo se registra."""

import html
import logging
from typing import Any

import httpx

from api.alertas.servicio import AlertaNueva
from api.config import Configuracion

log = logging.getLogger(__name__)
API = "https://api.resend.com/emails"
COLOR = {"alta": "#dc2626", "media": "#f59e0b", "baja": "#64748b"}
NOMBRE_TIPO = {
    "anomalia": "Caída",
    "oportunidad": "Oportunidad",
    "operativa": "Operativa",
    "comercial": "CRM",
}


ESTILO_CAJA = "border:1px solid #e9e9ec;border-radius:14px;padding:12px 14px;margin:8px 0"
ESTILO_ETIQUETA = (
    "display:inline-block;color:#fff;font-size:11px;padding:2px 8px;"
    "border-radius:999px;margin-right:8px;background:"
)
ESTILO_BOTON = (
    "background:#0EA5E9;color:#fff;padding:10px 18px;border-radius:999px;text-decoration:none"
)


def renderizar_resumen(alertas: list[AlertaNueva], fecha: str, url_admin: str) -> str:
    por_cliente: dict[str, list[AlertaNueva]] = {}
    for a in alertas:
        por_cliente.setdefault(a.cliente, []).append(a)
    e = html.escape
    partes = [
        '<div style="font-family:Inter,system-ui,sans-serif;max-width:640px;'
        'margin:0 auto;color:#1f1f2e">',
        '<h1 style="font-weight:300;font-size:24px">Dat<span style="color:#0EA5E9">IO</span>'
        f" · alertas del {e(fecha)}</h1>",
        f'<p style="color:#71717a">{len(alertas)} alerta(s) nueva(s). '
        "Revísalas antes de que las note el cliente.</p>",
    ]
    for cliente, lista in por_cliente.items():
        partes.append(
            f'<h2 style="font-weight:400;font-size:17px;margin:22px 0 8px">{e(cliente)}</h2>'
        )
        for a in lista:
            color = COLOR.get(a.severidad, "#64748b")
            partes.append(
                f'<div style="{ESTILO_CAJA}">'
                f'<span style="{ESTILO_ETIQUETA}{color}">'
                f"{e(NOMBRE_TIPO.get(a.tipo, a.tipo))} · {e(a.severidad)}</span>"
                f'<span style="font-size:12px;color:#71717a">{e(a.red)}</span>'
                f'<div style="margin-top:6px;font-size:14px">{e(a.titulo)}</div></div>'
            )
    partes.append(
        f'<p style="margin-top:24px"><a href="{e(url_admin)}" style="{ESTILO_BOTON}">'
        "Ver en DatIO</a></p></div>"
    )
    return "".join(partes)


async def enviar_resumen(
    config: Configuracion, destinatarios: list[str], alertas: list[AlertaNueva], fecha: str
) -> bool:
    if not alertas:
        return False
    if not config.resend_api_key:
        log.info(
            "RESEND_API_KEY no configurada: %d alerta(s) quedan solo en el admin", len(alertas)
        )
        return False
    if not destinatarios:
        log.warning("Sin destinatarios de alertas (usuarios de equipo activos)")
        return False
    altas = sum(1 for a in alertas if a.severidad == "alta")
    sufijo = f" · {altas} alta(s)" if altas else ""
    asunto = f"DatIO · {len(alertas)} alerta(s){sufijo} · {fecha}"
    cuerpo: dict[str, Any] = {
        "from": config.correo_remitente,
        "to": destinatarios,
        "subject": asunto,
        "html": renderizar_resumen(alertas, fecha, f"{config.frontend_url}/admin/alertas"),
    }
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            API, json=cuerpo, headers={"Authorization": f"Bearer {config.resend_api_key}"}
        )
    if r.status_code >= 400:
        log.error("Resend rechazó el correo: %s %s", r.status_code, r.text[:300])
        return False
    return True

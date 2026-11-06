"""Correos al cliente vía Resend: invitación al reporte y reporte mensual con el PDF adjunto.
Sin RESEND_API_KEY no se envía nada y se informa (nunca se finge el envío)."""

import base64
import html
import logging
from typing import Any

import httpx

from api.config import Configuracion

log = logging.getLogger(__name__)
API = "https://api.resend.com/emails"
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


def _marco(color: str, cuerpo: str) -> str:
    return (
        '<div style="font-family:Inter,system-ui,sans-serif;max-width:620px;margin:0 auto;'
        'color:#1f1f2e;line-height:1.55">'
        f'<div style="height:6px;border-radius:6px;background:{html.escape(color)};'
        'margin-bottom:22px"></div>'
        f"{cuerpo}"
        '<p style="font-size:12px;color:#a1a1aa;margin-top:28px">Enviado por DatIO, la '
        "plataforma de reportería de Geeks Ecuador.</p></div>"
    )


def _boton(url: str, texto: str, color: str) -> str:
    return (
        f'<p style="margin:22px 0"><a href="{html.escape(url)}" style="background:'
        f"{html.escape(color)};color:#fff;padding:11px 20px;border-radius:999px;"
        f'text-decoration:none;font-size:14px">{html.escape(texto)}</a></p>'
    )


def html_invitacion(cliente: str, url: str, color: str) -> str:
    e = html.escape
    return _marco(
        color,
        f'<h1 style="font-weight:300;font-size:24px;margin:0 0 12px">Tu reporte de {e(cliente)} '
        "ya está disponible</h1>"
        "<p>Desde hoy puedes consultar en cualquier momento las métricas de tus redes sociales, "
        "tu sitio web y tu competencia, actualizadas cada mañana.</p>"
        + _boton(url, "Abrir mi reporte", color)
        + '<p style="font-size:13px;color:#52525b">Para entrar usa este mismo correo: con el '
        "botón de Google o pidiendo un enlace de acceso. No necesitas contraseña.</p>",
    )


def html_mensual(
    cliente: str, mes: str, url: str, color: str, secciones: list[dict[str, Any]]
) -> str:
    e = html.escape
    partes = [
        f'<h1 style="font-weight:300;font-size:24px;margin:0 0 6px">Reporte de {e(mes)}</h1>',
        f'<p style="color:#71717a;margin:0 0 18px">{e(cliente)}</p>',
    ]
    for s in secciones:
        if not s.get("texto"):
            continue
        partes.append(
            f'<h2 style="font-weight:500;font-size:15px;margin:18px 0 4px">{e(s["titulo"])}</h2>'
            f'<p style="margin:0;font-size:14px">{e(s["texto"])}</p>'
        )
    partes.append(_boton(url, "Ver el reporte completo", color))
    partes.append('<p style="font-size:13px;color:#52525b">El PDF con el detalle va adjunto.</p>')
    return _marco(color, "".join(partes))


async def enviar(
    config: Configuracion,
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str,
    adjunto: tuple[str, bytes] | None = None,
) -> tuple[bool, str | None]:
    """Devuelve (enviado, error)."""
    if not config.resend_api_key:
        return False, "RESEND_API_KEY no configurada"
    if not destinatarios:
        return False, "sin destinatarios"
    cuerpo: dict[str, Any] = {
        "from": config.correo_remitente,
        "to": destinatarios,
        "subject": asunto,
        "html": cuerpo_html,
    }
    if adjunto is not None:
        cuerpo["attachments"] = [
            {"filename": adjunto[0], "content": base64.b64encode(adjunto[1]).decode()}
        ]
    async with httpx.AsyncClient(timeout=60) as http:
        r = await http.post(
            API, json=cuerpo, headers={"Authorization": f"Bearer {config.resend_api_key}"}
        )
    if r.status_code >= 400:
        log.error("Resend rechazó el correo: %s %s", r.status_code, r.text[:300])
        return False, f"Resend {r.status_code}: {r.text[:200]}"
    return True, None

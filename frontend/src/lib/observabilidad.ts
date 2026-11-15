import * as Sentry from "@sentry/react";

// Sentry en el navegador (Fase 4). Apagado si VITE_SENTRY_DSN no está definida.
// Sin datos personales: sendDefaultPii=false y se limpian del evento el token de render de la
// vista de impresión (?render=…), cualquier JWT y los correos.
const DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined;

const RE_PARAM = /\b(render|token|code|state|access_token)=[^&\s"']+/gi;
const RE_JWT = /eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g;
const RE_CORREO = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;

export function limpiarTexto(texto: string): string {
  return texto.replace(RE_PARAM, "$1=[filtrado]").replace(RE_JWT, "[jwt]").replace(RE_CORREO, "[correo]");
}

function limpiar<T>(valor: T): T {
  if (typeof valor === "string") return limpiarTexto(valor) as T;
  if (Array.isArray(valor)) return valor.map(limpiar) as T;
  if (valor && typeof valor === "object") {
    return Object.fromEntries(Object.entries(valor).map(([k, v]) => [k, limpiar(v)])) as T;
  }
  return valor;
}

export function iniciarSentry(): void {
  if (!DSN) return;
  Sentry.init({
    dsn: DSN,
    environment: import.meta.env.MODE,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend: (evento) => { delete evento.user; return limpiar(evento); },
    beforeBreadcrumb: (miga) => limpiar(miga),
  });
}

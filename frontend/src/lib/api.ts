import { supabase } from "./supabase";
import type { Rango, Reporte, RespuestaConsulta } from "./tipos";

const BASE = import.meta.env.VITE_API_URL as string;

export class ErrorApi extends Error {
  constructor(public status: number, mensaje: string) {
    super(mensaje);
  }
}

export function tokenRender(): string | null {
  return new URLSearchParams(window.location.search).get("render");
}

async function token(): Promise<string> {
  const render = tokenRender();
  if (render) return render; // PT-11: Playwright abre la vista con un token emitido por la API
  const { data } = await supabase.auth.getSession();
  if (!data.session) throw new ErrorApi(401, "Sesión no iniciada");
  return data.session.access_token;
}

async function llamar<T>(ruta: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`${BASE}${ruta}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${await token()}`,
      ...(init.headers ?? {}),
    },
  });
  if (!r.ok) {
    let detalle = r.statusText;
    try {
      detalle = (await r.json()).detail ?? detalle;
    } catch {
      /* sin cuerpo */
    }
    throw new ErrorApi(r.status, detalle);
  }
  return (await r.json()) as T;
}

export const api = {
  reporte: (slug: string) => llamar<Reporte>(`/reportes/${encodeURIComponent(slug)}`),
  consulta: <T>(instancia_id: number, bloque_id: number, rango: Rango, comparar = "periodo_anterior") =>
    llamar<RespuestaConsulta<T>>("/consulta", {
      method: "POST",
      body: JSON.stringify({ instancia_id, bloque_id, ...rango, comparar }),
    }),
  pdf: async (slug: string, rango: Rango): Promise<Blob> => {
    const q = new URLSearchParams({ desde: rango.desde, hasta: rango.hasta });
    const r = await fetch(`${BASE}/reportes/${encodeURIComponent(slug)}/pdf?${q}`, {
      headers: { Authorization: `Bearer ${await token()}` },
    });
    if (!r.ok) throw new ErrorApi(r.status, r.statusText);
    return r.blob();
  },
  yo: () => llamar<{ email: string; rol: string; cliente_id: number | null; slug: string | null }>("/yo"),
};

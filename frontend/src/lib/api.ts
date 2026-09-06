import { supabase } from "./supabase";
import type {
  ActivoConexion, Conexion, Captura, Catalogos, ClienteAdmin, ClienteDetalle, Rango, Reporte, RespuestaConsulta, TemaAdmin, UsuarioAdmin,
} from "./tipos";

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
  admin: {
    clientes: () => llamar<ClienteAdmin[]>("/admin/clientes"),
    cliente: (id: number) => llamar<ClienteDetalle>(`/admin/clientes/${id}`),
    crearCliente: (cuerpo: { nombre: string; slug: string; sector?: string | null }) =>
      llamar<{ id: number; slug: string }>("/admin/clientes", { method: "POST", body: JSON.stringify(cuerpo) }),
    editarCliente: (id: number, cuerpo: Partial<{ nombre: string; sector: string | null; activo: boolean }>) =>
      llamar<ClienteAdmin>(`/admin/clientes/${id}`, { method: "PATCH", body: JSON.stringify(cuerpo) }),
    guardarTema: (id: number, cuerpo: Partial<TemaAdmin>) =>
      llamar<TemaAdmin>(`/admin/clientes/${id}/tema`, { method: "PUT", body: JSON.stringify(cuerpo) }),
    crearCuenta: (id: number, cuerpo: { plataforma: string; id_externo: string; nombre_cuenta?: string; credencial?: string }) =>
      llamar<{ id: number }>(`/admin/clientes/${id}/cuentas`, { method: "POST", body: JSON.stringify(cuerpo) }),
    editarCuenta: (id: number, cuerpo: { nombre_cuenta?: string; activo?: boolean; credencial?: string }) =>
      llamar<{ estado: string }>(`/admin/cuentas/${id}`, { method: "PATCH", body: JSON.stringify(cuerpo) }),
    guardarUsuario: (cuerpo: { email: string; rol: "cliente" | "equipo"; cliente_id?: number | null }) =>
      llamar<{ email: string }>("/admin/usuarios", { method: "POST", body: JSON.stringify(cuerpo) }),
    desactivarUsuario: (email: string) =>
      llamar<{ estado: string }>(`/admin/usuarios/${encodeURIComponent(email)}`, { method: "DELETE" }),
    usuarios: () => llamar<UsuarioAdmin[]>("/admin/usuarios"),
    catalogos: () => llamar<Catalogos>("/admin/catalogos"),
    iniciarConexion: (proveedor: "meta" | "google" | "linkedin", cliente_id: number) =>
      llamar<{ url: string }>(`/admin/conectar/${proveedor}/iniciar?cliente_id=${cliente_id}`),
    importarBusiness: (cliente_id: number) =>
      llamar<{ conexion_id: number; activos: number }>(`/admin/conectar/meta/business?cliente_id=${cliente_id}`, { method: "POST" }),
    conexion: (id: number) => llamar<Conexion>(`/admin/conexiones/${id}`),
    activarConexion: (id: number, activos: ActivoConexion[]) =>
      llamar<{ cuentas: number[] }>(`/admin/conexiones/${id}/activar`, { method: "POST", body: JSON.stringify({ activos }) }),
    capturas: (limite = 50) => llamar<Captura[]>(`/admin/capturas?limite=${limite}`),
  },
  yo: () => llamar<{ email: string; rol: string; cliente_id: number | null; slug: string | null }>("/yo"),
};

// Contratos con el backend (PT-08). No cambiar sin acuerdo.

export type Estado = "consolidado" | "provisional" | "proyectado";

export interface Tema {
  nombre: string;
  slug: string;
  logo_url: string | null;
  banner_url: string | null;
  color_primario: string;
  color_secundario: string;
  color_acento: string;
  fuente_titulos: string;
  fuente_cuerpo: string;
  modo_oscuro: boolean;
}

export interface Bloque {
  id: number;
  tipo: string;
  orden: number;
  ancho: number;
  config: Record<string, unknown>;
}

export interface Pagina {
  id: number;
  plataforma: string | null;
  slug: string;
  titulo: string;
  orden: number;
  icono: string | null;
  cuentas: number; // cuentas activas del cliente en esta red
  bloques: Bloque[];
}

export interface Reporte {
  instancia_id: number;
  nombre_publico: string | null;
  slug_publico: string;
  tema: Tema;
  paginas: Pagina[];
}

export interface RespuestaConsulta<T = unknown> {
  datos: T;
  estado: Estado;
  meta: Record<string, unknown> & { tipo: string; cuentas?: number };
}

export interface Kpi {
  metrica: string;
  etiqueta: string;
  valor: number | null;
  anterior: number | null;
  delta: number | null;
  formato: "entero" | "porcentaje" | "moneda" | "duracion";
  decimales: number;
  unidad: string | null;
  sparkline: number[];
}

export interface SerieLeyenda {
  metrica: string;
  etiqueta: string;
  color: string | null;
  nota: string | null;
  unidad: string | null;
}

export interface DatosSerie {
  puntos: Array<{ periodo: string } & Record<string, number | null>>;
  series: SerieLeyenda[];
}

export interface Publicacion {
  id: number;
  tipo: string | null;
  publicado_en: string | null;
  permalink: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  metricas: Record<string, number>;
}

export interface Rango {
  desde: string; // AAAA-MM-DD
  hasta: string;
}

// ---- administración ----------------------------------------------------------

export interface ClienteAdmin {
  id: number;
  nombre: string;
  slug: string;
  sector: string | null;
  activo: boolean;
  creado_en: string;
  cuentas: number;
  usuarios: number;
  slug_publico: string | null;
  color_primario: string | null;
  logo_url: string | null;
}

export interface TemaAdmin {
  logo_url: string | null;
  banner_url: string | null;
  color_primario: string;
  color_secundario: string;
  color_acento: string;
  fuente_titulos: string;
  fuente_cuerpo: string;
  modo_oscuro: boolean;
}

export interface CuentaAdmin {
  id: number;
  plataforma: string;
  plataforma_nombre: string;
  id_externo: string;
  nombre_cuenta: string | null;
  activo: boolean;
  tiene_credencial: boolean;
  ultima_captura: string | null;
}

export interface UsuarioAdmin {
  email: string;
  rol: "cliente" | "equipo";
  cliente_id: number | null;
  cliente_nombre: string | null;
  activo: boolean;
}

export interface AlertaAdmin {
  id: number;
  cuenta_id: number | null;
  tipo: "anomalia" | "oportunidad" | "operativa";
  severidad: "alta" | "media" | "baja";
  titulo: string;
  detalle: Record<string, unknown> | null;
  resuelta: boolean;
  creada_en: string;
  plataforma: string | null;
  nombre_cuenta: string | null;
  cliente: string | null;
  cliente_id: number | null;
}

export interface CompetidorAdmin {
  id: number;
  plataforma: string;
  plataforma_nombre: string;
  nombre: string;
  handle: string;
  logo_url: string | null;
  orden: number;
  ultimo_snapshot: string | null;
}

export interface ClienteDetalle {
  id: number;
  nombre: string;
  slug: string;
  sector: string | null;
  activo: boolean;
  crm_proveedor: "prometio" | "hubspot" | null;
  crm_empresa_ref: string | null;
  crm_contacto_ref: string | null;
  crm_config: Record<string, unknown>;
  crm_con_credencial: boolean;
  tema: TemaAdmin;
  cuentas: CuentaAdmin[];
  usuarios: UsuarioAdmin[];
  competidores: CompetidorAdmin[];
}

export interface Catalogos {
  plataformas: Array<{ codigo: string; nombre: string }>;
  plantillas: Array<{ id: number; nombre: string; descripcion: string | null }>;
  sectores: string[];
}

export interface Captura {
  id: number;
  conector: string;
  cuenta_id: number | null;
  cliente: string | null;
  nombre_cuenta: string | null;
  estado: string;
  filas_escritas: number;
  error_detalle: string | null;
  iniciado_en: string;
  finalizado_en: string | null;
}

export interface ActivoConexion {
  plataforma: string;
  id_externo: string;
  nombre: string;
  extra?: Record<string, unknown>;
}

export interface Conexion {
  id: number;
  cliente_id: number;
  proveedor: "meta" | "google" | "linkedin";
  creado_por: string;
  activos: ActivoConexion[];
  estado: "pendiente" | "activada";
  creado_en: string;
}

export interface EmpresaCrm { id: string; nombre: string | null; contactos: Array<{ id: string; nombre: string | null; email: string | null }> }
export interface EvaluacionCrm {
  cliente: string; crm: string; ejecutado: boolean; omitidos: string[];
  candidatos: Array<{ codigo: string; tipo: string; titulo: string; evidencia: string; valor: number | null; prioridad: string }>;
  disparados: Array<{ codigo: string; titulo: string; objeto_ref: string | null; error: string | null; url: string | null }>;
}
export interface DisparoCrm {
  id: number; cliente_id: number | null; cliente: string | null; crm_proveedor: string | null; codigo: string;
  titulo: string | null; contexto: Record<string, unknown>; crm_objeto_ref: string | null; error: string | null; disparado_en: string;
}

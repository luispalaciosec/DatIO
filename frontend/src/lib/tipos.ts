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

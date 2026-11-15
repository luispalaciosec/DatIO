import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import { formatearFecha, hoyISO } from "../lib/formato";
import type { Pagina as TPagina, Rango, Reporte as TReporte } from "../lib/tipos";
import { TemaProvider } from "../tema/TemaProvider";
import { Pagina } from "./Pagina";

const NOMBRES: Record<string, string> = {
  meta_fb: "Facebook", meta_ig: "Instagram", linkedin: "LinkedIn", tiktok: "TikTok",
  youtube: "YouTube", ga4: "Sitio web", gsc: "Búsqueda", meta_ads: "Meta Ads", google_ads: "Google Ads",
  app_store: "App Store", google_play: "Google Play", prometio: "CRM", hubspot: "CRM", zoho: "CRM", google_negocio: "Google Negocio",
  todas: "Resumen",
};
const NOMBRE_PAGINA: Record<string, string> = { metricas: "Métricas", publicaciones: "Publicaciones", benchmark: "Benchmark", audiencia: "Audiencia", busqueda: "Búsqueda" };

// Vista de impresión (PT-11): todas las páginas del reporte seguidas, una por hoja.
// Contrato con api/pdf/render.py (generar_pdf):
// - éxito: `data-impresion-lista="1"` en el contenedor y ningún `.bloque-cargando`;
// - fallo: `data-impresion-error="1"` y NUNCA `data-impresion-lista` (el PDF no se imprime);
// - un bloque que falla marca `data-bloque-error="1"` (ver Bloque.tsx) y el PDF se descarta.
export function Imprimir() {
  const { slug = "" } = useParams();
  const [params] = useSearchParams();
  const [reporte, setReporte] = useState<TReporte | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rango: Rango = useMemo(() => ({
    desde: params.get("desde") ?? hoyISO(-28),
    hasta: params.get("hasta") ?? hoyISO(-1),
  }), [params]);

  useEffect(() => {
    document.body.classList.add("modo-print");
    api.reporte(slug).then(setReporte).catch((e: ErrorApi) => setError(e.message));
  }, [slug]);

  // Sin detalles técnicos: esta vista solo la lee el generador del PDF, que la descarta.
  if (error) return <div className="bloque-error" data-impresion-error="1">No se pudo cargar el reporte.</div>;
  if (!reporte) return <div className="bloque-cargando" />;

  const generado = new Date().toLocaleDateString("es-EC", { day: "numeric", month: "long", year: "numeric" });

  return (
    <TemaProvider tema={reporte.tema}>
      <div className="impresion" data-impresion-lista="1">
        {reporte.paginas.filter((p) => p.cuentas > 0 && p.bloques.length > 0).map((p: TPagina) => (
          <section className="hoja" key={p.id}>
            <header className="hoja-cabecera">
              <div className="marca">
                {reporte.tema.logo_url && <img src={reporte.tema.logo_url} alt="" />}
                <span>{reporte.tema.nombre}</span>
              </div>
              <div className="hoja-titulo">
                <h1>{NOMBRES[p.plataforma ?? "todas"] ?? p.plataforma} <small>{NOMBRE_PAGINA[p.slug] ?? p.titulo}</small></h1>
                <div className="hoja-rango">{formatearFecha(rango.desde)} a {formatearFecha(rango.hasta)}</div>
              </div>
            </header>
            <Pagina reporte={reporte} pagina={p} rango={rango} />
            <footer className="hoja-pie">
              <span>{reporte.nombre_publico ?? reporte.tema.nombre} · generado el {generado}</span>
              <span className="pie-datio"><img src="/marca/isotipo.svg" alt="" /> DatIO</span>
            </footer>
          </section>
        ))}
      </div>
    </TemaProvider>
  );
}

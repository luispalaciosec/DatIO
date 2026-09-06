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
  todas: "Resumen",
};
const NOMBRE_PAGINA: Record<string, string> = { metricas: "Métricas", publicaciones: "Publicaciones", benchmark: "Benchmark" };

// Vista de impresión (PT-11): todas las páginas del reporte seguidas, una por hoja.
// Playwright espera a `data-impresion-lista="1"` y a que no quede ningún bloque cargando.
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

  if (error) return <div className="bloque-error" data-impresion-lista="1">{error}</div>;
  if (!reporte) return <div className="bloque-cargando" />;

  const generado = new Date().toLocaleDateString("es-EC", { day: "numeric", month: "long", year: "numeric" });

  return (
    <TemaProvider tema={reporte.tema}>
      <div className="impresion" data-impresion-lista="1">
        {reporte.paginas.filter((p) => p.cuentas > 0).map((p: TPagina) => (
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

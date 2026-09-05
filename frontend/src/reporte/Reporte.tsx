import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import { hoyISO } from "../lib/formato";
import type { Pagina as TPagina, Rango, Reporte as TReporte } from "../lib/tipos";
import { supabase } from "../lib/supabase";
import { TemaProvider } from "../tema/TemaProvider";
import { Pagina } from "./Pagina";

const NOMBRES: Record<string, string> = {
  meta_fb: "Facebook", meta_ig: "Instagram", linkedin: "LinkedIn", tiktok: "TikTok",
  youtube: "YouTube", ga4: "Sitio web", gsc: "Búsqueda", meta_ads: "Meta Ads", google_ads: "Google Ads",
};

export function Reporte() {
  const { slug = "", plataforma, pagina } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [reporte, setReporte] = useState<TReporte | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.reporte(slug).then(setReporte).catch((e: ErrorApi) =>
      setError(e.status === 403 ? "No tienes acceso a este reporte." : e.message));
  }, [slug]);

  // Rango por defecto: últimos 28 días cerrados (hasta ayer).
  const rango: Rango = useMemo(() => ({
    desde: params.get("desde") ?? hoyISO(-28),
    hasta: params.get("hasta") ?? hoyISO(-1),
  }), [params]);

  const actual: TPagina | undefined = useMemo(() => {
    if (!reporte) return undefined;
    return reporte.paginas.find((p) => (p.plataforma ?? "todas") === plataforma && p.slug === pagina)
      ?? reporte.paginas[0];
  }, [reporte, plataforma, pagina]);

  useEffect(() => {
    if (reporte && actual && (!plataforma || !pagina)) {
      navigate(`/${slug}/${actual.plataforma ?? "todas"}/${actual.slug}?${params}`, { replace: true });
    }
  }, [reporte, actual, plataforma, pagina, slug, navigate, params]);

  if (error) return <div className="entrar"><div className="tarjeta"><h1>Reporte</h1><p>{error}</p></div></div>;
  if (!reporte || !actual) return <div className="contenido"><div className="bloque-cargando" /></div>;

  const porRed = agrupar(reporte.paginas);

  return (
    <TemaProvider tema={reporte.tema}>
      <div className="reporte">
        <nav className="nav">
          <h1>{reporte.nombre_publico ?? reporte.tema.nombre}</h1>
          <div className="cliente">{reporte.tema.nombre}</div>
          {Object.entries(porRed).map(([red, paginas]) => (
            <div key={red}>
              <div className="red">{NOMBRES[red] ?? red}</div>
              {paginas.map((p) => (
                <Link
                  key={p.id}
                  className={p.id === actual.id ? "activa" : ""}
                  to={`/${slug}/${p.plataforma ?? "todas"}/${p.slug}?${params}`}
                >
                  {p.slug === "metricas" ? "Métricas" : p.slug === "publicaciones" ? "Publicaciones" : p.titulo}
                </Link>
              ))}
            </div>
          ))}
          <button className="salir" onClick={() => supabase.auth.signOut()}>Cerrar sesión</button>
        </nav>
        <main className="contenido">
          <div className="barra">
            <h2>{actual.titulo}</h2>
            <SelectorRango rango={rango} onChange={(r) => setParams({ desde: r.desde, hasta: r.hasta })} />
          </div>
          <Pagina reporte={reporte} pagina={actual} rango={rango} />
        </main>
      </div>
    </TemaProvider>
  );
}

function agrupar(paginas: TPagina[]): Record<string, TPagina[]> {
  const salida: Record<string, TPagina[]> = {};
  for (const p of paginas) (salida[p.plataforma ?? "todas"] ??= []).push(p);
  return salida;
}

function SelectorRango({ rango, onChange }: { rango: Rango; onChange: (r: Rango) => void }) {
  const [local, setLocal] = useState(rango);
  useEffect(() => setLocal(rango), [rango]);
  const preset = (dias: number) => onChange({ desde: hoyISO(-dias), hasta: hoyISO(-1) });
  return (
    <form className="rango" onSubmit={(e) => { e.preventDefault(); onChange(local); }}>
      <button type="button" onClick={() => preset(7)}>7 días</button>
      <button type="button" onClick={() => preset(28)}>28 días</button>
      <button type="button" onClick={() => preset(90)}>90 días</button>
      <input type="date" value={local.desde} max={local.hasta} onChange={(e) => setLocal({ ...local, desde: e.target.value })} />
      <span>a</span>
      <input type="date" value={local.hasta} min={local.desde} onChange={(e) => setLocal({ ...local, hasta: e.target.value })} />
      <button type="submit">Aplicar</button>
    </form>
  );
}

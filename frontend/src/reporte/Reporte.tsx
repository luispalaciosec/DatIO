import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import { formatearFecha, hoyISO } from "../lib/formato";
import type { Pagina as TPagina, Rango, Reporte as TReporte } from "../lib/tipos";
import { supabase } from "../lib/supabase";
import { TemaProvider } from "../tema/TemaProvider";
import { Pagina } from "./Pagina";

const NOMBRES: Record<string, string> = {
  meta_fb: "Facebook", meta_ig: "Instagram", linkedin: "LinkedIn", tiktok: "TikTok",
  youtube: "YouTube", ga4: "Sitio web", gsc: "Búsqueda", meta_ads: "Meta Ads", google_ads: "Google Ads",
  todas: "Resumen",
};
const NOMBRE_PAGINA: Record<string, string> = { metricas: "Métricas", publicaciones: "Publicaciones", benchmark: "Benchmark", audiencia: "Audiencia", busqueda: "Búsqueda" };

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
  if (!reporte || !actual) return <div className="lienzo"><div className="bloque-cargando" /></div>;

  const porRed = agrupar(reporte.paginas);
  const redActual = actual.plataforma ?? "todas";
  const ruta = (p: TPagina) => `/${slug}/${p.plataforma ?? "todas"}/${p.slug}?${params}`;

  return (
    <TemaProvider tema={reporte.tema}>
      <div className="lienzo">
        <header className="cabecera">
          <div className="marca">
            {reporte.tema.logo_url && <img src={reporte.tema.logo_url} alt="" />}
            <span>{reporte.tema.nombre}</span>
          </div>
          <nav className="tabs">
            {Object.entries(porRed).map(([red, paginas]) => (
              <Link key={red} className={red === redActual ? "activa" : ""} to={ruta(paginas[0])}>
                {NOMBRES[red] ?? red}
              </Link>
            ))}
          </nav>
          <div className="acciones">
            <BotonPdf slug={slug} rango={rango} />
            <button className="boton-redondo" title="Cerrar sesión" onClick={() => supabase.auth.signOut()}>⏻</button>
          </div>
        </header>

        <div className="encabezado">
          <h1>
            {NOMBRES[redActual] ?? redActual}
            <small>
              {reporte.nombre_publico ?? reporte.tema.nombre} · {formatearFecha(rango.desde)} a {formatearFecha(rango.hasta)}
            </small>
          </h1>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <div className="subtabs">
              {porRed[redActual].map((p) => (
                <Link key={p.id} className={p.id === actual.id ? "activa" : ""} to={ruta(p)}>
                  {NOMBRE_PAGINA[p.slug] ?? p.titulo}
                </Link>
              ))}
            </div>
            <SelectorRango rango={rango} onChange={(r) => setParams({ desde: r.desde, hasta: r.hasta })} />
          </div>
        </div>

        {actual.cuentas > 0 ? (
          <Pagina reporte={reporte} pagina={actual} rango={rango} />
        ) : (
          <SinConexion red={NOMBRES[redActual] ?? redActual} />
        )}
      </div>
    </TemaProvider>
  );
}

function SinConexion({ red }: { red: string }) {
  return (
    <div className="tarjeta sin-conexion">
      <h2>{red} todavía no está conectado</h2>
      <p>
        Esta marca no tiene una cuenta de {red} vinculada a DatIO, por eso no hay métricas que mostrar.
        Un usuario del equipo puede conectarla desde el administrador con el botón «Conectar».
      </p>
      <Link className="boton" to="/admin">Ir al administrador</Link>
    </div>
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
      <button type="button" onClick={() => preset(7)}>7 d</button>
      <button type="button" onClick={() => preset(28)}>28 d</button>
      <button type="button" onClick={() => preset(90)}>90 d</button>
      <input type="date" value={local.desde} max={local.hasta} onChange={(e) => setLocal({ ...local, desde: e.target.value })} />
      <span className="comparado">a</span>
      <input type="date" value={local.hasta} min={local.desde} onChange={(e) => setLocal({ ...local, hasta: e.target.value })} />
      <span className="comparado">vs. período anterior</span>
      <button type="submit">Aplicar</button>
    </form>
  );
}

function BotonPdf({ slug, rango }: { slug: string; rango: Rango }) {
  const [estado, setEstado] = useState<"listo" | "generando" | "error">("listo");
  async function descargar() {
    setEstado("generando");
    try {
      const blob = await api.pdf(slug, rango);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slug}_${rango.desde}_${rango.hasta}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setEstado("listo");
    } catch {
      setEstado("error");
    }
  }
  return (
    <button className="boton-pdf" onClick={descargar} disabled={estado === "generando"}>
      {estado === "generando" ? "Generando PDF…" : estado === "error" ? "Error, reintentar" : "Descargar PDF"}
    </button>
  );
}

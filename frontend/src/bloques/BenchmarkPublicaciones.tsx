import { urlImagen } from "../lib/api";
import { formatearCompacto } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

interface PubCompetencia {
  id: string;
  competidor: string;
  handle: string | null;
  logo_url: string | null;
  tipo: string | null;
  publicado_en: string | null;
  permalink: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  metricas: Record<string, number | null>;
}

export function BenchmarkPublicaciones({ respuesta }: { respuesta: RespuestaConsulta<PubCompetencia[]> }) {
  const metricas = (respuesta.meta.metricas as Array<{ metrica: string; etiqueta: string }>) ?? [];
  if (respuesta.datos.length === 0) return <div className="vacio">Todavía no hay publicaciones de la competencia capturadas por el radar.</div>;
  return (
    <div className="top-pubs">
      {respuesta.datos.map((p, i) => (
        <a key={p.id} className="pub" href={p.permalink ?? "#"} target="_blank" rel="noreferrer">
          <div className="pub-imagen">
            {p.thumbnail_url ? <img src={urlImagen(p.thumbnail_url) ?? ""} alt="" referrerPolicy="no-referrer" loading="lazy" /> : <div className="pub-sin-imagen">{p.tipo ?? "post"}</div>}
            <span className="pub-rank">#{i + 1}</span>
            {p.tipo && <span className="pub-tipo">{p.tipo}</span>}
          </div>
          <div className="pub-cuerpo">
            <div className="pub-competidor">
              {p.logo_url ? <img src={urlImagen(p.logo_url) ?? ""} alt="" referrerPolicy="no-referrer" /> : <span className="inicial">{p.competidor.slice(0, 1)}</span>}
              <strong>{p.competidor}</strong>
            </div>
            <div className="pub-caption">{p.caption ? (p.caption.length > 80 ? `${p.caption.slice(0, 80)}…` : p.caption) : "(sin texto)"}</div>
            <div className="pub-fecha">{p.publicado_en ? new Date(p.publicado_en).toLocaleDateString("es-EC", { day: "numeric", month: "short" }) : ""}</div>
            <div className="pub-metricas">
              {metricas.filter((m) => p.metricas[m.metrica] != null).map((m) => (
                <span key={m.metrica}><strong>{formatearCompacto(p.metricas[m.metrica])}</strong> {m.etiqueta.toLowerCase()}</span>
              ))}
            </div>
          </div>
        </a>
      ))}
    </div>
  );
}

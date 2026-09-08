import { formatearCompacto } from "../lib/formato";
import type { Publicacion, RespuestaConsulta } from "../lib/tipos";

export function TopPublicaciones({ respuesta }: { respuesta: RespuestaConsulta<Publicacion[]> }) {
  const metricas = (respuesta.meta.metricas as Array<{ metrica: string; etiqueta: string }>) ?? [];
  if (respuesta.datos.length === 0) return <div className="vacio">Sin publicaciones en el período.</div>;
  return (
    <div className="top-pubs">
      {respuesta.datos.map((p, i) => (
        <a key={p.id} className="pub" href={p.permalink ?? "#"} target="_blank" rel="noreferrer">
          <div className="pub-imagen">
            {p.thumbnail_url ? <img src={p.thumbnail_url} alt="" referrerPolicy="no-referrer" loading="lazy" /> : <div className="pub-sin-imagen">{p.tipo ?? "post"}</div>}
            <span className="pub-rank">#{i + 1}</span>
            {p.tipo && <span className="pub-tipo">{p.tipo}</span>}
          </div>
          <div className="pub-cuerpo">
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

import { formatearValor } from "../lib/formato";
import type { Publicacion, RespuestaConsulta } from "../lib/tipos";

export function TablaPublicaciones({ respuesta }: { respuesta: RespuestaConsulta<Publicacion[]> }) {
  const columnas = (respuesta.meta.columnas as Array<{ metrica: string; etiqueta: string }>) ?? [];
  if (respuesta.datos.length === 0) {
    return <div className="vacio">Sin publicaciones en el período. Las métricas por publicación llegan con los conectores de contenido.</div>;
  }
  return (
    <table className="publicaciones">
      <thead>
        <tr>
          <th></th>
          <th>Publicación</th>
          <th>Fecha</th>
          {columnas.map((c) => <th key={c.metrica} className="num">{c.etiqueta}</th>)}
        </tr>
      </thead>
      <tbody>
        {respuesta.datos.map((p) => (
          <tr key={p.id}>
            <td>{p.thumbnail_url ? <img src={p.thumbnail_url} alt="" /> : null}</td>
            <td>
              {p.permalink ? <a href={p.permalink} target="_blank" rel="noreferrer">{recortar(p.caption)}</a> : recortar(p.caption)}
              {p.tipo && <div style={{ fontSize: 11, color: "var(--gris-500)" }}>{p.tipo}</div>}
            </td>
            <td>{p.publicado_en ? new Date(p.publicado_en).toLocaleDateString("es-EC") : "—"}</td>
            {columnas.map((c) => <td key={c.metrica} className="num">{formatearValor(p.metricas[c.metrica] ?? null)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function recortar(texto: string | null, n = 90): string {
  if (!texto) return "(sin texto)";
  return texto.length > n ? `${texto.slice(0, n)}…` : texto;
}

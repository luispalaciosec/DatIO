import { formatearValor } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

type Fila = { etiqueta: string; valores: Record<string, number> };

export function TablaRanking({ respuesta }: { respuesta: RespuestaConsulta<Fila[]> }) {
  const columnas = (respuesta.meta.columnas as Array<{ metrica: string; etiqueta: string; unidad: string | null }>) ?? [];
  if (respuesta.datos.length === 0) return <div className="vacio">Sin datos en el período.</div>;
  const formato = (u: string | null) => (u === "porcentaje" ? "porcentaje" : u === "posicion" ? "entero" : "entero");
  return (
    <table className="publicaciones tabla">
      <thead><tr><th>#</th><th>{String(respuesta.meta.etiqueta_dimension)}</th>{columnas.map((c) => <th key={c.metrica} className="num">{c.etiqueta}</th>)}</tr></thead>
      <tbody>
        {respuesta.datos.map((f, i) => (
          <tr key={f.etiqueta}>
            <td className="sutil">{i + 1}</td>
            <td className="celda-larga" title={f.etiqueta}>{f.etiqueta.startsWith("http") ? f.etiqueta.replace(/^https?:\/\/[^/]+/, "") || "/" : f.etiqueta}</td>
            {columnas.map((c) => <td key={c.metrica} className="num">{formatearValor(f.valores[c.metrica] ?? null, formato(c.unidad), c.unidad === "posicion" || c.unidad === "porcentaje" ? 1 : 0)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

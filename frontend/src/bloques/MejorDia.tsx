import { formatearCompacto } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

type Fila = { dia: string; publicaciones: number; promedio: number | null };

export function MejorDia({ respuesta }: { respuesta: RespuestaConsulta<Fila[]> }) {
  const filas = respuesta.datos;
  if (filas.every((f) => f.promedio == null)) return <div className="vacio">Sin publicaciones suficientes en el período.</div>;
  const max = Math.max(...filas.map((f) => f.promedio ?? 0), 1);
  const mejor = respuesta.meta.mejor as string | null;
  return (
    <div className="geo">
      <div className="sutil" style={{ marginBottom: 10 }}>Interacciones promedio por publicación según el día en que se publicó{mejor && <> · mejor día: <strong>{mejor}</strong></>}</div>
      <div className="dias">
        {filas.map((f) => (
          <div key={f.dia} className={`dia ${f.dia === mejor ? "mejor" : ""}`}>
            <div className="edad-barra"><div style={{ height: `${((f.promedio ?? 0) / max) * 100}%` }} /></div>
            <div className="edad-valor">{f.promedio != null ? formatearCompacto(f.promedio) : "—"}</div>
            <div className="edad-etiqueta">{f.dia.slice(0, 3)}</div>
            <div className="sutil">{f.publicaciones} pub.</div>
          </div>
        ))}
      </div>
    </div>
  );
}

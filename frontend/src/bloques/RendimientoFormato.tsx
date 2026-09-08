import { formatearCompacto } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

type Fila = { tipo: string; publicaciones: number; promedios: Record<string, number> };

export function RendimientoFormato({ respuesta }: { respuesta: RespuestaConsulta<Fila[]> }) {
  const metricas = (respuesta.meta.metricas as Array<{ metrica: string; etiqueta: string }>) ?? [];
  if (respuesta.datos.length === 0) return <div className="vacio">Sin publicaciones en el período.</div>;
  return (
    <div className="formatos">
      {respuesta.datos.map((f) => (
        <div key={f.tipo} className="formato">
          <div className="formato-tipo">{f.tipo}</div>
          <div className="sutil">{f.publicaciones} publicación{f.publicaciones === 1 ? "" : "es"}</div>
          <dl>
            {metricas.map((m) => (
              <div key={m.metrica}><dt>{m.etiqueta} promedio</dt><dd>{f.promedios[m.metrica] != null ? formatearCompacto(f.promedios[m.metrica]) : "—"}</dd></div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

import { formatearValor } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

interface FilaBenchmark {
  nombre: string;
  handle: string | null;
  logo_url: string | null;
  propio: boolean;
  valores: Record<string, number | null>;
  deltas: Record<string, number | null>;
  fecha: string | null;
}

export function BenchmarkGrid({ respuesta }: { respuesta: RespuestaConsulta<FilaBenchmark[]> }) {
  const metricas = (respuesta.meta.metricas as Array<{ metrica: string; etiqueta: string }>) ?? [];
  const filas = respuesta.datos;
  if (respuesta.meta.sin_competidores) {
    return <div className="vacio">Sin competidores configurados para esta red. Se agregan desde Administración, ficha del cliente, pestaña Competidores.</div>;
  }
  const principal = metricas[0]?.metrica ?? "seguidores";
  const max = Math.max(...filas.map((f) => f.valores[principal] ?? 0), 1);
  return (
    <div className="benchmark">
      {filas.map((f) => (
        <div className={`competidor ${f.propio ? "propio" : ""}`} key={f.nombre}>
          <div className="competidor-cabecera">
            {f.logo_url ? <img src={f.logo_url} alt="" referrerPolicy="no-referrer" /> : <span className="inicial">{f.nombre.slice(0, 1)}</span>}
            <div>
              <strong>{f.nombre}</strong>
              {f.handle && <div className="sutil">@{f.handle}</div>}
            </div>
          </div>
          <div className="competidor-principal">
            <div className="valor">{formatearValor(f.valores[principal] ?? null)}</div>
            <div className="sutil">{metricas[0]?.etiqueta}</div>
            <div className="barra"><div style={{ width: `${((f.valores[principal] ?? 0) / max) * 100}%` }} /></div>
            {f.deltas[principal] != null && (
              <div className={`delta ${f.deltas[principal]! > 0 ? "sube" : f.deltas[principal]! < 0 ? "baja" : "neutro"}`}>
                {f.deltas[principal]! > 0 ? "▲" : f.deltas[principal]! < 0 ? "▼" : "•"} {Math.abs(f.deltas[principal]!).toLocaleString("es-EC", { maximumFractionDigits: 1 })}% vs. snapshot anterior
              </div>
            )}
          </div>
          <dl className="competidor-secundarias">
            {metricas.slice(1).map((m) => (
              <div key={m.metrica}><dt>{m.etiqueta}</dt><dd>{formatearValor(f.valores[m.metrica] ?? null)}</dd></div>
            ))}
          </dl>
          {f.fecha && !f.propio && <div className="sutil">snapshot {f.fecha}</div>}
        </div>
      ))}
    </div>
  );
}

import { urlImagen } from "../lib/api";
import { formatearValor } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

interface FilaTabla {
  nombre: string;
  handle: string | null;
  logo_url: string | null;
  propio: boolean;
  valores: Record<string, number | null>;
  delta_seguidores: number | null;
  formatos: Record<string, number>;
  formato_dominante: string | null;
  posicion: Record<string, number>;
  share_interacciones: number | null;
  fecha: string | null;
}
interface Columna { metrica: string; etiqueta: string; formato: string }

const FORMATO_COLOR: Record<string, string> = { reel: "#7c3aed", carrusel: "#0ea5e9", imagen: "#f59e0b", video: "#10b981", otro: "#9ca3af" };

function celda(v: number | null, formato: string): string {
  if (formato === "decimal") return formatearValor(v, "entero", 1);
  if (formato === "porcentaje") return formatearValor(v, "porcentaje", 2);
  return formatearValor(v, "entero", 0);
}

export function BenchmarkTabla({ respuesta }: { respuesta: RespuestaConsulta<FilaTabla[]> }) {
  const columnas = (respuesta.meta.columnas as Columna[]) ?? [];
  const filas = respuesta.datos;
  if (respuesta.meta.sin_competidores) {
    return <div className="vacio">Sin competidores configurados para esta red. Se agregan desde Administración, ficha del cliente, pestaña Competidores.</div>;
  }
  const max: Record<string, number> = {};
  for (const c of columnas) max[c.metrica] = Math.max(...filas.map((f) => f.valores[c.metrica] ?? 0), 0);
  const marcas = filas.length;
  return (
    <div className="bench-tabla-envoltura">
      <table className="bench-tabla">
        <thead>
          <tr>
            <th>Marca</th>
            {columnas.map((c) => <th key={c.metrica}>{c.etiqueta}</th>)}
            <th>Formatos (últimas {String(respuesta.meta.ultimas_publicaciones ?? 12)})</th>
            <th>Share de interacciones</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.nombre} className={f.propio ? "propio" : ""}>
              <td className="bench-marca">
                {f.logo_url ? <img src={urlImagen(f.logo_url) ?? ""} alt="" referrerPolicy="no-referrer" /> : <span className="inicial">{f.nombre.slice(0, 1)}</span>}
                <div>
                  <strong>{f.nombre}</strong>
                  <div className="sutil">{f.handle ? `@${f.handle}` : f.propio ? "tu cuenta" : ""}</div>
                </div>
              </td>
              {columnas.map((c) => {
                const v = f.valores[c.metrica] ?? null;
                const pos = f.posicion[c.metrica];
                return (
                  <td key={c.metrica} className="bench-celda">
                    <div className="bench-valor">
                      <span>{celda(v, c.formato)}</span>
                      {pos != null && <span className={`bench-pos ${pos === 1 ? "lider" : ""}`}>#{pos}/{marcas}</span>}
                    </div>
                    {c.metrica === "seguidores" && f.delta_seguidores != null && (
                      <div className={`delta ${f.delta_seguidores > 0 ? "sube" : f.delta_seguidores < 0 ? "baja" : "neutro"}`}>
                        {f.delta_seguidores > 0 ? "▲" : f.delta_seguidores < 0 ? "▼" : "•"} {Math.abs(f.delta_seguidores).toLocaleString("es-EC", { maximumFractionDigits: 2 })}% en la semana
                      </div>
                    )}
                    <div className="barra"><div style={{ width: `${max[c.metrica] ? ((v ?? 0) / max[c.metrica]) * 100 : 0}%` }} /></div>
                  </td>
                );
              })}
              <td>
                <Formatos formatos={f.formatos} />
              </td>
              <td className="bench-celda">
                <div className="bench-valor"><span>{formatearValor(f.share_interacciones, "porcentaje", 1)}</span></div>
                <div className="barra"><div style={{ width: `${f.share_interacciones ?? 0}%` }} /></div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="sutil bench-nota">
        Promedios por publicación calculados sobre las últimas {String(respuesta.meta.ultimas_publicaciones ?? 12)} publicaciones de cada marca. Engagement = interacciones por publicación / seguidores.
        {respuesta.meta.snapshot ? ` Competencia capturada el ${String(respuesta.meta.snapshot)}.` : ""}
      </div>
    </div>
  );
}

function Formatos({ formatos }: { formatos: Record<string, number> }) {
  const total = Object.values(formatos).reduce((a, b) => a + b, 0);
  if (!total) return <span className="sutil">—</span>;
  const entradas = Object.entries(formatos).sort((a, b) => b[1] - a[1]);
  return (
    <div className="bench-formatos">
      <div className="bench-formatos-barra">
        {entradas.map(([t, n]) => <span key={t} style={{ width: `${(n / total) * 100}%`, background: FORMATO_COLOR[t] ?? FORMATO_COLOR.otro }} title={`${t}: ${n}`} />)}
      </div>
      <div className="bench-formatos-leyenda">
        {entradas.map(([t, n]) => <span key={t}><i style={{ background: FORMATO_COLOR[t] ?? FORMATO_COLOR.otro }} />{t} {Math.round((n / total) * 100)}%</span>)}
      </div>
    </div>
  );
}

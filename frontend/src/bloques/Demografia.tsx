import { formatearValor } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

type Datos = { edades: Array<{ etiqueta: string; valor: number }>; generos: Array<{ etiqueta: string; valor: number; porcentaje: number | null }> };
const COLORES = ["var(--color-primario)", "var(--color-secundario)", "#a1a1aa"];

export function Demografia({ respuesta }: { respuesta: RespuestaConsulta<Datos> }) {
  const { edades, generos } = respuesta.datos;
  if (edades.length === 0 && generos.length === 0) return <div className="vacio">Sin demografía disponible. Instagram la entrega a partir de 100 seguidores.</div>;
  const max = Math.max(...edades.map((e) => e.valor), 1);
  return (
    <div className="geo demografia">
      <div>
        <div className="sutil" style={{ marginBottom: 10 }}>Edad de la audiencia</div>
        <div className="edades">
          {edades.map((e) => (
            <div key={e.etiqueta} className="edad">
              <div className="edad-barra"><div style={{ height: `${(e.valor / max) * 100}%` }} /></div>
              <div className="edad-valor">{formatearValor(e.valor)}</div>
              <div className="edad-etiqueta">{e.etiqueta}</div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="sutil" style={{ marginBottom: 10 }}>Género</div>
        <div className="generos">
          <div className="genero-barra">
            {generos.map((g, i) => <div key={g.etiqueta} style={{ width: `${g.porcentaje ?? 0}%`, background: COLORES[i % COLORES.length] }} title={`${g.etiqueta} ${g.porcentaje}%`} />)}
          </div>
          {generos.map((g, i) => (
            <div key={g.etiqueta} className="genero-item"><span className="punto" style={{ background: COLORES[i % COLORES.length] }} />{g.etiqueta} <strong>{g.porcentaje}%</strong> <span className="sutil">{formatearValor(g.valor)}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}

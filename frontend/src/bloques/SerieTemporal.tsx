import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatearCompacto, formatearFecha } from "../lib/formato";
import type { DatosSerie, RespuestaConsulta } from "../lib/tipos";

const PALETA = ["#4285F4", "#34A853", "#FBBC04", "#EA4335", "#9333EA"];

export function SerieTemporal({ respuesta, provisional }: { respuesta: RespuestaConsulta<DatosSerie>; provisional: boolean }) {
  const { puntos, series } = respuesta.datos;
  if (puntos.length === 0) return <div className="vacio">Sin datos en el período seleccionado.</div>;
  const mostrarNotas = respuesta.meta.mostrar_notas !== false;
  return (
    <div className="serie">
      {provisional && <span className="provisional">incluye datos provisionales</span>}
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={puntos} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="periodo" tickFormatter={formatearFecha} fontSize={12} />
          <YAxis tickFormatter={(v) => formatearCompacto(Number(v))} fontSize={12} width={48} />
          <Tooltip labelFormatter={(l) => formatearFecha(String(l))} formatter={(v) => Number(v).toLocaleString("es-EC")} />
          <Legend />
          {series.map((s, i) => (
            <Line
              key={s.metrica}
              type="monotone"
              dataKey={s.metrica}
              name={s.etiqueta}
              stroke={s.color ?? PALETA[i % PALETA.length]}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      {mostrarNotas && (
        <div className="notas">
          {series.filter((s) => s.nota).map((s, i) => (
            <div key={s.metrica}>
              <span className="punto" style={{ background: s.color ?? PALETA[i % PALETA.length] }} />
              <strong>{s.etiqueta}:</strong> {s.nota}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

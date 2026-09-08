import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatearCompacto, formatearFecha } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

interface DatosBench { puntos: Array<Record<string, number | string>>; series: Array<{ clave: string; propio: boolean }> }
const PALETA = ["#64748b", "#f59e0b", "#10b981", "#8b5cf6", "#ec4899", "#0ea5e9"];

export function BenchmarkSerie({ respuesta }: { respuesta: RespuestaConsulta<DatosBench> }) {
  const { puntos, series } = respuesta.datos;
  if (respuesta.meta.sin_competidores) return <div className="vacio">Sin competidores configurados para esta red.</div>;
  if (puntos.length === 0) return <div className="vacio">Todavía no hay capturas del radar.</div>;
  const snapshots = Number(respuesta.meta.snapshots ?? 0);
  let i = 0;
  return (
    <div className="serie">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={puntos} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="fecha" tickFormatter={formatearFecha} fontSize={12} />
          <YAxis tickFormatter={(v) => formatearCompacto(Number(v))} fontSize={12} width={56} scale="log" domain={["auto", "auto"]} allowDataOverflow />
          <Tooltip labelFormatter={(l) => formatearFecha(String(l))} formatter={(v) => Number(v).toLocaleString("es-EC")} />
          <Legend />
          {series.map((s) => (
            <Line
              key={s.clave}
              type="monotone"
              dataKey={s.clave}
              name={s.clave}
              stroke={s.propio ? "var(--color-primario)" : PALETA[i++ % PALETA.length]}
              strokeWidth={s.propio ? 3 : 2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="sutil">
        Tu marca: dato diario. Competencia: una captura semanal del radar{snapshots <= 1 ? " (con la próxima captura aparecerá la tendencia)" : ` (${snapshots} capturas)`}. Escala logarítmica para que quepan marcas de distinto tamaño.
      </div>
    </div>
  );
}

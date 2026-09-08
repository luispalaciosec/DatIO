import { formatearValor } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

type Fila = { etiqueta: string; valor: number; porcentaje: number | null };
const PAISES: Record<string, string> = { EC: "Ecuador", US: "Estados Unidos", CO: "Colombia", PE: "Perú", ES: "España", AR: "Argentina", VE: "Venezuela", MX: "México", CL: "Chile", BR: "Brasil", IT: "Italia", CA: "Canadá", DE: "Alemania", GB: "Reino Unido", ECU: "Ecuador", USA: "Estados Unidos", COL: "Colombia", PER: "Perú", ESP: "España", ARG: "Argentina", VEN: "Venezuela", MEX: "México", CHL: "Chile", BRA: "Brasil", ITA: "Italia", CAN: "Canadá", DEU: "Alemania", GBR: "Reino Unido", "United States": "Estados Unidos", Spain: "España", Germany: "Alemania", Brazil: "Brasil", Peru: "Perú", Mexico: "México" };

export function Distribucion({ respuesta }: { respuesta: RespuestaConsulta<Fila[]> }) {
  const filas = respuesta.datos;
  if (filas.length === 0) return <div className="vacio">Sin datos de {String(respuesta.meta.dimension)} en el período.</div>;
  const max = Math.max(...filas.map((f) => f.valor), 1);
  const dimension = String(respuesta.meta.dimension);
  const etiqueta = (t: string) => (dimension === "pais" ? PAISES[t.toUpperCase()] ?? PAISES[t] ?? t : t.replace(/, .*Province$/, ""));
  return (
    <div className="geo">
      <div className="sutil" style={{ marginBottom: 10 }}>{String(respuesta.meta.etiqueta)} por {dimension.replace("_", " ")}{respuesta.meta.modo === "ultimo" ? " · último snapshot" : " · acumulado del período"}</div>
      {filas.map((f) => (
        <div key={f.etiqueta} className="fila-dist">
          <span className="fila-dist-etiqueta" title={f.etiqueta}>{etiqueta(f.etiqueta)}</span>
          <div className="barra"><div style={{ width: `${(f.valor / max) * 100}%` }} /></div>
          <span className="fila-dist-valor">{formatearValor(f.valor)}{f.porcentaje != null && <small> {f.porcentaje}%</small>}</span>
        </div>
      ))}
    </div>
  );
}

import { Area, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatearCompacto, formatearFecha, formatearValor } from "../lib/formato";
import type { RespuestaConsulta } from "../lib/tipos";

interface DatosPacing {
  metrica: string; etiqueta: string; agregacion: string;
  mes_inicio: string; mes_fin: string; corte: string;
  dias_transcurridos: number; dias_restantes: number;
  acumulado: number; proyeccion_p50: number | null; proyeccion_p10: number | null; proyeccion_p90: number | null;
  ritmo_diario: number | null; cierre_anterior: number | null; mismo_dia_anterior: number | null;
  delta_vs_anterior: number | null; delta_mismo_dia: number | null;
  objetivo: number | null; avance_objetivo: number | null; proyeccion_vs_objetivo: number | null;
  curva: Array<Record<string, number | string>>; cerrado: boolean; confiable: boolean;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

export function PacingMes({ respuesta, provisional }: { respuesta: RespuestaConsulta<DatosPacing | null>; provisional: boolean }) {
  const d = respuesta.datos;
  if (!d) return <div className="vacio">Sin datos suficientes para el mes.</div>;
  const mes = MESES[Number(d.mes_inicio.slice(5, 7)) - 1];
  const totalDias = d.dias_transcurridos + d.dias_restantes;
  const avanceMes = totalDias ? (d.dias_transcurridos / totalDias) * 100 : 0;
  const esNivel = d.agregacion === "ultimo";
  const delta = (v: number | null) => v == null ? null : (
    <span className={`delta ${v > 0 ? "sube" : v < 0 ? "baja" : "neutro"}`}>{v > 0 ? "▲" : v < 0 ? "▼" : "•"} {Math.abs(v).toLocaleString("es-EC", { maximumFractionDigits: 1 })}%</span>
  );
  return (
    <div className="pacing">
      <div className="pacing-cabecera">
        <div>
          <div className="etiqueta">{d.etiqueta} · {mes}{provisional && <span className="provisional">provisional</span>}</div>
          <div className="pacing-grande">{formatearValor(d.acumulado)}</div>
          <div className="sutil">{esNivel ? `nivel al ${formatearFecha(d.corte)}` : `acumulado al ${formatearFecha(d.corte)}`} · día {d.dias_transcurridos} de {totalDias}</div>
        </div>
        <div className="pacing-proyeccion">
          <div className="etiqueta">{d.cerrado ? "Cierre" : "Cierre proyectado"}</div>
          <div className="pacing-mediano">{formatearValor(d.proyeccion_p50)}</div>
          {!d.cerrado && d.proyeccion_p10 != null && d.proyeccion_p90 != null && (
            <div className="sutil">rango {formatearCompacto(d.proyeccion_p10)} – {formatearCompacto(d.proyeccion_p90)}</div>
          )}
          {d.cierre_anterior != null && (
            <div className="sutil">mes anterior {formatearCompacto(d.cierre_anterior)} {delta(d.delta_vs_anterior)}</div>
          )}
        </div>
      </div>

      <div className="pacing-barras">
        <div className="pacing-barra"><span>Mes transcurrido</span><div className="barra"><div style={{ width: `${avanceMes}%` }} /></div><b>{Math.round(avanceMes)}%</b></div>
        {d.objetivo != null ? (
          <div className="pacing-barra"><span>Objetivo {formatearCompacto(d.objetivo)}</span><div className="barra"><div className={d.avance_objetivo != null && d.avance_objetivo >= avanceMes ? "ok" : "atras"} style={{ width: `${Math.min(100, d.avance_objetivo ?? 0)}%` }} /></div><b>{Math.round(d.avance_objetivo ?? 0)}%</b></div>
        ) : d.mismo_dia_anterior != null && !esNivel ? (
          <div className="pacing-barra"><span>Mismo día del mes anterior: {formatearCompacto(d.mismo_dia_anterior)}</span><b>{delta(d.delta_mismo_dia)}</b></div>
        ) : null}
      </div>

      <ResponsiveContainer width="100%" height={150}>
        <ComposedChart data={d.curva} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <XAxis dataKey="fecha" tickFormatter={formatearFecha} fontSize={11} interval={6} />
          <YAxis tickFormatter={(v) => formatearCompacto(Number(v))} fontSize={11} width={44} domain={["auto", "auto"]} />
          <Tooltip labelFormatter={(l) => formatearFecha(String(l))} formatter={(v, n) => [Number(v).toLocaleString("es-EC", { maximumFractionDigits: 0 }), n === "real" ? "Real" : n === "proyeccion" ? "Proyección" : n === "p90" ? "Escenario alto" : "Escenario bajo"]} />
          <Area type="monotone" dataKey="p90" stroke="none" fill="var(--color-primario)" fillOpacity={0.08} isAnimationActive={false} />
          <Area type="monotone" dataKey="p10" stroke="none" fill="#ffffff" fillOpacity={1} isAnimationActive={false} />
          <Line type="monotone" dataKey="real" stroke="var(--color-primario)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="proyeccion" stroke="var(--color-primario)" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      {!d.confiable && <div className="sutil">Proyección con pocos días de referencia: se afina a medida que se acumula historia.</div>}
    </div>
  );
}

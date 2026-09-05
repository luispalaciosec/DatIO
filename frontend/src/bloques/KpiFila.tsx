import { formatearValor } from "../lib/formato";
import type { Kpi, RespuestaConsulta } from "../lib/tipos";

export function KpiFila({ respuesta, provisional }: { respuesta: RespuestaConsulta<Kpi[]>; provisional: boolean }) {
  return (
    <div className="kpis">
      {respuesta.datos.map((k) => (
        <div className="kpi" key={k.metrica}>
          <div className="etiqueta">{k.etiqueta}{provisional && <span className="provisional">provisional</span>}</div>
          <div className="valor">{formatearValor(k.valor, k.formato, k.decimales)}</div>
          <Delta delta={k.delta} anterior={k.anterior} formato={k.formato} />
          <Sparkline valores={k.sparkline} />
        </div>
      ))}
    </div>
  );
}

function Delta({ delta, anterior, formato }: { delta: number | null; anterior: number | null; formato: string }) {
  if (delta === null) return <div className="delta neutro">{anterior === null ? "sin período anterior" : "—"}</div>;
  const clase = delta > 0 ? "sube" : delta < 0 ? "baja" : "neutro";
  const signo = delta > 0 ? "▲" : delta < 0 ? "▼" : "•";
  return (
    <div className={`delta ${clase}`} title={`Período anterior: ${formatearValor(anterior, formato)}`}>
      {signo} {Math.abs(delta).toLocaleString("es-EC", { maximumFractionDigits: 1 })}% vs. período anterior
    </div>
  );
}

function Sparkline({ valores }: { valores: number[] }) {
  if (valores.length < 2) return null;
  const w = 160, h = 32;
  const min = Math.min(...valores), max = Math.max(...valores);
  const puntos = valores.map((v, i) => {
    const x = (i / (valores.length - 1)) * w;
    const y = max === min ? h / 2 : h - ((v - min) / (max - min)) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline points={puntos.join(" ")} fill="none" stroke="var(--color-primario)" strokeWidth="2" />
    </svg>
  );
}

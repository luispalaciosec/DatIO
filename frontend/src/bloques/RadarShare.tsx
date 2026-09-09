import { urlImagen } from "../lib/api";
import type { RespuestaConsulta } from "../lib/tipos";

interface FilaShare {
  competidor_id: number; nombre: string; handle: string | null; logo_url: string | null;
  activos: number; historicos: number; share: number | null; dias_promedio: number | null; dias_maximo: number | null;
  veteranos: number; formatos: Record<string, number>; plataformas: Record<string, number>; ultima_captura: string | null;
}

export function RadarShare({ respuesta }: { respuesta: RespuestaConsulta<FilaShare[]> }) {
  if (respuesta.meta.sin_competidores) return <div className="vacio">Sin competidores de Facebook configurados para el radar de pauta.</div>;
  const max = Math.max(...respuesta.datos.map((f) => f.activos), 1);
  return (
    <div className="radar-share">
      {respuesta.datos.map((f) => (
        <div key={f.competidor_id} className="radar-share-fila">
          <div className="bench-marca">
            {f.logo_url ? <img src={urlImagen(f.logo_url) ?? ""} alt="" referrerPolicy="no-referrer" /> : <span className="inicial">{f.nombre.slice(0, 1)}</span>}
            <div><strong>{f.nombre}</strong><div className="sutil">{f.handle ? `@${f.handle}` : ""}</div></div>
          </div>
          <div className="radar-share-barra">
            <div className="barra"><div style={{ width: `${(f.activos / max) * 100}%` }} /></div>
            <div className="sutil">{f.share != null ? `${Math.round(f.share)} % de la pauta activa del grupo` : "sin anuncios activos"}</div>
          </div>
          <div className="radar-share-cifras">
            <div><b>{f.activos}</b><span>activos</span></div>
            <div><b>{f.dias_promedio != null ? Math.round(f.dias_promedio) : "—"}</b><span>días prom.</span></div>
            <div><b>{f.dias_maximo ?? "—"}</b><span>más antiguo</span></div>
            <div><b>{f.veteranos}</b><span>&gt; 30 días</span></div>
          </div>
          <div className="radar-share-mix sutil">
            {Object.entries(f.formatos).sort((a, b) => b[1] - a[1]).map(([k, v]) => <span key={k}>{k} {v}</span>)}
          </div>
        </div>
      ))}
      <div className="sutil">Share of voice = participación en el total de anuncios activos de la competencia observada. Fuente: Biblioteca de anuncios de Meta (Ecuador).</div>
    </div>
  );
}

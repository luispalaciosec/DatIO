import type { RespuestaConsulta } from "../lib/tipos";

type Fila = { etiqueta: string; valor: number };

export function DistribucionGeo({ respuesta }: { respuesta: RespuestaConsulta<Fila[]> }) {
  if (respuesta.datos.length === 0) {
    return <div className="vacio">{String(respuesta.meta.aviso ?? "Sin datos geográficos.")}</div>;
  }
  const max = Math.max(...respuesta.datos.map((f) => f.valor));
  return (
    <div className="serie">
      {respuesta.datos.map((f) => (
        <div key={f.etiqueta} style={{ display: "grid", gridTemplateColumns: "160px 1fr 80px", gap: 8, alignItems: "center", fontSize: 13, marginBottom: 6 }}>
          <span>{f.etiqueta}</span>
          <div style={{ background: "var(--gris-100)", borderRadius: 4, height: 14 }}>
            <div style={{ width: `${(f.valor / max) * 100}%`, background: "var(--color-primario)", height: "100%", borderRadius: 4 }} />
          </div>
          <span style={{ textAlign: "right" }}>{f.valor.toLocaleString("es-EC")}</span>
        </div>
      ))}
    </div>
  );
}

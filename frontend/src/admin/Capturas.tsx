import { useEffect, useState } from "react";
import { api, ErrorApi } from "../lib/api";
import type { Captura } from "../lib/tipos";

export function Capturas() {
  const [capturas, setCapturas] = useState<Captura[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.admin.capturas(100).then(setCapturas).catch((e: ErrorApi) => setError(e.message)); }, []);
  if (error) return <div className="admin-cuerpo"><div className="bloque-error">{error}</div></div>;
  if (!capturas) return <div className="admin-cuerpo"><div className="bloque-cargando" /></div>;
  const errores = capturas.filter((c) => c.estado === "error").length;
  return (
    <div className="admin-cuerpo">
      <div className="encabezado"><h1>Capturas<small>últimas {capturas.length} · {errores} con error</small></h1></div>
      <table className="publicaciones tarjeta">
        <thead><tr><th>Cuándo</th><th>Cliente</th><th>Cuenta</th><th>Conector</th><th>Estado</th><th className="num">Filas</th><th>Detalle</th></tr></thead>
        <tbody>{capturas.map((c) => (
          <tr key={c.id}>
            <td>{new Date(c.iniciado_en).toLocaleString("es-EC")}</td>
            <td>{c.cliente ?? "—"}</td><td>{c.nombre_cuenta ?? c.cuenta_id ?? "—"}</td><td><code>{c.conector}</code></td>
            <td><span className={`estado estado-${c.estado}`}>{c.estado}</span></td>
            <td className="num">{c.filas_escritas}</td>
            <td className="sutil">{c.error_detalle ?? ""}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

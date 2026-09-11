import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { DisparoCrm } from "../lib/tipos";

const NOMBRE_CODIGO: Record<string, string> = {
  bajo_meta: "Refuerzo de pauta", organico_sin_pauta: "Venta cruzada", caida_sostenida: "Riesgo de fuga",
};
function nombreCodigo(c: string) { return NOMBRE_CODIGO[c] ?? (c.startsWith("competencia_pauta") ? "Alerta competitiva" : c); }

export function Puente() {
  const [disparos, setDisparos] = useState<DisparoCrm[] | null>(null);
  useEffect(() => { api.admin.disparosCrm().then(setDisparos); }, []);
  return (
    <div className="admin-seccion">
      <div className="tarjeta">
        <h3>Puente CRM</h3>
        <p className="sutil">
          Cada mañana, después de la captura, DatIO evalúa cuatro disparadores por cliente con CRM configurado: refuerzo de pauta
          (cierre proyectado muy por debajo del mes anterior), venta cruzada (buen orgánico sin pauta), alerta competitiva
          (un competidor lanzó 3 o más anuncios en la semana) y riesgo de fuga (tres períodos de 28 días cayendo).
          Cada disparo crea una oportunidad o tarea en el CRM con la evidencia. No se repite en 30 días.
          El CRM de cada cliente se configura en su ficha, pestaña Datos.
        </p>
      </div>
      <div className="tarjeta">
        <h3>Bitácora de disparos</h3>
        {disparos === null ? <div className="bloque-cargando" /> : disparos.length === 0 ? (
          <div className="vacio">Todavía no se ha disparado nada. Configura el CRM de un cliente y usa «Evaluar ahora» en su ficha.</div>
        ) : (
          <table className="publicaciones tarjeta">
            <thead><tr><th>Fecha</th><th>Cliente</th><th>Disparador</th><th>Título</th><th>CRM</th><th>Resultado</th></tr></thead>
            <tbody>
              {disparos.map((d) => (
                <tr key={d.id}>
                  <td>{new Date(d.disparado_en).toLocaleString("es-EC", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
                  <td>{d.cliente ?? "—"}</td>
                  <td>{nombreCodigo(d.codigo)}</td>
                  <td>{d.titulo}</td>
                  <td>{d.crm_proveedor ?? "—"}</td>
                  <td>{d.error ? <span className="delta baja">✗ {d.error.slice(0, 80)}</span> : (
                    typeof d.contexto.url === "string" ? <a href={d.contexto.url} target="_blank" rel="noreferrer">✓ abrir {d.crm_objeto_ref}</a> : <span className="delta sube">✓ {d.crm_objeto_ref}</span>
                  )}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

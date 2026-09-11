import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import type { AlertaAdmin } from "../lib/tipos";

const NOMBRE_TIPO: Record<string, string> = { anomalia: "Caída", oportunidad: "Oportunidad", operativa: "Operativa", comercial: "CRM" };
const NOMBRE_RED: Record<string, string> = { meta_ig: "Instagram", meta_fb: "Facebook", linkedin: "LinkedIn", tiktok: "TikTok", youtube: "YouTube", ga4: "Sitio web", gsc: "Search Console", meta_ads: "Meta Ads" };

export function Alertas() {
  const [alertas, setAlertas] = useState<AlertaAdmin[] | null>(null);
  const [abiertas, setAbiertas] = useState(true);
  const [aviso, setAviso] = useState<string | null>(null);
  const cargar = () => api.admin.alertas(abiertas).then(setAlertas).catch((e: ErrorApi) => setAviso(e.message));
  useEffect(() => { cargar(); }, [abiertas]); // eslint-disable-line react-hooks/exhaustive-deps

  async function resolver(a: AlertaAdmin) {
    try { await api.admin.resolverAlerta(a.id, !a.resuelta); cargar(); } catch (e) { setAviso((e as ErrorApi).message); }
  }

  return (
    <div className="admin-cuerpo">
      <div className="encabezado">
        <h1>Alertas<small>Caídas fuera de banda, oportunidades, problemas operativos y disparos al CRM detectados cada mañana. Se avisan por correo al equipo.</small></h1>
        <div className="subtabs">
          <button className={abiertas ? "activa" : ""} onClick={() => setAbiertas(true)}>Abiertas</button>
          <button className={!abiertas ? "activa" : ""} onClick={() => setAbiertas(false)}>Todas</button>
        </div>
      </div>
      {aviso && <p className="aviso">{aviso}</p>}
      {alertas === null ? <div className="bloque-cargando" /> : alertas.length === 0 ? (
        <div className="vacio">Sin alertas {abiertas ? "abiertas" : "registradas"}. Buena señal.</div>
      ) : (
        <div className="alertas-lista">
          {alertas.map((a) => (
            <div key={a.id} className={`alerta-tarjeta sev-${a.severidad} ${a.resuelta ? "resuelta" : ""}`}>
              <div className="alerta-etiquetas">
                <span className={`alerta-sev sev-${a.severidad}`}>{NOMBRE_TIPO[a.tipo] ?? a.tipo} · {a.severidad}</span>
                {a.plataforma && <span className="sutil">{NOMBRE_RED[a.plataforma] ?? a.plataforma}</span>}
                <span className="sutil">{new Date(a.creada_en).toLocaleString("es-EC", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
              </div>
              <div className="alerta-titulo">{a.titulo}</div>
              {a.detalle?.error ? <div className="alerta-detalle">{String(a.detalle.error)}</div> : null}
              <div className="alerta-acciones">
                {a.cliente_id && <Link to={`/admin/clientes/${a.cliente_id}`} className="enlace">Ficha del cliente</Link>}
                <button type="button" className="enlace" onClick={() => resolver(a)}>{a.resuelta ? "Reabrir" : "Marcar resuelta"}</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

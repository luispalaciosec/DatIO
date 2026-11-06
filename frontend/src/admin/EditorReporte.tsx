import { useEffect, useState } from "react";
import { api, ErrorApi } from "../lib/api";
import type { BloqueEditor, ClienteDetalle, EstructuraReporte, PaginaEditor } from "../lib/tipos";

const RED: Record<string, string> = {
  meta_fb: "Facebook", meta_ig: "Instagram", linkedin: "LinkedIn", tiktok: "TikTok", youtube: "YouTube",
  ga4: "Sitio web", gsc: "Búsqueda", meta_ads: "Meta Ads", google_ads: "Google Ads", app_store: "App Store",
  google_play: "Google Play", prometio: "CRM PrometIO", hubspot: "CRM HubSpot", zoho: "CRM Zoho", google_negocio: "Google Negocio",
};
const TIPO: Record<string, string> = {
  hero_banner: "Banner", titulo_seccion: "Título de sección", separador: "Separador", narrativa: "Resumen narrado",
  kpi_fila: "Fila de KPIs", serie_temporal: "Evolutivo", pacing_mes: "Pacing del mes", tabla_publicaciones: "Tabla de publicaciones",
  top_publicaciones: "Mejores publicaciones", distribucion: "Distribución", demografia: "Demografía", tabla_ranking: "Ranking",
  rendimiento_formato: "Rendimiento por formato", mejor_dia: "Mejor día", benchmark_grid: "Tarjetas de competencia",
  benchmark_tabla: "Tabla comparativa", benchmark_serie: "Evolución vs. competencia", benchmark_publicaciones: "Publicaciones de la competencia",
  radar_share_of_voice: "Pauta: share of voice", radar_longevidad: "Pauta: anuncios longevos", radar_anuncios_activos: "Pauta: anuncios activos",
};
const SIN_EDICION = new Set(["hero_banner", "separador"]);

export function EditorReporte({ cliente }: { cliente: ClienteDetalle }) {
  const [e, setE] = useState<EstructuraReporte | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const cargar = () => api.admin.estructuraReporte(cliente.id).then(setE).catch((x: ErrorApi) => setError(x.message));
  useEffect(() => { cargar(); }, [cliente.id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <div className="bloque-error">{error}</div>;
  if (!e) return <div className="bloque-cargando" />;
  const conectadas = e.paginas.filter((p) => p.cuentas > 0);
  const sinConectar = e.paginas.filter((p) => p.cuentas === 0);
  return (
    <div className="editor-reporte">
      <div className="tarjeta">
        <h3>Reporte de {cliente.nombre}</h3>
        <p className="sutil">
          Aquí decides qué ve este cliente: oculta páginas o bloques, cambia títulos y fija objetivos mensuales.
          Los cambios aplican solo a este cliente y se ven al recargar su reporte (la caché puede tardar hasta 15 minutos).
          El cliente nunca ve las redes sin cuenta conectada.
        </p>
      </div>
      {conectadas.map((p) => (
        <PaginaCard key={p.id} cliente={cliente} pagina={p} abierta={abierta === p.id}
          alAbrir={() => setAbierta(abierta === p.id ? null : p.id)} alCambiar={cargar} />
      ))}
      {sinConectar.length > 0 && (
        <div className="tarjeta">
          <h3>Redes sin conectar</h3>
          <p className="sutil">{[...new Set(sinConectar.map((p) => RED[p.plataforma ?? ""] ?? p.plataforma))].join(" · ")}. No aparecen en el reporte del cliente. Se conectan en la pestaña Cuentas.</p>
        </div>
      )}
      <Envios cliente={cliente} estructura={e} alCambiar={cargar} />
    </div>
  );
}

function PaginaCard({ cliente, pagina, abierta, alAbrir, alCambiar }: {
  cliente: ClienteDetalle; pagina: PaginaEditor; abierta: boolean; alAbrir: () => void; alCambiar: () => void;
}) {
  const visibles = pagina.bloques.filter((b) => !b.oculto).length;
  const todaOculta = visibles === 0;
  async function alternarPagina() { await api.admin.ocultarPagina(cliente.id, pagina.id, !todaOculta); alCambiar(); }
  return (
    <div className={`tarjeta catalogo-plataforma ${todaOculta ? "pagina-oculta" : ""}`}>
      <div className="catalogo-cabecera" style={{ cursor: "default" }}>
        <strong>{(() => {
          const red = RED[pagina.plataforma ?? ""] ?? pagina.plataforma ?? "";
          return pagina.titulo.startsWith(red) ? pagina.titulo : `${red} · ${pagina.titulo}`;
        })()}</strong>
        <span className="sutil">{todaOculta ? "oculta para el cliente" : `${visibles} de ${pagina.bloques.length} bloques visibles`}</span>
        <button type="button" className="boton-secundario" onClick={alternarPagina}>{todaOculta ? "Mostrar página" : "Ocultar página"}</button>
        <button type="button" className="boton-secundario" onClick={alAbrir}>{abierta ? "Cerrar" : "Editar bloques"}</button>
      </div>
      {abierta && (
        <div className="catalogo-cuerpo">
          {pagina.bloques.filter((b) => b.tipo !== "separador").map((b) => (
            <BloqueFila key={b.id} cliente={cliente} bloque={b} alCambiar={alCambiar} />
          ))}
        </div>
      )}
    </div>
  );
}

function BloqueFila({ cliente, bloque, alCambiar }: { cliente: ClienteDetalle; bloque: BloqueEditor; alCambiar: () => void }) {
  const efectivo = { ...bloque.config, ...bloque.override } as Record<string, unknown>;
  const [titulo, setTitulo] = useState(String(efectivo.titulo ?? ""));
  const [bajada, setBajada] = useState(String(efectivo.bajada ?? ""));
  const [objetivo, setObjetivo] = useState(String(bloque.override.objetivo ?? ""));
  const [aviso, setAviso] = useState<string | null>(null);
  const editable = !SIN_EDICION.has(bloque.tipo);

  async function guardar(oculto: boolean) {
    const config: Record<string, unknown> = { ...bloque.override };
    if (bloque.tipo === "titulo_seccion") {
      if (titulo !== String(bloque.config.titulo ?? "")) config.titulo = titulo; else delete config.titulo;
      if (bajada !== String(bloque.config.bajada ?? "")) config.bajada = bajada; else delete config.bajada;
    }
    if (bloque.tipo === "pacing_mes") {
      if (objetivo.trim()) config.objetivo = Number(objetivo); else delete config.objetivo;
    }
    try { await api.admin.guardarBloque(cliente.id, bloque.id, { oculto, config }); setAviso("Guardado"); alCambiar(); }
    catch (x) { setAviso((x as ErrorApi).message); }
  }
  const resumen = bloque.tipo === "titulo_seccion" ? String(efectivo.titulo ?? "")
    : bloque.tipo === "pacing_mes" ? `${String(efectivo.etiqueta ?? efectivo.metrica ?? "")}${bloque.override.objetivo ? ` · objetivo ${bloque.override.objetivo}` : ""}`
    : bloque.tipo === "kpi_fila" ? ((efectivo.items as Array<{ etiqueta?: string }> | undefined) ?? []).map((i) => i.etiqueta).join(", ")
    : String(efectivo.titulo ?? efectivo.dimension ?? "");
  return (
    <div className={`editor-bloque ${bloque.oculto ? "oculto" : ""}`}>
      <div className="editor-bloque-cabecera">
        <label className="fila"><input type="checkbox" checked={!bloque.oculto} onChange={(ev) => guardar(!ev.target.checked)} /> <strong>{TIPO[bloque.tipo] ?? bloque.tipo}</strong></label>
        <span className="sutil">{resumen}</span>
      </div>
      {editable && !bloque.oculto && bloque.tipo === "titulo_seccion" && (
        <div className="editor-bloque-campos formulario">
          <label>Título<input value={titulo} onChange={(ev) => setTitulo(ev.target.value)} /></label>
          <label>Bajada<input value={bajada} onChange={(ev) => setBajada(ev.target.value)} /></label>
          <button type="button" className="boton-secundario" onClick={() => guardar(false)}>Guardar textos</button>
        </div>
      )}
      {editable && !bloque.oculto && bloque.tipo === "pacing_mes" && (
        <div className="editor-bloque-campos formulario">
          <label>Objetivo mensual de {String(efectivo.etiqueta ?? efectivo.metrica ?? "la métrica")} (vacío = sin objetivo)
            <input type="number" min="0" value={objetivo} onChange={(ev) => setObjetivo(ev.target.value)} /></label>
          <button type="button" className="boton-secundario" onClick={() => guardar(false)}>Guardar objetivo</button>
        </div>
      )}
      {aviso && <span className="aviso-ok">{aviso}</span>}
    </div>
  );
}

function Envios({ cliente, estructura, alCambiar }: { cliente: ClienteDetalle; estructura: EstructuraReporte; alCambiar: () => void }) {
  const [correo, setCorreo] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const clientes = cliente.usuarios.filter((u) => u.activo).map((u) => u.email);
  async function enviar(destinatarios?: string[]) {
    if (!destinatarios && !window.confirm(`Se enviará el reporte del mes anterior a ${clientes.join(", ")}. ¿Continuar?`)) return;
    setOcupado(true); setAviso("Generando el PDF y enviando… puede tardar un minuto.");
    try {
      const r = await api.admin.enviarReporte(cliente.id, destinatarios ? { destinatarios } : {});
      setAviso(`Enviado a ${r.destinatarios.join(", ")} (período ${r.periodo.slice(0, 7)}).`); alCambiar();
    } catch (x) { setAviso(`No se pudo enviar: ${(x as ErrorApi).message}`); }
    setOcupado(false);
  }
  return (
    <div className="tarjeta formulario">
      <h3>Envío mensual por correo</h3>
      <p className="sutil">
        El día 1 de cada mes DatIO envía solo, a los usuarios del cliente, el PDF del mes cerrado con un resumen narrado.
        {clientes.length === 0 ? " Este cliente aún no tiene usuarios: no se le enviará nada hasta que invites a alguien." : ` Destinatarios: ${clientes.join(", ")}.`}
      </p>
      <div className="fila">
        <label>Enviarme una prueba a<input type="email" value={correo} onChange={(ev) => setCorreo(ev.target.value)} placeholder="tu@correo.com" /></label>
        <button type="button" className="boton-secundario" disabled={ocupado || !correo} onClick={() => enviar([correo])}>Enviar prueba</button>
        <button type="button" className="boton-pdf" disabled={ocupado || clientes.length === 0} onClick={() => enviar()}>Enviar al cliente ahora</button>
      </div>
      {aviso && <div className="aviso-ok">{aviso}</div>}
      {estructura.envios.length > 0 && (
        <table className="publicaciones">
          <thead><tr><th>Período</th><th>Enviado</th><th>Destinatarios</th><th>Tipo</th><th>Estado</th></tr></thead>
          <tbody>{estructura.envios.map((v, i) => (
            <tr key={i}><td>{v.periodo.slice(0, 7)}</td><td>{new Date(v.enviado_en).toLocaleString("es-EC", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</td>
              <td>{v.destinatarios.join(", ")}</td><td>{v.automatico ? "automático" : "manual"}</td>
              <td>{v.estado === "enviado" ? <span className="delta sube">✓ enviado</span> : <span className="delta baja">✗ {v.error ?? v.estado}</span>}</td></tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import type { EmpresaCrm, EvaluacionCrm, ActivoConexion, Catalogos, ClienteDetalle, Conexion, CuentaAdmin, TemaAdmin } from "../lib/tipos";
import { supabase } from "../lib/supabase";
import { EditorReporte } from "./EditorReporte";

export function FichaCliente() {
  const { id = "0" } = useParams();
  const [cliente, setCliente] = useState<ClienteDetalle | null>(null);
  const [catalogos, setCatalogos] = useState<Catalogos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params] = useSearchParams();
  const [pestana, setPestana] = useState<Pestana>(
    params.get("conexion") || params.get("error") ? "cuentas" : "datos",
  );

  const cargar = () => api.admin.cliente(Number(id)).then(setCliente).catch((e: ErrorApi) => setError(e.message));
  useEffect(() => { cargar(); api.admin.catalogos().then(setCatalogos).catch(() => null); }, [id]);

  if (error) return <div className="admin-cuerpo"><div className="bloque-error">{error}</div></div>;
  if (!cliente) return <div className="admin-cuerpo"><div className="bloque-cargando" /></div>;

  return (
    <div className="admin-cuerpo">
      <div className="encabezado">
        <h1>{cliente.nombre}<small><Link to={`/${cliente.slug}`}>/{cliente.slug}</Link> · {cliente.sector ?? "sin sector"}{!cliente.activo && " · inactivo"}</small></h1>
        <div className="subtabs">
          {(["datos", "marca", "cuentas", "competidores", "usuarios", "reporte"] as const).map((p) => (
            <a key={p} href="#" className={pestana === p ? "activa" : ""} onClick={(e) => { e.preventDefault(); setPestana(p); }}>
              {{ datos: "Datos", marca: "Marca", cuentas: `Cuentas (${cliente.cuentas.length})`, competidores: `Competidores (${cliente.competidores.length})`, usuarios: `Usuarios (${cliente.usuarios.length})`, reporte: "Reporte" }[p]}
            </a>
          ))}
        </div>
      </div>
      <PuestaEnMarcha cliente={cliente} irA={setPestana} />
      {pestana === "datos" && <><Datos cliente={cliente} catalogos={catalogos} alGuardar={cargar} /><Crm cliente={cliente} alGuardar={cargar} /></>}
      {pestana === "marca" && <Marca cliente={cliente} alGuardar={cargar} />}
      {pestana === "cuentas" && <Cuentas cliente={cliente} catalogos={catalogos} alGuardar={cargar} />}
      {pestana === "competidores" && <Competidores cliente={cliente} alGuardar={cargar} />}
      {pestana === "usuarios" && <UsuariosCliente cliente={cliente} alGuardar={cargar} />}
      {pestana === "reporte" && <EditorReporte cliente={cliente} />}
    </div>
  );
}

type Pestana = "datos" | "marca" | "cuentas" | "competidores" | "usuarios" | "reporte";

/** Checklist de alta: qué falta para que el cliente pueda usar su reporte. Se oculta al completarse. */
function PuestaEnMarcha({ cliente, irA }: { cliente: ClienteDetalle; irA: (p: Pestana) => void }) {
  const usuarios = cliente.usuarios.filter((u) => u.activo).length;
  const pasos: Array<{ hecho: boolean; texto: string; detalle: string; pestana: Pestana }> = [
    { hecho: Boolean(cliente.tema.logo_url), texto: "Marca", detalle: cliente.tema.logo_url ? "logo y colores listos" : "sube el logo y define colores", pestana: "marca" },
    { hecho: cliente.cuentas.length > 0, texto: "Cuentas", detalle: cliente.cuentas.length ? `${cliente.cuentas.length} conectada(s)` : "conecta al menos una red", pestana: "cuentas" },
    { hecho: cliente.competidores.length > 0, texto: "Competidores", detalle: cliente.competidores.length ? `${cliente.competidores.length} en el radar` : "agrega 4 a 6 por red", pestana: "competidores" },
    { hecho: usuarios > 0, texto: "Reporte", detalle: "revisa qué páginas y bloques verá", pestana: "reporte" },
    { hecho: usuarios > 0, texto: "Invitación", detalle: usuarios ? `${usuarios} usuario(s) con acceso` : "invita al cliente por correo", pestana: "usuarios" },
  ];
  if (pasos.every((p) => p.hecho)) return null;
  return (
    <div className="tarjeta puesta-en-marcha">
      <strong>Puesta en marcha</strong>
      <div className="pasos">
        {pasos.map((p, i) => (
          <button type="button" key={p.texto} className={`paso ${p.hecho ? "hecho" : ""}`} onClick={() => irA(p.pestana)}>
            <span className="paso-num">{p.hecho ? "✓" : i + 1}</span>
            <span><b>{p.texto}</b><small>{p.detalle}</small></span>
          </button>
        ))}
      </div>
    </div>
  );
}

type TextoAviso = string | { error: string } | null;

function Aviso({ texto }: { texto: TextoAviso }) {
  if (!texto) return null;
  if (typeof texto === "string") return <div className="aviso-ok">{texto}</div>;
  return <div className="aviso" role="alert">{texto.error}</div>;
}

function Datos({ cliente, catalogos, alGuardar }: { cliente: ClienteDetalle; catalogos: Catalogos | null; alGuardar: () => void }) {
  const [f, setF] = useState({ nombre: cliente.nombre, sector: cliente.sector ?? "", activo: cliente.activo });
  const [aviso, setAviso] = useState<TextoAviso>(null);
  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    await api.admin.editarCliente(cliente.id, { nombre: f.nombre, sector: f.sector || null, activo: f.activo });
    setAviso("Guardado"); alGuardar();
  }
  return (
    <form className="tarjeta formulario estrecho" onSubmit={guardar}>
      <label>Nombre<input value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></label>
      <label>Sector<select value={f.sector} onChange={(e) => setF({ ...f, sector: e.target.value })}>
        <option value="">—</option>{catalogos?.sectores.map((s) => <option key={s} value={s}>{s}</option>)}
      </select></label>
      <label className="fila"><input type="checkbox" checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} /> Cliente activo (se captura y puede entrar)</label>
      <p className="sutil">El slug <code>{cliente.slug}</code> no se cambia: es la URL del reporte que ya tiene el cliente.</p>
      <button className="boton-pdf" type="submit">Guardar</button><Aviso texto={aviso} />
    </form>
  );
}

function Crm({ cliente, alGuardar }: { cliente: ClienteDetalle; alGuardar: () => void }) {
  const [proveedor, setProveedor] = useState<string>(cliente.crm_proveedor ?? "");
  const [empresa, setEmpresa] = useState<string>(cliente.crm_empresa_ref ?? "");
  const [contacto, setContacto] = useState<string>(cliente.crm_contacto_ref ?? "");
  const [token, setToken] = useState("");
  const [dealstage, setDealstage] = useState<string>(String(cliente.crm_config?.dealstage ?? ""));
  const [empresas, setEmpresas] = useState<EmpresaCrm[] | null>(null);
  const [evaluacion, setEvaluacion] = useState<EvaluacionCrm | null>(null);
  const [aviso, setAviso] = useState<TextoAviso>(null);
  const [ocupado, setOcupado] = useState(false);

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    setOcupado(true);
    try {
      await api.admin.guardarCrm(cliente.id, {
        proveedor: proveedor || null, empresa_ref: empresa || null, contacto_ref: contacto || null,
        config: dealstage ? { ...cliente.crm_config, dealstage } : undefined, credencial: token || undefined,
      });
      setToken(""); setAviso("CRM guardado"); alGuardar();
    } catch (err) { setAviso({ error: `No se pudo guardar: ${(err as Error).message}` }); }
    setOcupado(false);
  }
  async function probar() {
    setOcupado(true);
    try { const r = await api.admin.probarCrm(cliente.id); setAviso(`Conexión OK: ${JSON.stringify(r).slice(0, 160)}`); }
    catch (err) { setAviso({ error: `Falló: ${(err as Error).message}` }); }
    setOcupado(false);
  }
  async function cargarEmpresas() {
    setOcupado(true);
    try { setEmpresas(await api.admin.empresasCrm(proveedor, cliente.id)); }
    catch (err) { setAviso({ error: `No se pudieron listar: ${(err as Error).message}` }); }
    setOcupado(false);
  }
  async function evaluar(ejecutar: boolean) {
    if (ejecutar && !window.confirm("Esto crea oportunidades o tareas reales en el CRM. ¿Continuar?")) return;
    setOcupado(true);
    try { setEvaluacion(await api.admin.evaluarCrm(cliente.id, ejecutar)); }
    catch (err) { setAviso({ error: `Falló: ${(err as Error).message}` }); }
    setOcupado(false);
  }
  const empresaElegida = empresas?.find((e) => e.id === empresa);
  return (
    <form className="tarjeta formulario estrecho" onSubmit={guardar} style={{ marginTop: 16 }}>
      <h3>Puente CRM</h3>
      <p className="sutil">Dónde crea DatIO las oportunidades de este cliente. PrometIO usa el usuario de servicio de la agencia; HubSpot necesita un token de app privada del cliente.</p>
      <label>CRM<select value={proveedor} onChange={(e) => { setProveedor(e.target.value); setEmpresas(null); }}>
        <option value="">Sin CRM (no dispara)</option><option value="prometio">PrometIO (Geeks)</option><option value="hubspot">HubSpot</option>
      </select></label>
      {proveedor === "hubspot" && (
        <>
          <label>Token de app privada {cliente.crm_con_credencial && <span className="sutil">(ya hay uno guardado; déjalo vacío para conservarlo)</span>}
            <input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="pat-na1-…" autoComplete="off" /></label>
          <label>Etapa inicial del deal (id de HubSpot)<input value={dealstage} onChange={(e) => setDealstage(e.target.value)} placeholder="appointmentscheduled" /></label>
        </>
      )}
      {proveedor && (
        <>
          <div className="fila" style={{ gap: 8 }}>
            <label style={{ flex: 1 }}>Empresa en el CRM (id)<input value={empresa} onChange={(e) => setEmpresa(e.target.value)} /></label>
            <button type="button" className="boton-secundario" disabled={ocupado} onClick={cargarEmpresas}>Elegir de la lista</button>
          </div>
          {empresas && (
            <label>Empresas del CRM<select value={empresa} onChange={(e) => { setEmpresa(e.target.value); setContacto(""); }}>
              <option value="">—</option>{empresas.map((e) => <option key={e.id} value={e.id}>{e.nombre ?? e.id}</option>)}
            </select></label>
          )}
          {proveedor === "prometio" && (
            empresaElegida && empresaElegida.contactos.length > 0 ? (
              <label>Contacto (PrometIO lo exige)<select value={contacto} onChange={(e) => setContacto(e.target.value)}>
                <option value="">—</option>{empresaElegida.contactos.map((c) => <option key={c.id} value={c.id}>{c.nombre ?? c.id}{c.email ? ` · ${c.email}` : ""}</option>)}
              </select></label>
            ) : <label>Contacto en PrometIO (id)<input value={contacto} onChange={(e) => setContacto(e.target.value)} /></label>
          )}
        </>
      )}
      <div className="fila" style={{ gap: 8, flexWrap: "wrap" }}>
        <button className="boton-pdf" type="submit" disabled={ocupado}>Guardar</button>
        {proveedor && <button type="button" className="boton-secundario" disabled={ocupado} onClick={probar}>Probar conexión</button>}
        {cliente.crm_proveedor && cliente.crm_empresa_ref && (
          <>
            <button type="button" className="boton-secundario" disabled={ocupado} onClick={() => evaluar(false)}>Evaluar ahora (simular)</button>
            <button type="button" className="boton-secundario" disabled={ocupado} onClick={() => evaluar(true)}>Disparar al CRM</button>
          </>
        )}
      </div>
      <Aviso texto={aviso} />
      {evaluacion && (
        <div className="evaluacion-crm">
          <strong>{evaluacion.ejecutado ? "Disparado" : "Simulación"} · {evaluacion.candidatos.length} condición(es) hoy</strong>
          {evaluacion.candidatos.length === 0 && <p className="sutil">Ningún disparador aplica hoy para este cliente. Eso es buena señal.</p>}
          {evaluacion.candidatos.map((c) => (
            <div key={c.codigo} className="evaluacion-item">
              <div><b>{c.titulo}</b> <span className="sutil">· {c.tipo} · prioridad {c.prioridad}{c.valor ? ` · USD ${c.valor}` : ""}</span></div>
              <p>{c.evidencia}</p>
              {evaluacion.disparados.filter((d) => d.codigo === c.codigo).map((d) => (
                <p key={d.codigo} className={d.error ? "delta baja" : "delta sube"}>{d.error ? `✗ ${d.error}` : `✓ creado en el CRM${d.url ? ` — ${d.url}` : ` (${d.objeto_ref})`}`}</p>
              ))}
              {evaluacion.ejecutado && !evaluacion.disparados.some((d) => d.codigo === c.codigo) && <p className="sutil">No se envió: ya se disparó en los últimos 30 días.</p>}
            </div>
          ))}
          {evaluacion.omitidos.length > 0 && <p className="delta baja">{evaluacion.omitidos.join(" · ")}</p>}
        </div>
      )}
    </form>
  );
}

function Marca({ cliente, alGuardar }: { cliente: ClienteDetalle; alGuardar: () => void }) {
  const [t, setT] = useState<TemaAdmin>(cliente.tema);
  const [aviso, setAviso] = useState<TextoAviso>(null);
  const [subiendo, setSubiendo] = useState<string | null>(null);

  async function subir(campo: "logo_url" | "banner_url", archivo: File) {
    setSubiendo(campo);
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "png";
    const ruta = `${cliente.slug}/${campo === "logo_url" ? "logo" : "banner"}-${Date.now()}.${ext}`;
    const { error } = await supabase.storage.from("marcas").upload(ruta, archivo, { upsert: true, contentType: archivo.type });
    setSubiendo(null);
    if (error) { setAviso({ error: `No se pudo subir: ${error.message}` }); return; }
    const url = supabase.storage.from("marcas").getPublicUrl(ruta).data.publicUrl;
    const nuevo = { ...t, [campo]: url };
    setT(nuevo);
    await api.admin.guardarTema(cliente.id, { [campo]: url });
    setAviso("Imagen guardada"); alGuardar();
  }

  async function guardar(e: React.FormEvent) {
    e.preventDefault();
    await api.admin.guardarTema(cliente.id, t);
    setAviso("Tema guardado. Recarga el reporte para verlo."); alGuardar();
  }

  return (
    <div className="grid">
      <form className="bloque tarjeta formulario" style={{ "--ancho": 6 } as React.CSSProperties} onSubmit={guardar}>
        <h3>Colores y tipografía</h3>
        {(["color_primario", "color_secundario", "color_acento"] as const).map((c) => (
          <label key={c} className="fila">
            <input type="color" value={t[c]} onChange={(e) => setT({ ...t, [c]: e.target.value })} />
            <span>{{ color_primario: "Primario (títulos, KPIs héroe, fondo)", color_secundario: "Secundario (texto, botones)", color_acento: "Acento (fondos suaves)" }[c]}</span>
            <code>{t[c]}</code>
          </label>
        ))}
        <label>Fuente de títulos<input value={t.fuente_titulos} onChange={(e) => setT({ ...t, fuente_titulos: e.target.value })} placeholder="Outfit" /></label>
        <label>Fuente de cuerpo<input value={t.fuente_cuerpo} onChange={(e) => setT({ ...t, fuente_cuerpo: e.target.value })} placeholder="Inter" /></label>
        <p className="sutil">Cualquier fuente de Google Fonts, escrita como aparece allí.</p>
        <button className="boton-pdf" type="submit">Guardar tema</button><Aviso texto={aviso} />
      </form>
      <div className="bloque tarjeta formulario" style={{ "--ancho": 6 } as React.CSSProperties}>
        <h3>Logo y banner</h3>
        {(["logo_url", "banner_url"] as const).map((campo) => (
          <div key={campo} className="imagen-marca">
            <div className="previa" style={{ background: campo === "banner_url" ? t.color_secundario : "#fff" }}>
              {t[campo] ? <img src={t[campo] ?? ""} alt="" /> : <span className="sutil">sin {campo === "logo_url" ? "logo" : "banner"}</span>}
            </div>
            <label className="boton-pdf archivo">
              {subiendo === campo ? "Subiendo…" : campo === "logo_url" ? "Subir logo" : "Subir banner"}
              <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" hidden onChange={(e) => e.target.files?.[0] && subir(campo, e.target.files[0])} />
            </label>
          </div>
        ))}
        <p className="sutil">Logo: PNG o SVG con fondo transparente, cuadrado o apaisado. Banner: JPG apaisado, mínimo 1600 px de ancho. Máximo 5 MB.</p>
        <div className="previa-tema" style={{ background: `linear-gradient(135deg, ${t.color_primario}, ${t.color_secundario})` }}>
          <span style={{ fontFamily: t.fuente_titulos }}>Así se ven las tarjetas héroe</span>
        </div>
      </div>
    </div>
  );
}

function Cuentas({ cliente, catalogos, alGuardar }: { cliente: ClienteDetalle; catalogos: Catalogos | null; alGuardar: () => void }) {
  const [f, setF] = useState({ plataforma: "meta_ig", id_externo: "", nombre_cuenta: "", credencial: "" });
  const [aviso, setAviso] = useState<TextoAviso>(null);
  const [params, setParams] = useSearchParams();
  const [conexion, setConexion] = useState<Conexion | null>(null);
  const [elegidos, setElegidos] = useState<Set<string>>(new Set());
  const errorRetorno = params.get("error");
  const conexionId = params.get("conexion");

  useEffect(() => {
    if (!conexionId) return;
    api.admin.conexion(Number(conexionId)).then((c) => {
      setConexion(c);
      setElegidos(new Set(c.activos.filter((a) => a.plataforma !== "aviso").map((a) => `${a.plataforma}|${a.id_externo}`)));
    }).catch((e: ErrorApi) => setAviso({ error: e.message }));
  }, [conexionId]);

  async function conectar(proveedor: "meta" | "google" | "linkedin") {
    try {
      const { url } = await api.admin.iniciarConexion(proveedor, cliente.id);
      window.location.href = url;
    } catch (err) { setAviso({ error: (err as ErrorApi).message }); }
  }

  async function importarBusiness() {
    try {
      const r = await api.admin.importarBusiness(cliente.id);
      setParams({ conexion: String(r.conexion_id) });
    } catch (err) { setAviso({ error: (err as ErrorApi).message }); }
  }

  async function activar() {
    if (!conexion) return;
    const activos: ActivoConexion[] = conexion.activos.filter((a) => elegidos.has(`${a.plataforma}|${a.id_externo}`));
    try {
      const r = await api.admin.activarConexion(conexion.id, activos);
      setAviso(`${r.cuentas.length} cuenta(s) conectada(s). Se capturan en la próxima corrida diaria.`);
      setConexion(null); setParams({}); alGuardar();
    } catch (err) { setAviso({ error: (err as ErrorApi).message }); }
  }
  const AYUDA: Record<string, string> = {
    meta_fb: "Page ID de la página de Facebook. Token: System User de Meta (si va vacío usa el de la agencia).",
    meta_ig: "Instagram Business Account ID (número, no el usuario).",
    meta_ads: "Ad Account ID con prefijo act_.",
    ga4: "Property ID numérico de GA4. Dar acceso de lectura al Service Account de DatIO.",
    gsc: "siteUrl exacto de Search Console: https://dominio.com/ o sc-domain:dominio.com",
    linkedin: "URN de la página: urn:li:organization:123456. Usa «Conectar con LinkedIn» para que la cuenta tenga su token (conector nativo); sin token sigue dependiendo del puente Metricool.",
    tiktok: "Usuario de TikTok tal como aparece en Metricool.",
    youtube: "ID del canal (UC...). Conector pendiente.",
    google_ads: "Customer ID sin guiones. Conector pendiente.",
    app_store: "Apple ID de la app (número, en App Store Connect → App Information). Credencial: JSON {\"issuer_id\",\"key_id\",\"private_key\",\"vendor_number\"} de una clave de API con rol Sales and Reports.",
    google_play: "Nombre del paquete (com.empresa.app). Credencial opcional: JSON {\"bucket\":\"pubsite_prod_rev_…\"}; sin ella usa GOOGLE_PLAY_BUCKET. Invitar al Service Account de DatIO en Play Console con permiso de ver estadísticas.",
    prometio: "Organización de PrometIO (solo informativo, p. ej. geeks). Usa el usuario de servicio PROMETIO_* de la agencia.",
    zoho: "ID de la organización (informativo). Credencial: JSON {\"client_id\",\"client_secret\",\"refresh_token\",\"dominio\":\"com\"} de una app Self Client en api-console.zoho.com con scope ZohoCRM.modules.READ.",
    google_negocio: "Se conecta con el botón Google Analytics · Search Console · YouTube · Negocio: aparecen las fichas de negocio del usuario. A mano: accounts/{cuenta}/locations/{ficha}.",
    hubspot: "Portal ID de HubSpot. Credencial: token de app privada con scopes crm.objects.deals.read y crm.objects.contacts.read.",
  };
  async function crear(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.admin.crearCuenta(cliente.id, { plataforma: f.plataforma, id_externo: f.id_externo, nombre_cuenta: f.nombre_cuenta || undefined, credencial: f.credencial || undefined });
      setF({ ...f, id_externo: "", nombre_cuenta: "", credencial: "" }); setAviso("Cuenta conectada. Se captura en la próxima corrida diaria."); alGuardar();
    } catch (err) { setAviso({ error: (err as ErrorApi).message }); }
  }
  async function alternar(c: CuentaAdmin) { await api.admin.editarCuenta(c.id, { activo: !c.activo }); alGuardar(); }
  return (
    <div className="grid">
      <div className="bloque tarjeta conectar" style={{ "--ancho": 12 } as React.CSSProperties}>
        <div>
          <h3>Conectar con un clic</h3>
          <p className="sutil">El cliente autoriza con su cuenta y eliges qué páginas, propiedades o canales conectar. Los tokens quedan cifrados por cuenta.</p>
        </div>
        <div className="botones-conectar">
          <button className="boton-conectar meta" onClick={() => conectar("meta")}>Facebook · Instagram · Meta Ads</button>
          <button className="boton-conectar business" onClick={importarBusiness} title="Lista lo que administra el Business Manager de Geeks con el token de la agencia">Importar desde Business Manager</button>
          <button className="boton-conectar google" onClick={() => conectar("google")}>Google Analytics · Search Console · YouTube</button>
          <button className="boton-conectar linkedin" onClick={() => conectar("linkedin")} title="Requiere que LinkedIn apruebe Community Management API">LinkedIn</button>
          <button className="boton-conectar pendiente" disabled title="Pendiente de aprobación de TikTok">TikTok (vía Metricool)</button>
        </div>
        {errorRetorno && <div className="bloque-error">No se pudo conectar: {errorRetorno}</div>}
      </div>
      {conexion && conexion.estado === "pendiente" && (
        <SelectorActivos
          conexion={conexion}
          catalogos={catalogos}
          elegidos={elegidos}
          setElegidos={setElegidos}
          alActivar={activar}
          alCancelar={() => { setConexion(null); setParams({}); }}
        />
      )}
      <div className="bloque cuentas-lista" style={{ "--ancho": 7 } as React.CSSProperties}>
        {cliente.cuentas.length === 0 ? <div className="vacio">Sin cuentas conectadas todavía.</div> : (
          <div className="tarjeta tabla-scroll"><table className="publicaciones">
            <thead><tr><th>Red</th><th>ID externo</th><th>Nombre</th><th>Credencial</th><th>Última captura</th><th></th></tr></thead>
            <tbody>{cliente.cuentas.map((c) => (
              <tr key={c.id} style={{ opacity: c.activo ? 1 : 0.5 }}>
                <td>{c.plataforma_nombre}</td><td><code>{c.id_externo}</code></td><td>{c.nombre_cuenta ?? "—"}</td>
                <td>{c.tiene_credencial ? "propia" : "de la agencia"}</td>
                <td>{c.ultima_captura ? new Date(c.ultima_captura).toLocaleString("es-EC") : "nunca"}</td>
                <td><button className="boton-pdf" onClick={() => alternar(c)}>{c.activo ? "Pausar" : "Activar"}</button></td>
              </tr>))}</tbody>
          </table></div>
        )}
      </div>
      <form className="bloque tarjeta formulario" style={{ "--ancho": 5 } as React.CSSProperties} onSubmit={crear}>
        <h3>Conectar a mano</h3>
        <p className="sutil">Para redes sin botón o cuando ya tienes el ID y el token.</p>
        <label>Red<select value={f.plataforma} onChange={(e) => setF({ ...f, plataforma: e.target.value })}>
          {catalogos?.plataformas.map((p) => <option key={p.codigo} value={p.codigo}>{p.nombre}</option>)}
        </select></label>
        <label>ID externo<input required value={f.id_externo} onChange={(e) => setF({ ...f, id_externo: e.target.value })} /></label>
        <p className="sutil">{AYUDA[f.plataforma]}</p>
        <label>Nombre visible<input value={f.nombre_cuenta} onChange={(e) => setF({ ...f, nombre_cuenta: e.target.value })} placeholder="@cuenta o nombre de la página" /></label>
        <label>{["app_store", "google_play", "zoho"].includes(f.plataforma) ? "Credencial (JSON)" : "Token propio (opcional)"}
          {["app_store", "google_play", "zoho"].includes(f.plataforma)
            ? <textarea rows={5} value={f.credencial} onChange={(e) => setF({ ...f, credencial: e.target.value })} autoComplete="off" placeholder='{"issuer_id":"…","key_id":"…","private_key":"-----BEGIN PRIVATE KEY-----…","vendor_number":"…"}' />
            : <input type="password" value={f.credencial} onChange={(e) => setF({ ...f, credencial: e.target.value })} autoComplete="off" />}
        </label>
        <p className="sutil">Se cifra en el servidor y nunca vuelve a mostrarse. Déjalo vacío para usar la credencial de la agencia.</p>
        <button className="boton-pdf" type="submit">Conectar</button><Aviso texto={aviso} />
      </form>
    </div>
  );
}

function UsuariosCliente({ cliente, alGuardar }: { cliente: ClienteDetalle; alGuardar: () => void }) {
  const [email, setEmail] = useState("");
  const [aviso, setAviso] = useState<TextoAviso>(null);
  const [conCorreo, setConCorreo] = useState(true);
  const TEXTO: Record<string, string> = { invitado: "invitación enviada", habilitado: "acceso habilitado" };
  async function agregar(e: React.FormEvent) {
    e.preventDefault();
    const emails = email.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
    try {
      const r = await api.admin.invitar(cliente.id, emails, conCorreo);
      setEmail("");
      setAviso(r.resultados.map((x) => {
        if (x.estado === "habilitado_sin_correo") return `${x.email}: acceso habilitado, pero el correo no salió (${x.detalle ?? "sin detalle"})`;
        if (x.estado === "omitido") return `${x.email}: omitido (${x.detalle})`;
        return `${x.email}: ${TEXTO[x.estado] ?? x.estado}`;
      }).join(" · "));
      alGuardar();
    } catch (err) { setAviso({ error: (err as ErrorApi).message }); }
  }
  async function quitar(e: string) { await api.admin.desactivarUsuario(e); alGuardar(); }
  return (
    <div className="grid">
      <div className="bloque" style={{ "--ancho": 7 } as React.CSSProperties}>
        {cliente.usuarios.length === 0 ? <div className="vacio">Nadie del cliente tiene acceso todavía.</div> : (
          <table className="publicaciones tarjeta"><thead><tr><th>Email</th><th>Estado</th><th></th></tr></thead>
            <tbody>{cliente.usuarios.map((u) => (
              <tr key={u.email}><td>{u.email}</td><td>{u.activo ? "activo" : "inactivo"}</td>
                <td>{u.activo && <button className="boton-pdf" onClick={() => quitar(u.email)}>Quitar acceso</button>}</td></tr>))}</tbody></table>
        )}
      </div>
      <form className="bloque tarjeta formulario" style={{ "--ancho": 5 } as React.CSSProperties} onSubmit={agregar}>
        <h3>Dar acceso</h3>
        <label>Correos del cliente (uno o varios, separados por coma)<input required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="gerente@cliente.com, marketing@cliente.com" /></label>
        <label className="fila"><input type="checkbox" checked={conCorreo} onChange={(e) => setConCorreo(e.target.checked)} /> Enviar correo de invitación con el enlace al reporte</label>
        <p className="sutil">Solo verá el reporte de {cliente.nombre}. Con la misma cuenta de Google o por enlace al correo.</p>
        <button className="boton-pdf" type="submit">Habilitar</button><Aviso texto={aviso} />
      </form>
    </div>
  );
}

const NOMBRE_PROVEEDOR: Record<string, string> = { meta: "Meta", google: "Google", linkedin: "LinkedIn" };

function SelectorActivos({ conexion, catalogos, elegidos, setElegidos, alActivar, alCancelar }: {
  conexion: Conexion; catalogos: Catalogos | null; elegidos: Set<string>;
  setElegidos: (s: Set<string>) => void; alActivar: () => void; alCancelar: () => void;
}) {
  const [filtro, setFiltro] = useState("");
  const clave = (a: ActivoConexion) => `${a.plataforma}|${a.id_externo}`;
  const nombrePlataforma = (codigo: string) => catalogos?.plataformas.find((p) => p.codigo === codigo)?.nombre ?? codigo;
  const avisos = conexion.activos.filter((a) => a.plataforma === "aviso");
  const visibles = conexion.activos.filter((a) => a.plataforma !== "aviso" && (!filtro || `${a.nombre} ${a.id_externo}`.toLowerCase().includes(filtro.toLowerCase())));
  const grupos = new Map<string, ActivoConexion[]>();
  for (const a of visibles) grupos.set(a.plataforma, [...(grupos.get(a.plataforma) ?? []), a]);

  function alternar(k: string, on: boolean) { const n = new Set(elegidos); on ? n.add(k) : n.delete(k); setElegidos(n); }
  function alternarGrupo(items: ActivoConexion[], on: boolean) {
    const n = new Set(elegidos); for (const a of items) on ? n.add(clave(a)) : n.delete(clave(a)); setElegidos(n);
  }

  return (
    <div className="bloque tarjeta selector" style={{ "--ancho": 12 } as React.CSSProperties}>
      <div className="selector-cabecera">
        <div>
          <h3>Elige qué conectar</h3>
          <p className="sutil">{NOMBRE_PROVEEDOR[conexion.proveedor]} devolvió {conexion.activos.length} activo(s) visibles para la cuenta autorizada. Marca solo los de este cliente.</p>
        </div>
        <input className="buscador" placeholder="Filtrar por nombre o ID" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
      </div>
      {avisos.length > 0 && (
        <div className="aviso-conexion">
          {avisos.map((a) => <p key={a.id_externo}>⚠️ No se pudo listar {a.nombre}</p>)}
        </div>
      )}
      {conexion.activos.length === avisos.length && (
        <p className="sutil">La cuenta autorizada no tiene activos visibles. En Meta, la página debe estar en un Business Manager al que el usuario tenga acceso.</p>
      )}
      {[...grupos.entries()].map(([plataforma, items]) => {
        const marcados = items.filter((a) => elegidos.has(clave(a))).length;
        return (
          <section className="grupo-activos" key={plataforma}>
            <header>
              <span className="estado">{nombrePlataforma(plataforma)}</span>
              <span className="sutil">{marcados} de {items.length}</span>
              <button type="button" className="enlace" onClick={() => alternarGrupo(items, marcados < items.length)}>
                {marcados < items.length ? "Marcar todos" : "Desmarcar todos"}
              </button>
            </header>
            <ul>
              {items.map((a) => {
                const k = clave(a);
                return (
                  <li key={k} className={elegidos.has(k) ? "marcado" : ""}>
                    <label>
                      <input type="checkbox" checked={elegidos.has(k)} onChange={(e) => alternar(k, e.target.checked)} />
                      <span className="nombre" title={a.nombre}>{a.nombre}</span>
                      <code title={a.id_externo}>{a.id_externo}</code>
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
      <div className="selector-pie">
        <span className="sutil">{elegidos.size} seleccionado(s)</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="boton-pdf secundario" type="button" onClick={alCancelar}>Cancelar</button>
          <button className="boton-pdf" type="button" onClick={alActivar} disabled={elegidos.size === 0}>Conectar seleccionadas</button>
        </div>
      </div>
    </div>
  );
}

const REDES_COMPETENCIA = [["meta_ig", "Instagram"], ["meta_fb", "Facebook"], ["tiktok", "TikTok"], ["linkedin", "LinkedIn"], ["youtube", "YouTube"]] as const;
const EJEMPLO_HANDLE: Record<string, string> = {
  meta_ig: "@bancoguayaquil", meta_fb: "BancoGuayaquil o URL de la página", tiktok: "@bancoguayaquil",
  linkedin: "URL de la página", youtube: "@canal o URL",
};
const clave = (nombre: string) => nombre.trim().toLowerCase();

function Competidores({ cliente, alGuardar }: { cliente: ClienteDetalle; alGuardar: () => void }) {
  const [nombre, setNombre] = useState("");
  const [handles, setHandles] = useState<Record<string, string>>({});
  const [aviso, setAviso] = useState<TextoAviso>(null);
  const [ocupado, setOcupado] = useState(false);

  // Matriz competidor × red: deja a la vista en qué redes falta cada uno.
  const filas = new Map<string, { nombre: string; redes: Map<string, (typeof cliente.competidores)[number]> }>();
  for (const c of cliente.competidores) {
    const f = filas.get(clave(c.nombre)) ?? { nombre: c.nombre, redes: new Map() };
    f.redes.set(c.plataforma, c);
    filas.set(clave(c.nombre), f);
  }
  const porRed = (red: string) => cliente.competidores.filter((c) => c.plataforma === red).length;
  const redesUsadas = REDES_COMPETENCIA.filter(([r]) => porRed(r) > 0 || r === "meta_ig" || r === "meta_fb");

  function editar(n: string) {
    setNombre(n);
    const f = filas.get(clave(n));
    // Solo se precargan los usuarios si el nombre es de un competidor ya cargado.
    if (f) setHandles(Object.fromEntries(REDES_COMPETENCIA.map(([r]) => [r, f.redes.get(r)?.handle ?? ""])));
  }

  async function agregar(e: React.FormEvent) {
    e.preventDefault();
    const existentes = filas.get(clave(nombre))?.redes;
    const nuevos = REDES_COMPETENCIA.filter(([r]) => (handles[r] ?? "").trim() && !existentes?.has(r));
    if (!nuevos.length) { setAviso({ error: "Escribe el usuario en al menos una red donde aún no esté." }); return; }
    setOcupado(true);
    const fallos: string[] = []; const ok: string[] = [];
    for (const [r, n] of nuevos) {
      try {
        await api.admin.crearCompetidor(cliente.id, { plataforma: r, nombre: nombre.trim(), handle: handles[r].trim(), orden: porRed(r) });
        ok.push(n);
      } catch (err) { fallos.push(`${n}: ${(err as ErrorApi).message}`); }
    }
    setOcupado(false);
    if (fallos.length) setAviso({ error: `${ok.length ? `Agregado en ${ok.join(", ")}. ` : ""}No se pudo en ${fallos.join(" · ")}` });
    else { setAviso(`${nombre.trim()} agregado en ${ok.join(", ")}. Entra al radar semanal.`); setNombre(""); setHandles({}); }
    alGuardar();
  }
  async function quitar(id: number) { await api.admin.borrarCompetidor(id); alGuardar(); }

  return (
    <div className="grid">
      <div className="bloque" style={{ "--ancho": 7 } as React.CSSProperties}>
        {filas.size === 0 ? <div className="vacio">Sin competidores todavía. Se recomiendan entre 4 y 6, en cada red donde estén.</div> : (
          <div className="tabla-scroll">
            <table className="publicaciones tarjeta matriz-competidores">
              <thead><tr><th>Competidor</th>{redesUsadas.map(([r, n]) => <th key={r}>{n} <span className="sutil">({porRed(r)})</span></th>)}</tr></thead>
              <tbody>{[...filas.values()].map((f) => (
                <tr key={f.nombre}>
                  <td><button type="button" className="enlace" onClick={() => editar(f.nombre)} title="Completar sus redes">{f.nombre}</button></td>
                  {redesUsadas.map(([r]) => {
                    const c = f.redes.get(r);
                    return c ? (
                      <td key={r}><code>{c.handle}</code>
                        <div className="sutil">{c.ultimo_snapshot ? `snapshot ${new Date(c.ultimo_snapshot).toLocaleDateString("es-EC")}` : "aún sin snapshot"}
                          {" · "}<button type="button" className="enlace peligro" onClick={() => quitar(c.id)}>quitar</button></div></td>
                    ) : <td key={r} className="falta"><button type="button" className="enlace" onClick={() => editar(f.nombre)}>+ agregar</button></td>;
                  })}
                </tr>))}</tbody>
            </table>
          </div>
        )}
        {filas.size > 0 && <p className="sutil">El benchmark de cada red solo compara a los competidores cargados en esa red. Las celdas «+ agregar» son redes donde ese competidor todavía no entra al radar.</p>}
      </div>
      <form className="bloque tarjeta formulario" style={{ "--ancho": 5 } as React.CSSProperties} onSubmit={agregar}>
        <h3>Agregar competidor</h3>
        <label>Nombre<input required value={nombre} onChange={(e) => editar(e.target.value)} placeholder="Banco Guayaquil" list="competidores-existentes" /></label>
        <datalist id="competidores-existentes">{[...filas.values()].map((f) => <option key={f.nombre} value={f.nombre} />)}</datalist>
        <p className="sutil">Llena el usuario en cada red donde esté. Se crea uno por red.</p>
        {REDES_COMPETENCIA.map(([r, n]) => {
          const ya = filas.get(clave(nombre))?.redes.has(r);
          return (
            <label key={r}>{n}{ya && <span className="sutil"> · ya está</span>}
              <input value={handles[r] ?? ""} disabled={ya} onChange={(e) => setHandles({ ...handles, [r]: e.target.value })} placeholder={EJEMPLO_HANDLE[r]} />
            </label>
          );
        })}
        <p className="sutil">El radar toma un snapshot semanal de seguidores y publicaciones vía Apify (errata E-02). Costo aproximado: unos centavos por perfil y semana.</p>
        <button className="boton-pdf" type="submit" disabled={ocupado}>{ocupado ? "Agregando…" : "Agregar"}</button><Aviso texto={aviso} />
      </form>
    </div>
  );
}

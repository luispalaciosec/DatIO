import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import type { ActivoConexion, Catalogos, ClienteDetalle, Conexion, CuentaAdmin, TemaAdmin } from "../lib/tipos";
import { supabase } from "../lib/supabase";

export function FichaCliente() {
  const { id = "0" } = useParams();
  const [cliente, setCliente] = useState<ClienteDetalle | null>(null);
  const [catalogos, setCatalogos] = useState<Catalogos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [params] = useSearchParams();
  const [pestana, setPestana] = useState<"datos" | "marca" | "cuentas" | "usuarios">(
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
          {(["datos", "marca", "cuentas", "usuarios"] as const).map((p) => (
            <a key={p} href="#" className={pestana === p ? "activa" : ""} onClick={(e) => { e.preventDefault(); setPestana(p); }}>
              {{ datos: "Datos", marca: "Marca", cuentas: `Cuentas (${cliente.cuentas.length})`, usuarios: `Usuarios (${cliente.usuarios.length})` }[p]}
            </a>
          ))}
        </div>
      </div>
      {pestana === "datos" && <Datos cliente={cliente} catalogos={catalogos} alGuardar={cargar} />}
      {pestana === "marca" && <Marca cliente={cliente} alGuardar={cargar} />}
      {pestana === "cuentas" && <Cuentas cliente={cliente} catalogos={catalogos} alGuardar={cargar} />}
      {pestana === "usuarios" && <UsuariosCliente cliente={cliente} alGuardar={cargar} />}
    </div>
  );
}

function Aviso({ texto }: { texto: string | null }) {
  return texto ? <div className="aviso-ok">{texto}</div> : null;
}

function Datos({ cliente, catalogos, alGuardar }: { cliente: ClienteDetalle; catalogos: Catalogos | null; alGuardar: () => void }) {
  const [f, setF] = useState({ nombre: cliente.nombre, sector: cliente.sector ?? "", activo: cliente.activo });
  const [aviso, setAviso] = useState<string | null>(null);
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

function Marca({ cliente, alGuardar }: { cliente: ClienteDetalle; alGuardar: () => void }) {
  const [t, setT] = useState<TemaAdmin>(cliente.tema);
  const [aviso, setAviso] = useState<string | null>(null);
  const [subiendo, setSubiendo] = useState<string | null>(null);

  async function subir(campo: "logo_url" | "banner_url", archivo: File) {
    setSubiendo(campo);
    const ext = archivo.name.split(".").pop()?.toLowerCase() ?? "png";
    const ruta = `${cliente.slug}/${campo === "logo_url" ? "logo" : "banner"}-${Date.now()}.${ext}`;
    const { error } = await supabase.storage.from("marcas").upload(ruta, archivo, { upsert: true, contentType: archivo.type });
    setSubiendo(null);
    if (error) { setAviso(`No se pudo subir: ${error.message}`); return; }
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
  const [aviso, setAviso] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();
  const [conexion, setConexion] = useState<Conexion | null>(null);
  const [elegidos, setElegidos] = useState<Set<string>>(new Set());
  const errorRetorno = params.get("error");
  const conexionId = params.get("conexion");

  useEffect(() => {
    if (!conexionId) return;
    api.admin.conexion(Number(conexionId)).then((c) => {
      setConexion(c);
      setElegidos(new Set(c.activos.map((a) => `${a.plataforma}|${a.id_externo}`)));
    }).catch((e: ErrorApi) => setAviso(e.message));
  }, [conexionId]);

  async function conectar(proveedor: "meta" | "google") {
    try {
      const { url } = await api.admin.iniciarConexion(proveedor, cliente.id);
      window.location.href = url;
    } catch (err) { setAviso((err as ErrorApi).message); }
  }

  async function activar() {
    if (!conexion) return;
    const activos: ActivoConexion[] = conexion.activos.filter((a) => elegidos.has(`${a.plataforma}|${a.id_externo}`));
    try {
      const r = await api.admin.activarConexion(conexion.id, activos);
      setAviso(`${r.cuentas.length} cuenta(s) conectada(s). Se capturan en la próxima corrida diaria.`);
      setConexion(null); setParams({}); alGuardar();
    } catch (err) { setAviso((err as ErrorApi).message); }
  }
  const AYUDA: Record<string, string> = {
    meta_fb: "Page ID de la página de Facebook. Token: System User de Meta (si va vacío usa el de la agencia).",
    meta_ig: "Instagram Business Account ID (número, no el usuario).",
    meta_ads: "Ad Account ID con prefijo act_.",
    ga4: "Property ID numérico de GA4. Dar acceso de lectura al Service Account de DatIO.",
    gsc: "siteUrl exacto de Search Console: https://dominio.com/ o sc-domain:dominio.com",
    linkedin: "URN de la página: urn:li:organization:123456. Llega por el puente Metricool.",
    tiktok: "Usuario de TikTok tal como aparece en Metricool.",
    youtube: "ID del canal (UC...). Conector pendiente.",
    google_ads: "Customer ID sin guiones. Conector pendiente.",
  };
  async function crear(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.admin.crearCuenta(cliente.id, { plataforma: f.plataforma, id_externo: f.id_externo, nombre_cuenta: f.nombre_cuenta || undefined, credencial: f.credencial || undefined });
      setF({ ...f, id_externo: "", nombre_cuenta: "", credencial: "" }); setAviso("Cuenta conectada. Se captura en la próxima corrida diaria."); alGuardar();
    } catch (err) { setAviso((err as ErrorApi).message); }
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
          <button className="boton-conectar google" onClick={() => conectar("google")}>Google Analytics · Search Console · YouTube</button>
          <button className="boton-conectar pendiente" disabled title="Pendiente de aprobación de LinkedIn">LinkedIn (vía Metricool)</button>
          <button className="boton-conectar pendiente" disabled title="Pendiente de aprobación de TikTok">TikTok (vía Metricool)</button>
        </div>
        {errorRetorno && <div className="bloque-error">No se pudo conectar: {errorRetorno}</div>}
      </div>
      {conexion && conexion.estado === "pendiente" && (
        <div className="bloque tarjeta formulario" style={{ "--ancho": 12 } as React.CSSProperties}>
          <h3>Elige qué conectar ({conexion.proveedor === "meta" ? "Meta" : "Google"})</h3>
          {conexion.activos.length === 0 ? <p className="sutil">La cuenta autorizada no tiene activos visibles. En Meta, la página debe estar en un Business Manager al que el usuario tenga acceso.</p> : (
            <div className="activos">
              {conexion.activos.map((a) => {
                const k = `${a.plataforma}|${a.id_externo}`;
                return (
                  <label key={k} className="fila activo">
                    <input type="checkbox" checked={elegidos.has(k)} onChange={(e) => { const n = new Set(elegidos); e.target.checked ? n.add(k) : n.delete(k); setElegidos(n); }} />
                    <span className="estado">{catalogos?.plataformas.find((p) => p.codigo === a.plataforma)?.nombre ?? a.plataforma}</span>
                    <strong>{a.nombre}</strong><code>{a.id_externo}</code>
                  </label>
                );
              })}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button className="boton-pdf" onClick={activar} disabled={elegidos.size === 0}>Conectar seleccionadas</button>
            <button className="boton-pdf" style={{ background: "var(--gris-300)", color: "var(--gris-700)" }} onClick={() => { setConexion(null); setParams({}); }}>Cancelar</button>
          </div>
        </div>
      )}
      <div className="bloque" style={{ "--ancho": 7 } as React.CSSProperties}>
        {cliente.cuentas.length === 0 ? <div className="vacio">Sin cuentas conectadas todavía.</div> : (
          <table className="publicaciones tarjeta">
            <thead><tr><th>Red</th><th>ID externo</th><th>Nombre</th><th>Credencial</th><th>Última captura</th><th></th></tr></thead>
            <tbody>{cliente.cuentas.map((c) => (
              <tr key={c.id} style={{ opacity: c.activo ? 1 : 0.5 }}>
                <td>{c.plataforma_nombre}</td><td><code>{c.id_externo}</code></td><td>{c.nombre_cuenta ?? "—"}</td>
                <td>{c.tiene_credencial ? "propia" : "de la agencia"}</td>
                <td>{c.ultima_captura ? new Date(c.ultima_captura).toLocaleString("es-EC") : "nunca"}</td>
                <td><button className="boton-pdf" onClick={() => alternar(c)}>{c.activo ? "Pausar" : "Activar"}</button></td>
              </tr>))}</tbody>
          </table>
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
        <label>Token propio (opcional)<input type="password" value={f.credencial} onChange={(e) => setF({ ...f, credencial: e.target.value })} autoComplete="off" /></label>
        <p className="sutil">Se cifra en el servidor y nunca vuelve a mostrarse. Déjalo vacío para usar la credencial de la agencia.</p>
        <button className="boton-pdf" type="submit">Conectar</button><Aviso texto={aviso} />
      </form>
    </div>
  );
}

function UsuariosCliente({ cliente, alGuardar }: { cliente: ClienteDetalle; alGuardar: () => void }) {
  const [email, setEmail] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  async function agregar(e: React.FormEvent) {
    e.preventDefault();
    try { await api.admin.guardarUsuario({ email, rol: "cliente", cliente_id: cliente.id }); setEmail(""); setAviso("Usuario habilitado. Puede entrar con Google o enlace por correo."); alGuardar(); }
    catch (err) { setAviso((err as ErrorApi).message); }
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
        <label>Email del cliente<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <p className="sutil">Solo verá el reporte de {cliente.nombre}. Con la misma cuenta de Google o por enlace al correo.</p>
        <button className="boton-pdf" type="submit">Habilitar</button><Aviso texto={aviso} />
      </form>
    </div>
  );
}

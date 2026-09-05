import { useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import type { Catalogos, ClienteAdmin } from "../lib/tipos";
import { supabase } from "../lib/supabase";
import { FichaCliente } from "./FichaCliente";
import { Capturas } from "./Capturas";
import { Usuarios } from "./Usuarios";

// Módulo administrador (solo rol equipo). Marca DatIO, no la de un cliente.
export function Admin() {
  return (
    <div className="admin">
      <header className="admin-cabecera">
        <Link to="/admin" className="marca"><img src="/marca/isotipo.svg" alt="" /><span>DatIO · Administración</span></Link>
        <nav className="tabs">
          <Link to="/admin">Clientes</Link>
          <Link to="/admin/usuarios">Usuarios</Link>
          <Link to="/admin/capturas">Capturas</Link>
        </nav>
        <div className="acciones">
          <button className="boton-redondo" title="Cerrar sesión" onClick={() => supabase.auth.signOut()}>⏻</button>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<ListaClientes />} />
        <Route path="/clientes/:id" element={<FichaCliente />} />
        <Route path="/usuarios" element={<Usuarios />} />
        <Route path="/capturas" element={<Capturas />} />
      </Routes>
    </div>
  );
}

function ListaClientes() {
  const [clientes, setClientes] = useState<ClienteAdmin[] | null>(null);
  const [catalogos, setCatalogos] = useState<Catalogos | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState({ nombre: "", slug: "", sector: "" });
  const navigate = useNavigate();

  const cargar = () => api.admin.clientes().then(setClientes).catch((e: ErrorApi) => setError(e.message));
  useEffect(() => { cargar(); api.admin.catalogos().then(setCatalogos).catch(() => null); }, []);

  async function crear(e: React.FormEvent) {
    e.preventDefault();
    try {
      const r = await api.admin.crearCliente({ nombre: nuevo.nombre, slug: nuevo.slug, sector: nuevo.sector || null });
      navigate(`/admin/clientes/${r.id}`);
    } catch (err) {
      setError((err as ErrorApi).message);
    }
  }

  if (error) return <div className="bloque-error">{error}</div>;
  if (!clientes) return <div className="bloque-cargando" />;

  return (
    <div className="admin-cuerpo">
      <div className="encabezado"><h1>Clientes<small>{clientes.length} en total</small></h1></div>
      <div className="grid">
        <div className="bloque" style={{ "--ancho": 8 } as React.CSSProperties}>
          <table className="publicaciones tarjeta">
            <thead><tr><th></th><th>Cliente</th><th>Sector</th><th className="num">Cuentas</th><th className="num">Usuarios</th><th>Reporte</th><th></th></tr></thead>
            <tbody>
              {clientes.map((c) => (
                <tr key={c.id} style={{ opacity: c.activo ? 1 : 0.5 }}>
                  <td><span className="muestra-color" style={{ background: c.color_primario ?? "#ccc" }}>{c.logo_url && <img src={c.logo_url} alt="" />}</span></td>
                  <td><Link to={`/admin/clientes/${c.id}`}><strong>{c.nombre}</strong></Link><div className="sutil">{c.slug}{!c.activo && " · inactivo"}</div></td>
                  <td>{c.sector ?? "—"}</td>
                  <td className="num">{c.cuentas}</td>
                  <td className="num">{c.usuarios}</td>
                  <td>{c.slug_publico ? <Link to={`/${c.slug_publico}`}>ver reporte</Link> : "—"}</td>
                  <td><Link to={`/admin/clientes/${c.id}`} className="boton-pdf">Editar</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="bloque" style={{ "--ancho": 4 } as React.CSSProperties}>
          <form className="tarjeta formulario" onSubmit={crear}>
            <h3>Nuevo cliente</h3>
            <label>Nombre<input required value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value, slug: nuevo.slug || aSlug(e.target.value) })} /></label>
            <label>Slug (URL del reporte)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={nuevo.slug} onChange={(e) => setNuevo({ ...nuevo, slug: aSlug(e.target.value) })} /></label>
            <label>Sector<select value={nuevo.sector} onChange={(e) => setNuevo({ ...nuevo, sector: e.target.value })}>
              <option value="">—</option>
              {catalogos?.sectores.map((s) => <option key={s} value={s}>{s}</option>)}
            </select></label>
            <p className="sutil">Se crea con tema por defecto y un reporte con la plantilla RRSS Full. Los clientes del sector banca o financiero usan proveedor de IA occidental.</p>
            <button className="boton-pdf" type="submit">Crear cliente</button>
          </form>
        </div>
      </div>
    </div>
  );
}

export function aSlug(texto: string): string {
  return texto.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

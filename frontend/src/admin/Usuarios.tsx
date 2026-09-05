import { useEffect, useState } from "react";
import { api, ErrorApi } from "../lib/api";
import type { UsuarioAdmin } from "../lib/tipos";

export function Usuarios() {
  const [usuarios, setUsuarios] = useState<UsuarioAdmin[] | null>(null);
  const [email, setEmail] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const cargar = () => api.admin.usuarios().then(setUsuarios).catch((e: ErrorApi) => setAviso(e.message));
  useEffect(() => { cargar(); }, []);
  async function agregarEquipo(e: React.FormEvent) {
    e.preventDefault();
    try { await api.admin.guardarUsuario({ email, rol: "equipo", cliente_id: null }); setEmail(""); setAviso("Miembro del equipo habilitado."); cargar(); }
    catch (err) { setAviso((err as ErrorApi).message); }
  }
  if (!usuarios) return <div className="admin-cuerpo"><div className="bloque-cargando" /></div>;
  return (
    <div className="admin-cuerpo">
      <div className="encabezado"><h1>Usuarios<small>{usuarios.filter((u) => u.activo).length} activos</small></h1></div>
      <div className="grid">
        <div className="bloque" style={{ "--ancho": 8 } as React.CSSProperties}>
          <table className="publicaciones tarjeta"><thead><tr><th>Email</th><th>Rol</th><th>Cliente</th><th>Estado</th><th></th></tr></thead>
            <tbody>{usuarios.map((u) => (
              <tr key={u.email} style={{ opacity: u.activo ? 1 : 0.5 }}>
                <td>{u.email}</td><td>{u.rol}</td><td>{u.cliente_nombre ?? (u.rol === "equipo" ? "todos" : "—")}</td><td>{u.activo ? "activo" : "inactivo"}</td>
                <td>{u.activo && <button className="boton-pdf" onClick={() => api.admin.desactivarUsuario(u.email).then(cargar).catch((e: ErrorApi) => setAviso(e.message))}>Quitar</button>}</td>
              </tr>))}</tbody></table>
        </div>
        <form className="bloque tarjeta formulario" style={{ "--ancho": 4 } as React.CSSProperties} onSubmit={agregarEquipo}>
          <h3>Agregar al equipo</h3>
          <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <p className="sutil">Ve todos los clientes y puede administrar. Los usuarios de un cliente se agregan desde su ficha.</p>
          <button className="boton-pdf" type="submit">Habilitar</button>
          {aviso && <div className="aviso-ok">{aviso}</div>}
        </form>
      </div>
    </div>
  );
}

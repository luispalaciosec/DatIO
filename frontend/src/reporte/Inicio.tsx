import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, ErrorApi } from "../lib/api";
import { supabase } from "../lib/supabase";

// Sin slug en la URL: un cliente va a su reporte; el equipo elige.
export function Inicio() {
  const [estado, setEstado] = useState<{ slug?: string; error?: string; equipo?: boolean }>({});

  useEffect(() => {
    api
      .yo()
      .then((yo) => {
        if (yo.rol === "equipo") return setEstado({ equipo: true });
        // El cliente entra directo a su reporte: el slug viene del servidor, nunca del cliente.
        setEstado({ slug: yo.slug ?? "", equipo: false });
      })
      .catch((e: ErrorApi) => setEstado({ error: e.status === 403 ? "Tu usuario no está habilitado en DatIO. Escribe a tu ejecutivo de cuenta." : e.message }));
  }, []);

  if (estado.error) return <div className="entrar"><div className="tarjeta"><h1>Sin acceso</h1><p>{estado.error}</p><button onClick={() => supabase.auth.signOut()}>Salir</button></div></div>;
  if (estado.equipo) return <Selector />;
  if (estado.slug) return <Navigate to={`/${estado.slug}`} replace />;
  if (estado.slug === "") return <div className="entrar"><div className="tarjeta"><h1>DatIO</h1><p>Pide a tu ejecutivo el enlace de tu reporte.</p></div></div>;
  return null;
}

function Selector() {
  const [slug, setSlug] = useState("");
  return (
    <div className="entrar">
      <div className="tarjeta">
        <h1>Equipo Geeks</h1>
        <p>Escribe el slug del cliente para abrir su reporte.</p>
        <form onSubmit={(e) => { e.preventDefault(); window.location.href = `/${slug}`; }}>
          <input placeholder="banco-amazonas" value={slug} onChange={(e) => setSlug(e.target.value)} />
          <button className="primario" type="submit">Abrir reporte</button>
        </form>
        <button onClick={() => { window.location.href = "/admin"; }}>Administración</button>
        <button onClick={() => supabase.auth.signOut()}>Salir</button>
      </div>
    </div>
  );
}

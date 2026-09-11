import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./lib/supabase";
import { tokenRender } from "./lib/api";
import { Imprimir } from "./reporte/Imprimir";
import { Entrar } from "./reporte/Entrar";
import { Reporte } from "./reporte/Reporte";
import { Inicio } from "./reporte/Inicio";
import { Admin } from "./admin/Admin";

export function App() {
  const [sesion, setSesion] = useState<Session | null | undefined>(undefined);
  const { search } = useLocation();
  const print = new URLSearchParams(search).get("modo") === "print";

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSesion(data.session));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSesion(s));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    document.body.classList.toggle("modo-print", print);
  }, [print]);

  if (tokenRender()) {
    return (
      <Routes>
        <Route path="/:slug/imprimir" element={<Imprimir />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    );
  }
  if (sesion === undefined) return null; // resolviendo sesión
  if (!sesion) return <Entrar />;

  return (
    <Routes>
      <Route path="/" element={<Inicio />} />
      <Route path="/admin" element={<Admin />} />
      <Route path="/admin/clientes/:id" element={<Admin />} />
      <Route path="/admin/usuarios" element={<Admin />} />
      <Route path="/admin/capturas" element={<Admin />} />
      <Route path="/admin/alertas" element={<Admin />} />
      <Route path="/admin/puente" element={<Admin />} />
      <Route path="/admin/datos" element={<Admin />} />
      <Route path="/:slug" element={<Reporte />} />
      <Route path="/:slug/imprimir" element={<Imprimir />} />
      <Route path="/:slug/:plataforma/:pagina" element={<Reporte />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

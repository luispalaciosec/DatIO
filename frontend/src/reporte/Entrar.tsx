import { useState } from "react";
import { supabase } from "../lib/supabase";

// Login vía Supabase Auth: Google (equipo y clientes) o enlace mágico por correo.
export function Entrar() {
  const [email, setEmail] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);

  async function conGoogle() {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
  }

  async function conCorreo(e: React.FormEvent) {
    e.preventDefault();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    setAviso(error ? error.message : "Te enviamos un enlace de acceso a tu correo.");
  }

  return (
    <div className="entrar">
      <div className="tarjeta">
        <h1>DatIO</h1>
        <p>Reportería de redes sociales y pauta</p>
        <button className="primario" onClick={conGoogle}>Entrar con Google</button>
        <form onSubmit={conCorreo}>
          <input
            type="email"
            required
            placeholder="o tu correo para recibir un enlace"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button type="submit">Enviarme el enlace</button>
        </form>
        {aviso && <div className="aviso">{aviso}</div>}
      </div>
    </div>
  );
}

import { useCallback, useState } from "react";
import { supabase } from "../lib/supabase";
import { Turnstile, turnstileActivo } from "./Turnstile";

// Login vía Supabase Auth: Google (equipo y clientes) o enlace mágico por correo.
export function Entrar() {
  const [email, setEmail] = useState("");
  const [aviso, setAviso] = useState<string | null>(null);
  const [captcha, setCaptcha] = useState<string | null>(null);
  const alResolver = useCallback((t: string | null) => setCaptcha(t), []);

  async function conGoogle() {
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin },
    });
  }

  async function conCorreo(e: React.FormEvent) {
    e.preventDefault();
    if (turnstileActivo && !captcha) { setAviso("Completa la verificación antes de pedir el enlace."); return; }
    // #12: shouldCreateUser:false → solo entran correos dados de alta por Geeks (la API los
    // crea en Supabase Auth al invitarlos). captchaToken: protección contra bots (Turnstile).
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: window.location.origin,
        shouldCreateUser: false,
        ...(captcha ? { captchaToken: captcha } : {}),
      },
    });
    // Mismo mensaje exista o no el correo: no revela quién tiene acceso.
    setAviso(error && error.status !== 400 && error.status !== 422
      ? "No pudimos enviar el enlace. Intenta de nuevo en unos minutos."
      : "Si tu correo tiene acceso, te llegará un enlace en unos minutos.");
  }

  return (
    <div className="entrar">
      <div className="tarjeta">
        <img src="/marca/logo.svg" alt="DatIO" style={{ width: 180, marginBottom: 12 }} />
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
          <Turnstile alResolver={alResolver} />
          <button type="submit">Enviarme el enlace</button>
        </form>
        {aviso && <div className="aviso">{aviso}</div>}
      </div>
    </div>
  );
}

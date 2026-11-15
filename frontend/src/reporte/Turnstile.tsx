import { useEffect, useRef } from "react";

// Cloudflare Turnstile (checklist #12). Si VITE_TURNSTILE_SITE_KEY no está definida (desarrollo),
// no se muestra nada y el formulario funciona igual; se avisa en consola.
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;
const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type TurnstileApi = {
  render: (el: HTMLElement, opciones: Record<string, unknown>) => string;
  reset: (id?: string) => void;
  remove: (id?: string) => void;
};
declare global {
  interface Window { turnstile?: TurnstileApi }
}

export const turnstileActivo = Boolean(SITE_KEY);

function cargarScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  const existente = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT}"]`);
  return new Promise((ok, falla) => {
    const s = existente ?? document.createElement("script");
    s.addEventListener("load", () => ok());
    s.addEventListener("error", () => falla(new Error("No se pudo cargar Turnstile")));
    if (!existente) { s.src = SCRIPT; s.async = true; document.head.appendChild(s); }
  });
}

/** Widget de Turnstile. Llama a `alResolver` con el token (o null si expira o falla). */
export function Turnstile({ alResolver }: { alResolver: (token: string | null) => void }) {
  const caja = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!SITE_KEY) {
      console.warn("VITE_TURNSTILE_SITE_KEY no definida: el enlace mágico se pide sin captcha.");
      return;
    }
    let id: string | undefined;
    let vigente = true;
    cargarScript()
      .then(() => {
        if (!vigente || !caja.current || !window.turnstile) return;
        id = window.turnstile.render(caja.current, {
          sitekey: SITE_KEY,
          callback: (t: string) => alResolver(t),
          "expired-callback": () => alResolver(null),
          "error-callback": () => alResolver(null),
        });
      })
      .catch(() => alResolver(null));
    return () => { vigente = false; if (id && window.turnstile) window.turnstile.remove(id); };
  }, [alResolver]);
  return SITE_KEY ? <div ref={caja} className="turnstile" /> : null;
}

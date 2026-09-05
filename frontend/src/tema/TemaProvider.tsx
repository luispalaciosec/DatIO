import { useEffect, type CSSProperties, type ReactNode } from "react";
import type { Tema } from "../lib/tipos";

const PRECARGADAS = new Set(["Inter", "Outfit", "Manrope"]);

// Variables CSS de tema (contrato PT-09): todos los bloques las consumen, ninguno hardcodea color.
export function TemaProvider({ tema, children }: { tema: Tema; children: ReactNode }) {
  useEffect(() => {
    for (const fuente of [tema.fuente_titulos, tema.fuente_cuerpo]) {
      if (PRECARGADAS.has(fuente) || document.querySelector(`link[data-fuente="${fuente}"]`)) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.dataset.fuente = fuente;
      link.href = `https://fonts.googleapis.com/css2?family=${encodeURIComponent(fuente)}:wght@300;400;500&display=swap`;
      document.head.appendChild(link);
    }
  }, [tema.fuente_titulos, tema.fuente_cuerpo]);

  const vars = {
    "--color-primario": tema.color_primario,
    "--color-secundario": tema.color_secundario,
    "--color-acento": tema.color_acento,
    "--fuente-titulos": `'${tema.fuente_titulos}', 'Outfit', system-ui, sans-serif`,
    "--fuente-cuerpo": `'${tema.fuente_cuerpo}', 'Inter', system-ui, sans-serif`,
  } as CSSProperties;
  return (
    <div className="tema" style={vars} data-modo={tema.modo_oscuro ? "oscuro" : "claro"}>
      {children}
    </div>
  );
}

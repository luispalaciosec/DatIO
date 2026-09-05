import type { CSSProperties, ReactNode } from "react";
import type { Tema } from "../lib/tipos";

// Variables CSS de tema (contrato PT-09): todos los bloques las consumen, ninguno hardcodea color.
export function TemaProvider({ tema, children }: { tema: Tema; children: ReactNode }) {
  const vars = {
    "--color-primario": tema.color_primario,
    "--color-secundario": tema.color_secundario,
    "--color-acento": tema.color_acento,
    "--fuente-titulos": `'${tema.fuente_titulos}', system-ui, sans-serif`,
    "--fuente-cuerpo": `'${tema.fuente_cuerpo}', system-ui, sans-serif`,
  } as CSSProperties;
  return (
    <div className="tema" style={vars} data-modo={tema.modo_oscuro ? "oscuro" : "claro"}>
      {children}
    </div>
  );
}

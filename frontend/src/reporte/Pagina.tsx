import type { CSSProperties } from "react";
import type { Pagina as TPagina, Rango, Reporte } from "../lib/tipos";
import { Bloque } from "./Bloque";

// Grid de 12 columnas. Cada bloque carga y falla por separado (PT-09).
export function Pagina({ reporte, pagina, rango }: { reporte: Reporte; pagina: TPagina; rango: Rango }) {
  return (
    <div className="grid">
      {pagina.bloques.map((b) => (
        <div key={b.id} className="bloque" style={{ "--ancho": b.ancho } as CSSProperties}>
          <Bloque reporte={reporte} pagina={pagina} bloque={b} rango={rango} />
        </div>
      ))}
    </div>
  );
}

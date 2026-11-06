import type { RespuestaConsulta } from "../lib/tipos";

export function Narrativa({ respuesta }: { respuesta: RespuestaConsulta<{ texto: string }> }) {
  if (!respuesta.datos.texto) return null;
  return (
    <div className="narrativa">
      <span className="narrativa-marca">Resumen del período</span>
      <p>{respuesta.datos.texto}</p>
    </div>
  );
}

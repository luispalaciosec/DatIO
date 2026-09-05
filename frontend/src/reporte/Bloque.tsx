import { useEffect, useState } from "react";
import { api, ErrorApi } from "../lib/api";
import type { Bloque as TBloque, Pagina, Rango, Reporte, RespuestaConsulta } from "../lib/tipos";
import { HeroBanner } from "../bloques/HeroBanner";
import { TituloSeccion } from "../bloques/TituloSeccion";
import { Separador } from "../bloques/Separador";
import { KpiFila } from "../bloques/KpiFila";
import { SerieTemporal } from "../bloques/SerieTemporal";
import { TablaPublicaciones } from "../bloques/TablaPublicaciones";
import { DistribucionGeo } from "../bloques/DistribucionGeo";

// Bloques estáticos: no consultan datos.
const ESTATICOS = new Set(["hero_banner", "titulo_seccion", "separador"]);

export function Bloque({ reporte, pagina, bloque, rango }: {
  reporte: Reporte; pagina: Pagina; bloque: TBloque; rango: Rango;
}) {
  const [respuesta, setRespuesta] = useState<RespuestaConsulta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ESTATICOS.has(bloque.tipo)) return;
    let vigente = true;
    setRespuesta(null);
    setError(null);
    api.consulta(reporte.instancia_id, bloque.id, rango)
      .then((r) => vigente && setRespuesta(r))
      .catch((e: ErrorApi) => vigente && setError(e.message));
    return () => { vigente = false; };
  }, [reporte.instancia_id, bloque.id, bloque.tipo, rango]);

  switch (bloque.tipo) {
    case "hero_banner":
      return <HeroBanner tema={reporte.tema} titulo={reporte.nombre_publico ?? reporte.tema.nombre} pagina={pagina} rango={rango} config={bloque.config} />;
    case "titulo_seccion":
      return <TituloSeccion config={bloque.config} />;
    case "separador":
      return <Separador />;
  }

  if (error) return <div className="bloque-error">No se pudo cargar este bloque: {error}</div>;
  if (!respuesta) return <div className="bloque-cargando" />;

  const provisional = respuesta.estado === "provisional";
  switch (bloque.tipo) {
    case "kpi_fila":
      return <KpiFila respuesta={respuesta as never} provisional={provisional} />;
    case "serie_temporal":
      return <SerieTemporal respuesta={respuesta as never} provisional={provisional} />;
    case "tabla_publicaciones":
      return <TablaPublicaciones respuesta={respuesta as never} />;
    case "distribucion_geo":
      return <DistribucionGeo respuesta={respuesta as never} />;
    default:
      return <div className="vacio">Bloque «{bloque.tipo}» aún no disponible en esta versión.</div>;
  }
}

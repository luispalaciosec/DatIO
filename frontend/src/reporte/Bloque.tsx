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
import { BenchmarkGrid } from "../bloques/BenchmarkGrid";
import { BenchmarkTabla } from "../bloques/BenchmarkTabla";
import { BenchmarkSerie } from "../bloques/BenchmarkSerie";
import { BenchmarkPublicaciones } from "../bloques/BenchmarkPublicaciones";
import { Distribucion } from "../bloques/Distribucion";
import { Demografia } from "../bloques/Demografia";
import { TablaRanking } from "../bloques/TablaRanking";
import { TopPublicaciones } from "../bloques/TopPublicaciones";
import { RendimientoFormato } from "../bloques/RendimientoFormato";
import { MejorDia } from "../bloques/MejorDia";
import { PacingMes } from "../bloques/PacingMes";

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
      if (document.body.classList.contains("modo-print")) return null; // la hoja ya lleva cabecera
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
    case "pacing_mes":
      return <PacingMes respuesta={respuesta as never} provisional={provisional} />;
    case "kpi_fila":
      return <KpiFila respuesta={respuesta as never} provisional={provisional} />;
    case "serie_temporal":
      return <SerieTemporal respuesta={respuesta as never} provisional={provisional} />;
    case "tabla_publicaciones":
      return <TablaPublicaciones respuesta={respuesta as never} />;
    case "distribucion_geo":
      return <DistribucionGeo respuesta={respuesta as never} />;
    case "benchmark_grid":
      return <BenchmarkGrid respuesta={respuesta as never} />;
    case "benchmark_tabla":
      return <BenchmarkTabla respuesta={respuesta as never} />;
    case "benchmark_serie":
      return <BenchmarkSerie respuesta={respuesta as never} />;
    case "benchmark_publicaciones":
      return <BenchmarkPublicaciones respuesta={respuesta as never} />;
    case "distribucion":
      return <Distribucion respuesta={respuesta as never} />;
    case "demografia":
      return <Demografia respuesta={respuesta as never} />;
    case "tabla_ranking":
      return <TablaRanking respuesta={respuesta as never} />;
    case "top_publicaciones":
      return <TopPublicaciones respuesta={respuesta as never} />;
    case "rendimiento_formato":
      return <RendimientoFormato respuesta={respuesta as never} />;
    case "mejor_dia":
      return <MejorDia respuesta={respuesta as never} />;
    default:
      return <div className="vacio">Bloque «{bloque.tipo}» aún no disponible en esta versión.</div>;
  }
}

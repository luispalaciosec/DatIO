import { useState } from "react";
import { urlImagen } from "../lib/api";
import type { RespuestaConsulta } from "../lib/tipos";

interface Anuncio {
  id: number; competidor: string; handle: string | null; logo_url: string | null;
  ad_archive_id: string; primera_vez_visto: string; ultima_vez_visto: string; dias_activo: number;
  plataformas: string[]; creatividad_url: string | null; copy_texto: string | null; formato: string | null;
  cta: string | null; titulo: string | null; enlace: string | null; url_biblioteca: string | null; activo: boolean;
}
const PLAT: Record<string, string> = { facebook: "FB", instagram: "IG", messenger: "MSG", audience_network: "AN", whatsapp: "WA", threads: "TH" };

export function RadarAnuncios({ respuesta }: { respuesta: RespuestaConsulta<Anuncio[]> }) {
  const [filtro, setFiltro] = useState<string>("todos");
  if (respuesta.meta.sin_competidores) return <div className="vacio">Sin competidores de Facebook configurados. El radar de pauta usa la página de Facebook de cada competidor: agrégalos en Administración, ficha del cliente, pestaña Competidores.</div>;
  if (respuesta.meta.sin_datos) return <div className="vacio">La competencia no tiene anuncios activos en Ecuador en la última captura, o el radar aún no corrió para esta red.</div>;
  const competidores = (respuesta.meta.competidores as Array<{ id: number; nombre: string }>) ?? [];
  const anuncios = respuesta.datos.filter((a) => filtro === "todos" || a.competidor === filtro);
  return (
    <div className="radar">
      {competidores.length > 1 && (
        <div className="subtabs radar-filtro">
          <button className={filtro === "todos" ? "activa" : ""} onClick={() => setFiltro("todos")}>Todos ({respuesta.datos.length})</button>
          {competidores.map((c) => (
            <button key={c.id} className={filtro === c.nombre ? "activa" : ""} onClick={() => setFiltro(c.nombre)}>{c.nombre} ({respuesta.datos.filter((a) => a.competidor === c.nombre).length})</button>
          ))}
        </div>
      )}
      <div className="radar-grid">
        {anuncios.map((a) => (
          <a key={a.id} className="anuncio" href={a.url_biblioteca ?? "#"} target="_blank" rel="noreferrer">
            <div className="anuncio-imagen">
              {a.creatividad_url ? <img src={urlImagen(a.creatividad_url) ?? ""} alt="" referrerPolicy="no-referrer" loading="lazy" /> : <div className="pub-sin-imagen">{a.formato ?? "anuncio"}</div>}
              <span className={`anuncio-dias ${a.dias_activo >= 90 ? "veterano" : a.dias_activo >= 30 ? "maduro" : ""}`}>{a.dias_activo} d activo</span>
              {a.formato && <span className="pub-tipo">{a.formato}</span>}
            </div>
            <div className="pub-cuerpo">
              <div className="pub-competidor">
                {a.logo_url ? <img src={urlImagen(a.logo_url) ?? ""} alt="" referrerPolicy="no-referrer" /> : <span className="inicial">{a.competidor.slice(0, 1)}</span>}
                <strong>{a.competidor}</strong>
              </div>
              {a.titulo && <div className="anuncio-titulo">{a.titulo}</div>}
              <div className="pub-caption">{a.copy_texto ? (a.copy_texto.length > 110 ? `${a.copy_texto.slice(0, 110)}…` : a.copy_texto) : "(sin texto)"}</div>
              <div className="anuncio-pie">
                {a.cta && <span className="anuncio-cta">{a.cta}</span>}
                <span className="sutil">{a.plataformas.map((p) => PLAT[p] ?? p).join(" · ")}</span>
              </div>
            </div>
          </a>
        ))}
      </div>
      <div className="sutil">Fuente: Biblioteca de anuncios de Meta, anuncios activos en Ecuador. Un anuncio con muchos días activo es un anuncio que le está funcionando a la competencia.{respuesta.meta.ultima_captura ? ` Última captura ${String(respuesta.meta.ultima_captura)}.` : ""}</div>
    </div>
  );
}

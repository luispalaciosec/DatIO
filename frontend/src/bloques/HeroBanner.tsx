import { formatearFecha } from "../lib/formato";
import type { Pagina, Rango, Tema } from "../lib/tipos";

export function HeroBanner({ tema, titulo, pagina, rango, config }: {
  tema: Tema; titulo: string; pagina: Pagina; rango: Rango; config: Record<string, unknown>;
}) {
  const banner = (config.banner_url as string | undefined) ?? tema.banner_url;
  return (
    <div className="hero" style={banner ? { backgroundImage: `url(${banner})` } : undefined}>
      {tema.logo_url && <img src={tema.logo_url} alt={tema.nombre} />}
      <div>
        <div className="titulo">{(config.titulo as string | undefined) ?? titulo}</div>
        <div className="sub">
          {pagina.titulo} · {formatearFecha(rango.desde)} a {formatearFecha(rango.hasta)}
        </div>
      </div>
    </div>
  );
}

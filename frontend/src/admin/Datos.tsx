import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { hoyISO } from "../lib/formato";
import type { CatalogoPlataforma, ConsultaDatos, ResultadoDatos } from "../lib/tipos";

const NOMBRE_UNIDAD: Record<string, string> = { conteo: "número", porcentaje: "%", moneda: "USD", segundos: "segundos" };
const NOMBRE_AGG: Record<string, string> = { suma: "se suma", promedio: "se promedia", ultimo: "último valor", maximo: "máximo" };

export function Datos() {
  const [catalogo, setCatalogo] = useState<CatalogoPlataforma[] | null>(null);
  const [vista, setVista] = useState<"catalogo" | "explorador">("catalogo");
  useEffect(() => { api.admin.catalogoDatos().then((c) => setCatalogo(c.plataformas)); }, []);
  if (!catalogo) return <div className="admin-seccion"><div className="bloque-cargando" /></div>;
  return (
    <div className="admin-seccion">
      <div className="subtabs" style={{ marginBottom: 12 }}>
        <button className={vista === "catalogo" ? "activa" : ""} onClick={() => setVista("catalogo")}>Catálogo de conectores</button>
        <button className={vista === "explorador" ? "activa" : ""} onClick={() => setVista("explorador")}>Explorador y descarga</button>
      </div>
      {vista === "catalogo" ? <Catalogo plataformas={catalogo} /> : <Explorador plataformas={catalogo} />}
    </div>
  );
}

function Catalogo({ plataformas }: { plataformas: CatalogoPlataforma[] }) {
  const [abierta, setAbierta] = useState<string | null>(plataformas.find((p) => p.metricas.some((m) => m.hasta))?.codigo ?? null);
  return (
    <div className="catalogo">
      <p className="sutil">Todo lo que cada conector entrega a DatIO: la métrica tal como la llama la plataforma, cómo se llama aquí, cómo se agrega y desde cuándo hay datos reales. Las que no tienen fecha están mapeadas pero ninguna cuenta las ha traído todavía.</p>
      {plataformas.map((p) => {
        const conDatos = p.metricas.filter((m) => m.hasta).length;
        return (
          <div key={p.codigo} className="tarjeta catalogo-plataforma">
            <button type="button" className="catalogo-cabecera" onClick={() => setAbierta(abierta === p.codigo ? null : p.codigo)}>
              <strong>{p.nombre}</strong>
              <span className="sutil">{p.metricas.length} métricas · {conDatos} con datos · {p.dimensiones.length} dimensiones · {p.publicaciones.length} métricas por publicación · {p.cuentas.length} cuentas</span>
              <span>{abierta === p.codigo ? "▾" : "▸"}</span>
            </button>
            {abierta === p.codigo && (
              <div className="catalogo-cuerpo">
                <h4>Métricas diarias</h4>
                <div style={{ overflowX: "auto" }}>
                  <table className="publicaciones">
                    <thead><tr><th>En DatIO</th><th>Código</th><th>Nombre nativo en {p.nombre}</th><th>Unidad</th><th>Agregación</th><th>Categoría</th><th>Datos desde</th><th>Hasta</th><th>Cuentas</th></tr></thead>
                    <tbody>
                      {p.metricas.map((m) => (
                        <tr key={m.metrica_nativa} className={m.hasta ? "" : "sin-datos"}>
                          <td>{m.nombre_es}</td><td><code>{m.codigo}</code></td><td><code>{m.metrica_nativa}</code>{m.factor && Number(m.factor) !== 1 ? <span className="sutil"> ×{m.factor}</span> : null}</td>
                          <td>{NOMBRE_UNIDAD[m.unidad] ?? m.unidad}</td><td>{NOMBRE_AGG[m.agregacion] ?? m.agregacion}{m.es_acumulada ? " (acumulada)" : ""}</td>
                          <td>{m.categoria}</td><td>{m.desde ?? "—"}</td><td>{m.hasta ?? "—"}</td><td>{m.cuentas ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {p.dimensiones.length > 0 && (
                  <>
                    <h4>Dimensiones (desgloses)</h4>
                    <table className="publicaciones">
                      <thead><tr><th>Dimensión</th><th>Métricas desglosadas</th><th>Valores distintos</th><th>Desde</th><th>Hasta</th></tr></thead>
                      <tbody>{p.dimensiones.map((d) => <tr key={d.dimension}><td><code>{d.dimension}</code></td><td>{d.metricas.join(", ")}</td><td>{d.valores}</td><td>{d.desde}</td><td>{d.hasta}</td></tr>)}</tbody>
                    </table>
                  </>
                )}
                {p.publicaciones.length > 0 && (
                  <>
                    <h4>Métricas por publicación</h4>
                    <p className="sutil">{p.publicaciones.map((x) => `${x.nombre_es} (${x.publicaciones} publicaciones)`).join(" · ")}</p>
                  </>
                )}
                {p.cuentas.length > 0 && (
                  <>
                    <h4>Cuentas conectadas</h4>
                    <table className="publicaciones">
                      <thead><tr><th>Cliente</th><th>Cuenta</th><th>ID externo</th><th>Estado</th><th>Datos desde</th><th>Hasta</th><th>Filas</th></tr></thead>
                      <tbody>{p.cuentas.map((c) => <tr key={c.id}><td>{c.cliente}</td><td>{c.nombre_cuenta ?? "—"}</td><td><code>{c.id_externo}</code></td><td>{c.activo ? "activa" : "pausada"}</td><td>{c.desde ?? "—"}</td><td>{c.hasta ?? "—"}</td><td>{c.filas.toLocaleString("es-EC")}</td></tr>)}</tbody>
                    </table>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Explorador({ plataformas }: { plataformas: CatalogoPlataforma[] }) {
  const [plataforma, setPlataforma] = useState<string>(plataformas.find((p) => p.cuentas.some((c) => c.filas > 0))?.codigo ?? plataformas[0]?.codigo ?? "");
  const p = plataformas.find((x) => x.codigo === plataforma);
  const [cuentas, setCuentas] = useState<number[]>([]);
  const [metricas, setMetricas] = useState<string[]>([]);
  const [dimension, setDimension] = useState<string>("");
  const [granularidad, setGranularidad] = useState<ConsultaDatos["granularidad"]>("dia");
  const [desde, setDesde] = useState(hoyISO(-28));
  const [hasta, setHasta] = useState(hoyISO(-1));
  const [resultado, setResultado] = useState<ResultadoDatos | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => { setCuentas([]); setMetricas([]); setDimension(""); setResultado(null); }, [plataforma]);
  const metricasDisponibles = useMemo(() => {
    if (!p) return [];
    if (!dimension) return p.metricas.filter((m) => m.hasta);
    const permitidas = new Set(p.dimensiones.find((d) => d.dimension === dimension)?.metricas ?? []);
    return p.metricas.filter((m) => permitidas.has(m.codigo));
  }, [p, dimension]);
  const cuerpo = (): ConsultaDatos => ({ cuentas, metricas, desde, hasta, granularidad, dimension: dimension || null });
  const listo = cuentas.length > 0 && metricas.length > 0;

  async function consultar() {
    setOcupado(true); setAviso(null);
    try { setResultado(await api.admin.consultarDatos(cuerpo())); }
    catch (err) { setAviso(`Falló: ${(err as Error).message}`); }
    setOcupado(false);
  }
  async function descargar() {
    setOcupado(true);
    try {
      const blob = await api.admin.descargarCsv(cuerpo());
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `datio_${plataforma}_${desde}_${hasta}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch (err) { setAviso(`Falló: ${(err as Error).message}`); }
    setOcupado(false);
  }
  const alternar = <T,>(lista: T[], v: T, set: (x: T[]) => void) => set(lista.includes(v) ? lista.filter((x) => x !== v) : [...lista, v]);

  return (
    <div className="explorador">
      <div className="tarjeta formulario">
        <div className="explorador-fila">
          <label>Conector<select value={plataforma} onChange={(e) => setPlataforma(e.target.value)}>{plataformas.map((x) => <option key={x.codigo} value={x.codigo}>{x.nombre}</option>)}</select></label>
          <label>Desde<input type="date" value={desde} onChange={(e) => setDesde(e.target.value)} /></label>
          <label>Hasta<input type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} /></label>
          <label>Agrupar por<select value={granularidad} onChange={(e) => setGranularidad(e.target.value as ConsultaDatos["granularidad"])}>
            <option value="dia">Día</option><option value="semana">Semana</option><option value="mes">Mes</option><option value="total">Total del rango</option></select></label>
          <label>Desglose<select value={dimension} onChange={(e) => { setDimension(e.target.value); setMetricas([]); }}>
            <option value="">Sin desglose</option>{p?.dimensiones.map((d) => <option key={d.dimension} value={d.dimension}>{d.dimension}</option>)}</select></label>
        </div>
        <div className="explorador-columnas">
          <div>
            <h4>Cuentas <button type="button" className="enlace" onClick={() => setCuentas(cuentas.length === (p?.cuentas.length ?? 0) ? [] : (p?.cuentas.map((c) => c.id) ?? []))}>todas / ninguna</button></h4>
            <ul className="lista-marcable">
              {p?.cuentas.map((c) => (
                <li key={c.id}><label className="fila"><input type="checkbox" checked={cuentas.includes(c.id)} onChange={() => alternar(cuentas, c.id, setCuentas)} /> {c.cliente} · {c.nombre_cuenta ?? c.id_externo} <span className="sutil">{c.filas ? `hasta ${c.hasta}` : "sin datos"}</span></label></li>
              ))}
              {p?.cuentas.length === 0 && <li className="sutil">Ninguna cuenta conectada en este conector.</li>}
            </ul>
          </div>
          <div>
            <h4>Métricas <button type="button" className="enlace" onClick={() => setMetricas(metricas.length === metricasDisponibles.length ? [] : metricasDisponibles.map((m) => m.codigo))}>todas / ninguna</button></h4>
            <ul className="lista-marcable">
              {metricasDisponibles.map((m) => (
                <li key={m.codigo}><label className="fila"><input type="checkbox" checked={metricas.includes(m.codigo)} onChange={() => alternar(metricas, m.codigo, setMetricas)} /> {m.nombre_es} <span className="sutil">{m.metrica_nativa} · {NOMBRE_AGG[m.agregacion] ?? m.agregacion}</span></label></li>
              ))}
              {metricasDisponibles.length === 0 && <li className="sutil">Sin métricas con datos para esta combinación.</li>}
            </ul>
          </div>
        </div>
        <div className="fila" style={{ gap: 8 }}>
          <button type="button" className="boton-pdf" disabled={!listo || ocupado} onClick={consultar}>Consultar</button>
          <button type="button" className="boton-secundario" disabled={!listo || ocupado} onClick={descargar}>Descargar CSV</button>
          {aviso && <span className="delta baja">{aviso}</span>}
        </div>
      </div>
      {resultado && (
        <div className="tarjeta">
          <p className="sutil">{resultado.filas.length.toLocaleString("es-EC")} fila(s){resultado.truncado ? " · resultado truncado, acota el rango o descarga el CSV" : ""}. Se muestran las primeras 500.</p>
          <div style={{ overflowX: "auto" }}>
            <table className="publicaciones">
              <thead><tr>{resultado.columnas.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {resultado.filas.slice(0, 500).map((f, i) => (
                  <tr key={i}>{resultado.columnas.map((c) => <td key={c}>{typeof f[c] === "number" ? (f[c] as number).toLocaleString("es-EC", { maximumFractionDigits: 2 }) : (f[c] ?? "—")}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

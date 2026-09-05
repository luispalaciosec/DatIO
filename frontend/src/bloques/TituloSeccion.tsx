export function TituloSeccion({ config }: { config: Record<string, unknown> }) {
  return (
    <div className="titulo-seccion">
      <h3>{String(config.titulo ?? "")}</h3>
      {config.bajada ? <p>{String(config.bajada)}</p> : null}
    </div>
  );
}

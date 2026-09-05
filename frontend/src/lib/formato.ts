const es = "es-EC";

export function formatearValor(
  valor: number | null,
  formato: string = "entero",
  decimales = 0,
): string {
  if (valor === null || Number.isNaN(valor)) return "—";
  switch (formato) {
    case "porcentaje":
      return `${valor.toLocaleString(es, { maximumFractionDigits: decimales || 1 })}%`;
    case "moneda":
      return valor.toLocaleString(es, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
    case "duracion": {
      const h = Math.floor(valor / 3600);
      const m = Math.floor((valor % 3600) / 60);
      return h > 0 ? `${h} h ${m} min` : `${m} min`;
    }
    default:
      return valor.toLocaleString(es, { maximumFractionDigits: decimales });
  }
}

export function formatearCompacto(valor: number | null): string {
  if (valor === null) return "—";
  return valor.toLocaleString(es, { notation: "compact", maximumFractionDigits: 1 });
}

export function formatearFecha(iso: string): string {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString(es, { day: "numeric", month: "short" });
}

export function hoyISO(offsetDias = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDias);
  return d.toISOString().slice(0, 10);
}

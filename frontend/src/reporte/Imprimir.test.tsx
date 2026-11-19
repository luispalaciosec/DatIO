// B-4: la vista de impresión nunca se marca "lista" cuando falla. Si lo hiciera, el generador
// del PDF imprimiría la pantalla de error y el envío mensual se la mandaría al cliente.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../lib/api", () => ({
  api: { reporte: vi.fn(() => Promise.reject(new Error("401 detalle técnico interno"))) },
  ErrorApi: class extends Error {},
}));

import { Imprimir } from "./Imprimir";

afterEach(cleanup);

describe("Imprimir", () => {
  it("en error marca data-impresion-error y nunca data-impresion-lista", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/banco/imprimir?desde=2026-10-01&hasta=2026-10-31"]}>
        <Routes><Route path="/:slug/imprimir" element={<Imprimir />} /></Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(container.querySelector('[data-impresion-error="1"]')).not.toBeNull());
    expect(container.querySelector("[data-impresion-lista]")).toBeNull();
    // sin detalles técnicos en la vista que lee el generador del PDF
    expect(container.textContent).not.toContain("detalle técnico");
  });
});

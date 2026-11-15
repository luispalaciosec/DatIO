import { describe, expect, it } from "vitest";
import { limpiarTexto } from "./observabilidad";

describe("limpiarTexto", () => {
  it("quita el token de render, JWT y correos", () => {
    const jwt = "eyJhbGciOi.eyJzdWIiOi.firma_123";
    const limpio = limpiarTexto(`https://x/banco/imprimir?desde=1&render=${jwt} a@b.com Bearer ${jwt}`);
    expect(limpio).not.toContain(jwt);
    expect(limpio).not.toContain("a@b.com");
    expect(limpio).toContain("render=[filtrado]");
    expect(limpio).toContain("desde=1");
  });
});

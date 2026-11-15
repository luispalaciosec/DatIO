// #12: el enlace mágico no crea usuarios (shouldCreateUser:false) y lleva el token de Turnstile.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";

const signInWithOtp = vi.fn(() => Promise.resolve({ error: null }));
vi.mock("../lib/supabase", () => ({ supabase: { auth: { signInWithOtp, signInWithOAuth: vi.fn() } } }));

afterEach(() => { cleanup(); vi.resetModules(); signInWithOtp.mockClear(); });

describe("Entrar", () => {
  describe("sin Turnstile configurado (desarrollo)", () => {
    beforeEach(() => {
      vi.doMock("./Turnstile", () => ({ turnstileActivo: false, Turnstile: () => null }));
    });
    it("pide el enlace con shouldCreateUser:false y sin captcha", async () => {
      const { Entrar } = await import("./Entrar");
      const { container } = render(<Entrar />);
      fireEvent.change(container.querySelector("input[type=email]")!, { target: { value: "a@b.com" } });
      fireEvent.submit(container.querySelector("form")!);
      await waitFor(() => expect(signInWithOtp).toHaveBeenCalledTimes(1));
      const opciones = (signInWithOtp.mock.calls[0] as unknown as [{ options: Record<string, unknown> }])[0].options;
      expect(opciones.shouldCreateUser).toBe(false);
      expect(opciones).not.toHaveProperty("captchaToken");
    });
  });

  describe("con Turnstile", () => {
    beforeEach(() => {
      vi.doMock("./Turnstile", () => ({
        turnstileActivo: true,
        Turnstile: ({ alResolver }: { alResolver: (t: string | null) => void }) => (
          <button type="button" data-testid="resolver" onClick={() => alResolver("token-captcha")}>ok</button>
        ),
      }));
    });
    it("exige el captcha y lo envía como captchaToken", async () => {
      const { Entrar } = await import("./Entrar");
      const { container, getByTestId } = render(<Entrar />);
      fireEvent.change(container.querySelector("input[type=email]")!, { target: { value: "a@b.com" } });
      fireEvent.submit(container.querySelector("form")!);
      expect(signInWithOtp).not.toHaveBeenCalled(); // sin resolver el captcha no se pide
      fireEvent.click(getByTestId("resolver"));
      fireEvent.submit(container.querySelector("form")!);
      await waitFor(() => expect(signInWithOtp).toHaveBeenCalledTimes(1));
      const opciones = (signInWithOtp.mock.calls[0] as unknown as [{ options: Record<string, unknown> }])[0].options;
      expect(opciones).toMatchObject({ shouldCreateUser: false, captchaToken: "token-captcha" });
    });
  });
});

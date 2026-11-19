/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx", "src/**/*.test.ts"],
    env: { VITE_API_URL: "http://api.test", VITE_SUPABASE_URL: "http://supabase.test", VITE_SUPABASE_KEY: "clave-de-prueba" },
  },
});

# frontend — renderer white-label (PT-09 / PT-10)

React + Vite + TypeScript. Consume `GET /reportes/{slug}` (estructura y tema) y `POST /consulta`
(datos por bloque). Login con Supabase Auth (Google o enlace por correo).

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_URL, VITE_SUPABASE_URL, VITE_SUPABASE_KEY (clave publicable)
npm run dev               # http://localhost:5173
npm run build             # dist/ para Vercel
```

- Ruteo: `/{slug_publico}/{plataforma}/{pagina}?desde=AAAA-MM-DD&hasta=AAAA-MM-DD`
- `?modo=print` oculta navegación y selector (lo usa PT-11 con Playwright)
- `TemaProvider` inyecta las variables CSS `--color-primario`, `--color-secundario`,
  `--color-acento`, `--fuente-titulos`, `--fuente-cuerpo` desde `cliente_tema`.
  Ningún bloque hardcodea colores.
- Bloques: `hero_banner`, `titulo_seccion`, `kpi_fila`, `serie_temporal`,
  `tabla_publicaciones`, `separador`, `distribucion_geo`. Cada uno carga y falla por separado.
- Agregar un bloque = un componente en `src/bloques/` + un `case` en `src/reporte/Bloque.tsx`.

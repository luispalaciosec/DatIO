# HARDENING-CHANGELOG — rama `hardening/2026-11-14`

> **⚠️ Bloque 0 (B-4, S-1, B-1, N-1, B-7) debe estar desplegado y con un PDF de prueba validado
> por un humano antes del 1/12; si no, apagar el envío automático.**
> (Dejar `RESEND_API_KEY` vacía en el servicio del cron hace que `enviar_mensuales` no envíe
> nada; luego mandar los reportes a mano tras revisarlos.)

Base: `main` @ `d250e4e`. Guía: auditoría 2026-10-10 (S-x, B-x, Calidad n, checklist de 20) y
re-auditoría 2026-11-14 (N-1, N-2, R-1..R-4). Alcance: seguridad + repo. La Fase 3 de calidad
queda diferida a una pasada 2 (ver sección al final).

**Cómo se verificó todo:** Postgres 17 local desechable (Homebrew, puerto 5433) con
`scripts/aplicar_sql.sh` (todas las migraciones compatibles + seeds). Nunca contra producción.
Comandos: en `backend/` `ruff check .`, `mypy`, `pytest -q` (con `DATABASE_URL` local y sin
él); en `frontend/` `npx tsc --noEmit`, `npx vite build`, `npx vitest run`, `npm audit`.

---

## Bloque 0 — antes del envío del 1/12

### B-4 / R-1 · El envío mensual podía mandar el PDF de la pantalla de error — **hecho**
- Commit: `14a8ac3`
- Archivos: `frontend/src/reporte/Imprimir.tsx`, `frontend/src/reporte/Bloque.tsx`,
  `backend/api/pdf/render.py`, `backend/api/pdf/router.py`, `backend/api/reportes/envio.py`,
  `backend/api/reportes/correo.py`, `backend/pyproject.toml` (pypdf, sentry-sdk).
- Arreglo:
  - (a) La vista de impresión marca `data-impresion-error="1"` y nunca
    `data-impresion-lista`; cada bloque que falla marca `data-bloque-error="1"`. En modo
    impresión no hay detalle técnico.
  - (b) `generar_pdf` espera a «lista o error» y decide con `decidir_impresion`, que es pura.
    Error de la vista, bloque con error, algo cargando, sin hojas o timeout →
    `PdfInvalidoError` con un motivo corto, sin URL ni token.
  - (c) `validar_pdf(contenido, paginas_esperadas)` comprueba la cabecera `%PDF-`,
    `TAMANO_MINIMO_PDF` = 1024 bytes y que las páginas (contadas con pypdf) sean ≥ las
    `section.hoja` del DOM.
  - (d)(f) `enviar_reporte`: PDF → validación (segunda barrera) → narrativa → envío. Si algo
    falla, al cliente no le llega nada. Se registra `pdf_invalido` o `error`, con un motivo
    corto sin token. La columna `estado` es TEXT sin CHECK; valores documentados en
    `ResultadoEnvio`. `ya_enviado` sigue contando solo `enviado`, así que el cron reintenta.
  - (e) Aviso interno al equipo en envíos automáticos fallidos: `correos_equipo()` +
    `alertas_destinatarios_extra`, sin adjunto. Sin Resend, solo log. Además se captura en
    Sentry si hay DSN.
  - (g) `/reportes/{slug}/pdf`: 502 «No se pudo generar el PDF, intenta de nuevo». El detalle
    va al log sin token (cierra B-11 en este punto).
  - (h) El envío manual usa el mismo `enviar_reporte`. Responde 502 con el motivo corto y no
    avisa al equipo, porque el pedido lo hizo el propio equipo.
- Verificación:
  - `tests/test_envio_pdf.py`: decisión del DOM (6 casos de rechazo), `validar_pdf`, PDF
    inválido/basura sin correo al cliente + aviso al equipo + `ya_enviado` en False, log y
    motivo sin token, caso feliz, envío manual fallido.
  - `tests/test_pdf.py::test_endpoint_pdf_error_de_render_502` (mensaje genérico).
  - `frontend/src/reporte/Imprimir.test.tsx` (vitest).
  - Los tests nuevos fallan con el código anterior (comprobado).

### S-1 · Un cliente desactivado seguía entrando y bajando el PDF — **hecho**
- Commit: `118fac0`
- Archivos: `backend/api/auth/repositorio.py`, `backend/api/consulta/repositorio.py`,
  `backend/api/deps.py`, `backend/api/consulta/router.py`, `backend/api/pdf/router.py`.
- Arreglo:
  - `usuario_por_email` hace LEFT JOIN a clientes y exige `u.activo AND (u.rol = 'equipo' OR
    c.activo)`.
  - Las instancias traen `cliente_activo`.
  - Una sola regla: `deps.autorizar_instancia` + `instancia_autorizada` (por slug) e
    `instancia_autorizada_por_id` (para el cuerpo de `/consulta`). Devuelve 404 si no existe
    y 403 si es ajena o el cliente está inactivo. Se borraron las tres comprobaciones a mano.
  - No hay caché de usuarios: la API lee `usuarios` en cada petición, así que desactivar
    surte efecto en la siguiente.
- Decisión: el reporte de un cliente inactivo da 403 también al equipo. El equipo sigue
  entrando a la plataforma y al admin.
- Verificación: `tests/test_acceso.py` (activo 200×3; inactivo 403×3 para el cliente y para
  el equipo; `usuario_por_email` None; ajeno 403; inexistente 404). Falla con el código
  anterior.

### B-1 · Activar una conexión OAuth reasignaba una cuenta a otro cliente — **hecho**
- Commit: `b128fe9`
- Archivos: `backend/api/admin/repositorio.py`, `backend/api/admin/router_conectar.py`.
- Arreglo:
  - `ON CONFLICT ... DO UPDATE ... WHERE cuentas_conectadas.cliente_id = EXCLUDED.cliente_id
    RETURNING id`. Sin fila devuelta → `CuentaDeOtroClienteError`, que revierte la
    transacción entera.
  - La conexión sigue `pendiente`.
  - Responde 409 «Esa cuenta ya está conectada a un cliente», sin revelar el dueño.
- Verificación: `tests/test_conectar.py::test_activar_no_mueve_cuentas_de_otro_cliente`
  (cuenta intacta, lote sin cambios, conexión pendiente) y
  `test_reconectar_cuenta_del_mismo_cliente_renueva_token`. El primero falla con el código
  anterior.

### N-1 · /invitar y guardar_usuario reasignaban usuarios en silencio — **hecho**
- Commit: `91089e3`
- Archivos: `backend/api/reportes/repositorio.py`, `backend/api/admin/router_reporte.py`,
  `backend/api/admin/repositorio.py`, `backend/api/admin/router.py`,
  `frontend/src/admin/FichaCliente.tsx`.
- Arreglo:
  - `invitar()` decide en una transacción (`FOR UPDATE`) y devuelve `creado`, `reinvitado`,
    `reactivado`, `pertenece_a_otro_cliente` o `es_equipo`.
  - `/invitar` lo informa por correo, sin revelar el otro cliente, y no envía la invitación a
    los conflictos.
  - `guardar_usuario` solo reactiva si el rol y el cliente coinciden; si no → 409 «Ese correo
    ya pertenece a otro cliente o al equipo».
  - Se eliminó `rol_de`, que quedó sin uso.
- **Decisión de producto [PENDIENTE-HUMANO confirmar]:** invitar de nuevo, desde SU cliente,
  a un usuario desactivado lo reactiva (estado `reactivado`, visible en la ficha). Si se
  prefiere que no, cambiar esa rama en `RepositorioReportes.invitar` para que devuelva
  `desactivado` sin tocar la fila.
- Verificación: `tests/test_usuarios_conflicto.py` (estados del repositorio, endpoint sin
  revelar cliente, guardar_usuario 409 ×2 + reactivación del mismo cliente). Falla con el
  código anterior.

### B-7 / R-2 · Lo editado en el editor tardaba hasta 15 min en verse — **hecho**
- Commit: `fa4bcad`
- Migración nueva: **`sql/015_version_configuracion.sql`**
- Archivos: `backend/api/consulta/{cache,repositorio,router}.py`, `backend/api/deps.py`,
  `backend/api/admin/{router,router_reporte,router_conectar}.py`.
- Verificado en el código: la respuesta cacheada sí depende de la configuración. El
  resolvedor recibe `config` con overrides (`limite`, `objetivo`, `items`), el tema y los
  competidores.
- Arreglo:
  - Fila `config_version` que suben triggers por sentencia en las tablas de configuración.
    La generación pasa a ser «captura ETL | config_version».
  - Los routers del admin vacían la caché de su proceso tras cualquier escritura; `vaciar()`
    también obliga a re-leer la generación.
  - **Opción elegida para el PDF:** las peticiones con token de render se saltan la caché, en
    lectura y en escritura.
- Verificación: `tests/test_cache_config.py` (override visible de inmediato; invalidación
  entre procesos por `config_version`; render sin caché). Falla con el código anterior.

---

## Fase 1 — resto de seguridad

### S-3 · Textos de «solo lectura» contra permisos reales — **hecho (código + texto); confirmación de LinkedIn pendiente-humano**
- Commits: `a3ce0e8`, `c11aea0`
- Archivos: `backend/api/admin/conectar.py`, `frontend/public/terminos/index.html`, `README.md`
  (tabla «Permisos OAuth por red»), `backend/tests/test_conectar.py`.
- Arreglo:
  - Revisado en el código: LinkedIn solo hace GET a `organizationAcls`, `organizations` y a
    las estadísticas y publicaciones. El único POST es el canje del código OAuth.
  - Se mantiene `rw_organization_admin`, con un comentario que explica por qué es
    imprescindible: LinkedIn rechazó `r_organization_admin` para la app.
  - Los Términos §3 nombran `rw_organization_admin` y `business.manage`, y explican que
    técnicamente permiten administrar pero DatIO solo lee.
  - En el README, los permisos de Meta no se listan porque viven en el panel de la app
    (**verificar a mano**).
- Verificación: `test_linkedin_solo_lee` (sin métodos de escritura en el conector; el único
  POST a LinkedIn es `accessToken`).

### N-2 · LINKEDIN_SCOPES aceptaba cualquier permiso — **hecho**
- Commit: `a3ce0e8`
- Arreglo: `LINKEDIN_SCOPES_PERMITIDOS` en `config.py` (`r_organization_social`,
  `r_organization_admin`, `rw_organization_admin`). Cualquier otro valor detiene el arranque.
- Verificación: `test_config.py::test_linkedin_scope_fuera_de_la_lista_blanca_impide_arrancar`
  y `..._dentro_de_la_lista_blanca`.

### S-2 · La API confiaba en el email sin exigir verificación (+ compare_digest del cron) — **hecho**
- Commit: `c8f5635`
- Archivos: `backend/api/auth/supabase.py`, `backend/api/deps.py`, `backend/api/etl/router.py`,
  `backend/tests/conftest.py`.
- Arreglo:
  - `correo_verificado(claims)` acepta si `amr` trae `otp`/`magiclink`/`oauth`, o si
    `email_verified` es true en la raíz o en `user_metadata`. Rechaza `is_anonymous` y el
    resto (p. ej. contraseña sin confirmar) con 401.
  - El cron usa `hmac.compare_digest`.
- **Supuesto a confirmar [PENDIENTE-HUMANO]:** que los tokens reales de Supabase de este
  proyecto traen `amr` con `otp` (enlace mágico) y `oauth` (Google). Es el comportamiento
  documentado de Supabase y la regla acepta cualquiera de las tres señales, pero no se probó
  con un token real porque no se tocó producción. Ver acción humana 4.
- Verificación: `tests/test_correo_verificado.py` (5 aceptados, 6 rechazados, 401 por
  endpoint, cron).

### S-4 · Inyección de fórmulas en el CSV — **hecho**
- Commit: `3ba4059`
- Arreglo: `router_datos.celda_segura` antepone `'` a las celdas de texto que empiezan con
  `= + - @ \t \r`, cabecera incluida. Los números no se tocan.
- Verificación: `test_datos.py::test_csv_neutraliza_formulas_y_respeta_numeros`.

### S-5 · El token de render valía para toda la API — **hecho**
- Commit: `9dc66df`
- Arreglo:
  - `usuario_actual` ya no acepta el token de render.
  - `usuario_o_render` lo acepta solo en `GET /reportes/{slug}`
    (`instancia_autorizada_impresion`) y en `POST /consulta`.
  - `autorizar_instancia` exige que la instancia del token sea la pedida.
  - Playwright ya no registra visitas.
- Verificación:
  - `test_acceso.py::test_token_de_render_atado_a_su_instancia`.
  - `test_pdf.py::test_endpoint_pdf_devuelve_archivo`: `/yo`, `/mi/cuentas`, el PDF y
    `/admin` responden 401 con el token de render.

### S-6 · X-Forwarded-Host decidía el redirect_uri de OAuth — **hecho**
- Commit: `6ff0f1d`
- Arreglo:
  - Se borró la heurística. Si `API_URL` está en localhost y la petición llega por un
    dominio público, responde 503 con un mensaje claro.
  - Con `AMBIENTE` = `produccion` o `production`, `API_URL`, `FRONTEND_URL` y
    `ORIGENES_PERMITIDOS` deben ser https o la app no arranca. Cierra también #19.
- Verificación: `test_conectar.py::test_redirect_uri_sale_solo_de_api_url`,
  `test_config.py::test_produccion_exige_https`.
- **Antes de desplegar:** confirmar `API_URL` https y el valor de `AMBIENTE` en Railway
  (acción humana 6).

### S-7 · Bucket público `marcas` aceptaba SVG — **hecho (migración pendiente de aplicar)**
- Commits: `183ab04`, `dccf6c2` (texto de ayuda)
- Migración nueva: **`sql/016_storage_marcas_sin_svg.sql`**. Depende del esquema storage de
  Supabase y CI la excluye. Incluye la consulta para revisar SVG ya subidos.
- Frontend: solo PNG, JPEG o WebP, máximo 5 MB, extensión derivada del MIME y ruta sin el
  nombre del archivo del usuario.
- Verificación: revisión manual en el navegador local (los `accept` de los inputs y el texto
  de ayuda); `tsc` y build.

### B-11 · Errores con detalle interno al usuario — **hecho**
- Commits: `14a8ac3` (PDF), `c8f5635` (auth)
- Arreglo:
  - El PDF responde 502 genérico.
  - Un token inválido responde 401 «Token inválido o vencido», sin nombrar variables de
    configuración.
  - El detalle va al log.
- Se dejaron a propósito con detalle los mensajes de endpoints **solo del equipo**
  (`router_puente`, `router_conectar`): el equipo los necesita para diagnosticar y no llegan
  a clientes.
- Verificación: `test_pdf.py::test_endpoint_pdf_error_de_render_502`,
  `test_correo_verificado.py::test_token_invalido_mensaje_generico`.

---

## Fase 2 — checklist de 20

| # | Estado | Cómo se cerró |
|---|---|---|
| ❌→✅ #12 Bots en el enlace mágico | **hecho (activación pendiente-humano)** | `2f046e0`. Ver detalle abajo |
| ⚠️→✅ #6 Forzar autenticación | hecho | S-1 (`118fac0`), S-2 + compare_digest (`c8f5635`), S-5 (`9dc66df`) |
| ⚠️→✅ #7 IDOR | hecho | `instancia_autorizada` (S-1), B-1 (`b128fe9`), N-1 (`91089e3`) |
| ⚠️→✅ #9 Token/sesión | hecho | S-5 (`9dc66df`) |
| ⚠️→✅ #11 Rate limiting | **hecho (config de Railway pendiente-humano)** | `ac8910b`. Ver abajo |
| ⚠️→✅ #14 Validación de inputs | hecho | `3f0d837` + B-9 en `3ba4059` |
| ⚠️→✅ #15 Sanitizar | hecho | S-4 (`3ba4059`) |
| ⚠️→✅ #16 Restringir archivos | **hecho (migración 016 pendiente de aplicar)** | S-7 (`183ab04`) |
| ⚠️→✅ #20 Dependencias | hecho | `48d0655` (npm), `fd2b604` (lockfiles Python + auditorías en CI) |

### #12 · Protección contra bots en el enlace mágico
- Verificado en el código: `/invitar` solo escribía en `usuarios` y el alta en Supabase Auth
  ocurría en el primer enlace mágico. Por eso `shouldCreateUser:false` exige crear al
  invitado del lado del servidor.
- Arreglo:
  - `api/auth/admin_supabase.asegurar_usuario_auth` crea al usuario con la Admin API
    (`email_confirm: true`, `SUPABASE_SERVICE_ROLE_KEY` solo en Railway). Nunca genera ni
    devuelve enlaces ni tokens.
  - Lo usan `/invitar` (estado `habilitado_sin_auth` si falla) y `POST /admin/usuarios`.
  - `python -m api.auth.sincronizar` da de alta en Auth a los usuarios activos existentes.
  - `Entrar.tsx`: `shouldCreateUser:false` + `captchaToken` de Turnstile
    (`VITE_TURNSTILE_SITE_KEY`; sin clave funciona igual y avisa en consola). La respuesta es
    la misma exista o no el correo.
  - CSP: `script-src`, `frame-src` y `connect-src` para `challenges.cloudflare.com`.
  - Google OAuth no pasa por captcha: Supabase no lo exige en OAuth y Google ya hace su propia
    verificación. Es el único otro formulario de Auth.
- **Orden de despliegue obligatorio:**
  1. Cargar `SUPABASE_SERVICE_ROLE_KEY` en Railway.
  2. Correr `python -m api.auth.sincronizar`.
  3. Recién entonces publicar el frontend.
  4. Al final, activar Captcha en Supabase.

  Si se publica antes, los invitados que nunca entraron no podrán pedir su enlace.
- Verificación: `tests/test_auth_invitados.py` (MockTransport: creado/existente/error/sin
  clave; endpoint sin enlaces ni tokens) y `frontend/src/reporte/Entrar.test.tsx`.

### #11 · Rate limiting
- Arreglo:
  - `ip_cliente` usa `request.client`, sin leer `X-Forwarded-For` crudo. El Dockerfile
    arranca uvicorn con `--proxy-headers --forwarded-allow-ips "*"`.
  - Límites por usuario: PDF 6/min, envío manual 3/min, `/invitar` 10/min.
  - Como mucho 2 Chromium a la vez por proceso.
- Verificación: `test_seguridad.py` (`test_x_forwarded_for_no_salta_el_limite`,
  `test_pdf_limitado_por_usuario`).
- [PENDIENTE-HUMANO] confirmar que Railway usa el CMD del Dockerfile (o poner las mismas
  flags en su «Start Command») y, si publica rangos de IP del proxy, reemplazar `"*"`.

### Textos legales
- **R-3** — hecho (`cda3416`):
  - Política de privacidad §6 nombra Resend (correos y PDF mensual), Cloudflare Turnstile y
    Sentry.
  - §2 los registros de accesos denegados; §3 ya nombraba LinkedIn; §10 suma los términos de
    la API de LinkedIn; §8 el plazo real de borrado de tokens.
  - [PENDIENTE-HUMANO] publicar (deploy de Vercel).
- **AntiSlop 1** — hecho, opción «corregir el texto» (`cda3416`): no hay callback de
  desautorización de Meta. La página dice ahora que el token deja de funcionar al revocar y
  que el borrado se hace a pedido (48 h tras confirmar). Implementar el callback queda como
  mejora opcional.
- **AntiSlop 2** — hecho, opción «registrar» (`118fac0`): cada 403 de un reporte queda en
  el log con correo, instancia pedida y motivo, sin token. La frase de los Términos §2 ahora
  es cierta.

---

## Fase 4 — repo / ops

| Tarea | Estado | Commit | Verificación |
|---|---|---|---|
| **B-2** CI y docker-compose con TODAS las migraciones | hecho (docker-compose sin probar: no hay Docker en esta máquina) | `7a8df8c`, `fd2b604` | `scripts/aplicar_sql.sh` sobre una base nueva + suite completa: 230 pasan y **0 se saltan** (`pytest -rs`) |
| CI: jobs `backend` y `frontend` + auditorías que fallan desde moderada | hecho | `fd2b604` | Comandos del CI corridos a mano en local con las versiones del lock. El workflow en GitHub no se ejecutó (no hay push) |
| **#20** react-router 7.18.5, vite 7.3.8, vitest 4.1.12 | hecho | `48d0655` | `npm audit --audit-level=moderate` → 0; tsc, build, vitest; admin y login revisados en el navegador local |
| **#20** lockfile Python con hashes en Dockerfile y CI | hecho | `fd2b604` | venv limpio 3.12 desde `requirements-dev.lock` → ruff, format, mypy, pytest en verde; `pip-audit` → sin vulnerabilidades. La imagen Docker no se construyó (sin Docker) |
| **R-4** test sin marca `requiere_db` | hecho | `ac8910b` | `env -u DATABASE_URL pytest` → 0 fallos (147 pasan, 83 se saltan) |
| Check obligatorio en `main` | **pendiente-humano** | — | Ver acción humana 9 |
| Dependabot | hecho (activación pendiente-humano) | `fd2b604` | `.github/dependabot.yml` |
| Sentry | hecho (DSN pendiente-humano) | `93baafd` | `test_observabilidad.py`, `observabilidad.test.ts` |
| `.env.example` completos | hecho | `93baafd` | Comparado con `Configuracion.model_fields` (0 faltantes) y con `import.meta.env` |
| Logs sin secretos | hecho | `14a8ac3`, `d86aaa6` | `test_envio_pdf.py::test_falla_interna_registra_motivo_sin_token`, `test_observabilidad.py::test_error_de_conector_no_guarda_tokens` |

Notas:
- Los tests nunca leen `backend/.env` (`7a8df8c`): antes cargaban claves reales al correr
  desde `backend/`, y un test dependía de eso.
- Sentry: `send_default_pii=False`, sin cuerpos de petición, y `before_send` limpia
  Authorization, cookies, `x-cron-secret`, `render`/`token`/`code`/`state`, JWT y correos.
  El fallo de un envío mensual se captura de forma explícita.

---

## Fase 5 — tests que fijan cada arreglo

Todos los tests nuevos de seguridad se corrieron también contra el código anterior y
**fallaron** (comprobado con `git stash` sobre `api/`). Prueban la defensa, sin recetas de
ataque.

| Grupo | Tests |
|---|---|
| B-4 | `test_envio_pdf.py` (decisión del DOM, `validar_pdf`, envío fallido sin correo al cliente + aviso al equipo + reintento, log sin token, caso feliz, envío manual), `test_pdf.py`, `Imprimir.test.tsx` |
| S-1 | `test_acceso.py` (inactivo 403 en las 3 rutas, `usuario_por_email` None, equipo sigue entrando, ajeno 403 registrado, 404) |
| B-1 / N-1 | `test_conectar.py::test_activar_no_mueve_cuentas_de_otro_cliente` / `..._renueva_token`; `test_usuarios_conflicto.py` |
| B-7 | `test_cache_config.py` (override visible de inmediato, invalidación entre procesos, render sin caché) |
| S-2, cron | `test_correo_verificado.py` |
| S-4, B-9 | `test_datos.py` |
| S-5 | `test_acceso.py::test_token_de_render_atado_a_su_instancia`, `test_pdf.py` |
| S-6, N-2 | `test_config.py`, `test_conectar.py` |
| S-3 | `test_conectar.py::test_linkedin_solo_lee` |
| #12 | `test_auth_invitados.py`, `Entrar.test.tsx` |
| #11, R-4 | `test_seguridad.py` |
| #14 | `test_validaciones.py`, `test_estreno.py::test_override_rechaza_metricas_inventadas` |
| Sentry / logs | `test_observabilidad.py`, `observabilidad.test.ts` |

Estado final verificado:
- Backend: `ruff` y `ruff format --check` limpios, `mypy` estricto sin errores, **230 tests
  con base** (ninguno saltado) y 0 fallos sin base. `pip-audit` sin vulnerabilidades.
- Frontend: `tsc`, `vite build`, **4 tests de vitest** y `npm audit --audit-level=moderate`
  en 0.

---

## Fase 3 diferida a pasada 2

No se tocó (solo se hizo el cambio de seguridad o correctitud en las zonas compartidas):
- **Regla de agregación copiada en 4 capas:** CASE `agregacion` en
  `consulta/repositorio.py` ×3 y `datos/repositorio.py`; ramas en `pacing_mes.py`,
  `prediccion/pacing.py`, `disparadores.py`, `detector.py` y `dimensiones.py` (Calidad 1).
- **Partir archivos grandes:** `consulta/repositorio.py` (883 líneas hoy; 877 en la auditoría), `etl/radar.py` (547) y
  `frontend/src/admin/FichaCliente.tsx` (~620, creció un poco por #12 y S-7).
- **God functions:** `correr_alertas` (167 líneas / CC 32), `evaluar_cliente`,
  `linkedin.normalizar` (CC 26) y `narrativa.construir_hechos` (CC 24).
- **OAuth:** reemplazar `if proveedor == ...` por una tabla de proveedores (Calidad 4).
- **`_update_parcial`** (Calidad 7) y los ~263 `dict[str, Any]`.
- **Basura restante:** `conectores/demo.py` y `NORMALIZADORES`.
- **Bugs de ETL B-3, B-5, B-6, B-8 y B-10** (B-9 sí entró por #14).
- Detectado en esta pasada para la pasada 2: `deps.py` concentra auth, autorización de
  instancias, límites y caché. Convendría separarlo cuando se parta `consulta/`.

---

## Consultas de verificación (SOLO LECTURA, editor SQL de Supabase)

Para saber si algún usuario o cuenta ya quedó movido de cliente por B-1/N-1. No se corrieron
contra producción.

```sql
-- Usuarios que vieron reportes de un cliente distinto al que tienen hoy (posible reasignación):
SELECT DISTINCT v.usuario_email, i.cliente_id AS cliente_visto, u.cliente_id AS cliente_actual,
       u.creado_en, u.invitado_en
FROM   reporte_visitas v
JOIN   reporte_instancias i ON i.id = v.instancia_id
JOIN   usuarios u ON u.email = v.usuario_email
WHERE  u.rol = 'cliente' AND u.cliente_id IS DISTINCT FROM i.cliente_id;

-- Usuarios invitados que ya existían antes de la invitación (revisar a mano su cliente):
SELECT email, cliente_id, activo, creado_en, invitado_en
FROM   usuarios
WHERE  rol = 'cliente' AND invitado_en IS NOT NULL AND creado_en < invitado_en - interval '1 minute';

-- Cuentas que aparecen en conexiones OAuth de más de un cliente (posible reasignación por B-1):
SELECT a->>'plataforma' AS plataforma, a->>'id_externo' AS id_externo,
       array_agg(DISTINCT co.cliente_id) AS clientes_que_la_conectaron,
       (SELECT cc.cliente_id FROM cuentas_conectadas cc
         WHERE cc.plataforma = a->>'plataforma' AND cc.id_externo = a->>'id_externo') AS cliente_actual
FROM   conexiones_oauth co, jsonb_array_elements(co.activos) a
GROUP  BY 1, 2
HAVING count(DISTINCT co.cliente_id) > 1;
```

Si aparece algo: devolver cada usuario o cuenta a su cliente correcto a mano, revisar qué vio
y avisar a los clientes afectados según corresponda.

Nota: `reporte_visitas` incluía visitas de `render@datio` (Playwright) hasta S-5. Esas filas
no son personas y la primera consulta las excluye sola (no existe ese usuario).

---

## [PENDIENTE-HUMANO] — paso a paso

Orden sugerido para que todo quede desplegado antes del 1/12:

1. **Revisar y fusionar la rama** `hardening/2026-11-14` (no se hizo push). Abrir PR, revisar
   y fusionar a `main`.
2. **Supabase, migraciones** (editor SQL, en orden): `sql/015_version_configuracion.sql` y
   `sql/016_storage_marcas_sin_svg.sql`. Después correr la consulta de revisión de SVG que
   trae la 016.
3. **Railway** (servicios `DatIO` y `datio-cron`):
   - `SUPABASE_SERVICE_ROLE_KEY` = la service role del proyecto (Supabase → Settings → API).
     Solo en Railway, nunca en Vercel.
   - `SENTRY_DSN` (paso 10), en los dos servicios.
   - Confirmar que `API_URL` es `https://datio-production.up.railway.app`, y que
     `FRONTEND_URL` y todos los `ORIGENES_PERMITIDOS` son https.
   - Confirmar el valor de `AMBIENTE`: con `produccion` se activa la comprobación de https.
   - Confirmar que el servicio `DatIO` arranca con el CMD del Dockerfile (o copiar
     `--proxy-headers --forwarded-allow-ips "*"` al Start Command).
   - `LINKEDIN_SCOPES` vacío, o solo con valores de la lista blanca: si no, la API no
     arranca.
   - Desplegar la API y luego correr una vez en el servicio de la API:
     `python -m api.auth.sincronizar`. Debe terminar sin `error_auth` ni `sin_clave_auth`.
4. **Supabase Auth:**
   - Confirmar que el registro con contraseña está desactivado y que «Confirm email» está
     activo (S-2).
   - Decodificar un token real (enlace mágico y Google) y confirmar que trae
     `amr: [{method: "otp"}]` / `"oauth"`.
   - Recién después del paso 5, activar Captcha protection con el secret de Turnstile.
5. **Cloudflare Turnstile:** crear el sitio para `dat-io.vercel.app`. Site key → Vercel
   (`VITE_TURNSTILE_SITE_KEY`); secret → Supabase (paso 4).
6. **Vercel:** publicar el frontend (CSP, Turnstile, Sentry y los textos legales) **después**
   del paso 3 (sincronizar).
7. **Antes del 1/12 (obligatorio):**
   - Con todo desplegado, usar «Enviar ahora» en la ficha de un cliente real, a un correo
     del equipo.
   - Validar a mano el PDF: todas las páginas, sin mensajes de error, cifras del mes
     correcto y ediciones del editor visibles.
   - Provocar un fallo controlado (en staging, o con un cliente de prueba sin cuentas) y
     confirmar que llega el aviso «[DatIO] No se envió…» al equipo y nada al cliente.
   - **Si algo falla o el Bloque 0 no está desplegado: dejar `RESEND_API_KEY` vacía en
     `datio-cron` hasta resolverlo y enviar a mano.**
8. **LinkedIn Developer Portal:** revisar qué productos y permisos tiene aprobados la app.
   Pedir `r_organization_admin` si está disponible y, si se aprueba, reemplazar
   `rw_organization_admin` en `SCOPES_LINKEDIN`. Si no, dejar constancia de por qué se
   mantiene.
9. **GitHub:**
   - Settings → Code security → activar Dependabot (el archivo ya está).
   - Settings → Rules (o Branches) → `main`: requerir PR, requerir los checks `backend` y
     `frontend` en verde y bloquear force-push. Equivalente:
     ```bash
     gh api -X PUT repos/luispalaciosec/DatIO/branches/main/protection \
       -H "Accept: application/vnd.github+json" \
       -f "required_status_checks[strict]=true" \
       -f "required_status_checks[contexts][]=backend" \
       -f "required_status_checks[contexts][]=frontend" \
       -F "enforce_admins=false" \
       -F "required_pull_request_reviews[required_approving_review_count]=0" \
       -F "restrictions=null" \
       -F "allow_force_pushes=false" -F "allow_deletions=false"
     ```
10. **Sentry:** crear el proyecto (plan gratis), un DSN para Python y otro para React.
    `SENTRY_DSN` en Railway (API y cron) y `VITE_SENTRY_DSN` en Vercel.
11. **Resend:** verificar el dominio emisor (SPF/DKIM).
12. **Meta / Google:** con los textos corregidos, revisar que las App Reviews declaren los
    mismos permisos (incluido `business.manage`) y la URL de eliminación de datos.
13. **Confirmar la regla de N-1:** invitar de nuevo, desde su cliente, a un usuario
    desactivado lo reactiva (estado `reactivado`). Si no se quiere, ver la nota en N-1.
14. **Consultas de verificación** de arriba en el editor SQL. Si aparece algo, corregir a
    mano y avisar.

Rotación de secretos: la auditoría no encontró secretos versionados y esta pasada no
introdujo ninguno. No hay rotación obligatoria.

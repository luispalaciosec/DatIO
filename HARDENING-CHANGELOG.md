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

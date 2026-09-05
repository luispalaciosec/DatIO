# Instrucciones del proyecto

Plataforma propia de reportería de redes sociales y pauta para Geeks Ecuador,
en reemplazo de Supermetrics + Looker Studio. Construida por Stack-Studio.

## Antes de escribir cualquier código

1. Leer `README.md` completo, **incluida la sección ERRATA**. La errata manda sobre
   el texto de los documentos de `spec/`.
2. Leer `spec/06-paquetes-de-trabajo.md` e identificar qué PT estás ejecutando.
3. Leer `sql/001_schema_inicial.sql`. Es la fuente única de verdad del esquema.
4. Leer únicamente los documentos de `spec/` que tu PT referencia. No cargues todo.

## Reglas duras

- **No edites `sql/001_schema_inicial.sql`.** Si necesitas un cambio de esquema,
  crea `sql/0NN_<descripcion>.sql` y documéntalo en el PR.
- **No cambies un contrato** de la tabla de contratos de `spec/06` sin preguntar.
  Detente y consulta.
- **No inventes métricas.** Toda métrica debe existir en `dim_metrica`. Si falta,
  agrégala al seed de PT-02, no la escribas literal en el código.
- **Nunca `cliente_id` desde el request.** Se deriva del token, en el servidor.
- **Nunca credenciales en el código.** Variables de entorno o `credencial_cifrada`.
- **Guardar raw antes de normalizar**, siempre.
- **Ventana de re-sync de 28 días** en todo conector.

## Convenciones

- Nombres de dominio en **español**: tablas, columnas, variables de negocio,
  mensajes de commit y comentarios. El código de framework queda en inglés.
- Python: ruff + mypy estricto. Tipos en todas las firmas públicas.
- Async por defecto en la API y en los conectores.
- Sin SQL crudo fuera de la capa de repositorio.
- Commits atómicos con el código del PT: `PT-04: conector GA4 con re-sync de 28 días`

## Tests

Un PT no está cerrado sin tests. Mínimo: camino feliz + un caso de error.
Los conectores se testean con fixtures de payload, nunca llamando a la API real.
Test obligatorio de aislamiento: intentar leer data de otro cliente debe dar 403.

## Cuando algo no esté en la spec

Decide con criterio, implementa la opción más simple que funcione, y **documenta la
decisión en el PR**. No agregues dependencias pesadas ni abstracciones especulativas
para casos que la spec no pide.

## Contexto de negocio útil

- ~40 clientes, 5 redes por cliente. Volumen: ~5M filas/año. Postgres sobra.
- El usuario final es el gerente de marketing del cliente, no un analista de datos.
- La reportería se consulta en horario de oficina. No requiere alta disponibilidad.
- Los pilares de marca son **crecimiento** y **automatización**: si una feature no
  hace crecer al cliente/a Geeks ni elimina horas-persona, no debería estar aquí.

## LLM: reglas de uso

- **Nunca hardcodear un modelo.** Todo pasa por `api/llm/router.py`, que resuelve
  proveedor y modelo desde configuración. Ver `spec/07-infraestructura-costos.md` §5.
- Usar **LiteLLM** como capa de abstracción. Una sola interfaz para todos.
- Registrar cada llamada en `llm_uso` (tarea, modelo, tokens, costo, latencia)
  desde el primer día. Sin ese registro no se puede comparar proveedores con datos
  propios.
- La clasificación corre por **Batch API** (no es urgente, cuesta la mitad).
- Clientes del sector financiero: forzar proveedor occidental por residencia de datos.
- El LLM **nunca** genera cifras. Solo explica cifras ya calculadas, y toda cifra
  en su salida se valida contra los datos de entrada antes de publicar.

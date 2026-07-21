# LeadX — estado actual y próximos pasos

Última actualización material: 2026-07-21, America/Argentina/Cordoba.

Este archivo es el worklog operativo principal de LeadX. Cualquier agente debe leerlo primero y luego verificar HEAD remoto, PR, CI, Cloudflare y producción antes de escribir o desplegar. `CONTEXTO LEADX` en Google Drive es el resumen ejecutivo y respaldo histórico; no reemplaza esta fuente operativa.

## Estado ejecutivo

```text
PROJECT=LeadX
STATUS=P0_INGEST_SAFETY_RUNNER_PREFLIGHT_PENDING
PRODUCTION_FIX_ACTIVE=NO
DEPLOY_PENDING=YES
MAIN_SHA=91672001c893815a1f31f9cfdd11b31a18a6968a
WORKING_BRANCH=fix/ingest-vertical-safety-v1
PR=19
PR_STATE=DRAFT_OPEN
RUNTIME_CODE_SHA=0bbf00c70c5adf7e919233257e52671f7be86c4a
RUNNER_CODE_SHA=77c2c43298418dc6e27b433f36617a790e87e580
CURRENT_PR_HEAD=VERIFY_REMOTE_BEFORE_ACTION
INGEST_CI_RUN_ID=29810596593
INGEST_CI_CONCLUSION=success
WORKERS_FIRST_CI_RUN_ID=29810596600
WORKERS_FIRST_CI_CONCLUSION=success
SESSION_POLICY=20_MIN_IDLE_8_HOURS_ABSOLUTE
PRODUCTION_ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
PRODUCTION_TRAFFIC=100
RELEASE_ATTEMPTS=2
RELEASE_RESULT=ROLLED_BACK
BROWSER_SMOKE=NOT_APPROVED
BROWSER_RUNNER_PATCH=IMPLEMENTED_STATICALLY_VALIDATED
BROWSER_PREFLIGHT_ON_OPERATOR_MACHINE=NOT_EXECUTED
DEPLOY_EXECUTED_AFTER_RUNNER_PATCH=NO
```

Los commits posteriores a `RUNTIME_CODE_SHA` incluyen documentación y la corrección del operador/browser runner. Antes de cualquier operación, resolver el HEAD remoto actual del PR y revisar el diff desde `RUNTIME_CODE_SHA`.

## Último hito funcional

Se corrigió el riesgo P0 de reemplazo destructivo de `leads:live`.

Causa confirmada:

- el radar enviaba `/api/ingest` sin `mode` ni `vertical`;
- el backend interpretaba la ausencia de modo como `replace_all`;
- un batch válido de cinco o más leads podía reemplazar ambas verticales;
- IDs coincidentes podían desplazar registros de la otra vertical.

Política implementada en el candidato:

- `replace_all` no es un modo runtime aceptado;
- ambos endpoints de escritura exigen `mode=upsert_vertical`;
- `/api/ingest` sólo acepta `vertical=fotomultas`;
- `/api/admin/import` acepta `fotomultas` o `repuestos_agricolas` con sesión válida;
- una colisión de ID entre verticales devuelve HTTP 409 antes de escribir;
- la vertical no objetivo y el estado CRM existente se preservan;
- no existe eliminación implícita;
- un eventual snapshot destructivo debe diseñarse como `replace_vertical`, nunca como reemplazo global.

Archivos principales del fix:

- `worker/data-handlers.mjs`
- `.github/workflows/radar-cron.yml`
- `web/scripts/security-runtime-tests.mjs`
- `.github/workflows/ingest-vertical-safety-ci.yml`
- `docs/api-inventory.md`

## Rotación de credencial completada

```text
DASHBOARD_PASSWORD_ROTATION=COMPLETED
NEW_PASSWORD_LOGIN=PASS
OLD_PASSWORD_REJECTED=PASS
GITHUB_ACTIONS_SECRET_UPDATED=YES
SECRET_VALUES_DOCUMENTED=NO
PRODUCTION_AUTH_STATE=VERIFIED
```

La rotación se realizó desde Cloudflare y fue desplegada desde el panel. Después se verificó en una sesión de incógnito que la contraseña nueva funciona y que la anterior es rechazada. El secret homónimo de GitHub Actions fue actualizado. No registrar ningún valor en código, documentación, logs ni artefactos.

Las versiones de secreto creadas durante el incidente anterior continúan como evidencia histórica no promovida:

```text
UNTRUSTED_SECRET_VERSION=9f549e89-40f7-4b3d-9552-5e438cdcead3
CORRECTED_SECRET_VERSION=0d24cd66-7a34-485e-9e0c-f52fbd44fabc
PROMOTED_DIRECTLY=NO
```

## Evidencia CI del fix y del runner

### Ingest Vertical Safety

```text
WORKFLOW=LeadX Ingest Vertical Safety CI
RUN_ID=29810596593
CONCLUSION=success
HEAD_VALIDATED=77c2c43298418dc6e27b433f36617a790e87e580
SOURCE_CONTRACT=PASS
BUILD=PASS
INGEST_RUNTIME_TESTS=PASS
COMPLETE_TEST_SUITE=PASS
TYPECHECK=PASS
DOCUMENTATION_CONTRACT=PASS
```

### Workers-first Pipeline

```text
WORKFLOW=LeadX Workers-first Pipeline CI
RUN_ID=29810596600
CONCLUSION=success
HEAD_VALIDATED=77c2c43298418dc6e27b433f36617a790e87e580
SHELL_AND_WORKFLOW_SYNTAX=PASS
WORKERS_FIRST_CONTAINMENT=PASS
BUILD_TESTS_TYPECHECK=PASS
WRANGLER_DRY_RUN=PASS
PRODUCTION_ACCESS=NO
DEPLOY_ATTEMPTED=NO
```

La CI de contención de rama quedó `skipped`; no se cuenta como PASS.

## Corrección del browser runner

Archivos:

- `scripts/deploy-workers-first.sh`
- `web/scripts/production-smoke.spec.mjs`
- `web/scripts/run-browser-smoke.mjs`
- `web/scripts/browser-runner-preflight.mjs`

Cambios implementados:

1. Se eliminó `playwright install --with-deps chromium` del release.
2. Se detecta un Chromium, Chrome o Edge ya instalado.
3. Se ejecuta un preflight real del navegador antes de cualquier acceso o despliegue en Cloudflare.
4. Existe modo `LEADX_BROWSER_PREFLIGHT_ONLY=1`, que termina sin deploy y sin exigir secretos de Cloudflare.
5. El runner emite `START`, heartbeat periódico, resultado y tiempo transcurrido.
6. Se aplican timeout por test, timeout global y hard timeout externo.
7. Un bloqueo del proceso termina con código específico `86` y estado `BROWSER_RUNNER_BLOCKED`.
8. En Windows se termina el árbol de procesos mediante `taskkill`; en POSIX se termina el grupo de procesos.
9. `browser.log` recibe salida desde el inicio.
10. El smoke dejó de depender de `networkidle`; usa `domcontentloaded` y espera contratos concretos de UI.
11. Cada fase desktop, mobile y autenticada produce progreso visible.
12. Las capturas quedan dentro del artefacto del release.
13. Wrangler rollback utiliza `--message`, que omite los prompts de confirmación y mensaje según la documentación vigente de Wrangler.
14. Se diferencia un runner bloqueado de una falla funcional del smoke.

Validación ejecutada fuera de producción:

```text
BASH_SYNTAX=PASS
NODE_CHECK_RUNNER=PASS
NODE_CHECK_PREFLIGHT=PASS
NODE_CHECK_PRODUCTION_SPEC=PASS
WATCHDOG_PASS_PATH=PASS
WATCHDOG_FORCED_HANG_EXIT_CODE_86=PASS
GITHUB_WORKERS_FIRST_CI=PASS
GITHUB_INGEST_CI=PASS
REAL_BROWSER_PREFLIGHT_ON_WINDOWS=NOT_EXECUTED
PRODUCTION_DEPLOY_AFTER_PATCH=NO
```

## Intentos Workers-first del 2026-07-20

### Intento 1

```text
SOURCE_SHA=9aefc804abca9bc0d11e3a2eecefbf932863e6f5
CANDIDATE_VERSION=c0f97ab8-7101-44c4-840a-d8e652683639
TRAFFIC_REACHED=100
BUILD_TESTS_TYPECHECK=PASS
FAILURE=PLAYWRIGHT_CHROMIUM_DOWNLOAD_TIMEOUT
ROLLBACK_TARGET=3f605427-a8d0-45f8-af04-e62d1f28dac3
ROLLBACK=COMPLETED_AND_HEALTH_CHECKED
```

### Intento 2

```text
SOURCE_SHA=9aefc804abca9bc0d11e3a2eecefbf932863e6f5
CANDIDATE_VERSION=b097ee3c-79d8-4c7d-9d60-da0552c9d571
TRAFFIC_REACHED=100
BUILD_TESTS_TYPECHECK=PASS
HTTP_AUTHENTICATED_READBACK=EXECUTED_BEFORE_BROWSER_STAGE
FAILURE=PLAYWRIGHT_TEST_HUNG_WITH_EMPTY_BROWSER_LOG
ROLLBACK_TARGET=3f605427-a8d0-45f8-af04-e62d1f28dac3
ROLLBACK=COMPLETED_AND_HEALTH_CHECKED
```

No hubo evidencia de defecto funcional del producto, pero tampoco existe browser smoke aprobado. No ejecutar un tercer deploy sin completar primero el nuevo preflight local.

## Producción vigente

```text
PRODUCTION_URL=https://leadx.simondalmasso44.workers.dev
ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
ACTIVE_TRAFFIC=100
HEALTH_AFTER_ROLLBACK=PASS
AUTH_WITH_ROTATED_PASSWORD=PASS
OLD_PASSWORD_REJECTED=PASS
FOTOMULTAS_REAL_COUNT_LAST_VERIFIED=9
REPUESTOS_AGRICOLAS_REAL_COUNT_LAST_VERIFIED=40
CROSS_VERTICAL_ID_OVERLAP_LAST_VERIFIED=0
PR19_FIX_ACTIVE=NO
PRODUCTION_DATA_CHANGED_FOR_PR19=NO_EVIDENCE
```

Hasta que PR #19 sea desplegado y reconciliado:

> NO ejecutar manualmente `.github/workflows/radar-cron.yml`.

El workflow permanece manual, pero el Worker productivo todavía conserva la semántica antigua de ingestión.

## Decisiones vigentes

1. Cloudflare Workers es la primera autoridad de despliegue. GitHub se reconcilia después con el source exacto ya desplegado.
2. `docs/CURRENT_STATE.md` es el worklog operativo principal. Drive es resumen ejecutivo y respaldo externo.
3. No mergear PR #19 antes de desplegar y validar en Cloudflare el HEAD exacto del PR.
4. No confundir build/tests exitosos ni 100 % de tráfico con release aprobado.
5. No publicar leads reales, cookies, tokens, contraseñas ni valores secretos.
6. La importación manual privada usa exclusivamente `POST /api/admin/import` con `mode=upsert_vertical`.
7. El rollback de código no revierte KV; una reversión a una versión anterior puede cambiar secretos versionados y debe verificarse.
8. Health/readiness con sentinel separado sigue pendiente y no forma parte de PR #19.
9. Browser Enrichment V1 queda preservado como iniciativa futura separada; no se incorpora a PR #19.
10. No ejecutar un release hasta que el modo preflight-only pase en la máquina operadora.

## Bloqueo operativo actual

La corrección de código del runner está implementada y pasó validaciones estáticas/CI. Falta validar el lanzamiento real del navegador instalado en la misma máquina Windows desde la que se ejecutará el release.

Esto no es un deploy y no requiere contraseñas ni tokens de Cloudflare.

## Próximo paso exacto

En el checkout limpio de `fix/ingest-vertical-safety-v1`, actualizado al HEAD remoto vigente, ejecutar desde PowerShell con Git Bash disponible:

```powershell
$env:LEADX_BROWSER_PREFLIGHT_ONLY="1"
bash scripts/deploy-workers-first.sh
```

Resultado obligatorio:

```text
BROWSER_RUNNER_PREFLIGHT=PASS
DEPLOY_ATTEMPTED=NO
PRODUCTION_CHANGED=NO
ROLLBACK_EXECUTED=NO
```

Si devuelve `BROWSER_RUNNER_BLOCKED` o cualquier otro error, no desplegar: conservar `browser-preflight.log`, identificar la primera causa y corregirla.

Sólo después de ese PASS:

1. actualizar este worklog con la evidencia del preflight;
2. congelar el HEAD exacto;
3. ejecutar un único release Workers-first;
4. exigir una sola versión al 100 %, health, login, 9 Fotomultas, 40 agrícolas, cero solapamiento, logout, desktop/mobile, `pageerror=0`, requests accionables 0 y overflow 0;
5. registrar deployment ID, version ID, bundle SHA y rollback;
6. mergear PR #19 conservando el source exacto desplegado;
7. ejecutar `LeadX Workers-first Reconciliation`;
8. actualizar este archivo y `CONTEXTO LEADX`;
9. reactivar el radar manual sólo cuando el fix esté activo.

## Siguiente frente, después de PR #19

Diseñar y aprobar por separado:

- `/api/health` como liveness;
- `/api/readiness` con sentinel KV persistente y valor esperado exacto;
- data-freshness y smokes funcionales separados de readiness;
- múltiples intentos antes de rollback para evitar rollback por un fallo transitorio;
- `BROWSER_ENRICHMENT_V1` con `puppeteer-core` y navegador remoto o controlado, sin integrar dependencias abandonadas.

No reutilizar el experimento anterior que leía `leads:live` como dependencia de health.

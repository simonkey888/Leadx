# LeadX — estado operativo

Actualizado: 2026-07-21 · America/Argentina/Cordoba.

Este archivo es la fuente operativa principal. Verificar siempre HEAD remoto, PR, CI, Cloudflare y producción antes de actuar. Drive es resumen ejecutivo y respaldo histórico.

## Estado

```text
PROJECT=LeadX
STATUS=P0_INGEST_SAFETY_REMOTE_PREFLIGHT_PASS_RELEASE_OPERATOR_PENDING
MAIN_SHA=91672001c893815a1f31f9cfdd11b31a18a6968a
BRANCH=fix/ingest-vertical-safety-v1
PR=19
PR_STATE=DRAFT_OPEN
RUNTIME_CODE_SHA=0bbf00c70c5adf7e919233257e52671f7be86c4a
RUNNER_CODE_SHA=77c2c43298418dc6e27b433f36617a790e87e580
CURRENT_PR_HEAD=VERIFY_REMOTE_BEFORE_ACTION
PRODUCTION_FIX_ACTIVE=NO
DEPLOY_PENDING=YES
ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
ACTIVE_TRAFFIC=100
BROWSER_PREFLIGHT_GITHUB_ACTIONS=PASS
LOCAL_WINDOWS_CHECKOUT=NOT_REQUIRED
BROWSER_SMOKE_PRODUCTIVE=NOT_APPROVED
DEPLOY_AFTER_RUNNER_PATCH=NO
RADAR_MANUAL_DISPATCH=PAUSED
```

## Fix P0 de ingestión

Causa confirmada: `/api/ingest` podía llegar sin `mode` ni `vertical`; el backend interpretaba ese caso como reemplazo global y podía afectar ambas verticales.

El candidato:

- exige `mode=upsert_vertical`;
- limita `/api/ingest` a Fotomultas;
- mantiene `/api/admin/import` para ambas verticales con sesión válida;
- devuelve HTTP 409 ante colisiones entre verticales antes de escribir;
- preserva la vertical no objetivo y el estado CRM;
- elimina el borrado implícito.

Archivos principales:

- `worker/data-handlers.mjs`
- `.github/workflows/radar-cron.yml`
- `web/scripts/security-runtime-tests.mjs`
- `.github/workflows/ingest-vertical-safety-ci.yml`
- `docs/api-inventory.md`

## Acceso operativo

```text
ACCESS_ROTATION=COMPLETED
NEW_ACCESS=PASS
PREVIOUS_ACCESS=REJECTED
ACTIONS_CONFIGURATION=UPDATED
VALUES_DOCUMENTED=NO
```

## CI vigente

```text
INGEST_WORKFLOW=LeadX Ingest Vertical Safety CI
INGEST_RUN_ID=29811985576
INGEST_CONCLUSION=success
PIPELINE_WORKFLOW=LeadX Workers-first Pipeline CI
PIPELINE_RUN_ID=29811985551
PIPELINE_CONCLUSION=success
HEAD_VALIDATED=40ceaf03de3ef9d3ea610c7d9510d66fa5f831a5
BUILD=PASS
TESTS=PASS
TYPECHECK=PASS
SHELL_SYNTAX=PASS
WORKFLOW_SYNTAX=PASS
WORKERS_FIRST_CONTAINMENT=PASS
CHROMIUM_LAUNCH=PASS
LOCAL_DATA_PAGE_RENDER=PASS
BROWSER_PREFLIGHT=PASS
WRANGLER_DRY_RUN=PASS
PRODUCTION_ACCESS=NO
DEPLOY_EXECUTED=NO
```

Branch Containment CI quedó `skipped`; no se cuenta como PASS.

## Corrección del runner

Archivos:

- `scripts/deploy-workers-first.sh`
- `web/scripts/production-smoke.spec.mjs`
- `web/scripts/run-browser-smoke.mjs`
- `web/scripts/browser-runner-preflight.mjs`
- `.github/workflows/workers-first-pipeline-ci.yml`

Resultado:

- el release ya no descarga Chromium;
- hay preflight antes de cualquier operación productiva;
- hay progreso, heartbeat y timeouts;
- un bloqueo termina con código 86 y `BROWSER_RUNNER_BLOCKED`;
- se termina el árbol completo de procesos;
- `browser.log` recibe salida desde el inicio;
- el smoke usa `domcontentloaded` y contratos concretos de UI;
- desktop, mobile y sesión autenticada reportan fases visibles;
- el rollback es no interactivo;
- GitHub Actions lanzó Chromium y renderizó una página local sin acceder a producción.

## Producción

```text
PRODUCTION_URL=https://leadx.simondalmasso44.workers.dev
ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
ACTIVE_TRAFFIC=100
HEALTH_AFTER_ROLLBACK=PASS
ROTATED_ACCESS=PASS
FOTOMULTAS_LAST_VERIFIED=9
AGRO_LAST_VERIFIED=40
CROSS_VERTICAL_ID_OVERLAP=0
PR19_FIX_ACTIVE=NO
```

Hubo dos releases anteriores revertidos por problemas del runner. No se detectó un defecto funcional del producto. No ejecutar otro deploy hasta definir y autorizar un operador que no dependa de una carpeta local.

No ejecutar manualmente `.github/workflows/radar-cron.yml` mientras el fix no esté activo.

## Decisiones

1. Cloudflare Workers sigue siendo la primera autoridad de despliegue.
2. No mergear PR #19 antes de validar en producción su HEAD exacto.
3. CI exitoso no equivale a deploy exitoso.
4. Un rollback de código no revierte KV.
5. Health/readiness queda fuera de PR #19.
6. Browser Enrichment V1 queda para una fase separada.
7. El usuario no mantendrá un checkout local. No exigir carpetas ni comandos locales.
8. Cambiar el operador del release a GitHub Actions requiere autorización explícita.

## Próximo paso exacto

No hay ninguna acción local para el usuario.

1. Autorizar explícitamente un workflow manual sin `push` ni `schedule`.
2. Validarlo sin producción.
3. Congelar el HEAD exacto.
4. Ejecutar un único release Workers-first sólo con autorización de deploy.
5. Validar versión única al 100 %, health, acceso, 9 Fotomultas, 40 agrícolas, cero solapamiento, logout, desktop/mobile, `pageerror=0`, requests accionables 0 y overflow 0.
6. Registrar deployment ID, version ID, bundle SHA y rollback.
7. Mergear PR #19, reconciliar `main`, actualizar GitHub y Drive.
8. Reactivar el radar sólo cuando el fix esté activo.

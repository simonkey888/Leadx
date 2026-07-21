# LeadX — estado operativo

Actualizado: 2026-07-21 · America/Argentina/Cordoba.

Este archivo es la fuente operativa principal. Verificar siempre HEAD remoto, PR, Cloudflare, CI y producción antes de actuar. Drive es resumen ejecutivo y respaldo histórico.

## Estado

```text
PROJECT=LeadX
STATUS=P0_INGEST_SAFETY_CLOUDFLARE_CANDIDATE_PENDING
MAIN_SHA=91672001c893815a1f31f9cfdd11b31a18a6968a
BRANCH=fix/ingest-vertical-safety-v1
PR=19
PR_STATE=DRAFT_OPEN
RUNTIME_CODE_SHA=0bbf00c70c5adf7e919233257e52671f7be86c4a
CURRENT_PR_HEAD=VERIFY_REMOTE_BEFORE_ACTION
PRODUCTION_FIX_ACTIVE=NO
DEPLOY_PENDING=YES
ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
ACTIVE_TRAFFIC=100
BROWSER_PREFLIGHT_GITHUB_ACTIONS=PASS_SUPPORTING_EVIDENCE_ONLY
BROWSER_SMOKE_PRODUCTIVE=NOT_APPROVED
DEPLOY_AFTER_RUNNER_PATCH=NO
RADAR_MANUAL_DISPATCH=PAUSED
```

## Arquitectura canónica de release

```text
RELEASE_MODEL=CLOUDFLARE_FIRST_WORKERS_FIRST
RELEASE_OPERATOR=CLOUDFLARE
GITHUB_ROLE=SOURCE_HISTORY_AND_POST_RELEASE_EVIDENCE
GITHUB_ACTIONS_DEPLOY_OPERATOR=NO
LOCAL_CHECKOUT_REQUIRED=NO
```

Flujo obligatorio:

1. GitHub conserva el código fuente, la rama, el PR y el historial.
2. Se congela el HEAD exacto que se quiere validar.
3. Cloudflare toma ese source exacto.
4. Cloudflare instala dependencias de forma frozen.
5. Cloudflare construye el Worker y los assets.
6. Cloudflare crea una preview o versión candidata sin promoverla todavía.
7. Sobre esa candidata se validan Worker, bindings, KV, cron, APIs, UI desktop/mobile, autenticación y logs.
8. Sólo con todos los gates aprobados se promueve esa misma versión a producción.
9. Después de la promoción se repiten los smokes productivos críticos.
10. Finalmente se registra en GitHub el SHA exacto, version ID, deployment ID, bundle, smokes, tráfico, rollback y estado real.
11. Drive se actualiza sólo por tratarse de un hito material.

GitHub Actions puede aportar CI y evidencia previa, pero no reemplaza a Cloudflare como operador del release ni convierte un CI exitoso en un deploy aprobado.

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

## CI y evidencia previa

```text
INGEST_WORKFLOW=LeadX Ingest Vertical Safety CI
INGEST_RUN_ID=29812348402
INGEST_CONCLUSION=success
PIPELINE_WORKFLOW=LeadX Workers-first Pipeline CI
PIPELINE_RUN_ID=29812348417
PIPELINE_CONCLUSION=success
HEAD_VALIDATED=b0de0971ab0edd5236c905f8f5197c81318c79ac
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

Esta evidencia demuestra que el source y el runner son candidatos válidos para pasar a la etapa Cloudflare. No demuestra que una candidata de Cloudflare haya sido construida, validada o promovida.

Branch Containment CI quedó `skipped`; no se cuenta como PASS.

## Corrección del runner

Archivos:

- `scripts/deploy-workers-first.sh`
- `web/scripts/production-smoke.spec.mjs`
- `web/scripts/run-browser-smoke.mjs`
- `web/scripts/browser-runner-preflight.mjs`
- `.github/workflows/workers-first-pipeline-ci.yml`

Resultado:

- el release ya no descarga Chromium durante el smoke;
- hay progreso, heartbeat y timeouts;
- un bloqueo termina con código 86 y `BROWSER_RUNNER_BLOCKED`;
- se termina el árbol completo de procesos;
- `browser.log` recibe salida desde el inicio;
- el smoke usa `domcontentloaded` y contratos concretos de UI;
- desktop, mobile y sesión autenticada reportan fases visibles;
- el rollback es no interactivo;
- GitHub Actions lanzó Chromium y renderizó una página local como validación auxiliar, sin acceder a producción.

## Producción vigente

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

Hubo dos versiones candidatas anteriores promovidas y luego revertidas por fallos del runner de navegador:

```text
ATTEMPT_1_VERSION=c0f97ab8-7101-44c4-840a-d8e652683639
ATTEMPT_1_RESULT=ROLLED_BACK
ATTEMPT_2_VERSION=b097ee3c-79d8-4c7d-9d60-da0552c9d571
ATTEMPT_2_RESULT=ROLLED_BACK
ROLLBACK_TARGET=3f605427-a8d0-45f8-af04-e62d1f28dac3
```

No se detectó un defecto funcional del producto, pero no existe browser smoke productivo aprobado para el fix.

No ejecutar manualmente `.github/workflows/radar-cron.yml` mientras el fix no esté activo.

## Gates obligatorios para la próxima candidata

Antes de promover:

- source SHA exacto congelado;
- instalación frozen completada;
- build de Cloudflare completado;
- Worker y bindings correctos;
- namespace y acceso KV correctos;
- cron configurado pero sin disparo manual;
- APIs y health correctos;
- login válido y acceso anterior rechazado;
- 9 Fotomultas;
- 40 Repuestos agrícolas;
- IDs únicos y cero solapamiento;
- desktop y mobile;
- logout y regreso a demo;
- `pageerror=0`;
- requests accionables fallidas = 0;
- overflow horizontal = 0;
- logs sin errores causales;
- rollback preparado contra la versión activa previa.

Después de promover:

- una sola versión activa al 100 %;
- health productivo PASS;
- login y sesión PASS;
- conteos y contención PASS;
- browser smoke productivo desktop/mobile PASS;
- version ID, deployment ID, SHA y bundle registrados;
- rollback ejecutado sólo si algún gate productivo falla.

## Decisiones vigentes

1. Cloudflare es el operador del release y la primera autoridad de producción.
2. GitHub conserva source e historial y recibe la evidencia posterior al release.
3. No crear un workflow de GitHub Actions que reemplace a Cloudflare como operador de deploy.
4. No mergear PR #19 antes de validar en producción el HEAD exacto.
5. CI exitoso no equivale a candidata Cloudflare validada ni a deploy exitoso.
6. Un rollback de código no revierte KV.
7. Health/readiness queda fuera de PR #19.
8. Browser Enrichment V1 queda para una fase separada.
9. No exigir carpetas ni comandos locales al usuario.

## Próximo paso exacto

```text
NEXT_EXACT_ACTION=CREATE_AND_VALIDATE_CLOUDFLARE_CANDIDATE_FROM_EXACT_PR19_HEAD_WITHOUT_PROMOTION
```

Secuencia:

1. Verificar y congelar el HEAD remoto actual de PR #19.
2. Hacer que Cloudflare tome ese source exacto.
3. Ejecutar instalación frozen y build en Cloudflare.
4. Crear preview o versión candidata sin promoción productiva.
5. Validar todos los gates de Worker, bindings, KV, cron, APIs, UI y logs.
6. Sólo si todos pasan, solicitar o ejecutar la promoción autorizada de esa misma candidata.
7. Revalidar producción y recién después mergear, reconciliar `main` y actualizar GitHub/Drive.

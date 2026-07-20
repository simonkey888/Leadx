# LeadX — estado actual y próximos pasos

Última actualización material: 2026-07-20, America/Argentina/Cordoba.

Este archivo es el punto de entrada corto para retomar LeadX sin releer todo el historial. La fuente de verdad completa sigue siendo `CONTEXTO LEADX` en Google Drive. Antes de escribir o desplegar, verificar siempre el estado externo actual.

## Estado ejecutivo

```text
PROJECT=LeadX
STATUS=P0_INGEST_SAFETY_CANDIDATE_VALIDATED
PRODUCTION_FIX_ACTIVE=NO
DEPLOY_PENDING=YES
MAIN_SHA=91672001c893815a1f31f9cfdd11b31a18a6968a
WORKING_BRANCH=fix/ingest-vertical-safety-v1
PR=19
PR_STATE=DRAFT_OPEN
VALIDATED_CODE_SHA=0bbf00c70c5adf7e919233257e52671f7be86c4a
CI_RUN_ID=29784076923
CI_JOB_ID=88491663089
CI_CONCLUSION=success
SESSION_POLICY=20_MIN_IDLE_8_HOURS_ABSOLUTE
```

La rama puede recibir commits exclusivamente documentales después del SHA de código validado. Para el deploy, resolver y validar el HEAD remoto actual del PR inmediatamente antes de ejecutar el operador Workers-first.

## Último hito

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

Archivos principales del hito:

- `worker/data-handlers.mjs`
- `.github/workflows/radar-cron.yml`
- `web/scripts/security-runtime-tests.mjs`
- `.github/workflows/ingest-vertical-safety-ci.yml`
- `docs/api-inventory.md`

## Evidencia validada

```text
WORKFLOW=LeadX Ingest Vertical Safety CI
RUN_ID=29784076923
JOB_ID=88491663089
SOURCE_CONTRACT=PASS
BUILD=PASS
INGEST_RUNTIME_TESTS=PASS
COMPLETE_TEST_SUITE=PASS
TYPECHECK=PASS
DOCUMENTATION_CONTRACT=PASS
BRANCH_CONTAINMENT_CI=SKIPPED_NOT_COUNTED_AS_PASS
```

## Producción vigente

La producción todavía ejecuta el código anterior al fix.

```text
PRODUCTION_URL=https://leadx.simondalmasso44.workers.dev
FOTOMULTAS_REAL_COUNT=9
REPUESTOS_AGRICOLAS_REAL_COUNT=40
CROSS_VERTICAL_ID_OVERLAP=0
DEPLOY_EXECUTED_FOR_PR19=NO
ROLLBACK_EXECUTED_FOR_PR19=NO
PRODUCTION_DATA_CHANGED_FOR_PR19=NO
```

Hasta que PR #19 sea desplegado y reconciliado:

> NO ejecutar manualmente `.github/workflows/radar-cron.yml`.

El workflow permanece manual, pero el Worker productivo todavía conserva la semántica antigua de ingestión.

## Decisiones vigentes

1. Cloudflare Workers es la primera autoridad de despliegue. GitHub se reconcilia después con el source exacto ya desplegado.
2. No mergear PR #19 antes de desplegar y validar en Cloudflare el HEAD exacto del PR.
3. No confundir CI exitoso con deploy exitoso.
4. No publicar leads reales, cookies, tokens, contraseñas ni valores secretos.
5. La importación manual privada usa exclusivamente `POST /api/admin/import` con `mode=upsert_vertical`.
6. El rollback de código no revierte KV.
7. Health/readiness con sentinel separado sigue pendiente y no forma parte de PR #19.

## Bloqueo operativo actual

El entorno que preparó este archivo no dispone de:

- acceso de red saliente desde la terminal hacia GitHub o Cloudflare;
- repositorio local montado;
- sesión Wrangler persistida;
- variables `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `DASHBOARD_PASSWORD`, `INGEST_SECRET` o `SESSION_SECRET`.

Por eso no se ejecutó un deploy ficticio ni se sustituyó el pipeline canónico por GitHub Actions.

## Próximos pasos exactos

Ejecutar desde una máquina confiable con acceso a GitHub, Cloudflare y los secretos ya configurados, sin imprimir sus valores:

```bash
# 1. Obtener el source actual del PR.
git clone https://github.com/simonkey888/Leadx.git
cd Leadx
git fetch origin main fix/ingest-vertical-safety-v1 --prune
git checkout fix/ingest-vertical-safety-v1

# 2. Confirmar HEAD y árbol limpio.
git rev-parse HEAD
git status --short

# 3. No modificar el source después de congelar el SHA.
# Registrar:
# DEPLOY_SOURCE_SHA=$(git rev-parse HEAD)

# 4. Ejecutar el operador canónico.
bash scripts/deploy-workers-first.sh
```

Gates obligatorios después del deploy:

1. una sola versión activa y 100 % de tráfico;
2. `/api/health` responde según el contrato vigente;
3. login y sesión real funcionan;
4. Fotomultas conserva exactamente 9 registros e IDs únicos;
5. Repuestos agrícolas conserva exactamente 40 registros e IDs únicos;
6. solapamiento entre verticales igual a 0;
7. logout vuelve inmediatamente a demo;
8. desktop y mobile sin `pageerror`, requests accionables ni overflow horizontal;
9. rollback sólo si falla el smoke post-deploy;
10. registrar deployment ID, version ID, bundle SHA y estado de rollback.

Después de validar producción:

1. mergear PR #19 conservando el source exacto desplegado;
2. verificar el nuevo `main` SHA;
3. ejecutar `LeadX Workers-first Reconciliation`;
4. actualizar este archivo y `CONTEXTO LEADX`;
5. reactivar el uso manual del radar sólo después de confirmar que producción ejecuta la nueva semántica.

## Siguiente frente, después de PR #19

Diseñar y aprobar por separado:

- `/api/health` como liveness;
- `/api/readiness` con sentinel KV persistente y valor esperado exacto;
- data-freshness y smokes funcionales separados de readiness;
- múltiples intentos antes de rollback para evitar rollback por un fallo transitorio.

No reutilizar el experimento anterior que leía `leads:live` como dependencia de health.

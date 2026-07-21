# LeadX — estado actual y próximos pasos

Última actualización material: 2026-07-20, America/Argentina/Cordoba.

Este archivo es el punto de entrada corto para retomar LeadX sin releer todo el historial. La fuente de verdad completa sigue siendo `CONTEXTO LEADX` en Google Drive. Antes de escribir o desplegar, verificar siempre el estado externo actual.

## Estado ejecutivo

```text
PROJECT=LeadX
STATUS=P0_INGEST_SAFETY_DEPLOY_BLOCKED_BY_BROWSER_SMOKE
PRODUCTION_FIX_ACTIVE=NO
DEPLOY_PENDING=YES
MAIN_SHA=91672001c893815a1f31f9cfdd11b31a18a6968a
WORKING_BRANCH=fix/ingest-vertical-safety-v1
PR=19
PR_STATE=DRAFT_OPEN
RUNTIME_CODE_SHA=0bbf00c70c5adf7e919233257e52671f7be86c4a
CURRENT_PR_HEAD=VERIFY_REMOTE_BEFORE_ACTION
CI_RUN_ID=29784076923
CI_JOB_ID=88491663089
CI_CONCLUSION=success
SESSION_POLICY=20_MIN_IDLE_8_HOURS_ABSOLUTE
PRODUCTION_ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
PRODUCTION_TRAFFIC=100
RELEASE_ATTEMPTS=2
RELEASE_RESULT=ROLLED_BACK
BROWSER_SMOKE=BLOCKED_HUNG_NO_OUTPUT
DASHBOARD_PASSWORD_ROTATION=REQUIRES_PRODUCTION_VERIFICATION
```

Los commits posteriores a `RUNTIME_CODE_SHA` son exclusivamente documentales mientras el diff remoto confirme lo contrario. Para cualquier nueva operación, resolver y validar nuevamente el HEAD remoto actual del PR.

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
VALIDATED_RUNTIME_CODE_SHA=0bbf00c70c5adf7e919233257e52671f7be86c4a
RUN_ID=29784076923
JOB_ID=88491663089
SOURCE_CONTRACT=PASS
BUILD=PASS
INGEST_RUNTIME_TESTS=PASS
COMPLETE_TEST_SUITE=PASS
TYPECHECK=PASS
DOCUMENTATION_CONTRACT=PASS
BRANCH_CONTAINMENT_CI=SKIPPED_NOT_COUNTED_AS_PASS
DOCUMENTATION_ONLY_DELTA_AFTER_RUNTIME_SHA=VERIFY_WITH_GIT_COMPARE
```

El operador `scripts/deploy-workers-first.sh` volvió a ejecutar instalación, build, 66 pruebas baseline, 76 pruebas runtime de seguridad, 32 pruebas multi-línea, typecheck y dry-run sobre el HEAD exacto `9aefc804abca9bc0d11e3a2eecefbf932863e6f5`. Esos gates pasaron en ambos intentos.

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

Chromium fue preinstalado después y se verificó con `CHROMIUM_LAUNCH=PASS`.

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

Los procesos de Playwright se terminaron manualmente sólo después de confirmar que el test estaba bloqueado y no producía salida. No hubo evidencia de defecto funcional del producto, pero tampoco existe browser smoke aprobado. No ejecutar un tercer deploy idéntico.

## Producción vigente

La producción volvió al código anterior al fix.

```text
PRODUCTION_URL=https://leadx.simondalmasso44.workers.dev
ACTIVE_VERSION=3f605427-a8d0-45f8-af04-e62d1f28dac3
ACTIVE_TRAFFIC=100
HEALTH_AFTER_ROLLBACK=PASS
FOTOMULTAS_REAL_COUNT_LAST_VERIFIED=9
REPUESTOS_AGRICOLAS_REAL_COUNT_LAST_VERIFIED=40
CROSS_VERTICAL_ID_OVERLAP_LAST_VERIFIED=0
DEPLOY_EXECUTED_FOR_PR19=YES_TWO_ATTEMPTS
ROLLBACK_EXECUTED_FOR_PR19=YES_TWO_ATTEMPTS
PRODUCTION_DATA_CHANGED_FOR_PR19=NO_EVIDENCE
PR19_FIX_ACTIVE=NO
```

Hasta que PR #19 sea desplegado y reconciliado:

> NO ejecutar manualmente `.github/workflows/radar-cron.yml`.

El workflow permanece manual, pero el Worker productivo todavía conserva la semántica antigua de ingestión.

## Incidente de credencial

Una contraseña de dashboard fue escrita por error dentro de un comando local y debe considerarse expuesta. Se limpió el historial local y se generaron versiones de secreto no promovidas:

```text
UNTRUSTED_SECRET_VERSION=9f549e89-40f7-4b3d-9552-5e438cdcead3
CORRECTED_SECRET_VERSION=0d24cd66-7a34-485e-9e0c-f52fbd44fabc
PROMOTED_DIRECTLY=NO
```

El rollback interactivo informó que `DASHBOARD_PASSWORD` había cambiado respecto de la versión objetivo y exigió confirmación. Como los secretos son parte de la versión del Worker, tratar el estado efectivo de la contraseña productiva como `UNVERIFIED` hasta realizar un login controlado con la contraseña nueva. No registrar ni publicar ningún valor.

## Decisiones vigentes

1. Cloudflare Workers es la primera autoridad de despliegue. GitHub se reconcilia después con el source exacto ya desplegado.
2. No mergear PR #19 antes de desplegar y validar en Cloudflare el HEAD exacto del PR.
3. No confundir build/tests exitosos ni 100 % de tráfico con release aprobado.
4. No publicar leads reales, cookies, tokens, contraseñas ni valores secretos.
5. La importación manual privada usa exclusivamente `POST /api/admin/import` con `mode=upsert_vertical`.
6. El rollback de código no revierte KV; una reversión a una versión anterior puede cambiar secretos versionados y debe verificarse.
7. Health/readiness con sentinel separado sigue pendiente y no forma parte de PR #19.
8. No repetir el operador actual hasta corregir el smoke: timeout global, salida visible y rollback no interactivo.

## Bloqueo operativo actual

El release está bloqueado por el runner de browser smoke en Windows:

- primer intento: descarga de Chromium agotó el timeout;
- Chromium luego fue instalado y lanzó correctamente;
- segundo intento: `playwright test` quedó bloqueado sin salida en `browser.log`;
- el operador no tiene timeout global del test;
- `wrangler rollback` quedó interactivo y necesitó intervención manual.

## Próximo paso exacto

Antes de cualquier cambio de código o tercer deploy, verificar la credencial productiva sin revelar valores. En la PowerShell que todavía tenga cargada la contraseña nueva:

```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$body = @{ password = $env:DASHBOARD_PASSWORD } | ConvertTo-Json -Compress
try {
  $login = Invoke-RestMethod -Method Post `
    -Uri "https://leadx.simondalmasso44.workers.dev/api/auth/login?rotation_verify=$(Get-Date -Format yyyyMMddHHmmss)" `
    -WebSession $session `
    -ContentType "application/json" `
    -Body $body
  if ($login.ok -eq $true) { "NEW_PASSWORD_ACTIVE=YES" } else { "NEW_PASSWORD_ACTIVE=NO" }
} catch {
  "NEW_PASSWORD_ACTIVE=NO"
}
```

- Si devuelve `NEW_PASSWORD_ACTIVE=YES`, cerrar sesión y preservar esa contraseña.
- Si devuelve `NEW_PASSWORD_ACTIVE=NO`, la credencial expuesta puede seguir activa y la rotación pasa a ser P0 antes de continuar.

Después, en un commit separado del fix de ingest, corregir `scripts/deploy-workers-first.sh` y el smoke para:

1. no ejecutar `playwright install --with-deps chromium` dentro de cada release;
2. imponer timeout global y timeouts por test;
3. emitir progreso visible desde el primer test;
4. capturar diagnóstico en `browser.log` aunque el proceso se bloquee;
5. usar rollback no interactivo con `--message`;
6. distinguir `BROWSER_RUNNER_BLOCKED` de defecto del producto;
7. permitir validación Chromium directa controlada como fallback explícito, sin contarlo como Playwright PASS.

Sólo después:

1. validar el script corregido sin desplegar;
2. volver a congelar el HEAD exacto;
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
- múltiples intentos antes de rollback para evitar rollback por un fallo transitorio.

No reutilizar el experimento anterior que leía `leads:live` como dependencia de health.

# LeadX — estado operativo

Actualizado: 2026-07-21 · America/Argentina/Cordoba.

Este archivo es el worklog operativo principal. Antes de cualquier release, verificar siempre GitHub, Cloudflare y producción. No usar el historial del chat como fuente de verdad.

## Estado resumido

```text
PROJECT=LeadX
MAIN_SHA=91672001c893815a1f31f9cfdd11b31a18a6968a
PRODUCTION_STATE=REVERIFY_BEFORE_ANY_ACTION
PRODUCTION_TOUCHED_DURING_THIS_WORK=NO
CLOUDFLARE_TOUCHED_DURING_THIS_WORK=NO
KV_TOUCHED_DURING_THIS_WORK=NO
DEPLOY_EXECUTED=NO
ROLLBACK_EXECUTED=NO
MERGE_EXECUTED=NO
```

## Track P0 — seguridad de ingestión

```text
PR=19
BRANCH=fix/ingest-vertical-safety-v1
PR_STATE=DRAFT_OPEN
LAST_VERIFIED_PR_HEAD=5b18e8b33062f13fc29891c4d8d2d87d21438124
PRODUCTION_FIX_ACTIVE=NO_VERIFICADO
RADAR_MANUAL_DISPATCH=PAUSED
```

El candidato de PR #19:

- exige `mode=upsert_vertical`;
- restringe `/api/ingest` a `fotomultas`;
- preserva la vertical no objetivo;
- bloquea colisiones de IDs entre verticales con HTTP 409;
- preserva estado CRM durante el upsert;
- elimina el reemplazo global implícito.

No mergear PR #19 ni afirmar que el fix está activo sin verificar deployment activo, version ID, tráfico y código de esa versión mediante el flujo Cloudflare-first.

## Track aislado — Fotomultas Discovery Lab V1

```text
PR=20
BRANCH=feat/fotomultas-discovery-lab-v1
BASE_BRANCH=fix/ingest-vertical-safety-v1
PR_STATE=DRAFT_OPEN
CURRENT_PR_HEAD=VERIFY_REMOTE_BEFORE_ACTION
LAB_IMPLEMENTATION_HEAD_BEFORE_WORKLOG=fbb4ae5ecd04476f185ced28772f38dd74933d66
TARGET_VERTICAL=fotomultas
DEBT_THRESHOLD_ARS=1000000
REPUESTOS_AGRICOLAS_ACCESS=NO
PRODUCTION_ACCESS=NO
CLOUDFLARE_ACCESS=NO
KV_READ=NO
KV_WRITE=NO
LEADX_INGEST=NO
```

Objetivo exacto:

```text
CONTACT_REQUIRED=PUBLIC_EMAIL_OR_PUBLIC_PHONE_OR_PUBLIC_WHATSAPP
OFFICIAL_VERIFICATION_REQUIRED=YES
OFFICIAL_PROVIDER=sinai_official
OFFICIAL_SOURCE=https://consultainfracciones.seguridadvial.gob.ar/
ELIGIBILITY=SUM_ACTIVE_UNIQUE_NATIONAL_INFRACTIONS_ARS_GTE_1000000
```

La suma puede estar compuesta por varias infracciones. Las pagadas, anuladas, canceladas, prescritas o sin deuda no se computan. Un estado desconocido bloquea el caso.

### Componentes implementados

- `contacts.py`: normalización conservadora de email y teléfonos argentinos; sólo contactos explícitamente públicos.
- `debt.py`: importes ARS, deduplicación y suma acumulada de infracciones activas.
- `pipeline.py`: gates fail-closed, expiración, autorización, fuente oficial, hash de evidencia y estados de decisión.
- `cli.py`: evaluación artifact-only sin red ni producción.
- `worker.py`: inbox, outbox, processed y dead-letter sin reintento ciego.
- `discovery.py`: ejecuta el radar público existente en sandbox temporal y con secretos operativos vaciados.
- `orchestrator.py`: ciclo autónomo discovery → verificación privada → decisiones, con lock y `cycle_id` compartido.
- fixtures y tests exclusivamente sintéticos.
- CI de contención con permisos read-only.

### Estados del pipeline

```text
PENDING_VERIFICATION=contacto_publico_valido_sin_constancia_oficial
ELIGIBLE_VERIFIED=contacto_valido_y_deuda_activa_acumulada_gte_1000000
REJECTED=cualquier_gate_fail_closed
```

### Contención del descubrimiento

El runner de búsqueda:

- requiere `--allow-public-network`;
- corre `generate_payload.py` en un directorio temporal;
- vacía `INGEST_SECRET`, `WORKER_URL`, credenciales Cloudflare, contraseña y secreto de sesión;
- no hereda variables de entorno desconocidas;
- no ejecuta el workflow legacy `radar-cron.yml`;
- elimina registros que no sean `fotomultas`;
- elimina patente, texto crudo y deuda de fuentes no oficiales antes de publicar;
- conserva únicamente un artefacto privado sanitizado;
- no consulta SINAI en vivo.

### Tecnologías externas

```text
GOOGLESCRAPER=NOT_INTEGRATED
OPENPLANTER=NOT_INTEGRATED_AS_DEPENDENCY
OPENPLANTER_PATTERN=SOURCE_ENTITY_EVIDENCE_DECISION_ONLY
INTELX=NOT_INTEGRATED
LIVE_SINAI_AUTOMATION=NOT_INCLUDED
```

El radar existente ya resuelve el descubrimiento público inicial. GoogleScraper duplicaría esa responsabilidad. OpenPlanter es demasiado amplio para incorporarlo como agente con shell. IntelX queda fuera de V1.

## Validaciones ejecutadas

```text
CI_WORKFLOW=LeadX Fotomultas Discovery Lab CI
LAST_FULL_CODE_HEAD_VALIDATED=28112f664bc5bef2c203fdf265b7e11e593a2e17
LAST_FULL_CODE_RUN_ID=29834068571
LAST_FULL_CODE_CONCLUSION=success
CONTAINMENT=PASS
PYTHON_COMPILE=PASS
UNIT_TESTS=PASS
SYNTHETIC_ARTIFACT_FLOW=PASS
NETWORK_RUNNERS_OPT_IN=PASS
PRODUCTION_ACCESS=NO
CLOUDFLARE_KV_INGEST_ACCESS=NO
```

La CI sólo usa fixtures sintéticos. No ejecuta descubrimiento web real, no consulta SINAI y no crea artefactos con leads reales.

## Arquitectura de release vigente

```text
RELEASE_MODEL=CLOUDFLARE_FIRST_WORKERS_FIRST
RELEASE_OPERATOR=CLOUDFLARE
GITHUB_ROLE=SOURCE_HISTORY_CI_AND_POST_RELEASE_EVIDENCE
GITHUB_ACTIONS_DEPLOY_OPERATOR=NO
```

Secuencia obligatoria para un release futuro:

1. congelar el source SHA exacto;
2. Cloudflare toma ese source;
3. instalación frozen y build;
4. preview o versión candidata sin promoción;
5. validar Worker, bindings, KV, cron, APIs, UI y logs;
6. promover únicamente esa misma candidata con todos los gates aprobados;
7. repetir smokes productivos;
8. registrar SHA, version ID, deployment ID, tráfico, smokes y rollback en GitHub;
9. actualizar Drive si el cambio constituye un hito material.

## Riesgos y bloqueos abiertos

1. PR #19 todavía no fue validado y reconciliado mediante una candidata Cloudflare del HEAD exacto.
2. El laboratorio está implementado, pero no está ejecutándose en un host continuo.
3. SINAI en vivo no está automatizado: requiere revisión específica de finalidad, autorización, frecuencia, privacidad y condiciones vigentes.
4. Los candidatos reales y verificaciones privadas deben permanecer fuera de GitHub, CI, Drive y artefactos públicos.
5. `radar-cron.yml` sigue pausado y no debe ejecutarse manualmente.

## Próximo paso exacto

```text
NEXT_EXACT_ACTION=PREPARE_NON_PRODUCTION_CONTAINER_RUNTIME_FOR_PR20_WITHOUT_STARTING_PRODUCTION_OR_SINAI_AUTOMATION
```

La próxima fase debe preparar el runtime de un contenedor no productivo para ejecutar el supervisor y medir calidad. Iniciar ese runtime externo o conectar una verificación SINAI real constituye una operación externa y debe respetar los límites operativos vigentes. No desplegar LeadX, no tocar Cloudflare y no modificar Repuestos agrícolas.

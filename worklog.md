# Worklog — Radar de Oportunidades (Prototipo Fase 1)

---
Task ID: 0
Agent: main
Task: Construir prototipo Fase 1 del Radar de Oportunidades en Python + Sheet, con mock data + stubs, audit trail, evidence store, review queue, privacy filter, scoring 0-100, dedup, y roadmap fases 1→2→3. Idioma: español AR.

Decisiones clave:
- Stack: Python 3 (solo stdlib + dependencias mínimas) + Google Sheets via gspread (stub + dry-run)
- Fuentes: mock data realista AR + stubs documentados para Fase 2/3 (FB, X, marketplace, foros, news)
- Compliance: audit trail append-only (audit_trail.log), evidence store con hash SHA-256, review queue CSV con estados, privacy filter que rechaza PII antes de persistir
- Scoring: implementación exacta de los 7 pesos del spec (explicit_intent 30, urgency 15, jurisdiction_fit 15, evidence_quality 10, commercial_potential 10, channel_fit 10, signal_repetition 10), normalizado a 0-100
- Dedup: 4 match keys (source_url, profile_url, patent, normalized_text_hash), merge strategy keep_highest_confidence_and_latest_timestamp
- Sheet: integración con la URL del spec (1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0), modo dry-run sin credenciales, modo real con service account
- Idioma: español rioplatense en toda la UI, código y documentación

---
Task ID: 1-final
Agent: main
Task: Cierre del prototipo Fase 1 del Radar de Oportunidades.

Work Log:
- Construidos 12 módulos Python en /home/z/my-project/scripts/radar/
- Codigo copiado a /home/z/my-project/download/radar_prototipo_fase1/
- Sample data generada en /home/z/my-project/download/sample_data/
- Documentación: README.md, ROADMAP.md (fases 1→2→3), SCORING_MODEL.md
- Smoke tests exitosos en cada módulo individual y end-to-end

Stage Summary:
- 24 señales mock → 2 rechazadas por privacy filter (DNI, email, CUIT, teléfono)
  → 22 casos extraídos → 2 duplicados detectados → 20 casos canónicos
- Distribución: 2 critical, 6 high, 9 medium, 3 low
- Audit trail: 71 entradas con hash chaining íntegro
- Sheet sync: dry-run (20 filas listas para subir a la Sheet del spec)
- CLI de revisión: approve/reject/duplicate/needs_more_data funcionando
- Bundle final en /home/z/my-project/download/ listo para entrega

Cobertura del spec:
- ✓ entity_extraction (todos los campos)
- ✓ normalization (jurisdiction_map, vehicle_type_map, date, amount)
- ✓ scoring (7 pesos + 4 umbrales exactos del spec)
- ✓ deduplication (4 match keys + merge strategy)
- ✓ storage (evidence + structured + sheet)
- ✓ workflow (collect → extract → normalize → score → dedup → store → queue → review)
- ✓ review_queue (status + actions + SLA 24h)
- ✓ alerts (triggers documentados, audit en lugar de push)
- ✓ compliance (public_only, respect_platform_terms, no_spam, no_private_harvesting, manual_contact_only)
- ✓ constraints (no_auto_messaging, audit_trail_required, evidence_storage_required, human_review_required)

No cubierto en Fase 1 (documentado en ROADMAP.md para Fase 2/3):
- Dashboard web (Fase 2)
- Conectores reales (Fase 2: X API + RSS; Fase 3: dominio + intake público)
- LLM extractor (Fase 2)
- Alertas push (Fase 2)

---
Task ID: 2-sheet-uploader
Agent: main
Task: Implementar sheets_uploader.py como módulo SPEC-ONLY (contrato de entrada, sin ejecución real contra Google).

Work Log:
- Creado sheets_uploader.py con GoogleSheetsUploader class
- Contract: input = RADAR_GOOGLE_SERVICE_ACCOUNT_FILE (env var path string)
- Behavior: si path vacío o no existe → raise MissingCredentialsError("Missing credentials file ...")
- Sin modo mock ni dry-run implícito. Dry-run explícito vía --dry-run flag en CLI.
- Implementación real dentro de métodos (gspread.service_account, append_rows, etc.)
  pero NO se ejecutan en este entorno (no hay credenciales).
- Schema SHEET_HEADERS exacto del spec del uploader (20 columnas)
- Política de headers: create_headers / validate_and_merge_if_missing / never_overwrite_row_1
- Dedup strategy: update_score_if_higher (si case_id existe y nuevo score > existente → update)
- WhatsApp link builder: https://wa.me/{num}?text={encoded_msg}
- Audit logging en cada operación (ensure_headers, appended, updated_higher_score, skipped_lower_score, error)
- Retry policy: retry_once_then_log_error
- Actualizado main.py: --sheet-write flag que invoca uploader
- Actualizado config.py: SHEET_HEADERS, WHATSAPP_DEFAULT_MESSAGE, sheet policies
- Actualizado models.py: Case con campos whatsapp_number, whatsapp_link, priority_level, review_state; to_sheet_row() con schema exacto
- Actualizado README.md con sección --sheet-write
- Smoke test OK: 5 verificaciones pasaron (sin/credenciales, path inexistente, whatsapp link, schema, to_sheet_row)

Stage Summary:
- Contrato spec-only verificado: sin credenciales lanza "Missing credentials file"
- 5 tests pasaron sin tocar Google Sheets
- Bundle sincronizado en /home/z/my-project/download/radar_prototipo_fase1/
- Listo para que el operador ejecute --sheet-write en su máquina con credenciales locales

Archivos modificados:
- scripts/radar/sheets_uploader.py (NUEVO)
- scripts/radar/config.py (SHEET_HEADERS, WHATSAPP_DEFAULT_MESSAGE, policies)
- scripts/radar/models.py (Case +4 campos, to_sheet_row rewrite)
- scripts/radar/main.py (--sheet-write, --dry-run flags)
- scripts/radar/README.md (sección --sheet-write)

---
Task ID: 3-webhook-uploader
Agent: main
Task: Implementar webhook_uploader.py como vía alternativa de subida vía Apps Script Web App (SPEC-ONLY).

Work Log:
- Creado webhook_uploader.py con WebhookUploader class
- Contract: input = RADAR_WEBHOOK_URL (env var URL string)
- Behavior: si URL vacía o esquema inválido → raise MissingWebhookURLError("Missing webhook URL ...")
- Sin modo mock ni dry-run implícito. Dry-run explícito vía --dry-run flag.
- Implementación real dentro de métodos (urllib.request POST con retry_once_then_log_error)
  pero NO se ejecutan HTTP POST en este entorno (no hay URL).
- Static method case_to_payload() para construir payload sin instanciar (útil para dry-run)
- Payload JSON: {"cases": [...]} con 15 campos de entrada (sin priority_level, whatsapp_link,
  status, review_state — el script los computa)
- Respuestas esperadas: "OK" | "NO_CASES" | "ERROR: <msg>"
- Audit logging en cada operación (appended, failed, error)
- Actualizado main.py: --sheet-push-webhook flag + cmd_sheet_push_webhook()
- Actualizado README.md con sección completa comparando --sheet-write vs --sheet-push-webhook
- Creado apps_script/Code.gs con el script del usuario, extendido:
  * ensureHeaders() para crear row 1 si hoja vacía
  * try/catch en doPost con mensajes "OK" | "NO_CASES" | "ERROR: <msg>"
  * testDoPost() para probar desde el editor de Apps Script
  * Normalización de WhatsApp number (sólo dígitos)
- Smoke test webhook_uploader.py: 5 verificaciones OK (sin URL, esquema inválido, URL válida,
  case_to_payload schema, push([]) → NO_CASES)
- Smoke test main.py: --sheet-push-webhook sin URL → "Missing webhook URL"; --dry-run → payload JSON correcto

Stage Summary:
- Dos vías de subida a Google Sheet implementadas:
  1. --sheet-write (gspread + service account JSON) — con dedup + update_score_if_higher
  2. --sheet-push-webhook (HTTP POST + Apps Script Web App) — append simple, sin deps Python
- Ambas SPEC-ONLY: fail explícito si falta credencial/URL, sin mocks ni dry-run implícito
- Bundle sincronizado en /home/z/my-project/download/radar_prototipo_fase1/ (15 .py + 1 .gs + 3 .md)

Archivos modificados/creados:
- scripts/radar/webhook_uploader.py (NUEVO)
- scripts/radar/apps_script/Code.gs (NUEVO)
- scripts/radar/main.py (--sheet-push-webhook flag + cmd_sheet_push_webhook)
- scripts/radar/README.md (sección webhook + tabla comparativa)

---
Task ID: 4-event-pipeline-v2
Agent: main
Task: Implementar pipeline event-driven v2.0 con LLM extractor y sinks separados.

Work Log:
- Creado event_types.py: 6 tipos de eventos frozen dataclass (SignalCollected, EntitiesExtracted, CaseScored, CaseDeduplicated, CasePublished, EventRejected)
- Creado event_validator.py: validación contra data_contract del spec v2.0
  (case_id, patent, jurisdiction, score 0-100, source, evidence, timestamp iso8601)
- Creado event_bus.py: pub/sub in-process síncrono
  - todo evento pasa por validate_event() antes del dispatch
  - eventos inválidos → EventRejected, NO se dispatchean
  - handlers que fallan → logueado pero no rompe el bus
  - audit logging de cada publish y handler_error
- Creado llm_extractor.py: LLM extractor SPEC-ONLY
  - env var RADAR_LLM_API_KEY obligatoria
  - sin API key → MissingLLMApiKeyError("Missing LLM API key ...")
  - pure function: sólo chat completion, no tool calls (regla no_llm_side_effects)
  - SYSTEM_PROMPT con reglas anti-PII y no-alucinación
  - LLM_OUTPUT_SCHEMA con 7 entidades requeridas
  - extract_to_case(signal) mapea output a Case
- Creado sinks.py: 
  - Sink abstract base
  - WhatsAppLinkSink: trigger manual_or_score_threshold (score>=80 OR número manual OR approved)
    genera https://wa.me/{num}?text={encoded_msg}, no escribe externamente
  - GoogleSheetsWebhookSink: batch con flush(), delega en webhook_uploader
  - SinkFanOut: ejecuta N sinks sobre un case
- Creado event_pipeline.py: orquestador
  - pre-flight check: si no hay API key, falla ANTES de procesar
  - wire 3 handlers (signal_collected, entities_extracted, case_scored)
  - dedup batch al final sobre todos los casos
  - SinkFanOut.write + flush_all
- Actualizado main.py: --event-pipeline flag

Smoke tests OK:
- event_validator: 5 verificaciones (válido, inválido, score fuera de rango, timestamp inválido)
- event_bus: 4 verificaciones (publish válido, publish inválido rechazado, stats, audit)
- llm_extractor: 6 verificaciones (sin API key, constructor OK, prompt, schema, hash)
- sinks: 8 verificaciones (3 triggers de WhatsApp, sin URL sheets, fan-out)
- event_pipeline: sin API key → fail explícito; con dummy key → wiring OK, 24 eventos publicados

Stage Summary:
- v2.0 cumple las 3 reglas del spec:
  ✓ no_llm_side_effects: extractor es pure function (sólo chat completion)
  ✓ no_direct_external_writes: pipeline sólo escribe via sinks
  ✓ requires_event_validation: bus valida cada evento antes del dispatch
- 2 sinks implementados: WhatsApp (link gen) + Google Sheets (webhook batch)
- 6 tipos de eventos con data_contract validado
- v1.0 sigue funcionando sin cambios (regresión OK)
- Bundle sincronizado: 21 .py + 1 .gs + 3 .md

Archivos creados:
- scripts/radar/event_types.py
- scripts/radar/event_validator.py
- scripts/radar/event_bus.py
- scripts/radar/llm_extractor.py
- scripts/radar/sinks.py
- scripts/radar/event_pipeline.py
- scripts/radar/main.py (--event-pipeline flag)


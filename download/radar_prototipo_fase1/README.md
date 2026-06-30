# Radar de Oportunidades — Prototipo

Sistema de detección de oportunidades comerciales **públicas** relacionadas con
fotomultas, libre deuda, transferencia y regularización vehicular, con foco en
**trazabilidad** y **revisión humana obligatoria** (sin outreach automático).

## Dos versiones del pipeline

| Versión | Modo | Extractor | Orquestación | Cómo activarlo |
| ------- | ---- | --------- | ------------ | -------------- |
| v1.0 (default) | imperativo | regex + keyword matching | pipeline.py directo | `python main.py` |
| v2.0 | event-driven | LLM (GLM-4) | event_bus + sinks | `python main.py --event-pipeline` |

**v2.0 cumple 3 reglas del spec:**
- `no_llm_side_effects`: el extractor es pure function (sólo chat completion, no tool calls)
- `no_direct_external_writes`: el pipeline sólo escribe via sinks
- `requires_event_validation`: todo evento pasa por EventValidator antes del dispatch

---

## Qué hace este prototipo

1. **Recolecta señales** de 5 fuentes públicas (Facebook groups, Marketplace,
   X/Twitter, foros, news). En Fase 1 se usa mock data realista en español AR.
2. **Filtra PII** antes de almacenar (DNI, CUIT, email, teléfono, dirección).
3. **Extrae entidades**: nombre/alias, perfil, vehículo, patente, jurisdicción,
   localidad, problema, año, monto, fuente, URL, timestamp, evidencia textual.
4. **Normaliza**: jurisdicciones argentinas, tipos de vehículo, fechas ISO, montos.
5. **Puntúa 0-100** con 7 dimensiones ponderadas (intención explícita, urgencia,
   ajuste jurisdicción, calidad evidencia, potencial comercial, ajuste canal,
   repetición).
6. **Deduplica** por 4 match keys (source_url, profile_url, patent, text_hash)
   con merge strategy *keep highest confidence + latest timestamp*.
7. **Almacena evidencia** en disco con SHA-256 de integridad.
8. **Mantiene audit trail** append-only con hash chaining (tamper-evident).
9. **Puebla cola de revisión** CSV/JSONL con SLA 24h.
10. **Sincroniza** a Google Sheet del spec (modo dry-run en Fase 1).
11. **CLI de revisión** humana: list / show / approve / reject / duplicate /
    needs_more / stats / audit / verify.

---

## Stack

- **Python 3.10+** (sólo stdlib para Fase 1).
- Persistencia local: JSONL + CSV + archivos de texto.
- `gspread` opcional para sync real a Google Sheet (Fase 2/3).
- `zoneinfo` para timezones (incorporado en Python 3.9+).

Sin dependencias externas obligatorias para correr el prototipo. Sin Docker,
sin DB, sin cloud —simplicidad primero, como pidió el spec.

---

## Instalación

```bash
# Sin instalación. Sólo:
cd /home/z/my-project/scripts/radar
python main.py
```

Para habilitar sync real a Google Sheet (opcional, Fase 2):

```bash
pip install gspread
export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/a/service-account.json
python main.py --sheet-real
```

---

## Uso

### Pipeline end-to-end (mock data)

```bash
python main.py
```

Salida esperada:
- `download/sample_data/signals_mock.jsonl` — señales crudas
- `download/sample_data/cases.jsonl` — casos extraídos, normalizados y puntúados
- `download/sample_data/review_queue.csv` — cola de revisión humana
- `download/sample_data/audit_trail.log` — audit trail append-only
- `download/sample_data/evidence/<case_id>/` — evidencia por caso (txt + json + sha256)

### Subida a Google Sheet (`--sheet-write`)

El módulo `sheets_uploader.py` implementa el contrato del uploader v1.0:

```bash
# Dry-run: serializa filas a stdout sin tocar Google
python main.py --sheet-write --dry-run

# Subida real (en máquina del operador con credenciales):
export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json
pip install gspread
python main.py --sheet-write
```

**Comportamiento sin credenciales** (no hay modo mock ni dry-run implícito):

```
$ python main.py --sheet-write
✗ Missing credentials file (env var RADAR_GOOGLE_SERVICE_ACCOUNT_FILE is empty)
  Setear env var: export RADAR_GOOGLE_SERVICE_ACCOUNT_FILE=/path/local/service-account.json
```

**Schema de la Sheet** (worksheet `cases`, append_only):

```
case_id, timestamp, name_or_alias, profile_url, patent, vehicle_type,
jurisdiction, locality, problem_type, year, amount, score, priority_level,
source_name, source_url, evidence_text, whatsapp_number, whatsapp_link,
status, review_state
```

**Política de headers**:
- Hoja vacía → crea headers
- Headers existentes → valida y agrega faltantes al final (nunca sobrescribe row 1)

**Dedup**: si el `case_id` ya existe en la sheet, estrategia `update_score_if_higher`:
- Si el nuevo score > existente → actualiza la fila
- Si no → skip (no crea duplicado)

**WhatsApp link**: si el caso tiene `whatsapp_number`, se genera
`https://wa.me/{num}?text={encoded_message}` con el mensaje por defecto
(`config.WHATSAPP_DEFAULT_MESSAGE`).

**Audit**: cada operación (`ensure_headers`, `appended`, `updated_higher_score`,
`skipped_lower_score`, `error`) se loguea en `audit_trail.log`.

### Subida vía Apps Script Webhook (`--sheet-push-webhook`)

Alternativa sin `gspread` ni service account: el operador despliega el script
`apps_script/Code.gs` (en el repo del operador) como Web App y este módulo
hace POST HTTP con el payload JSON.

```bash
# Dry-run: serializa payload JSON a stdout sin hacer HTTP
python main.py --sheet-push-webhook --dry-run

# Push real (requiere Web App desplegada):
export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec
python main.py --sheet-push-webhook
```

**Comportamiento sin URL** (no hay modo mock ni dry-run implícito):

```
$ python main.py --sheet-push-webhook
✗ Missing webhook URL (env var RADAR_WEBHOOK_URL is empty)
  Setear env var: export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec
```

**Payload enviado** (POST `application/json`):

```json
{
  "cases": [
    {
      "case_id": "...",
      "timestamp": "...",
      "name_or_alias": "...",
      "profile_url": "...",
      "patent": "...",
      "vehicle_type": "...",
      "jurisdiction": "...",
      "locality": "...",
      "problem_type": "...",
      "year": "",
      "amount": "",
      "score": 82,
      "source_name": "...",
      "source_url": "...",
      "evidence_text": "...",
      "whatsapp_number": ""
    }
  ]
}
```

**Respuesta esperada del Apps Script**:
- `"OK"` → todos los casos fueron appendados
- `"NO_CASES"` → payload sin cases
- Otro string → error reportado por el script

**Diferencias vs `--sheet-write` (gspread)**:

| Aspecto               | `--sheet-write` (gspread)             | `--sheet-push-webhook` (Apps Script) |
| --------------------- | ------------------------------------- | ------------------------------------ |
| Auth                  | Service account JSON                  | Web App URL pública                  |
| Deps Python           | `gspread` + `oauth2client`            | Ninguna (sólo `urllib` de stdlib)    |
| Dedup                 | Cliente (Python busca case_id)        | No implementado en script actual     |
| Update score si mayor | Sí                                    | No (sólo append)                     |
| Headers               | Cliente asegura                       | Cliente debe asegurar (script no)    |
| WhatsApp link         | Cliente construye                     | Script construye                     |
| Status inicial        | `needs_review`                        | `"new"`                              |
| review_state inicial  | `needs_review`                        | `"pending_review"`                   |
| Latencia              | 1 llamada API por caso + 1 batch       | 1 POST total                          |

**Recomendación**: si el volumen es bajo (<50 casos/día) y querés dedup +
update, usar `--sheet-write`. Si el volumen es alto o no querés dependencias
Python, usar `--sheet-push-webhook` (más rápido, menos features).

### Pipeline v2.0 event-driven (`--event-pipeline`)

Arquitectura event-driven con LLM extractor, PolicyEngine y sinks separados.
Cumple las 3 reglas del spec v2.0 + 4 correcciones arquitectónicas:

**Reglas v2.0:**
- `no_llm_side_effects`: extractor LLM es pure function
- `no_direct_external_writes`: pipeline sólo escribe via sinks
- `requires_event_validation`: cada evento se valida contra data_contract

**Correcciones arquitectónicas:**
- **A. EventLog persistente** (SQLite/JSONL): append-only log con `event_id`, `event_type`, `payload`, `timestamp`, `version`. Habilita replay y debugging histórico.
- **B. Score versioning**: cada Case registra `score_version="v1.0_weighted_sum"`. Permite comparación histórica y replay con nuevos pesos.
- **C. PolicyEngine separa triggers de sinks**: los sinks ya NO consultan triggers, sólo ejecutan `PolicyDecision.actions`. Los sinks tienen `write_with_decision(case, decision)`.
- **D. PolicyEngine con reglas explícitas**: 4 reglas (score>=80, jurisdiction target, duplicate suppress, canonical publish).

```bash
# Requiere API key del LLM (GLM-4 o compatible OpenAI):
export RADAR_LLM_API_KEY=<tu-api-key>
# Opcional: endpoint y modelo
# export RADAR_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4/chat/completions
# export RADAR_LLM_MODEL=glm-4-flash
# Opcional: webhook URL para sink de Sheets
# export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<ID>/exec

python main.py --event-pipeline
```

**Comportamiento sin API key** (no hay modo mock):

```
$ python main.py --event-pipeline
✗ Missing LLM API key (env var RADAR_LLM_API_KEY is empty)
  Setear env var: export RADAR_LLM_API_KEY=<tu-api-key>
```

**Flujo de eventos con PolicyEngine (corrección C+D)**:

```
SignalCollected
  → handler_on_signal_collected
    → LLMExtractor.extract_to_case(signal)
    → publicar EntitiesExtracted
      → handler_on_entities_extracted
        → Scorer.update_case_score(case) [score_version = "v1.0_weighted_sum"]
        → publicar CaseScored
          → handler_on_case_scored (buffer para dedup batch)
            → merge_duplicates(casos)
            → por cada caso (canonical Y duplicate):
              → PolicyEngine.evaluate(case) → PolicyDecision
                Reglas:
                  1. if score >= 80 → generate_whatsapp_intent
                  2. if jurisdiction in TARGET → boost_priority (+5)
                  3. if duplicate → suppress_output (no más reglas)
                  4. if canonical → publish_to_sheets
              → apply_boost(case, decision) [PolicyEngine es pure, no muta]
              → publicar PolicyEvaluated
              → publicar CaseDeduplicated
              → si decision.should_suppress() → continue
              → SinkFanOut.write_with_decision(case, decision)
                → WhatsAppLinkSink.write_with_decision (genera link si action)
                → GoogleSheetsWebhookSink.write_with_decision (encola si action)
              → publicar CasePublished
            → SinkFanOut.flush_all() (envía batch a Sheets)
```

**EventLog (corrección A)** — schema persistido:

```
event_id (PK) | event_type | payload (JSON) | timestamp | version
```

Backends:
- `sqlite` (default, recomendado) — atomic, queryable, zero-deps
- `jsonl` (fallback) — simple, para Drive o FS simple

Persistido en `download/sample_data/event_log.db`. Cada evento del bus se
duplica al event_log para replay/auditoría.

**PolicyDecision** — output del PolicyEngine:

```python
PolicyDecision(
    case_id="case-xxx",
    actions=["generate_whatsapp_intent", "boost_priority", "publish_to_sheets"],
    reasons=["score 85 >= 80", "jurisdiction CABA in target [...]", "case is canonical"],
    boost_delta=5,
    metadata={"whatsapp_score_threshold": 80, "boost_delta": 5, "target_jurisdiction": "CABA"},
    decision_id="dec-pol-abc123",
    timestamp="2026-06-30T13:20:53..."
)
```

**Score versioning (corrección B)** — cada Case tiene:

```python
case.score_version = "v1.0_weighted_sum"
```

En el evento `CaseScored` y `CaseDeduplicated`, el validador emite warning si
falta `score_version`. Esto habilita:
- Replay con nuevos pesos (cambiar `SCORE_VERSION` en config)
- Comparación histórica entre versiones
- Debugging real (saber con qué pesos se calculó cada score)

**Sinks disponibles**:

| Sink ID | Tipo | Trigger (legacy) | Trigger (v2.0 con PolicyEngine) |
| ------- | ---- | ---------------- | ------------------------------- |
| `whatsapp` | link_generator | `manual_or_score_threshold` | `decision.should_generate_whatsapp()` |
| `google_sheets` | apps_script_webhook | batch (cada 50 casos) | `decision.should_publish_to_sheets()` |

Cada sink expone `write_with_decision(case, decision)` (recomendado) y
`write(case)` (legacy, backward-compat).

**Data_contract validado en cada evento**:

```json
{
  "case_id": "string (no vacío)",
  "patent": "string",
  "jurisdiction": "string",
  "score": "number 0-100",
  "score_version": "string (recommended: v1.0_weighted_sum)",
  "source": "string (no vacío)",
  "evidence": "string (no vacío)",
  "timestamp": "iso8601"
}
```

Eventos inválidos → se emite `EventRejected` y no se dispatchean a handlers.

### CLI de revisión humana

```bash
python main.py --review
```

Comandos disponibles:

| Comando                       | Acción                                          |
| ----------------------------- | ----------------------------------------------- |
| `list`                        | Lista casos pendientes (status=needs_review)    |
| `show <case_id>`              | Muestra detalle completo de un caso             |
| `approve <id> [notas]`        | Aprueba para acción comercial                   |
| `reject <id> [notas]`         | Rechaza                                         |
| `duplicate <id> [notas]`      | Marca como duplicado                            |
| `needs_more <id> [notas]`     | Marca como necesita más datos                   |
| `stats`                       | Estadísticas de la cola                         |
| `audit [N]`                   | Últimas N entradas del audit trail              |
| `verify`                      | Verifica integridad de la cadena de audit       |
| `quit`                        | Salir                                           |

### Demo automática (no interactiva)

```bash
python main.py --review --demo
```

---

## Compliance

El sistema respeta los constraints del spec:

| Constraint                          | Implementación                                                      |
| ----------------------------------- | ------------------------------------------------------------------- |
| `no_auto_messaging`                 | No hay ningún módulo de outreach automático. Revisión humana obligatoria. |
| `no_private_data_collection_without_legitimate_access` | `privacy_filter` rechaza PII antes de persistir. Stubs de Facebook/Marketplace documentan que requieren acceso legítimo. |
| `audit_trail_required`              | `AuditTrail` append-only con hash chaining (tamper-evident).        |
| `evidence_storage_required`         | `EvidenceStore` guarda txt + json + SHA-256 por caso.               |
| `human_review_required_for_action`  | Todos los casos nacen `needs_review`. Sin revisión, no hay acción.  |

Reglas de compliance activas (config.py `COMPLIANCE_RULES`):
- `public_only_preferred: True`
- `respect_platform_terms: True`
- `no_spam: True`
- `no_private_profile_harvesting: True`
- `manual_contact_only: True`

---

## Estructura del proyecto

```
scripts/radar/
├── main.py              # Entry point (--review | --event-pipeline | --sheet-write | --sheet-push-webhook | default v1)
│
│   ── v1.0 (pipeline imperativo, regex extractor) ──
├── pipeline.py          # Orquestador end-to-end v1
├── extractor.py         # Extracción regex + normalización + privacy filter
├── storage.py           # EvidenceStore + AuditTrail + ReviewQueue + SheetSync (legacy)
│
│   ── v2.0 (event-driven, LLM extractor, PolicyEngine) ──
├── event_types.py       # 7 tipos de eventos (SignalCollected, ..., PolicyEvaluated, EventRejected)
├── event_validator.py   # Validación contra data_contract + score_version warning
├── event_bus.py         # In-process pub/sub con validación obligatoria
├── event_log.py         # [A] Append-only event log (SQLite/JSONL) para replay/auditoría
├── llm_extractor.py     # LLM extractor (GLM-4, pure function, SPEC-ONLY)
├── policy_engine.py     # [C+D] PolicyEngine (pure) + PolicyDecision + apply_boost
├── sinks.py             # Sinks con write_with_decision (PolicyDecision) + write (legacy)
├── event_pipeline.py    # Orquestador event-driven v2 con PolicyEngine + EventLog
│
│   ── shared ──
├── config.py            # Constantes + SCORE_VERSION = "v1.0_weighted_sum" [B]
├── models.py            # Dataclasses: Signal, Case (+score_version), AuditEntry, ReviewAction
├── mock_sources.py      # Mock data AR + stubs documentados para Fase 2/3
├── scorer.py            # Scoring weighted_sum_v1 + score_version [B]
├── dedup.py             # Dedup con 4 match keys + union-find
├── sheets_uploader.py   # Subida vía gspread + service account (SPEC-ONLY)
├── webhook_uploader.py  # Subida vía POST a Apps Script Web App (SPEC-ONLY)
├── review_cli.py        # CLI interactivo de revisión
└── apps_script/Code.gs  # Script Apps Script para desplegar como Web App
```

Outputs en `/home/z/my-project/download/sample_data/`:

```
sample_data/
├── signals_mock.jsonl
├── cases.jsonl
├── review_queue.csv
├── review_queue.jsonl
├── audit_trail.log
├── dedup_index.json
└── evidence/
    ├── case-<id>/
    │   ├── evidence.txt
    │   ├── evidence.json
    │   └── evidence.sha256
    └── ...
```

---

## Cómo extender a Fase 2 (operación)

Ver `ROADMAP.md` para el detalle. Resumen:

1. Implementar `RealSourceStub.fetch_x_search` (X API v2, tier Basic).
2. Implementar `RealSourceStub.fetch_public_forums` y `fetch_news_and_comments` con `feedparser`.
3. Configurar `RADAR_GOOGLE_SERVICE_ACCOUNT_FILE` y correr `python main.py --sheet-real --no-mock`.
4. Reemplazar `extract_with_regex` por `LLMExtractor.extract` (GLM-4 / GPT-4 con schema JSON).
5. Migrar `ReviewQueue` de CSV a SQLite/Postgres (mantener interfaz).

---

## Limitaciones de Fase 1

- No hay conectores reales a Facebook/Marketplace (sin API pública viable).
- El extractor es regex (no LLM): limitado a patrones pre-definidos.
- No hay dashboard web (la cola CSV es el dashboard).
- No hay alertas push (sólo audit log).
- El `gspread` no se prueba aquí por no tener credenciales.

Todas estas limitaciones están cubiertas en el roadmap de Fase 2 y 3.

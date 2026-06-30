# Radar de Oportunidades — Prototipo

Sistema de detección de oportunidades comerciales **públicas** relacionadas con
fotomultas, libre deuda, transferencia y regularización vehicular, con foco en
**trazabilidad** y **revisión humana obligatoria** (sin outreach automático).

## Tres modos de uso

| Modo | Archivo | Complejidad | Cuándo usar |
| ---- | ------- | ----------- | ----------- |
| **Lite** | `radar_lite.py` | 1 archivo, 0 deps | Detección rápida manual con derivación a WhatsApp |
| **v1.0** | `pipeline.py` + 10 módulos | Media | Pipeline imperativo con regex, scoring 0-100, dedup, audit trail |
| **v2.0** | `event_pipeline.py` + 15 módulos | Alta | Event-driven con LLM, PolicyEngine, sinks, event_log |

### Radar Lite (recomendado para empezar)

**1 archivo, 0 dependencias, sin event_bus, sin database, sin sheets, sin policy_engine, sin LLM.**

Sólo hace: texto → keywords → score 0-3 → link de WhatsApp.

```bash
# Input por argumento
python radar_lite.py "URGENTE: vendo auto. Libre deuda pendiente. Transferir."

# Input por pipe
echo "Tengo una multa de CABA..." | python radar_lite.py

# Input interactivo
python radar_lite.py
# (luego pegar texto, Ctrl+D para finalizar)

# Tests
python radar_lite.py --test
```

**Output** (JSON):

```json
{
  "score": 3,
  "intent": "high_intent_actionable",
  "name_or_alias": "",
  "vehicle_reference": "auto",
  "patent_if_present": "ABC123",
  "location": "PBA",
  "problem_type": "transferencia",
  "source_text_snippet": "URGENTE: vendo auto Ford Fiesta 2015...",
  "matched_keywords": ["deuda", "patente", "libre deuda", "urgente", "vendo auto"],
  "whatsapp_link": "https://wa.me/5493425691516?text=CASO%20RADAR%0AINTENCION%3A%203%0ATIPO%3A%20transferencia%0AEXTRACTO%3A%20...",
  "triggered": true
}
```

**Scoring 0-3** (threshold >= 2 genera link):

| Score | Intent | Significado |
| ----- | ------ | ----------- |
| 0 | no_relevant | Nada matcheó |
| 1 | low_intent | Sólo problema mencionado (multa, deuda, patente) |
| 2 | medium_intent | Problema + contexto, o acción sola |
| 3 | high_intent_actionable | Problema + contexto + acción |

**Keywords** (3 categorías):
- Problema: `multa`, `fotomulta`, `deuda`, `patente`
- Contexto: `libre deuda`, `transferencia`, `urgente`
- Acción: `vendo auto`, `transferir auto`, `no puedo vender`, `no puedo transferir`

**WhatsApp link** (si score >= 2):
- Teléfono: `+5493425691516`
- Template: `CASO RADAR\nINTENCION: {score}\nTIPO: {problem_type}\nEXTRACTO: {snippet}`

**Reglas cumplidas**:
- ✓ no_external_writes (sólo genera link, no envía nada)
- ✓ no_databases (sin SQLite, sin sheets)
- ✓ no_crm_logic (sólo detección de intención)
- ✓ no_automation_spam (link manual, no auto-envío)
- ✓ manual_review_optional (el humano decide si abre el link)
- ✓ focus_only_on_intent_detection

---

## Lectura general del sistema (v1.0 / v2.0)

> **Es un decision pipeline determinístico con capa LLM de extracción, con
> auditoría completa.**

No es:
- ❌ un agent system
- ❌ event sourcing puro
- ❌ un CRM

Es:
- ✅ **lead intelligence + rule-based triage system con auditoría completa**

Eso es bueno. Y coherente.

## Dos versiones del pipeline

| Versión | Modo | Extractor | Orquestación | Cómo activarlo |
| ------- | ---- | --------- | ------------ | -------------- |
| v1.0 (default) | imperativo | regex + keyword matching | pipeline.py directo | `python main.py` |
| v2.0 | event-driven | LLM (GLM-4) | event_bus + sinks | `python main.py --event-pipeline` |

**v2.0 cumple 3 reglas del spec + 4 correcciones arquitectónicas + 3 estabilizaciones:**

Reglas v2.0:
- `no_llm_side_effects`: extractor es pure function
- `no_direct_external_writes`: pipeline sólo escribe via sinks
- `requires_event_validation`: todo evento pasa por EventValidator

Correcciones arquitectónicas:
- **A.** Roles congelados por capa (Extractor/Scoring/PolicyEngine/Sinks)
- **B.** PolicyEngine con contrato formal + 4 garantías
- **C.** Separación de namespaces Signal/Case/Decision en event stream
- **D.** EventLog persistente (SQLite/JSONL) para replay
- (Adicional) Score versioning (`v1.0_weighted_sum`)

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

**Reglas v2.0:**
- `no_llm_side_effects`: extractor LLM es pure function
- `no_direct_external_writes`: pipeline sólo escribe via sinks
- `requires_event_validation`: cada evento se valida contra data_contract

**Corrección A — Roles congelados por capa:**

| Capa | Rol | NO hace |
| ---- | --- | ------- |
| Extractor (LLM) | texto → estructura | decidir, escribir |
| Scoring | numérico + versionado | decidir, escribir |
| PolicyEngine | **única fuente de decisiones** | escribir externamente |
| Sinks | ejecución pura | decidir, evaluar triggers |

**Corrección B — PolicyEngine contract formal:**

```
Input:    CaseScored (case con score, score_version, is_canonical)
Output:   PolicyDecision (actions, reasons, boost_delta, decision_id, ruleset_version)

Garantías (4):
  1. no side effects       — no muta input, no escribe externo
  2. deterministic         — mismo input → mismo output
  3. versioned ruleset     — POLICY_RULESET_VERSION = "v1.0"
  4. idempotent per case_id — decision_id = hash(case_id, ruleset, actions)
```

**Corrección C — Namespaces Signal / Case / Decision:**

| Namespace | Eventos | Significado |
| --------- | ------- | ----------- |
| **Signal** | `signal_collected` | Observación cruda del mundo |
| **Case** | `entities_extracted`, `case_scored`, `case_deduplicated` | Estado agregado del sistema |
| **Decision** | `decision_issued`, `case_published` | Intención política del sistema |
| Meta | `event_rejected` | Evento inválido |

Renombrado: `policy_evaluated` (híbrido) → `decision_issued` (namespace Decision claro).

**Corrección D — EventLog persistente:**

```
event_id (PK) | event_type | payload (JSON) | timestamp | version
```

Backends: `sqlite` (default, atomic+queryable) | `jsonl` (fallback, simple).
Cada evento del bus se persiste al event_log para replay/auditoría.

```bash
# Requiere API key del LLM (GLM-4 o compatible OpenAI):
export RADAR_LLM_API_KEY=<tu-api-key>
# Opcional: webhook URL para sink de Sheets
export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<ID>/exec

python main.py --event-pipeline
```

**Comportamiento sin API key** (no hay modo mock):

```
$ python main.py --event-pipeline
✗ Missing LLM API key (env var RADAR_LLM_API_KEY is empty)
  Setear env var: export RADAR_LLM_API_KEY=<tu-api-key>
```

**Flujo de eventos con namespaces separados (corrección A+B+C+D)**:

```
[Signal] SignalCollected
  → handler_on_signal_collected
    → LLMExtractor.extract_to_case(signal)
    → publicar [Case] EntitiesExtracted
      → handler_on_entities_extracted
        → Scorer.update_case_score(case) [score_version = "v1.0_weighted_sum"]
        → publicar [Case] CaseScored
          → handler_on_case_scored (buffer para dedup batch)
            → merge_duplicates(casos)
            → por cada caso (canonical Y duplicate):
              → PolicyEngine.evaluate(case) → PolicyDecision
                [corrección B: pure, deterministic, versioned, idempotent]
                Reglas:
                  1. if score >= 80 → generate_whatsapp_intent
                  2. if jurisdiction in TARGET → boost_priority (+5)
                  3. if duplicate → suppress_output (corta evaluación)
                  4. if canonical → publish_to_sheets
              → apply_boost(case, decision) [fuera del engine, muta case]
              → publicar [Decision] DecisionIssued
              → publicar [Case] CaseDeduplicated
              → si decision.should_suppress() → continue
              → SinkFanOut.write_with_decision(case, decision) [corrección A: ejecución pura]
                → WhatsAppLinkSink.write_with_decision (ejecuta action)
                → GoogleSheetsWebhookSink.write_with_decision (ejecuta action)
              → publicar [Decision] CasePublished
            → SinkFanOut.flush_all() (POST a Apps Script)
```

**EventLog (corrección D)** — persistido en `download/sample_data/event_log.db`:

```sql
CREATE TABLE event_log (
    event_id    TEXT PRIMARY KEY,
    event_type  TEXT NOT NULL,
    payload     TEXT NOT NULL,  -- JSON
    timestamp   TEXT NOT NULL,  -- iso8601
    version     TEXT NOT NULL DEFAULT '1.0'
);
```

**PolicyDecision** — output del PolicyEngine (corrección B):

```python
PolicyDecision(
    case_id="case-xxx",
    actions=["generate_whatsapp_intent", "boost_priority", "publish_to_sheets"],
    reasons=["score 85 >= 80", "jurisdiction CABA in target [...]", "case is canonical"],
    boost_delta=5,
    metadata={"whatsapp_score_threshold": 80, "boost_delta": 5},
    decision_id="dec-2f69508c33a02a3b",  # idempotencia per case_id
    ruleset_version="v1.0",              # versioned ruleset
    timestamp="2026-06-30T13:20:53..."
)
```

**Sinks disponibles** (corrección A: ejecución pura, 0 lógica de negocio):

| Sink ID | Tipo | Ejecuta si | Escribe externamente? |
| ------- | ---- | ---------- | --------------------- |
| `whatsapp` | link_generator | `decision.should_generate_whatsapp()` | No (sólo genera link) |
| `google_sheets` | apps_script_webhook | `decision.should_publish_to_sheets()` | Sí (vía WebhookUploader) |

Cada sink expone `write_with_decision(case, decision)` (v2.0) y `write(case)` (legacy).

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
├── extractor.py         # [A] Extractor: texto → estructura (regex, no decide)
├── storage.py           # EvidenceStore + AuditTrail + ReviewQueue + SheetSync (legacy)
│
│   ── v2.0 (event-driven, LLM extractor, PolicyEngine) ──
│   ── [C] Namespaces: Signal / Case / Decision ──
├── event_types.py       # 7 tipos en 4 namespaces (Signal/Case/Decision/Meta)
├── event_validator.py   # Validación contra data_contract + score_version warning
├── event_bus.py         # In-process pub/sub con validación obligatoria
├── event_log.py         # [D] Append-only event log (SQLite/JSONL) para replay/auditoría
├── llm_extractor.py     # [A] Extractor: texto → estructura (LLM, no decide)
├── policy_engine.py     # [A+B] ÚNICA fuente de decisiones. Contract formal con 4 garantías
├── sinks.py             # [A] Sinks: ejecución pura (0 lógica de negocio)
├── event_pipeline.py    # Orquestador event-driven v2 con PolicyEngine + EventLog
│
│   ── shared ──
├── config.py            # Constantes + SCORE_VERSION = "v1.0_weighted_sum"
├── models.py            # Dataclasses: Signal, Case (+score_version), AuditEntry, ReviewAction
├── mock_sources.py      # Mock data AR + stubs documentados para Fase 2/3
├── scorer.py            # [A] Scoring: numérico + versionado (weighted_sum_v1)
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

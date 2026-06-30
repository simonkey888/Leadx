# Radar de Oportunidades — Prototipo Fase 1

Sistema de detección de oportunidades comerciales **públicas** relacionadas con
fotomultas, libre deuda, transferencia y regularización vehicular, con foco en
**trazabilidad** y **revisión humana obligatoria** (sin outreach automático).

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
├── main.py              # Entry point
├── pipeline.py          # Orquestador end-to-end
├── config.py            # Constantes del spec (jurisdicciones, pesos, etc.)
├── models.py            # Dataclasses: Signal, Case, AuditEntry, ReviewAction
├── mock_sources.py      # Mock data AR + stubs documentados para Fase 2/3
├── extractor.py         # Extracción regex + normalización + privacy filter
├── scorer.py            # Scoring 0-100 con 7 pesos del spec
├── dedup.py             # Dedup con 4 match keys + union-find
├── storage.py           # EvidenceStore + AuditTrail + ReviewQueue + SheetSync
└── review_cli.py        # CLI interactivo de revisión
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

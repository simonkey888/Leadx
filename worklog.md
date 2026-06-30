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

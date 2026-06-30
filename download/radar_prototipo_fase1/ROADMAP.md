# Roadmap — Radar de Oportunidades

Documento de transición entre fases. Cada fase tiene: objetivo, componentes del
spec implementados, criterios de graduación a la siguiente fase, y riesgos.

---

## Fase 1 — Validación (estado: ✓ implementado en este prototipo)

### Objetivo
Probar extracción, scoring y utilidad comercial con bajo volumen, sin dashboard
ni dominio propio.

### Componentes del spec cubiertos

| Componente spec       | Implementación                                    |
| --------------------- | ------------------------------------------------- |
| `drive`               | `EvidenceStore` en disco local (Fase 1)            |
| `structured_sheet_or_db` | `ReviewQueue` CSV/JSONL + Google Sheet (dry-run) |
| `llm_extractor`       | Stub documentado (`LLMExtractor`), regex en Fase 1 |
| `manual_review`       | `review_cli.py` interactivo                       |

### Compliance cubierto

- `audit_trail_required`: ✓ `AuditTrail` con hash chaining
- `evidence_storage_required`: ✓ `EvidenceStore` con SHA-256
- `human_review_required_for_action`: ✓ todos los casos nacen `needs_review`
- `no_private_data_collection`: ✓ `privacy_filter` rechaza PII

### Criterios de graduación a Fase 2

1. **Volumen**: procesar ≥ 200 señales reales (ingreso manual o RSS) sin degradación.
2. **Calidad de extracción**: precision ≥ 80% en muestra auditada de 50 casos.
3. **Calidad de scoring**: correlación manual ≥ 0.6 entre score automático y juicio
   humano de prioridad en 30 casos.
4. **Dedup**: detectar ≥ 90% de duplicados reales en muestra controlada.
5. **SLA**: revisión humana de casos críticos en < 24h durante 2 semanas.
6. **Decisión comercial**: al menos 5 contactos manuales exitosos desde la cola.

### Riesgos de Fase 1

- **R1 — Cobertura de fuentes**: Facebook y Marketplace no tienen API pública
  viable. Mitigación: ingreso manual por operador o RSS de grupos públicos si
  el grupo lo expone.
- **R2 — Sesgo del mock data**: las señales mock pueden no representar la
  variedad del lenguaje real. Mitigación: rotarOperadores que pegan señales
  reales en la sheet.
- **R3 — Falsos negativos del privacy filter**: patrones PII demasiado
  estrictos pueden dejar pasar PII real. Mitigación: revisar rejected_privacy
  en audit trail semanalmente y ajustar patrones.

---

## Fase 2 — Operación (siguiente)

### Objetivo
Gestionar flujo diario de casos con cola de revisión, dashboard, scoring
engine y dedup sobre DB real.

### Componentes del spec a cubrir

| Componente spec       | Implementación Fase 2                              |
| --------------------- | -------------------------------------------------- |
| `drive`               | Google Drive (carpeta compartida del negocio)     |
| `database`            | SQLite (local) o Postgres (Cloudflare D1)         |
| `dashboard`           | Next.js app con shadcn/ui (tabla + filtros + widgets) |
| `llm_extractor`       | GLM-4 / GPT-4 con schema JSON estricto             |
| `scoring_engine`      | Misma lógica que Fase 1 pero con historial         |
| `dedup_engine`        | DB con índices en match_keys + union-find en SQL  |

### Componentes nuevos vs Fase 1

1. **Conectores reales**:
   - `RealSourceStub.fetch_x_search` → X API v2 (Basic $100/mes)
   - `RealSourceStub.fetch_public_forums` → feedparser sobre foros AR
   - `RealSourceStub.fetch_news_and_comments` → feedparser sobre diarios
   - Facebook/Marketplace: ingreso manual validado en la sheet

2. **SheetSync en modo real**:
   - Service account configurada
   - Una fila por caso canónico
   - Sincronización bidireccional: cambios en la sheet actualizan el caso

3. **Dashboard web** (Next.js + Prisma):
   - Tabla principal con filtros (jurisdicción, score, source, status, vehicle_type, date)
   - Widgets: `new_cases`, `high_priority`, `trend_by_source`, `trend_by_jurisdiction`
   - Vista de detalle de caso con evidencia
   - Acciones de revisión in-line (approve/reject/duplicate/needs_more_data)

4. **Alertas** (cuando se cumple algún trigger de `ALERT_TRIGGERS`):
   - Email (Resend / SendGrid)
   - Workspace (Slack/Discord webhook)
   - Sheet update (marca visual en la fila)

### Criterios de graduación a Fase 3

1. **Volumen**: ≥ 50 casos canónicos por día, sostenido 30 días.
2. **Tiempo de revisión**: mediana < 4h para casos críticos.
3. **Conversión**: ≥ 15% de casos `approved` derivan en contacto comercial.
4. **Trazabilidad**: 0 incidentes de PII almacenada en 30 días.
5. **Disponibilidad**: dashboard con uptime ≥ 99% en 30 días.
6. **Cumplimiento legal**: documentación de bases legales por fuente firmada
   por asesor legal.

### Riesgos de Fase 2

- **R4 — Costo LLM**: extracción con LLM puede costar $50-200/mes a 50
  casos/día. Mitigación: cache de signals repetidas, batch processing,
  descuento por volumen.
- **R5 — Rate limits X API**: tier Basic permite 60 queries/15min. Mitigación:
  queue con backoff, queries con OR de keywords.
- **R6 — ToS Facebook**: aún con ingreso manual, el scraping masivo viola
  ToS. Mitigación:-policy explícita de "ingreso individual por operador
  autorizado", sin automatización.

---

## Fase 3 — Escala (futuro)

### Objetivo
Public intake, multi-source monitoring, team workflow.

### Componentes del spec a cubrir

| Componente spec       | Implementación Fase 3                              |
| --------------------- | -------------------------------------------------- |
| `domain`              | Dominio propio (ej: radar.tudominio.com.ar)       |
| `cloudflare`          | Cloudflare Pages/Workers + D1 (Postgres) + R2     |
| `landing`             | Landing pública explicando servicio + intake form |
| `dashboard`           | Multi-usuario con roles (operator / admin / auditor) |
| `queue_system`        | Asignación de casos a operadores, escalonado      |
| `alerts`              | Email + Workspace + SMS para críticos              |
| `storage`             | R2 (S3-compatible) para evidencia + D1 para casos |

### Nuevos módulos

1. **Intake público** (form en landing): el usuario puede auto-reportar su
   caso. Estos casos nacen con `status=intake_pending` y `source_id=public_intake`.
2. **Multi-equipo**: operadores asignados a jurisdicciones específicas.
3. **Auditoría externa**: rol de auditor con read-only a todo el audit trail.
4. **API pública** (rate-limited): para integración con CRM del negocio.
5. **Backup y DR**: snapshot diario de D1 + R2, retención 90 días.

### Criterios de graduación (no aplica — Fase 3 es estado estable)

Métricas operacionales:
- ≥ 200 casos canónicos/día
- Mediana de revisión < 2h para críticos
- ≥ 25% de approved → contacto exitoso
- NPS del operador ≥ 8/10
- 0 incidentes de seguridad en 90 días

### Riesgos de Fase 3

- **R7 — Escala legal**: mayor volumen puede llamar atención de plataformas.
  Mitigación: mantener ingreso manual para FB/Marketplace, usar APIs oficiales
  para X/RSS, no scraping.
- **R8 — Privacidad de intake público**: usuarios auto-reportando pueden
  incluir PII. Mitigación: privacy_filter estricto en intake, + checkbox de
  consentimiento, + política de retención clara.
- **R9 — Costo Cloudflare**: D1 + R2 + Workers escala con volumen. Mitigación:
  cache agresivo, batch processing, free tier cubre primeros 10K req/día.

---

## Tabla resumen

| Fase   | Componentes nuevos                  | Volumen objetivo   | Costo estimado (mensual) |
| ------ | ----------------------------------- | ------------------ | ------------------------ |
| Fase 1 | Prototipo Python + mock             | 20-50 señales/día  | $0 (sólo tiempo)         |
| Fase 2 | Dashboard + DB + conectores reales  | 50-200 casos/día   | $150-400 (LLM + X API)   |
| Fase 3 | Dominio + Cloudflare + intake       | 200+ casos/día     | $300-800 (Cloudflare + LLM + X) |

---

## Decisión de arquitectura: por qué este roadmap y no otro

1. **Por qué Fase 1 sin dashboard**: el spec lo dice explícitamente
   (`dashboard_required: false` para Fase 1). La cola CSV + CLI alcanza para
   validar utilidad comercial sin invertir en UI prematura.

2. **Por qué Fase 2 con dashboard antes que Fase 3**: el salto a multi-equipo
   (Fase 3) requiere un dashboard sólido y estable. Construir dominio + intake
   público sin haber validado el workflow interno es arriesgado.

3. **Por qué LLM en Fase 2 y no Fase 1**: el regex extractor es determinista,
  sin costo, y suficiente para validar el modelo de scoring. Introducir LLM
  antes agrega variables (latencia, costo, no-determinismo) que complican la
  validación.

4. **Por qué Cloudflare en Fase 3 y no Fase 2**: en Fase 2 el dashboard puede
  vivir en un VPS simple o incluso en localhost accesible por túnel. Cloudflare
  aporta valor real cuando hay dominio + intake público + multi-equipo.

5. **Por qué no scrapers reales en ninguna fase**: el spec es claro con
   `respect_platform_terms: True` y `no_private_profile_harvesting: True`.
   Facebook y Marketplace no ofrecen API pública confiable; scraping viola
   ToS. La alternativa viable es ingreso manual validado o APIs oficiales
   pagas (Meta Content Library para investigadores acreditados).

# Radar Leads PRO — Dashboard + Pipeline

Sistema de detección de oportunidades comerciales públicas relacionadas con
fotomultas, libre deuda, transferencia y regularización vehicular en Argentina.

## Arquitectura

```
static_dashboard + dynamic_json

┌─────────────────────────────────────────────────────────┐
│  GitHub Actions (cron 0 */3 * * *)                      │
│  ↓                                                       │
│  python generate_payload.py                              │
│  ↓                                                       │
│  z-ai web_search → extract → normalize → score → dedup  │
│  ↓                                                       │
│  data/dashboard_payload.json  (overwrite)                │
│  data/stats.json              (update)                   │
│  data/history.json            (append)                   │
│  ↓                                                       │
│  git commit + push                                       │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│  GitHub Pages (static hosting)                          │
│  ↓                                                       │
│  dashboard_prototype.html (FIJO, nunca se regenera)     │
│  ↓                                                       │
│  fetch('/data/dashboard_payload.json')                   │
│  ↓                                                       │
│  Render dashboard con datos actualizados                 │
│  Auto-refresh cada 60s                                   │
└─────────────────────────────────────────────────────────┘
```

**Regla de oro:** el HTML del dashboard NUNCA se regenera. Sólo se actualizan los JSONs.

## Archivos del proyecto

| Archivo | Rol | Se regenera? |
|---------|-----|---------------|
| `dashboard_prototype.html` | Frontend (single-file, 130KB) | ❌ No, es fijo |
| `generate_payload.py` | Pipeline (genera JSONs) | ❌ No, es código |
| `data/dashboard_payload.json` | Datos live del dashboard | ✅ Sí, cada 3h |
| `data/stats.json` | Métricas acumuladas | ✅ Sí, cada 3h |
| `data/history.json` | Historial de runs | ✅ Sí, cada 3h (append) |
| `.github/workflows/radar-cron.yml` | Cron job | ❌ No, es config |
| `sample_dashboard_payload.json` | Ejemplo de payload | ❌ No, es referencia |

## Cómo usar

### Local (desarrollo)

```bash
# 1. Generar payload
python generate_payload.py

# 2. Abrir dashboard
# Opción A: doble click en dashboard_prototype.html
#   → fetch falla (file://), usa datos embebidos del prototipo
#
# Opción B: server local
python -m http.server 8000
#   → abrir http://localhost:8000/dashboard_prototype.html
#   → fetch('./data/dashboard_payload.json') funciona
```

### Producción (GitHub Pages)

```bash
# 1. Push al repo
git add .
git commit -m "init radar"
git push

# 2. Activar GitHub Pages
#    Settings → Pages → Source: main branch → / (root)
#    URL: https://<usuario>.github.io/<repo>/dashboard_prototype.html

# 3. Configurar secret ZAI_API_KEY
#    Settings → Secrets and Variables → Actions → New secret
#    Name: ZAI_API_KEY
#    Value: <tu-api-key-de-z-ai>

# 4. El cron job corre cada 3 horas automáticamente
#    O disparar manualmente: Actions → Radar Leads → Run workflow
```

## Pipeline (7 pasos)

### 1. collect_public_sources
Búsquedas públicas vía z-ai web_search CLI. 20 queries orientadas a dolor explícito:
- Reddit: `site:reddit.com no puedo transferir auto argentina`
- Facebook: `site:facebook.com me llegó fotomulta`
- X: `site:x.com multa transferencia problema`
- Frases humanas: `me llegó una multa y no es mi auto`

### 2. extract_entities
Extrae: persona, problema, provincia, ciudad, vehículo, patente, fecha, contacto, whatsapp, teléfono, source_url, platform, quoted_text.

### 3. normalize_records
- Fechas → ISO 8601 cuando es posible
- Teléfonos → formato E.164
- URLs → canonical (sin tracking params)
- Snippets → trim
- Provincias → nombres estandarizados

### 4. classify_and_score
3 labels: `real_lead` (score >= 60) | `commercial_signal` (30-59) | `reject` (< 30)

Scoring:
| Signal | Puntos |
|--------|--------|
| multa_or_fotomulta | +60 |
| transfer_problem | +45 |
| libre_deuda_problem | +35 |
| 08_or_document_problem | +40 |
| public_contact_visible | +25 |
| recent_0_3_days | +20 |
| recent_4_7_days | +10 |
| argentina_signal | +15 |
| institutional_penalty | -40 |
| generic_penalty | -30 |
| foreign_country_penalty | -80 |

### 5. deduplicate_cases
SHA-256 composite hash de: `normalized_text + source_url + persona + platform`

### 6. build_dashboard_payload
Genera payload con schema:
```json
{
  "generated_at": "ISO timestamp",
  "run_id": "hash12",
  "summary": { "total_leads": N, "hot_leads": N, ... },
  "leads_hot": [...],
  "leads_warm": [...],
  "insights": ["patrón 1", "patrón 2", ...],
  "meta": { "version": "1.0", "runtime_seconds": N }
}
```

### 7. publish_artifacts
- Overwrite `data/dashboard_payload.json`
- Append a `data/history.json` (últimas 100 runs)
- Update `data/stats.json` (métricas acumuladas)
- Git commit + push (en GitHub Actions)

## Dashboard

### Command Center (NOC-style)
6 KPIs + Insights IA:
- 🔥 Leads críticos (score >= 90)
- 🟢 Nuevos desde última ejecución
- 📞 Con WhatsApp disponible
- ⏰ Próximos a vencer (>3 días sin revisar)
- 📈 Conversión estimada
- 🧠 Insights IA (patrones auto-detectados)

### Features
- Virtual scroll (10K+ leads sin lag)
- Drawer lateral (score breakdown, reasoning, notes)
- Filtros temporales + quick filters + búsqueda instantánea
- Keyboard shortcuts (/, j, k, Enter, Esc, r, c, i, e)
- localStorage (estado de revisión + notas)
- Export JSON / CSV
- Auto-refresh cada 60s
- Responsive mobile

### Fetch dinámico
El dashboard intenta cargar datos en este orden:
1. `fetch('/data/dashboard_payload.json')` (producción)
2. `fetch('./data/dashboard_payload.json')` (local con server)
3. `fetch('data/dashboard_payload.json')` (relativo)
4. Fallback a `__EMBEDDED_PAYLOAD__` (datos embebidos del prototipo)

## Compliance

- ✅ `only_public_data` — sólo contenido público indexado
- ✅ `no_login_scraping` — nunca bypass de logins
- ✅ `no_private_harvesting` — no recolecta datos privados
- ✅ `no_auto_messaging` — no envía mensajes automáticos
- ✅ `human_review_required` — revisión humana obligatoria antes de contacto
- ✅ `pii_handling` — store_minimized (sólo lo públicamente visible)

## Deployment (free stack)

| Componente | Servicio | Costo |
|------------|----------|-------|
| Cron job | GitHub Actions | Gratis |
| Hosting | GitHub Pages | Gratis |
| Repo | GitHub | Gratis |
| Buscador | z-ai web_search | API key |
| CDN (opcional) | Cloudflare | Gratis |

### Opcional: dominio custom
```
Cloudflare → CNAME → <usuario>.github.io
```

## Operación

### Cambiar frecuencia del cron
Editar `.github/workflows/radar-cron.yml`:
```yaml
schedule:
  - cron: '0 */3 * * *'  # cada 3 horas
  # - cron: '0 * * * *'   # cada hora
  # - cron: '0 9,12,18 * * *'  # 3 veces al día
```

### Ejecutar manualmente
GitHub → Actions → "Radar Leads — Cron Pipeline" → Run workflow

### Ver historial
`data/history.json` contiene las últimas 100 runs con summary de cada una.

### Métricas acumuladas
`data/stats.json` tiene:
- total_runs
- total_leads_all_time
- total_hot_leads_all_time
- avg_hot_per_run
- runs_today
- last_7_days (resúmenes)

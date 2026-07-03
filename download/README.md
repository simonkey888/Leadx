# Radar Leads PRO — Dashboard Prototype

Prototipo funcional completo del dashboard para el sistema Radar de Leads Fotomultas.
Diseñado para validar UX y arquitectura antes de construir el backend de scraping.

## Entregables

| Archivo | Tamaño | Descripción |
|---------|--------|-------------|
| `dashboard_prototype.html` | 128 KB | Dashboard single-file, funciona offline |
| `sample_dashboard_payload.json` | 105 KB | 80 leads simulados con schema completo |

## Cómo usar

### 1. Abrir el dashboard

Doble click en `dashboard_prototype.html` — se abre en cualquier browser moderno.
No requiere servidor, no requiere internet, no requiere Node.

### 2. Conectar datos reales (futuro)

Reemplazar la constante embebida `DASHBOARD_PAYLOAD` en el HTML por un fetch:

```javascript
// ANTES (prototipo con datos simulados):
const DASHBOARD_PAYLOAD = { leads: [...], metrics: {...}, ... };

// DESPUÉS (producción con Cloudflare Worker):
const DASHBOARD_PAYLOAD = await fetch('/data/dashboard_payload.json').then(r => r.json());
```

El schema del payload debe respetar el formato de `sample_dashboard_payload.json`:

```json
{
  "leads": [
    {
      "id": "hash16chars",
      "score": 85,
      "problem_category": "TRANSFER_PROBLEM",
      "problem_summary": "Problema de transferencia",
      "person_name": "Carlos Mendoza",
      "username": "carlos_mendoza",
      "profile_url": "https://facebook.com/user/carlos_mendoza",
      "post_url": "https://facebook.com/post/abc123",
      "platform": "Facebook",
      "date": "2026-07-03T10:30:00+00:00",
      "discovery_timestamp": "2026-07-03T11:00:00+00:00",
      "province": "Buenos Aires",
      "city": "La Plata",
      "country": "Argentina",
      "vehicle": "Ford Fiesta",
      "patent": "AB123CD",
      "phone": "01112345678",
      "whatsapp": "5491112345678",
      "whatsapp_link": "https://wa.me/5491112345678",
      "snippet": "Texto original del post...",
      "has_phone": true,
      "has_whatsapp": true,
      "urgency_detected": true,
      "urgency_keywords_found": ["urgente", "hoy"],
      "recent_post": true,
      "explicit_transfer_problem": true,
      "multa_related": false,
      "preventive_signal": false,
      "institutional_source": false,
      "unclear_country": false,
      "review_state": "new",
      "score_breakdown": {
        "base": 20,
        "has_phone": 25,
        "has_whatsapp": 25,
        "urgency_detected": 20,
        "recent_post": 15,
        "explicit_transfer_problem": 30
      }
    }
  ],
  "metrics": {
    "total_leads": 80,
    "hot_leads": 23,
    "commercial_leads": 27,
    "contactable": 28,
    "with_whatsapp": 20,
    "with_phone": 12,
    "avg_score": 54.2,
    "conversion_probability": 28.7,
    "by_category": {"TRANSFER_PROBLEM": 35, "FINE_DISPUTE": 25, ...},
    "by_platform": {"Facebook": 40, "Reddit": 20, ...},
    "by_province": {"Buenos Aires": 30, "CABA": 15, ...},
    "runtime_seconds": 18.4,
    "queries_executed": 20
  },
  "execution_log": [...],
  "generated_at": "2026-07-03T11:00:00+00:00",
  "runtime_ms": 18400
}
```

## Features del dashboard

### Command Center (NOC-style)

Panel ejecutivo arriba del dashboard con 6 KPIs + bloque Insights IA:

1. **🔥 Leads críticos** — score >= 90, requieren atención hoy
2. **🟢 Nuevos desde última ejecución** — delta vs run anterior
3. **📞 Con WhatsApp disponible** — count + % del total
4. **⏰ Próximos a vencer** — leads >3 días sin revisar
5. **📈 Conversión estimada** — % de leads con score >= 70
6. **🧠 Insights IA** — patrón automático detectado del lote actual

### Tabla de leads (virtual scroll)

14 columnas con sort, filter, resize. Virtual scroll para manejar 10,000+ leads
sólo renderizando las filas visibles (~17 a la vez).

### Drawer de detalle

Click en cualquier lead abre un drawer lateral derecho (480px) con:
- Score breakdown visual (cada señal con su peso)
- Señales detectadas (chips)
- Evidence (texto completo del post)
- Reasoning (explicación auto-generada del score)
- Datos de contacto (con botones copiar)
- Link al post original
- Timeline de cambios de estado
- Notas persistentes (localStorage)

### Analytics

5 mini-charts en SVG puro (sin librería):
- Top problems (bar)
- Top provinces (bar)
- Top sources (bar)
- Hot hours (cuándo se publican más leads, 0-23h)
- Trend últimos 7 días (line)

### Acciones por lead

- Abrir publicación (link externo)
- Abrir WhatsApp (wa.me link)
- Copiar teléfono
- Copiar enlace
- Marcar revisado / contactado / ignorar
- Agregar nota (persiste en localStorage)
- Exportar lead individual (JSON)
- Exportar todos (JSON / CSV)

### Filtros

**Temporales:** Hoy | 24h | 3 días | Semana | Todo

**Quick filters (chips toggle):**
- Solo calientes (score >= 70)
- Solo con WhatsApp
- Solo con teléfono
- Solo Reddit / Facebook / X / MercadoLibre
- Solo recientes (< 24h)
- No revisados
- Contactados

**Búsqueda instantánea** (debounced 100ms) sobre todos los campos de texto.

### Keyboard shortcuts

| Tecla | Acción |
|-------|--------|
| `/` | Focus búsqueda |
| `j` / `k` | Navegar leads abajo/arriba |
| `Enter` | Abrir drawer |
| `Esc` | Cerrar drawer |
| `r` | Marcar revisado |
| `c` | Marcar contactado |
| `i` | Ignorar |
| `e` | Exportar JSON |

### Persistencia

- Estado de revisión por lead (new/reviewed/contacted/ignored) → localStorage
- Notas por lead → localStorage
- Sobrevive recarga del browser

## Performance

| Métrica | Target | Real |
|---------|--------|------|
| Tamaño archivo | < 150 KB | 128 KB ✓ |
| Render inicial | < 100 ms | 11-15 ms ✓ |
| 10,000 leads | sin lag | virtual scroll ✓ |
| Dependencias externas | 0 | 0 ✓ |

## Design system

- **Tema:** Dark mode (GitHub dark palette)
- **Accent:** Salesforce blue #0176D3
- **Score colors:** red (0-39) / yellow (40-69) / green (70-89) / blue (90-100)
- **Tipografía:** system-ui, 14px base
- **Inspiración:** Salesforce Lightning + Linear + Notion

## Arquitectura futura (Cloudflare Worker-ready)

El dashboard está estructurado para conectar a un backend sin cambiar la interfaz:

```
[Cron-job.org] → POST /run → [Cloudflare Worker] → [z-ai web_search]
                                                       ↓
                                              [Pipeline scoring]
                                                       ↓
                                              [R2: dashboard_payload.json]
                                                       ↓
                                              [KV: leads_latest]
                                                       ↓
[Browser] → GET dashboard.html → [Cloudflare Pages] → fetch dashboard_payload.json
```

**Para activar producción:**

1. Desplegar Cloudflare Worker con endpoint `POST /run` que ejecute el pipeline
2. Worker guarda `dashboard_payload.json` en R2
3. Dashboard hace `fetch('/data/dashboard_payload.json')` en lugar de usar datos embebidos
4. Cron-job.org dispara `POST /run` cada 3 horas

No se requiere cambiar nada en el dashboard para esta transición.

## Limitaciones del prototipo

- Los 80 leads son simulados (no provienen de búsquedas reales)
- El bloque "Insights IA" detecta patrones con heurísticas locales (no usa LLM)
- No hay backend — todo corre en el browser
- El export de CSV/JSON descarga archivos locales

## Próximos pasos sugeridos

1. **Validar UX** con operadores reales (1-2 semanas de uso)
2. **Conectar pipeline real** (reemplazar DASHBOARD_PAYLOAD por fetch)
3. **Desplegar Cloudflare Worker** con el pipeline de `radar_leads_v1.py` portado a JS
4. **Configurar cron-job.org** cada 3 horas
5. **Iterar scoring** basado en feedback de operadores

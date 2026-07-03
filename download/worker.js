/**
 * LeadX Worker v10 — AUTOCONTENIDO
 * =================================
 * Un solo archivo. Sin env.ASSETS. Sin assets binding.
 * HTML embebido + APIs KV. El bug "Cannot read properties of undefined (reading 'fetch')" se acaba de morir.
 *
 * Endpoints:
 *   GET  /              → HTML del dashboard (embebido)
 *   GET  /api/leads     → JSON con leads desde KV
 *   GET  /api/metrics   → JSON con métricas
 *   POST /api/ingest    → Recibe batch del pipeline Python (auth: X-Webhook-Secret)
 */

// ─────────────────────────────────────────────────────────────
// HTML DEL DASHBOARD (embebido, sin dependencias externas)
// ─────────────────────────────────────────────────────────────
const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LeadX — Radar de Oportunidades</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0a0e1a;
    color: #e2e8f0;
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border-bottom: 1px solid #334155;
    padding: 20px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .header h1 {
    font-size: 24px;
    background: linear-gradient(135deg, #38bdf8, #818cf8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .header .meta {
    font-size: 12px;
    color: #64748b;
    text-align: right;
  }
  .controls {
    background: #0f172a;
    padding: 16px 32px;
    border-bottom: 1px solid #1e293b;
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: center;
  }
  .controls button {
    background: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s;
  }
  .controls button:hover { background: #334155; border-color: #475569; }
  .controls button.active { background: #0ea5e9; color: white; border-color: #0284c7; }
  .controls input[type="text"] {
    background: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    flex: 1;
    min-width: 200px;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    padding: 20px 32px;
  }
  .stat-card {
    background: #1e293b;
    border: 1px solid #334155;
    padding: 16px;
    border-radius: 8px;
  }
  .stat-card .label {
    font-size: 11px;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .stat-card .value {
    font-size: 28px;
    font-weight: 700;
    margin-top: 4px;
  }
  .stat-card.hot .value { color: #fbbf24; }
  .stat-card.total .value { color: #38bdf8; }
  .stat-card.contact .value { color: #10b981; }
  .stat-card.urgent .value { color: #f87171; }
  .lead-list {
    padding: 0 32px 32px;
    display: grid;
    gap: 12px;
  }
  .lead-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-left: 4px solid #475569;
    padding: 16px;
    border-radius: 8px;
    transition: all 0.15s;
  }
  .lead-card:hover { border-color: #64748b; transform: translateY(-1px); }
  .lead-card.hot { border-left-color: #fbbf24; }
  .lead-card.urgent { border-left-color: #f87171; }
  .lead-card.normal { border-left-color: #38bdf8; }
  .lead-card .top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 8px;
  }
  .lead-card .title {
    font-weight: 600;
    color: #f1f5f9;
    line-height: 1.4;
    flex: 1;
  }
  .lead-card .score-badge {
    background: #0f172a;
    border: 1px solid #475569;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 700;
    color: #fbbf24;
    white-space: nowrap;
  }
  .lead-card .score-badge.cold { color: #64748b; }
  .lead-card .score-badge.warm { color: #38bdf8; }
  .lead-card .score-badge.hot { color: #fbbf24; }
  .lead-card .score-badge.urgent { color: #f87171; }
  .lead-card .snippet {
    color: #94a3b8;
    font-size: 13px;
    line-height: 1.5;
    margin-bottom: 10px;
  }
  .lead-card .meta-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 11px;
    color: #64748b;
    margin-bottom: 10px;
  }
  .lead-card .meta-row .chip {
    background: #0f172a;
    border: 1px solid #334155;
    padding: 2px 8px;
    border-radius: 4px;
  }
  .lead-card .actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .lead-card .actions a, .lead-card .actions button {
    background: #0f172a;
    color: #cbd5e1;
    border: 1px solid #334155;
    padding: 5px 10px;
    border-radius: 4px;
    font-size: 11px;
    text-decoration: none;
    cursor: pointer;
    transition: all 0.15s;
  }
  .lead-card .actions a:hover, .lead-card .actions button:hover {
    background: #1e293b;
    border-color: #475569;
  }
  .lead-card .actions a.wa { color: #25d366; border-color: #1f5e3d; }
  .lead-card .actions a.wa:hover { background: #1f5e3d; }
  .empty {
    text-align: center;
    padding: 60px 32px;
    color: #64748b;
  }
  .empty .icon { font-size: 48px; margin-bottom: 12px; }
  .loading {
    text-align: center;
    padding: 40px;
    color: #64748b;
  }
  .error-banner {
    background: #7f1d1d;
    color: #fee2e2;
    padding: 12px 32px;
    font-size: 13px;
    border-bottom: 1px solid #991b1b;
  }
  .footer {
    text-align: center;
    padding: 24px;
    color: #475569;
    font-size: 11px;
    border-top: 1px solid #1e293b;
  }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>LeadX</h1>
    <div style="font-size:11px;color:#64748b;margin-top:2px;">Radar de Oportunidades · Argentina</div>
  </div>
  <div class="meta">
    <div id="last-update">—</div>
    <div id="source-tag">—</div>
  </div>
</div>

<div id="error-banner" class="error-banner" style="display:none;"></div>

<div class="controls">
  <button id="filter-todo" class="active">Todos</button>
  <button id="filter-hot">🔥 Hot (≥50)</button>
  <button id="filter-urgent">🚨 Urgentes</button>
  <button id="filter-contact">📞 Contactables</button>
  <input type="text" id="search" placeholder="Buscar texto..." />
  <button id="refresh">↻ Refrescar</button>
</div>

<div class="stats" id="stats"></div>
<div class="lead-list" id="leads"><div class="loading">Cargando leads...</div></div>

<div class="footer">LeadX v10 · OSINT Legal Intelligence Engine</div>

<script>
const STATE = {
  payload: null,
  filter: 'todo',
  search: '',
  loading: false,
  lastValid: null,
};

function normalizeLead(l) {
  const score = l.scoring?.final_score ?? l.score ?? 0;
  return {
    id: l.id || 'sin-id',
    score: score,
    title: l.title || l.snippet || l.lead_reason || 'Sin título',
    snippet: l.snippet || l.summary || '',
    url: l.source?.url || l.url || '#',
    platform: l.source?.type || l.platform || 'unknown',
    intent: l.intent_cluster || l.intent || '—',
    whatsapp: l.contact?.whatsapp || l.whatsapp_publico || '',
    phone: l.contact?.phone || l.telefono_publico || '',
    fecha: l.fecha_iso || l.discovery_timestamp || '',
    actions: l.actions || [],
    lead_reason: l.lead_reason || '',
    entity: l.entity_ref || l.entity || {},
  };
}

async function loadPayload() {
  STATE.loading = true;
  try {
    const res = await fetch('/api/leads?limit=500', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (!data || !Array.isArray(data.leads_all)) {
      throw new Error('Respuesta inválida: leads_all no es array');
    }
    STATE.payload = data;
    STATE.lastValid = data;
    hideError();
    return data;
  } catch (e) {
    showError('Error cargando leads: ' + e.message);
    if (STATE.lastValid) return STATE.lastValid;
    return null;
  } finally {
    STATE.loading = false;
  }
}

function showError(msg) {
  const el = document.getElementById('error-banner');
  el.textContent = '⚠ ' + msg;
  el.style.display = 'block';
}
function hideError() {
  document.getElementById('error-banner').style.display = 'none';
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function scoreClass(s) {
  if (s >= 80) return 'urgent';
  if (s >= 50) return 'hot';
  if (s >= 20) return 'warm';
  return 'cold';
}

function renderStats(p) {
  const leads = (p.leads_all || []).map(normalizeLead);
  const hot = leads.filter(l => l.score >= 50).length;
  const urgent = leads.filter(l => l.score >= 80).length;
  const contact = leads.filter(l => l.whatsapp || l.phone).length;
  const html = \`
    <div class="stat-card total"><div class="label">Total Leads</div><div class="value">\${leads.length}</div></div>
    <div class="stat-card hot"><div class="label">Hot (≥50)</div><div class="value">\${hot}</div></div>
    <div class="stat-card urgent"><div class="label">Urgentes (≥80)</div><div class="value">\${urgent}</div></div>
    <div class="stat-card contact"><div class="label">Contactables</div><div class="value">\${contact}</div></div>
  \`;
  document.getElementById('stats').innerHTML = html;
  document.getElementById('last-update').textContent = p.meta?.generated_at
    ? 'Actualizado: ' + new Date(p.meta.generated_at).toLocaleString('es-AR')
    : (p.meta?.version ? 'v' + p.meta.version : '—');
  document.getElementById('source-tag').textContent = p.meta?.source || '—';
}

function renderLeads(p) {
  let leads = (p.leads_all || []).map(normalizeLead);

  // Filter
  if (STATE.filter === 'hot') leads = leads.filter(l => l.score >= 50);
  else if (STATE.filter === 'urgent') leads = leads.filter(l => l.score >= 80);
  else if (STATE.filter === 'contact') leads = leads.filter(l => l.whatsapp || l.phone);

  // Search
  if (STATE.search) {
    const q = STATE.search.toLowerCase();
    leads = leads.filter(l =>
      (l.title + ' ' + l.snippet + ' ' + l.intent).toLowerCase().includes(q)
    );
  }

  // Sort by score desc
  leads.sort((a, b) => b.score - a.score);

  const container = document.getElementById('leads');
  if (leads.length === 0) {
    container.innerHTML = '<div class="empty"><div class="icon">📭</div><h3>Sin leads para este filtro</h3><p>Probá con otro filtro o esperá la próxima corrida del pipeline.</p></div>';
    return;
  }

  const html = leads.map(l => {
    const cls = l.score >= 80 ? 'urgent' : l.score >= 50 ? 'hot' : 'normal';
    const sCls = scoreClass(l.score);
    const fechaStr = l.fecha ? new Date(l.fecha).toLocaleDateString('es-AR') : '';
    const actions = [];

    // Acción principal: abrir fuente
    actions.push('<a href="' + escapeHtml(l.url) + '" target="_blank" rel="noopener">🔗 Fuente</a>');

    // WhatsApp
    if (l.whatsapp) {
      const wa = l.whatsapp.replace(/[^0-9]/g, '');
      actions.push('<a class="wa" href="https://wa.me/' + wa + '" target="_blank" rel="noopener">🟢 WhatsApp</a>');
    }

    // Phone
    if (l.phone) {
      actions.push('<a href="tel:' + escapeHtml(l.phone) + '">📞 Llamar</a>');
    }

    // Acciones del pipeline
    (l.actions || []).forEach(a => {
      if (!a || !a.url) return;
      const label = a.label || a.type || 'acción';
      actions.push('<a href="' + escapeHtml(a.url) + '" target="_blank" rel="noopener">' + escapeHtml(label) + '</a>');
    });

    return \`
      <div class="lead-card \${cls}">
        <div class="top">
          <div class="title">\${escapeHtml(l.title)}</div>
          <div class="score-badge \${sCls}">\${l.score}</div>
        </div>
        \${l.snippet ? '<div class="snippet">' + escapeHtml(l.snippet) + '</div>' : ''}
        <div class="meta-row">
          <span class="chip">📡 \${escapeHtml(l.platform)}</span>
          <span class="chip">🎯 \${escapeHtml(l.intent)}</span>
          \${fechaStr ? '<span class="chip">📅 ' + fechaStr + '</span>' : ''}
          \${l.whatsapp ? '<span class="chip">🟢 WA</span>' : ''}
        </div>
        <div class="actions">\${actions.join('')}</div>
      </div>
    \`;
  }).join('');

  container.innerHTML = html;
}

function render() {
  if (!STATE.payload) return;
  renderStats(STATE.payload);
  renderLeads(STATE.payload);
}

// Filter buttons
['todo', 'hot', 'urgent', 'contact'].forEach(f => {
  document.getElementById('filter-' + f).addEventListener('click', () => {
    STATE.filter = f;
    document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
    document.getElementById('filter-' + f).classList.add('active');
    render();
  });
});

document.getElementById('search').addEventListener('input', (e) => {
  STATE.search = e.target.value;
  render();
});

document.getElementById('refresh').addEventListener('click', async () => {
  document.getElementById('refresh').textContent = '⏳ Cargando...';
  await loadPayload();
  render();
  document.getElementById('refresh').textContent = '↻ Refrescar';
});

// Init
(async () => {
  await loadPayload();
  render();
})();

// Auto-refresh 60s (non-destructive)
setInterval(async () => {
  const data = await loadPayload();
  if (data) render();
}, 60000);
</script>
</body>
</html>`;

// ─────────────────────────────────────────────────────────────
// WORKER PRINCIPAL
// ─────────────────────────────────────────────────────────────
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '*';

    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': origin === 'null' ? '*' : origin,
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Webhook-Secret',
      'Access-Control-Max-Age': '86400',
    };

    // Handle preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // ─── GET / ─── Dashboard HTML
    if (url.pathname === '/' || url.pathname === '/index.html') {
      return new Response(DASHBOARD_HTML, {
        headers: { 'Content-Type': 'text/html; charset=utf-8' },
      });
    }

    // ─── GET /api/leads ───
    if (url.pathname === '/api/leads' && request.method === 'GET') {
      try {
        const raw = await env.LEADX_KV.get('leads:live');
        if (!raw) {
          return jsonResponse({
            leads_all: [],
            leads_hot: [],
            summary: { total_leads: 0, hot_leads: 0 },
            meta: { version: '10.0', source: 'empty_kv', generated_at: new Date().toISOString() }
          }, corsHeaders);
        }
        const data = JSON.parse(raw);
        // Asegurar estructura mínima
        if (!data.leads_all) data.leads_all = [];
        if (!data.leads_hot) data.leads_hot = (data.leads_all || []).filter(l => (l.scoring?.final_score ?? l.score ?? 0) >= 50);
        if (!data.summary) data.summary = { total_leads: data.leads_all.length, hot_leads: data.leads_hot.length };
        if (!data.meta) data.meta = { version: '10.0', source: 'kv', generated_at: new Date().toISOString() };
        return jsonResponse(data, corsHeaders);
      } catch (e) {
        return jsonResponse({
          error: 'kv_read_failed',
          message: e.message,
          leads_all: [],
          meta: { version: '10.0', source: 'error' }
        }, corsHeaders, 500);
      }
    }

    // ─── GET /api/metrics ───
    if (url.pathname === '/api/metrics' && request.method === 'GET') {
      try {
        const raw = await env.LEADX_KV.get('leads:live');
        if (!raw) {
          return jsonResponse({
            total_leads: 0, hot_leads: 0, contactable_leads: 0,
            urgent_leads: 0, status: 'empty'
          }, corsHeaders);
        }
        const data = JSON.parse(raw);
        const leads = data.leads_all || [];
        const hot = leads.filter(l => (l.scoring?.final_score ?? l.score ?? 0) >= 50);
        const urgent = leads.filter(l => (l.scoring?.final_score ?? l.score ?? 0) >= 80);
        const contact = leads.filter(l => l.contact?.whatsapp || l.contact?.phone || l.whatsapp_publico);
        return jsonResponse({
          total_leads: leads.length,
          hot_leads: hot.length,
          urgent_leads: urgent.length,
          contactable_leads: contact.length,
          status: 'ok',
          last_updated: data.meta?.generated_at || null,
          version: data.meta?.version || 'unknown'
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ error: e.message, status: 'error' }, corsHeaders, 500);
      }
    }

    // ─── POST /api/ingest ───
    if (url.pathname === '/api/ingest' && request.method === 'POST') {
      // Auth check
      const secret = request.headers.get('X-Webhook-Secret');
      const expected = env.INGEST_SECRET;
      if (!expected) {
        return jsonResponse({ status: 'rejected', reason: 'no_secret_configured' }, corsHeaders, 500);
      }
      if (secret !== expected) {
        return jsonResponse({ status: 'rejected', reason: 'auth_failed' }, corsHeaders, 401);
      }

      try {
        const body = await request.json();
        const newLeads = body.leads_all || [];
        const newHot = body.leads_hot || newLeads.filter(l => (l.scoring?.final_score ?? l.score ?? 0) >= 50);

        // Anti-wipe: si vienen <5 leads, NO sobrescribir
        const prevRaw = await env.LEADX_KV.get('leads:live');
        let prevLeads = [];
        if (prevRaw) {
          try {
            const prev = JSON.parse(prevRaw);
            prevLeads = prev.leads_all || [];
          } catch {}
        }

        if (newLeads.length < 5 && prevLeads.length >= 5) {
          return jsonResponse({
            status: 'rejected',
            reason: 'anti_wipe',
            incoming: newLeads.length,
            existing: prevLeads.length
          }, corsHeaders, 200);
        }

        // Merge upsert by ID
        const prevById = new Map();
        prevLeads.forEach(l => prevById.set(l.id, l));
        newLeads.forEach(l => prevById.set(l.id, l));
        const merged = Array.from(prevById.values());

        // Truncate to 500 most recent
        merged.sort((a, b) => {
          const da = new Date(a.fecha_iso || a.discovery_timestamp || 0).getTime();
          const db = new Date(b.fecha_iso || b.discovery_timestamp || 0).getTime();
          return db - da;
        });
        const truncated = merged.slice(0, 500);

        const payload = {
          leads_all: truncated,
          leads_hot: truncated.filter(l => (l.scoring?.final_score ?? l.score ?? 0) >= 50),
          summary: {
            total_leads: truncated.length,
            hot_leads: truncated.filter(l => (l.scoring?.final_score ?? l.score ?? 0) >= 50).length,
          },
          meta: {
            version: '10.0',
            source: 'pipeline_v7',
            generated_at: body.meta?.generated_at || new Date().toISOString(),
            ingest_at: new Date().toISOString(),
            merged_from_prev: prevLeads.length,
            new_in_batch: newLeads.length,
          }
        };

        await env.LEADX_KV.put('leads:live', JSON.stringify(payload));
        return jsonResponse({
          status: 'ok',
          total: truncated.length,
          new: newLeads.length,
          merged: prevLeads.length
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ status: 'error', message: e.message }, corsHeaders, 500);
      }
    }

    // ─── 404 ───
    return jsonResponse({ error: 'not_found', path: url.pathname }, corsHeaders, 404);
  }
};

function jsonResponse(data, corsHeaders, status = 200) {
  return new Response(JSON.stringify(data), {
    status: status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      ...corsHeaders,
    }
  });
}

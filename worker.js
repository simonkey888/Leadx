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
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #0f172a;
    color: #cbd5e1;
    border: 1px solid #334155;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    text-decoration: none;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .lead-card .actions a:hover, .lead-card .actions button:hover {
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }
  .lead-card .actions a svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
  }
  /* Reddit brand */
  .lead-card .actions a.btn-reddit {
    background: #ff4500; color: white; border-color: #ff4500;
  }
  .lead-card .actions a.btn-reddit:hover { background: #cc3700; }
  /* WhatsApp brand */
  .lead-card .actions a.btn-whatsapp {
    background: #25d366; color: white; border-color: #25d366;
  }
  .lead-card .actions a.btn-whatsapp:hover { background: #1da851; }
  /* MercadoLibre brand */
  .lead-card .actions a.btn-ml {
    background: #ffe600; color: #2d3277; border-color: #ffe600;
  }
  .lead-card .actions a.btn-ml:hover { background: #d4c200; }
  /* Facebook brand */
  .lead-card .actions a.btn-facebook {
    background: #1877f2; color: white; border-color: #1877f2;
  }
  .lead-card .actions a.btn-facebook:hover { background: #0f5ec7; }
  /* X/Twitter brand */
  .lead-card .actions a.btn-x {
    background: #000; color: white; border-color: #333;
  }
  .lead-card .actions a.btn-x:hover { background: #1a1a1a; }
  /* Phone */
  .lead-card .actions a.btn-phone {
    background: #0f172a; color: #93c5fd; border-color: #1e40af;
  }
  .lead-card .actions a.btn-phone:hover { background: #1e293b; }
  /* Email */
  .lead-card .actions a.btn-email {
    background: #0f172a; color: #fbbf24; border-color: #92400e;
  }
  .lead-card .actions a.btn-email:hover { background: #1e293b; }
  /* Generic source */
  .lead-card .actions a.btn-source {
    background: #1e293b; color: #cbd5e1; border-color: #475569;
  }
  .lead-card .actions a.btn-source:hover { background: #334155; }
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
  // Soporta ambos schemas: v8 nested (scoring.final_score, source.url) y v1.0 plano (score, source_url)
  const score = l.scoring?.final_score ?? l.score ?? 0;
  const title = l.title || l.quoted_text || l.problem_summary || l.snippet || l.lead_reason || 'Sin título';
  const snippet = l.snippet || l.problem_summary || l.quoted_text || '';
  const url = l.source?.url || l.source_url || l.url || '#';
  const platform = l.source?.type || l.platform || 'unknown';
  const whatsapp = l.contact?.whatsapp || l.whatsapp_publico || '';
  const phone = l.contact?.phone || l.telefono_publico || '';
  const email = l.contact?.email || l.email_publico || '';
  const fecha = l.fecha_iso || l.discovery_timestamp || l.fecha_visible || '';
  const intent = l.intent_cluster || l.intent || l.problem_category || '—';

  // Construir acciones
  const actions = [];
  if (l.actions && Array.isArray(l.actions)) {
    l.actions.forEach(a => actions.push(a));
  }
  if (url && url !== '#') actions.push({type: 'OPEN_SOURCE', url, label: '🔗 Fuente'});
  if (whatsapp) {
    const wa = whatsapp.replace(/[^0-9]/g, '');
    actions.push({type: 'OPEN_WHATSAPP', url: 'https://wa.me/' + wa, label: '🟢 WhatsApp'});
  }
  if (phone) actions.push({type: 'OPEN_PHONE', url: 'tel:' + phone, label: '📞 Llamar'});

  return {
    id: l.id || 'sin-id',
    score: score,
    title: title,
    snippet: snippet,
    url: url,
    platform: platform,
    intent: intent,
    whatsapp: whatsapp,
    phone: phone,
    email: email,
    fecha: fecha,
    actions: actions,
    lead_reason: l.lead_reason || l.problem_summary || '',
    entity: l.entity_ref || l.entity || {},
    persona: l.persona || '',
    provincia: l.provincia || '',
    vehiculo: l.vehiculo || '',
    patente: l.patente || '',
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

// ─── SVG ICONS (inline, no external deps) ───
const ICONS = {
  reddit: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M24 12c0-1.7-1.4-3-3-3-.8 0-1.5.3-2 .8-.6-.4-1.3-.7-2-.9V7.5c0-.8-.6-1.4-1.4-1.4H8.4c-.8 0-1.4.6-1.4 1.4v.4c-.7.2-1.4.5-2 .9-.5-.5-1.2-.8-2-.8-1.7 0-3 1.3-3 3 0 1.2.7 2.2 1.7 2.7-.1.4-.1.7-.1 1.1 0 3.3 3.8 6 8.5 6s8.5-2.7 8.5-6c0-.4 0-.7-.1-1.1 1-.5 1.5-1.5 1.5-2.7zm-12 4c-1.1 0-2-.6-2-1.5s.9-1.5 2-1.5 2 .6 2 1.5-.9 1.5-2 1.5zm5 0c-1.1 0-2-.6-2-1.5s.9-1.5 2-1.5 2 .6 2 1.5-.9 1.5-2 1.5z"/></svg>',
  whatsapp: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.1-1.7-.8-1.9-.9-.3-.1-.5-.1-.7.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-.3-.1-1.2-.5-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6.1-.1.3-.3.4-.5.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5-.1-.1-.7-1.6-.9-2.2-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.5s1.1 2.9 1.2 3.1c.1.2 2.1 3.2 5 4.5.7.3 1.2.5 1.7.6.7.2 1.3.2 1.8.1.6-.1 1.7-.7 1.9-1.3.2-.6.2-1.2.2-1.3-.1-.2-.3-.2-.6-.4zM12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.3 5L2 22l5.2-1.4c1.4.8 3.1 1.2 4.8 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2zm0 18c-1.5 0-3-.4-4.3-1.2l-.3-.2-3.1.8.8-3-.2-.3C4.1 14.9 3.7 13.5 3.7 12 3.7 7.3 7.3 3.7 12 3.7s8.3 3.6 8.3 8.3-3.6 8.3-8.3 8.3z"/></svg>',
  ml: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2 6l1.7 12.5c.1.5.5.9 1 .9h14.6c.5 0 .9-.4 1-.9L22 6H2zm10 9.5c-1.9 0-3.5-1.6-3.5-3.5s1.6-3.5 3.5-3.5 3.5 1.6 3.5 3.5-1.6 3.5-3.5 3.5z"/></svg>',
  facebook: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M24 12c0-6.6-5.4-12-12-12S0 5.4 0 12c0 6 4.4 11 10.1 11.9V15.5H7.1V12h3V9.4c0-3 1.8-4.6 4.5-4.6 1.3 0 2.7.2 2.7.2v2.9h-1.5c-1.5 0-2 .9-2 1.9V12h3.3l-.5 3.5h-2.8v8.4C19.6 23 24 18 24 12z"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.2 2H21l-6.5 7.4L22 22h-6l-4.7-6.1L5.8 22H3l7-8L2 2h6.2l4.3 5.7L18.2 2zm-1 18h1.7L7.9 3.8H6.1L17.2 20z"/></svg>',
  phone: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>',
  email: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
  source: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
};

// Detecta plataforma desde URL → devuelve {icon, label, btnClass}
function detectPlatform(url) {
  if (!url) return {icon: ICONS.source, label: 'Fuente', btnClass: 'btn-source'};
  const u = url.toLowerCase();
  if (u.includes('reddit.com')) return {icon: ICONS.reddit, label: 'Reddit', btnClass: 'btn-reddit'};
  if (u.includes('whatsapp.') || u.includes('wa.me')) return {icon: ICONS.whatsapp, label: 'WhatsApp', btnClass: 'btn-whatsapp'};
  if (u.includes('mercadolibre.') || u.includes('mercadolivre.')) return {icon: ICONS.ml, label: 'MercadoLibre', btnClass: 'btn-ml'};
  if (u.includes('facebook.')) return {icon: ICONS.facebook, label: 'Facebook', btnClass: 'btn-facebook'};
  if (u.includes('twitter.') || u.includes('x.com')) return {icon: ICONS.x, label: 'X', btnClass: 'btn-x'};
  return {icon: ICONS.source, label: 'Fuente', btnClass: 'btn-source'};
}

// Construye el HTML de un botón de acción con branding
function actionButton(url, overrideIcon, overrideLabel, overrideClass) {
  if (!url) return '';
  const p = detectPlatform(url);
  const icon = overrideIcon || p.icon;
  const label = overrideLabel || p.label;
  const cls = overrideClass || p.btnClass;
  const isTel = url.startsWith('tel:');
  const isMail = url.startsWith('mailto:');
  const target = (isTel || isMail) ? '' : ' target="_blank" rel="noopener"';
  return '<a class="' + cls + '" href="' + escapeHtml(url) + '"' + target + '>' + icon + '<span>' + escapeHtml(label) + '</span></a>';
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
    // Construir botones de acción con branding (sin duplicados)
    const seenUrls = new Set();
    const actions = [];

    function addAction(url, icon, label, cls) {
      if (!url || seenUrls.has(url)) return;
      seenUrls.add(url);
      actions.push(actionButton(url, icon, label, cls));
    }

    // WhatsApp (botón verde branded, SIEMPRE que haya número)
    if (l.whatsapp) {
      const wa = l.whatsapp.replace(/[^0-9]/g, '');
      if (wa) addAction('https://wa.me/' + wa, ICONS.whatsapp, 'WhatsApp', 'btn-whatsapp');
    }
    // Phone
    if (l.phone) {
      addAction('tel:' + l.phone, ICONS.phone, 'Llamar', 'btn-phone');
    }
    // Email (si existe)
    if (l.email) {
      addAction('mailto:' + l.email, ICONS.email, 'Email', 'btn-email');
    }
    // Fuente principal (URL del lead) — branded según plataforma
    addAction(l.url);

    // Acciones adicionales del pipeline (que no sean la fuente ya agregada)
    (l.actions || []).forEach(a => {
      if (!a || !a.url) return;
      addAction(a.url, null, a.label);
    });

    const extraChips = [];
    if (l.persona) extraChips.push('<span class="chip">👤 ' + escapeHtml(l.persona) + '</span>');
    if (l.provincia) extraChips.push('<span class="chip">📍 ' + escapeHtml(l.provincia) + '</span>');
    if (l.vehiculo) extraChips.push('<span class="chip">🚗 ' + escapeHtml(l.vehiculo) + '</span>');
    if (l.patente) extraChips.push('<span class="chip">🔧 ' + escapeHtml(l.patente) + '</span>');
    if (l.email) extraChips.push('<span class="chip">✉ ' + escapeHtml(l.email) + '</span>');

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
          \${extraChips.join('')}
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

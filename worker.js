Warning: truncated output (original token count: 44562)
Total output lines: 3918

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
 *   GET  /api/kv        → Lee key de KV (auth: X-Webhook-Secret)
 *   POST /api/kv        → Escribe key a KV con TTL opcional (auth: X-Webhook-Secret)
 */

// ─────────────────────────────────────────────────────────────
// HTML DEL DASHBOARD (embebido, sin dependencias externas)
// ─────────────────────────────────────────────────────────────
const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LeadX CRM — Gestión de Casos</title>
<style>
  /* ═════════════════════════════════════════════════════════════════════
     LEADX CRM — Rediseño estilo Twenty.com (Black & Zinc)
     Solo cambios visuales. Toda la lógica JS permanece intacta.
     ═════════════════════════════════════════════════════════════════════ */
  :root {
    --bg:       #000000;   /* Negro absoluto (Twenty fondo) */
    --surface:  #09090b;   /* Gris carbón (Twenty cards) */
    --surface2: #18181b;   /* Gris zinc elevado */
    --border:   #27272a;   /* Bordes sutiles zinc */
    --text:     #fafafa;   /* Texto principal blanco */
    --muted:    #71717a;   /* Texto secundario zinc-400 */
    --muted2:   #52525b;   /* Texto terciario zinc-500 */
    --primary:  #6366f1;   /* Índigo premium (accent) */
    --primary-h:#818cf8;   /* Índigo claro hover */
    --green:    #22c55e;   /* Verde WhatsApp */
    --green-h:  #16a34a;
    --orange:   #f59e0b;   /* Amber para tibios */
    --red:      #ef4444;   /* Rojo para calientes */
    --purple:   #a855f7;
    --radius:   8px;
    --shadow:   0 1px 2px rgba(0,0,0,.4);
    --shadow-lg:0 4px 24px rgba(0,0,0,.6);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* ── TOP BAR (Twenty: negro puro con brand sutil) ── */
  .topbar {
    background: #000000;
    color: #fafafa;
    padding: 0 24px;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    border-bottom: 1px solid var(--border);
    box-shadow: none;
  }
  .topbar-brand {
    font-size: 15px;
    font-weight: 600;
    letter-spacing: -.3px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #fafafa;
  }
  .topbar-brand span { opacity: .5; font-weight: 400; font-size: 12px; color: var(--muted2); }
  .topbar-right {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 12px;
    color: var(--muted);
  }
  .sync-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: background .15s, border-color .15s;
  }
  .sync-btn:hover { background: var(--surface2); border-color: var(--muted2); }

  /* ── LAYOUT ── */
  .layout {
    display: flex;
    min-height: calc(100vh - 52px);
  }

  /* ── SIDEBAR ── */
  .sidebar {
    width: 220px;
    flex-shrink: 0;
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: 20px 0;
    position: sticky;
    top: 52px;
    height: calc(100vh - 52px);
    overflow-y: auto;
  }
  .sidebar-section { margin-bottom: 24px; }
  .sidebar-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .6px;
    text-transform: uppercase;
    color: var(--muted);
    padding: 0 16px 8px;
  }
  .filter-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: all .1s;
    color: var(--muted);
    font-size: 13px;
  }
  .filter-item:hover { background: var(--surface2); color: var(--text); }
  .filter-item.active {
    background: rgba(99, 102, 241, 0.1);
    border-left-color: var(--primary);
    color: var(--primary-h);
    font-weight: 600;
  }
  .filter-count {
    background: var(--border);
    color: var(--muted);
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 11px;
    font-weight: 600;
  }
  .filter-item.active .filter-count {
    background: var(--primary);
    color: #fff;
  }

  /* ── MAIN ── */
  .main { flex: 1; padding: 24px; min-width: 0; }

  /* ── KPI ROW ── */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-bottom: 20px;
  }
  .kpi {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    box-shadow: var(--shadow);
  }
  .kpi-label { font-size: 11px; font-weight: 600; text-transform: uppercase;
    letter-spacing: .5px; color: var(--muted); margin-bottom: 6px; }
  .kpi-value { font-size: 28px; font-weight: 700; letter-spacing: -1px; }
  .kpi-value.green { color: var(--green); }
  .kpi-value.orange { color: var(--orange); }
  .kpi-value.red { color: var(--red); }
  .kpi-value.blue { color: var(--primary); }
  .kpi-sub { font-size: 11px; color: var(--muted); margin-top: 3px; }

  /* ── TOOLBAR ── */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }
  .search-wrap {
    flex: 1;
    min-width: 200px;
    position: relative;
  }
  .search-wrap input {
    width: 100%;
    padding: 8px 12px 8px 34px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 13px;
    background: var(--surface);
    color: var(--text);
    outline: none;
    transition: border-color .15s;
  }
  .search-wrap input:focus { border-color: var(--primary); }
  .search-icon {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    font-size: 14px;
  }
  select {
    padding: 8px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 13px;
    background: var(--surface);
    color: var(--text);
    outline: none;
    cursor: pointer;
  }
  select option { background: var(--surface); color: var(--text); }
  .search-wrap input::placeholder { color: var(--muted2); }
  .btn-primary {
    background: var(--primary);
    color: #fff;
    border: none;
    padding: 8px 16px;
    border-radius: var(--radius);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background .15s;
    white-space: nowrap;
  }
  .btn-primary:hover { background: var(--primary-h); }

  /* ── TABLE ── */
  .table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow: hidden;
  }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    padding: 10px 14px;
    text-align: left;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: var(--muted);
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }
  thead th:hover { color: var(--text); }
  tbody tr {
    border-bottom: 1px solid var(--border);
    transition: background .1s;
  }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: var(--surface2); }
  td { padding: 12px 14px; vertical-align: middle; }
  .td-nombre { font-weight: 600; font-size: 13px; max-width: 160px; }
  .td-nombre small { display: block; font-weight: 400; color: var(--muted); font-size: 11px; margin-top: 2px; }
  .td-resumen { max-width: 260px; }
  .td-resumen p { font-size: 12px; color: var(--muted);
    overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; }

  /* ── STATUS BADGE (desaturados, estilo Twenty) ── */
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
    border: 1px solid transparent;
  }
  .badge-nuevo    { background: rgba(99,102,241,.08); color: #818cf8; border-color: rgba(99,102,241,.2); }
  .badge-contactado  { background: rgba(245,158,11,.08); color: #fbbf24; border-color: rgba(245,158,11,.2); }
  .badge-gestion  { background: rgba(34,197,94,.08); color: #4ade80; border-color: rgba(34,197,94,.2); }
  .badge-cerrado  { background: rgba(34,197,94,.12); color: var(--green); border-color: rgba(34,197,94,.3); }
  .badge-descartado { background: rgba(239,68,68,.08); color: #f87171; border-color: rgba(239,68,68,.2); }
  .kpi-value.purple { color: var(--purple); }
  .badge-hot { background: rgba(239,68,68,.1); color: #f87171; margin-left: 4px; border:1px solid rgba(239,68,68,.2); }
  .badge-warm { background: rgba(245,158,11,.1); color: #fbbf24; margin-left: 4px; border:1px solid rgba(245,158,11,.2); }

  /* Heat score row colors (Twenty: tintes sutiles sobre negro) */
  tr.heat-hot { background: rgba(239,68,68,.04) !important; }
  tr.heat-hot:hover { background: rgba(239,68,68,.1) !important; }
  tr.heat-warm { background: rgba(245,158,11,.03) !important; }
  tr.heat-warm:hover { background: rgba(245,158,11,.08) !important; }
  tr.heat-cold { background: var(--surface) !important; opacity: 0.5; }
  tr.pinned-row { border-left: 3px solid var(--orange) !important; background: rgba(245,158,11,.05) !important; }
  tr.pinned-row:hover { background: rgba(245,158,11,.1) !important; }

  /* Boton WhatsApp grande verde (GPT: para tu viejo) */
  .btn-wa-big {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: #25D366;
    color: white;
    border: none;
    border-radius: 50%;
    font-size: 18px;
    cursor: pointer;
    text-decoration: none;
    transition: all 0.15s;
  }
  .btn-wa-big:hover { background: #1DAE53; transform: scale(1.1); }
  .btn-wa-pending {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: #E5E7EB;
    color: #6B7280;
    border: none;
    border-radius: 50%;
    font-size: 18px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .btn-wa-pending:hover { background: #D1D5DB; }
  .wa-none { font-size: 14px; color: var(--red); }

  /* ── SOURCE TAG ── */
  .source-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    background: #F1F5F9;
    color: var(--muted);
    white-space: nowrap;
  }

  /* ── ACTION BUTTONS ── */
  .actions { display: flex; gap: 6px; align-items: center; }
  .btn-wa {
    background: #25D366;
    color: #fff;
    border: none;
    padding: 6px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    transition: background .15s;
  }
  .btn-wa:hover { background: #1DAE53; }
  .btn-icon {
    background: #F1F5F9;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 6px 9px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    transition: all .15s;
  }
  .btn-icon:hover { background: #E2E8F0; color: var(--text); }

  /* ── STATUS SELECT ── */
  .status-sel {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    outline: none;
  }

  /* ── EMPTY STATE ── */
  .empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--muted);
  }
  .empty h3 { font-size: 16px; margin-bottom: 8px; color: var(--text); }
  .empty p { font-size: 13px; }

  /* ── SLIDING DRAWER (estilo Twenty: panel lateral derecho) ── */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.6);
    backdrop-filter: blur(4px);
    z-index: 200;
    justify-content: flex-end;  /* Drawer pegado a la derecha */
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface);
    border-radius: 0;
    border-left: 1px solid var(--border);
    width: 520px;
    max-width: 100vw;
    max-height: 100vh;
    overflow-y: auto;
    box-shadow: var(--shadow-lg);
    padding: 28px;
    animation: slideIn .25s cubic-bezier(.4,0,.2,1);
  }
  @keyframes slideIn {
    from { transform: translateX(100%); }
    to   { transform: translateX(0); }
  }
  .modal h2 { font-size: 18px; margin-bottom: 20px; color: var(--text); }
  .modal-field { margin-bottom: 16px; }
  .modal-field label { display: block; font-size: 12px; font-weight: 600;
    color: var(--muted); margin-bottom: 5px; text-transform: uppercase;
    letter-spacing: .4px; }
  .modal-field .val { font-size: 14px; color: var(--text); }
  .modal-field textarea {
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
    font-family: inherit;
    resize: vertical;
    min-height: 80px;
    outline: none;
    background: var(--bg);
    color: var(--text);
  }
  .modal-field textarea:focus { border-color: var(--primary); }
  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
  .btn-secondary {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 16px;
    border-radius: var(--radius);
    font-size: 13px;
    cursor: pointer;
  }
  .btn-secondary:hover { background: var(--border); }
  .modal-close {
    float: right;
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    color: var(--muted);
    line-height: 1;
    padding: 0 4px;
  }
  .divider { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
  .contact-box {
    background: rgba(34,197,94,.06);
    border: 1px solid rgba(34,197,94,.2);
    border-radius: 8px;
    padding: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .contact-box.no-contact {
    background: rgba(245,158,11,.06);
    border-color: rgba(245,158,11,.2);
  }

  /* ── LOADING ── */
  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 80px;
    color: var(--muted);
    gap: 10px;
    font-size: 13px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner {
    width: 20px; height: 20px;
    border: 2px solid var(--border);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin .8s linear infinite;
  }

  /* ── RESPONSIVE ── */
  @media (max-width: 900px) {
    .sidebar { display: none; }
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
  }

  /* ── DROPZONE & WIZARD VLM (Twenty.com Style) ── */
  .acta-dropzone {
    border: 2px dashed var(--border);
    background: rgba(24, 24, 27, 0.5);
    border-radius: var(--radius);
    padding: 20px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-bottom: 16px;
  }
  .acta-dropzone:hover, .acta-dropzone.dragover {
    border-color: var(--primary);
    background: rgba(99, 102, 241, 0.05);
  }
  .acta-dropzone p { font-size: 12px; color: var(--muted); margin-top: 8px; line-height: 1.4; }
  .wizard-card {
    background: rgba(99, 102, 241, 0.05);
    border: 1px solid rgba(99, 102, 241, 0.2);
    border-radius: var(--radius);
    padding: 16px;
    margin-top: 16px;
  }
  .wizard-badge {
    background: rgba(239, 68, 68, 0.1); color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.2); font-size: 11px; font-weight: 700;
    padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 10px;
    text-transform: uppercase; letter-spacing: 0.5px;
  }
  .btn-wizard-send {
    background: #25D366; color: white; font-weight: 700; padding: 8px 14px;
    border-radius: 6px; font-size: 12px; display: inline-flex; align-items: center;
    gap: 6px; text-decoration: none; border: none; cursor: pointer;
  }
  .btn-wizard-send:hover { background: #1dae53; }
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <div class="topbar-brand">
    📋 LeadX CRM
    <span>Gestión de casos · Sin Fotomultas</span>
  </div>
  <div class="topbar-right">
    <span id="syncTime">—</span>
    <button class="sync-btn" onclick="loadLeads()">↻ Sincronizar</button>
  </div>
</div>

<div class="layout">

  <!-- SIDEBAR -->
  <div class="sidebar">
    <div class="sidebar-section">
      <div class="sidebar-label">Estado</div>
      <div class="filter-item active" onclick="filterStatus('todos', this)" id="f-todos">
        Todos <span class="filter-count" id="cnt-todos">0</span>
      </div>
      <div class="filter-item" onclick="filterStatus('Nuevo', this)" id="f-Nuevo">
        🔵 Nuevo <span class="filter-count" id="cnt-Nuevo">0</span>
      </div>
      <div class="filter-item" onclick="filterStatus('Contactado', this)" id="f-Contactado">
        🟡 Contactado <span class="filter-count" id="cnt-Contactado">0</span>
      </div>
      <div class="filter-item" onclick="filterStatus('En gestión', this)" id="f-En gestión">
        🟢 En gestión <span class="filter-count" id="cnt-En gestión">0</span>
      </div>
      <div class="filter-item" onclick="filterStatus('Cerrado', this)" id="f-Cerrado">
        ✅ Cerrado <span class="filter-count" id="cnt-Cerrado">0</span>
      </div>
      <div class="filter-item" onclick="filterStatus('Descartado', this)" id="f-Descartado">
        ❌ Descartado <span class="filter-count" id="cnt-Descartado">0</span>
      </div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Provincia</div>
      <div id="prov-filters"></div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Fuente</div>
      <div id="source-filters"></div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Contacto</div>
      <div class="filter-item active" onclick="filterContact('todos', this)" id="fc-todos">
        Todos <span class="filter-count" id="cnt-contact-todos">0</span>
      </div>
      <div class="filter-item" onclick="filterContact('whatsapp', this)" id="fc-whatsapp">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#25D366" style="vertical-align:middle"><path d="M12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.3 5L2 22l5.2-1.4c1.4.8 3.1 1.2 4.8 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2z"/></svg>
        Con WhatsApp <span class="filter-count" id="cnt-whatsapp">0</span>
      </div>
      <div class="filter-item" onclick="filterContact('messenger', this)" id="fc-messenger">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#0084FF" style="vertical-align:middle"><path d="M12 2C6.5 2 2 6.5 2 12c0 5.5 4.5 10 10 10s10-4.5 10-10S17.5 2 12 2zm5.5 6.5l-2 5c-.1.2-.3.4-.5.5l-5 2c-.5.2-1-.3-.8-.8l2-5c.1-.2.3-.4.5-.5l5-2c.5-.2 1 .3.8.8z"/></svg>
        Con Messenger <span class="filter-count" id="cnt-messenger">0</span>
      </div>
      <div class="filter-item" onclick="filterContact('email', this)" id="fc-email">
        ✉️ Con Email <span class="filter-count" id="cnt-email">0</span>
      </div>
      <div class="filter-item" onclick="filterContact('sin_contacto', this)" id="fc-sin-contacto">
        ❌ Sin contacto <span class="filter-count" id="cnt-sin-contacto">0</span>
      </div>
    </div>

    <div class="sidebar-section">
      <div class="sidebar-label">Temperatura</div>
      <div class="filter-item active" onclick="filterHeat('todos', this)" id="fh-todos">
        Todos <span class="filter-count" id="cnt-heat-todos">0</span>
      </div>
      <div class="filter-item" onclick="filterHeat('hot', this)" id="fh-hot">
        🔥 Calientes <span class="filter-count" id="cnt-hot">0</span>
      </div>
      <div class="filter-item" onclick="filterHeat('warm', this)" id="fh-warm">
        ⚡ Tibios <span class="filter-count" id="cnt-warm">0</span>
      </div>
      <div class="filter-item" onclick="filterHeat('cold', this)" id="fh-cold">
        ⚪ Fríos <span class="filter-count" id="cnt-cold">0</span>
      </div>
    </div>
  </div>

  <!-- MAIN -->
  <div class="main">

    <!-- KPIs -->
    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-label">Total casos</div>
        <div class="kpi-value blue" id="kpi-total">—</div>
        <div class="kpi-sub">casos con contacto identificado</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Con WhatsApp</div>
        <div class="kpi-value green" id="kpi-wa">—</div>
        <div class="kpi-sub">teléfono directo verificado</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Con Messenger</div>
        <div class="kpi-value blue" id="kpi-messenger">—</div>
        <div class="kpi-sub">botón m.me (Facebook)</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">En proceso</div>
        <div class="kpi-value orange" id="kpi-proceso">—</div>
        <div class="kpi-sub">activos esta semana</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Cerrados</div>
        <div class="kpi-value green" id="kpi-cerrados">—</div>
        <div class="kpi-sub">casos resueltos</div>
      </div>
    </div>

    <!-- TOOLBAR -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">🔍</span>
        <input type="text" placeholder="Buscar por nombre, provincia, problema..."
          id="searchInput" oninput="renderTable()">
      </div>
      <select id="sortSel" onchange="renderTable()">
        <option value="heat">🔥 Más caliente</option>
        <option value="fecha">↓ Más reciente</option>
        <option value="provincia">↑ Provincia</option>
      </select>
      <button class="btn-primary" onclick="openAddModal()">+ Agregar caso</button>
    </div>

    <!-- TABLE -->
    <div class="table-wrap">
      <div id="tableContainer">
        <div class="loading"><div class="spinner"></div> Cargando casos...</div>
      </div>
    </div>

  </div>
</div>

<!-- DETAIL MODAL -->
<div class="modal-overlay" id="detailModal">
  <div class="modal">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h2 id="modal-title">Detalle del caso</h2>

    <div id="modal-contact-box" class="contact-box">
      <div>
        <strong id="modal-author">—</strong>
        <div style="font-size:12px;color:#166534;margin-top:2px" id="modal-phone-label"></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <a id="modal-wa-btn" class="btn-wa" href="#" target="_blank">
          💬 WhatsApp
        </a>
        <a id="modal-messenger-btn" class="btn-wa" href="#" target="_blank" style="display:none;text-decoration:none;background:#0084FF">
          ✉️ Messenger
        </a>
        <button id="modal-copy-tpl" class="btn-secondary" onclick="copyWaTemplate()">
          📋 Copiar
        </button>
      </div>
    </div>

    <hr class="divider">

    <div class="modal-field">
      <label>Provincia</label>
      <div class="val" id="modal-provincia">—</div>
    </div>
    <div class="modal-field">
      <label>Fuente</label>
      <div class="val" id="modal-source">—</div>
    </div>
    <div class="modal-field">
      <label>Descripción del caso</label>
      <div class="val" id="modal-body" style="font-size:13px;color:var(--muted);line-height:1.6"></div>
    </div>
    <div class="modal-field">
      <label>Publicación original</label>
      <a id="modal-url" href="#" target="_blank"
        style="font-size:12px;color:var(--primary)">Abrir enlace →</a>
    </div>
    <div class="modal-field" id="modal-profile-field" style="display:none">
      <label>Perfil del usuario</label>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <a id="modal-profile-url" href="#" target="_blank"
          style="font-size:12px;color:var(--orange)">Ver publicación original →</a>
        <button id="modal-copy-dm" class="btn-secondary" onclick="copyContactTemplate()" style="font-size:11px;padding:4px 10px">
          📋 Copiar mensaje
        </button>
      </div>
      <small style="color:var(--muted);font-size:11px;margin-top:6px;display:block;line-height:1.4">
        ⚠️ Reddit banea autopromoción. Usar guion genuino: ofrecer info primero, NO vender. Solo derivar a WA si hay interés.
      </small>
    </div>
    <div class="modal-field" id="modal-bio-field" style="display:none">
      <label>Contacto detectado en publicaciones</label>
      <div id="modal-bio-content" style="font-size:13px;color:var(--text);background:#F0FDF4;padding:8px 12px;border-radius:6px;border:1px solid #BBF7D0"></div>
    </div>

    <hr class="divider">

    <!-- SECCIÓN: ON-DEMAND ACTA ANALYZER (VLM) -->
    <div class="modal-field">
      <label style="color: var(--primary-h); font-weight: 700;">📄 Analizar Acta (VLM)</label>
      <div id="acta-dropzone" class="acta-dropzone" onclick="document.getElementById('acta-file-input').click()">
        <p style="font-size:24px;margin:0">📎</p>
        <p id="dropzone-text">Arrastrá la foto del acta aquí<br><span style="opacity:0.6;font-size:11px">o click para seleccionar</span></p>
        <input type="file" id="acta-file-input" accept="image/*" style="display:none">
      </div>
      <div id="vlm-loader" style="display:none;align-items:center;gap:8px;justify-content:center;padding:15px;color:var(--muted)">
        <div class="spinner"></div> <span style="font-size:12px">Analizando con VLM...</span>
      </div>
      <div id="vlm-result-card" class="wizard-card" style="display:none">
        <div class="wizard-badge" id="wizard-geo-badge">📍 Detectando...</div>
        <div style="font-size:14px;font-weight:700;color:#fff;margin-bottom:4px" id="wizard-patente-label">Patente: —</div>
        <p style="font-size:12px;color:var(--muted);margin-bottom:12px" id="wizard-ubicacion-label">Ubicación: —</p>
        <div style="background:rgba(0,0,0,0.3);border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:12px">
          <small style="color:var(--muted);font-weight:700;display:block;margin-bottom:6px;text-transform:uppercase;font-size:9px;letter-spacing:0.5px">Análisis Legal</small>
          <span style="font-size:12px;line-height:1.5;color:#fafafa;display:block" id="wizard-legal-analysis">—</span>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <a id="wizard-maps-btn" class="btn-secondary" style="font-size:11px;padding:8px 12px;display:inline-flex;align-items:center;gap:4px;text-decoration:none" href="#" target="_blank">📍 Maps</a>
          <a id="wizard-wa-btn" class="btn-wizard-send" href="#" target="_blank">💬 WhatsApp</a>
        </div>
      </div>
    </div>

    <hr class="divider">

    <div class="modal-field">
      <label>Estado</label>
      <select class="status-sel" id="modal-status-sel" onchange="saveStatusFromModal()">
        <option>Nuevo</option>
        <option>Contactado</option>
        <option>En gestión</option>
        <option>Cerrado</option>
        <option>Descartado</option>
      </select>
    </div>
    <div class="modal-field" id="modal-monto-field" style="display:none">
      <label>Monto cobrado (ARS)</label>
      <input type="number" id="modal-monto" placeholder="0"
        style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none"
        onchange="saveMontoFromModal()">
      <small style="color:var(--muted);font-size:11px;margin-top:4px;display:block">
        Comisión estimada (15%): <strong id="modal-comision">—</strong>
      </small>
    </div>
    <div class="modal-field">
      <label>Notas internas</label>
      <textarea id="modal-notes" placeholder="Anotá detalles del caso, monto estimado, acuerdos..."
        onchange="saveNotesFromModal()"></textarea>
    </div>

    <!-- FORENSIC LOG: registrar caso resuelto (solo visible cuando estado=Cerrado) -->
    <div id="forensic-log-card" style="display:none;background:rgba(34,197,94,.03);border:1px solid rgba(34,197,94,.15);border-radius:8px;padding:16px;margin-top:16px">
      <h5 style="font-size:12px;font-weight:700;color:var(--green);margin-bottom:10px;text-transform:uppercase">🎯 Registrar Descargo en Base Forense</h5>
      <label style="display:block;font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px;text-transform:uppercase">Resultado</label>
      <select id="log-result" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px;margin-bottom:12px;outline:none">
        <option value="ganado">🟢 Ganado (Multa Anulada)</option>
        <option value="perdido">🔴 Perdido (Multa Sostenida)</option>
      </select>
      <label style="display:block;font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px;text-transform:uppercase">Argumento</label>
      <select id="log-argument" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px;margin-bottom:12px;outline:none">
        <option value="Falta de Homologación APSV (Ley 12.217)">Falta de Homologación APSV (Ley 12.217)</option>
        <option value="Falta de Notificación Fehaciente">Falta de Notificación Fehaciente</option>
        <option value="Margen de Tolerancia Técnica Excedido">Margen de Tolerancia Técnica Excedido</option>
        <option value="Falta de Señalización de Radar (1km antes)">Falta de Señalización de Radar (1km antes)</option>
      </select>
      <label style="display:block;font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px;text-transform:uppercase">Honorario (ARS)</label>
      <input type="number" id="log-fee" placeholder="Ej: 15000" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;background:var(--bg);color:var(--text);font-size:13px;margin-bottom:12px;outline:none">
      <button class="btn-primary" style="background:var(--green);width:100%;justify-content:center" onclick="submitForensicCase()">💾 Guardar Caso</button>
    </div>

    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeModal()">Cerrar</button>
      <button class="btn-primary" onclick="saveAndClose()">Guardar y cerrar</button>
    </div>
  </div>
</div>

<!-- ADD MODAL -->
<div class="modal-overlay" id="addModal">
  <div class="modal">
    <button class="modal-close" onclick="closeAddModal()">✕</button>
    <h2>Agregar caso manual</h2>
    <div class="modal-field">
      <label>Nombre / Usuario</label>
      <input type="text" id="add-nombre" placeholder="Nombre del contacto"
        style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none">
    </div>
    <div class="modal-field">
      <label>Contacto</label>
      <input type="text" id="add-phone" placeholder="+54 9 11 1234-5678"
        style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none">
    </div>
    <div class="modal-field">
      <label>Provincia</label>
      <select id="add-prov" style="width:100%">
        <option value="">— Seleccionar —</option>
        <option>Santa Fe</option><option>Buenos Aires</option>
        <option>CABA</option><option>Córdoba</option>
        <option>Entre Ríos</option><option>Misiones</option>
        <option>La Pampa</option><option>Mendoza</option><option>Otra</option>
      </select>
    </div>
    <div class="modal-field">
      <label>Descripción del caso</label>
      <textarea id="add-body" placeholder="Resumen del problema: qué multas tiene, monto estimado, urgencia..."
        style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;font-family:inherit;min-height:80px;outline:none;resize:vertical"></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeAddModal()">Cancelar</button>
      <button class="btn-primary" onclick="addManualCase()">Agregar caso</button>
    </div>
  </div>
</div>

<!-- SETTINGS MODAL (N3) -->
<div class="modal-overlay" id="settingsModal">
  <div class="modal" style="width:400px">
    <button class="modal-close" onclick="closeSettings()">✕</button>
    <h2>Configuración</h2>
    <div class="modal-field">
      <label>% Comisión</label>
      <input type="number" id="settings-comision" min="0" max="100" step="0.5"
        style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none">
      <small style="color:var(--muted);font-size:11px;margin-top:4px;display:block">
        Porcentaje que cobrás por caso cerrado. Afecta el KPI "Comisión total".
      </small>
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeSettings()">Cancelar</button>
      <button class="btn-primary" onclick="saveSettings()">Guardar</button>
    </div>
  </div>

<script>
// ── STATE ──────────────────────────────────────────────────────────────────
// Iconos WhatsApp (SVG inline)
const WA_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="#25D366"><path d="M17.5 14.4c-.3-.1-1.7-.8-1.9-.9-.3-.1-.5-.1-.7.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-.3-.1-1.2-.5-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6.1-.1.3-.3.4-.5.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5-.1-.1-.7-1.6-.9-2.2-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.5s1.1 2.9 1.2 3.1c.1.2 2.1 3.2 5 4.5.7.3 1.2.5 1.7.6.7.2 1.3.2 1.8.1.6-.1 1.7-.7 1.9-1.3.2-.6.2-1.2.2-1.3-.1-.2-.3-.2-.6-.4zM12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.3 5L2 22l5.2-1.4c1.4.8 3.1 1.2 4.8 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2zm0 18c-1.5 0-3-.4-4.3-1.2l-.3-.2-3.1.8.8-3-.2-.3C4.1 14.9 3.7 13.5 3.7 12 3.7 7.3 7.3 3.7 12 3.7s8.3 3.6 8.3 8.3-3.6 8.3-8.3 8.3z"/></svg>';
const WA_ICON_GRAY = '<svg width="20" height="20" viewBox="0 0 24 24" fill="#9CA3AF"><path d="M17.5 14.4c-.3-.1-1.7-.8-1.9-.9-.3-.1-.5-.1-.7.1-.2.3-.7.9-.9 1.1-.2.2-.3.2-.6.1-.3-.1-1.2-.5-2.3-1.4-.9-.8-1.4-1.7-1.6-2-.2-.3 0-.5.1-.6.1-.1.3-.3.4-.5.1-.2.2-.3.3-.5.1-.2 0-.4 0-.5-.1-.1-.7-1.6-.9-2.2-.2-.6-.5-.5-.7-.5h-.6c-.2 0-.5.1-.8.4-.3.3-1 1-1 2.5s1.1 2.9 1.2 3.1c.1.2 2.1 3.2 5 4.5.7.3 1.2.5 1.7.6.7.2 1.3.2 1.8.1.6-.1 1.7-.7 1.9-1.3.2-.6.2-1.2.2-1.3-.1-.2-.3-.2-.6-.4zM12 2C6.5 2 2 6.5 2 12c0 1.8.5 3.5 1.3 5L2 22l5.2-1.4c1.4.8 3.1 1.2 4.8 1.2 5.5 0 10-4.5 10-10S17.5 2 12 2zm0 18c-1.5 0-3-.4-4.3-1.2l-.3-.2-3.1.8.8-3-.2-.3C4.1 14.9 3.7 13.5 3.7 12 3.7 7.3 7.3 3.7 12 3.7s8.3 3.6 8.3 8.3-3.6 8.3-8.3 8.3z"/></svg>';

const S = {
  allLeads:   [],   // todos los leads crudos de la API
  crmLeads:   [],   // leads con contacto o manual + leads manuales
  filtered:   [],
  statusFilter: 'todos',
  provFilter:   'todos',
  sourceFilter: 'todos',     // FIX GEMINI AUDIT v4: volver a 'todos' (era 'VentaFe')
  contactFilter: 'todos',   // FIX GEMINI AUDIT v4: volver a 'todos' (era 'whatsapp')
  heatFilter:    'todos',   // FIX GEMINI AUDIT v4: volver a 'todos' (era 'hot')
  currentId:    null,
};

// FIX QWEN v2.9: Sin prompt de autenticación.
// getUrlSecret() devuelve string vacío (no hardcoded secret). Auth server-side solo.

// Persistencia local (status + notes por lead ID)
const DB = {
  get: (id)     => { try { return JSON.parse(localStorage.getItem('crm_' + id)) || {}; } catch(e) { return {}; } },
  set: (id, d)  => localStorage.setItem('crm_' + id, JSON.stringify(d)),
  getManual: () => { try { return JSON.parse(localStorage.getItem('crm_manual')) || []; } catch(e) { return []; } },
  setManual: (a) => localStorage.setItem('crm_manual', JSON.stringify(a)),
};

// ── LOAD ───────────────────────────────────────────────────────────────────
async function loadLeads() {
  document.getElementById('tableContainer').innerHTML =
    '<div class="loading"><div class="spinner"></div> Sincronizando...</div>';

  try {
    const r    = await fetch('/api/leads');
    const data = await r.json();
    const raw  = [
      ...(data.leads_hot  || []),
      ...(data.leads_warm || []),
      ...(data.leads_all  || []),
    ];

    // Dedup
    const seen = new Set();
    S.allLeads = raw.filter(l => {
      if (seen.has(l.id)) return false;
      seen.add(l.id);
      return true;
    });

    // M2: Filtrar SEO/artículos (medios y blogs no son leads)
    const SEO_BLACKLIST = ['tn.com.ar','infobae.com','clarin.com','lanacion.com.ar',
      'iprofesional.com','perfil.com','cronista.com','ambito.com','pagina12.com.ar',
      'multabot.com.ar','segurarse.com.ar','iusnoticias.com.ar','parrillacero5.com.ar',
      'autocosmos.com.ar','wikipedia.org','youtube.com','reclamosonline.com.ar',
      'carchecking.com.ar','portaldeabogados.com','jus.gov.ar','gob.ar','gov.ar'];
    const isSeoSpam = (l) => {
      const src = ((l.platform||'') + ' ' + (l.source_url||'') + ' ' + (l.url||'')).toLowerCase();
      return SEO_BLACKLIST.some(d => src.includes(d));
    };

    // CRM: solo leads con persona real (no anónimo) o con contacto
    const apiCRM = S.allLeads.filter(l => {
      if (isSeoSpam(l)) return false;
      const persona = l.persona || l.author || '';
      const hasPersona = persona && persona.trim() && persona !== '(anónimo)' && persona !== 'anónimo' && persona !== '';
      const hasContact = l.whatsapp_publico || l.email_publico || l.telefono_publico || l.phone || l.whatsapp;
      const hasAuthorFlag = l.has_author === true || l.contactable === true;
      return hasPersona || hasContact || hasAuthorFlag;
    }).map(enrichLead);

    const manual = DB.getManual().map(l => ({ ...l, _manual: true }));

    // Merge (manual primero)
    const allIds  = new Set(apiCRM.map(l => l.id));
    S.crmLeads    = [
      ...manual,
      ...apiCRM.filter(l => !manual.some(m => m.id === l.id)),
    ];

    document.getElementById('syncTime').textContent =
      'Actualizado ' + new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });

    applyFilters();
    renderSidebar();
    renderKPIs();

  } catch (e) {
    document.getElementById('tableContainer').innerHTML =
      \`<div class="empty"><h3>Error al cargar</h3><p>\${e.message}</p></div>\`;
  }
}

function enrichLead(l) {
  const stored = DB.get(l.id);
  const persona = l.persona || l.author || '';
  const wa = l.whatsapp_publico || l.whatsapp || '';
  const phone = l.telefono_publico || l.phone || wa;
  const email = l.email_publico || l.email || '';
  const title = l.problem_summary || l.title || '';
  const body = l.quoted_text || l.snippet || l.body || title;
  const url = l.source_url || l.url || '#';
  const platform = l.platform || l.source_label || l.source || '';
  const leadScore = l.score || 0;

  const enriched = {
    ...l,
    author: persona,
    phone: phone,
    whatsapp: wa,
    email: email,
    source_label: platform,
    source: platform,
    title: title,
    body: body,
    url: url,
    _status: stored.status || 'Nuevo',
    _notes:  stored.notes  || '',
    _phone:  phone || extractPhone(body) || '',
    _display_name: (persona && persona !== '(anónimo)') ? persona : 'Sin nombre',
    _resumen: cleanSnippet(title || body),
  };

  // Normalizar telefono
  const norm = normalizePhoneAR(enriched._phone);
  enriched._wa_state = norm.state;
  enriched._wa_e164 = norm.e164;
  enriched._wa_display = norm.display;
  enriched._wa_url = norm.state === 'invalid_format' ? '' : norm.waUrl;

  // Cache validacion WA
  const waValidation = getWaValidation(enriched._wa_e164);
  if (waValidation !== null) {
    enriched._wa_state = waValidation === true ? 'validated_whatsapp' : 'not_whatsapp';
  }

  // GPT FIX 4: Usar SOLO score de Python (no recalcular en frontend)
  enriched._heat_score = l.score || 0;

  // CLASIFICACION VISUAL (GPT: 3 estados)
  if (enriched._heat_score >= 70) enriched._heat_label = 'hot';      // 🔥 ROJO
  else if (enriched._heat_score >= 40) enriched._heat_label = 'warm'; // ⚡ NARANJA
  else enriched._heat_label = 'cold';                                 // ⚪ GRIS

  return enriched;
}

function extractPhone(text) {
  const m = text.match(/(?:\\+54|0054)?[\\s\\-]?(?:9[\\s\\-]?)?(?:11|[2-9]\\d{2,3})[\\s\\-]?\\d{4}[\\s\\-]?\\d{4}/);
  return m ? m[0].trim() : '';
}

function normalizePhoneAR(raw) {
  if (!raw) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  let digits = String(raw).replace(/[^0-9]/g, '');
  if (!digits) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  if (digits.startsWith('54')) digits = digits.slice(2);
  if (digits.startsWith('0')) digits = digits.slice(1);
  // FIX GEMINI SABUESO v3: doble escape \\d dentro de template literal DASHBOARD_HTML.
  // Sin esto, /^\d{3,4}15\d{6,7}$/ se convierte en /^d{3,4}15d{6,7}$/ que matchea
  // el literal 'd' (no dígito) y rompe la normalización de teléfonos AR.
  if (digits.length === 12 && /^\\d{3,4}15\\d{6,7}$/.test(digits)) {
    digits = digits.replace(/15/, '');
  }
  if (digits.startsWith('9') && digits.length === 11) digits = digits.slice(1);
  if (digits.length !== 10) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  const validAC = ['11','221','223','249','261','264','291','294','297','299','341','342','343','351','353','358','362','364','370','376','379','380','381','383','385','387','388'];
  const ac3 = digits.slice(0, 3);
  const ac2 = digits.slice(0, 2);
  if (!validAC.includes(ac3) && !validAC.includes(ac2)) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  let mobile = digits;
  if (digits.startsWith('11')) mobile = '9' + digits;
  return {
    state: 'normalized_contact',
    e164: '+54' + mobile,
    display: '+54 ' + mobile.slice(0, 2) + ' ' + mobile.slice(2, 6) + '-' + mobile.slice(6),
    waUrl: 'https://wa.me/' + mobile,
  };
}

function buildWaUrl(phone) {
  const n = normalizePhoneAR(phone);
  return n.state === 'invalid_format' ? '' : n.waUrl;
}

// Cache de validacion WhatsApp por E.164 (localStorage)
function getWaValidation(e164) {
  if (!e164) return null;
  try { return JSON.parse(localStorage.getItem('wa_val_' + e164)); } catch (e) { return null; }
}
function setWaValidation(e164, isValid) {
  if (!e164) return;
  localStorage.setItem('wa_val_' + e164, JSON.stringify(isValid));
}

function cleanSnippet(text) {
  if (!text) return '';
  let t = String(text);
  // Quitar scripts de VentaFe (googletag, etc)
  t = t.split('googletag')[0]; // Quitar googletag y todo lo que sigue
  t = t.split('<script')[0]; // Quitar scripts
  // Quitar comentarios HTML
  t = t.replace(/<!--[\s\S]*?-->/g, '');
  // Quitar tags HTML
  t = t.replace(/<[^>]+>/g, ' ');
  // Decodificar TODAS las entidades HTML
  t = t.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  t = t.replace(/&#x27;/g, "'").replace(/&#x2F;/g, '/').replace(/&#47;/g, '/');
  t = t.replace(/&#8217;/g, "'").replace(/&#8230;/g, '...').replace(/&#8220;/g, '"').replace(/&#8221;/g, '"');
  t = t.replace(/&#8211;/g, '-').replace(/&#8212;/g, '--').replace(/&#8216;/g, "'");
  t = t.replace(/&#8242;/g, "'").replace(/&#8243;/g, '"').replace(/&nbsp;/g, ' ');
  // Colapsar espacios
  // FIX GEMINI SABUESO v3: doble escape \\s dentro de template literal DASHBOARD_HTML.
  // Sin esto, el motor JS come la barra invertida y deja /s+/g que destruye todas las 's'
  // del CRM ("Disputa" → "Di puta", "transferencia" → "tran ferencia", etc.)
  t = t.replace(/\\s+/g, ' ').trim();
  return t;
}

function cleanText(t) {
  return t.replace(/<[^>]+>/g, '').replace(/\\s+/g, ' ').trim().slice(0, 200);
}

// ── FILTERS ────────────────────────────────────────────────────────────────
function filterStatus(val, el) {
  S.statusFilter = val;
  document.querySelectorAll('.sidebar .filter-item').forEach(e => {
    if (e.id && e.id.startsWith('f-')) e.classList.remove('active');
  });
  if (el) el.classList.add('active');
  applyFilters();
}

// FIX QWEN v2.8: Nuevos filtros Contacto y Temperatura
function filterContact(val, el) {
  S.contactFilter = val;
  document.querySelectorAll('#fc-todos, #fc-whatsapp, #fc-messenger, #fc-email, #fc-sin-contacto').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  applyFilters();
}

function filterHeat(val, el) {
  S.heatFilter = val;
  document.querySelectorAll('#fh-todos, #fh-hot, #fh-warm, #fh-cold').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  applyFilters();
}

function applyFilters() {
  const q   = (document.getElementById('searchInput')?.value || '').toLowerCase();
  const pv  = S.provFilter;
  const sf  = S.sourceFilter;
  const cf  = S.contactFilter;
  const hf  = S.heatFilter;

  S.filtered = S.crmLeads.filter(l => {
    if (S.statusFilter !== 'todos' && l._status !== S.statusFilter) return false;
    if (pv !== 'todos' && (l.provincia || '') !== pv) return false;
    // FIX GEMINI: sourceFilter case-insensitive + substring match.
    // Antes: comparacion estricta fallaba porque Python hacia .title() → "Ventafe.Com.Ar"
    // Ahora: matchea si el source del lead contiene el filtro (case-insensitive)
    if (sf !== 'todos') {
      const leadSrc = (l.source_label || l.source || l.platform || '').toLowerCase();
      const filterSrc = sf.toLowerCase();
      if (!leadSrc.includes(filterSrc) && !filterSrc.includes(leadSrc)) return false;
    }
    // FIX QWEN v2.8: filtro Contacto (SIMON FIX 2026-07-09: separar WA real de Messenger)
    if (cf === 'whatsapp' && !l._wa_url) return false;
    if (cf === 'messenger' && !(l.fb_username || l.fb_author_id)) return false;
    if (cf === 'email' && !(l.email || l.email_publico)) return false;
    if (cf === 'sin_contacto' && (l._wa_url || l.fb_username || l.fb_author_id || l.email || l.email_publico)) return false;
    // FIX QWEN v2.8: filtro Temperatura
    if (hf !== 'todos' && l._heat_label !== hf) return false;
    if (q) {
      const hay = \`\${l._display_name} \${l.provincia} \${l._resumen} \${l.source_label}\`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    // FIX GEMINI AUDIT v5: NO bloquear leads sin provincia ni por resumen genérico.
    // Esos filtros extras hacían que la tabla mostrara 3 leads mientras el KPI decía 32.
    // Ahora la tabla respeta solo los filtros de la sidebar (igual que el KPI).
    return true;
  });

  const sort = document.getElementById('sortSel')?.value || 'heat';
  S.filtered.sort((a, b) => {
    // Pinned primero (por pinned_rank ascendente)
    const aPin = a.pinned ? 0 : 1;
    const bPin = b.pinned ? 0 : 1;
    if (aPin !== bPin) return aPin - bPin;
    if (a.pinned && b.pinned) return (a.pinned_rank || 99) - (b.pinned_rank || 99);
    // Resto: por heat_score o fecha
    if (sort === 'heat') return (b._heat_score || 0) - (a._heat_score || 0);
    if (sort === 'provincia') return (a.provincia || '').localeCompare(b.provincia || '');
    return (b.fecha_iso || '').localeCompare(a.fecha_iso || '');
  });

  renderTable();
  renderCounts();
}

// ── RENDER TABLE ───────────────────────────────────────────────────────────
function renderTable() {
  // NO llamar applyFilters() aquí — causa recursión infinita
  // (applyFilters llama a renderTable al final)
  const leads = S.filtered;

  if (!leads.length) {
    document.getElementById('tableContainer').innerHTML = \`
      <div class="empty">
        <h3>No hay casos en este filtro</h3>
        <p>Probá cambiar el filtro de estado o buscá por otro término.</p>
      </div>\`;
    return;
  }

  const rows = leads.map(l => \`
    <tr onclick="openDetail('\${l.id}')" style="cursor:pointer" class="heat-\${l._heat_label} \${l.pinned ? 'pinned-row' : ''}">
      <td class="td-nombre">
        \${l.pinned ? '📌 ' : ''}\${l._heat_label === 'hot' ? '🔥 ' : l._heat_label === 'warm' ? '⚡ ' : ''}
        \${escH(l._display_name)}
        <small>\${escH(l.fecha_iso || '—')} · \${escH(l.source_label || '?')}</small>
      </td>
      <td>\${escH(l.provincia || '—')}</td>
      <td class="td-resumen"><p>\${escH(l._resumen)}</p></td>
      <td>
        <span class="badge badge-\${cssStatus(l._status)}">\${l._status}</span>
      </td>
      <td>
        <div class="actions" onclick="event.stopPropagation()">
          \${l._wa_state === 'validated_whatsapp'
            ? \`<a class="btn-wa-big" href="\${l._wa_url}" target="_blank" title="WhatsApp verificado">\${WA_ICON}</a>\`
            : l._wa_state === 'normalized_contact'
              ? \`<button class="btn-wa-pending" onclick="validateWaFromTable('\${l.id}')" title="Click para validar WhatsApp">\${WA_ICON_GRAY}</button>\`
              : l._wa_state === 'not_whatsapp'
                ? \`<span class="wa-none" title="No tiene WhatsApp">❌</span>\`
                : l.email
                  ? \`<span style="font-size:16px" title="\${l.email}">✉️</span>\`
                  : \`\`
          }
          \${l.fb_username && !l._wa_url && (l.source_label === 'Facebook' || l.platform === 'Facebook')
            ? \`<a class="btn-wa-big" href="https://m.me/\${l.fb_username}" target="_blank" title="Mensaje por Messenger" style="background:#0084FF">\${'<svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M12 2C6.5 2 2 6.1 2 11.2c0 2.9 1.4 5.5 3.7 7.2V22l3.4-1.9c.9.3 1.9.4 2.9.4 5.5 0 10-4.1 10-9.3S17.5 2 12 2zm1 12.5l-2.5-2.7-4.9 2.7 5.4-5.7 2.6 2.7 4.8-2.7-5.4 5.7z"/></svg>'}</a>\`
            : \`\`
          }
          <button class="btn-icon" onclick="openDetail('\${l.id}')" title="Ver detalle">📋</button>
        </div>
      </td>
    </tr>
  \`).join('');

  document.getElementById('tableContainer').innerHTML = \`
    <table>
      <thead>
        <tr>
          <th>Nombre / Usuario</th>
          <th>Provincia</th>
          <th>Problema</th>
          <th>Estado</th>
          <th>Acción</th>
        </tr>
      </thead>
      <tbody>\${rows}</tbody>
    </table>\`;
}

function cssStatus(s) {
  const map = { 'Nuevo': 'nuevo', 'Contactado': 'contactado',
    'En gestión': 'gestion', 'Cerrado': 'cerrado', 'Descartado': 'descartado' };
  return map[s] || 'nuevo';
}

function escH(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── KPIs ──────────────────────────────────────────────────────────────────
function renderKPIs() {
  const leads    = S.crmLeads;
  // SIMON FIX 2026-07-09: KPI honesto — WhatsApp solo si hay teléfono real, Messenger separado.
  const withWa   = leads.filter(l => l._wa_url || l._wa_state === 'validated_whatsapp' || l._wa_state === 'normalized_contact').length;
  const withMsg  = leads.filter(l => (l.fb_username || l.fb_author_id) && (l.source_label === 'Facebook' || l.platform === 'Facebook' || l.source === 'facebook_apify')).length;
  const enProc   = leads.filter(l => ['Contactado','En gestión'].includes(l._status)).length;
  const cerrados = leads.filter(l => l._status === 'Cerrado');
  const pct = getComisionPct() / 100;
  const comision = cerrados.reduce((sum, l) => {
    const stored = DB.get(l.id);
    return sum + (stored.monto || 0) * pct;
  }, 0);

  document.getElementById('kpi-total').textContent    = leads.length;
  document.getElementById('kpi-wa').textContent       = withWa;
  const kpiMsgEl = document.getElementById('kpi-messenger');
  if (kpiMsgEl) kpiMsgEl.textContent = withMsg;
  document.getElementById('kpi-proceso').textContent  = enProc;
  document.getElementById('kpi-cerrados').textContent = cerrados.length;
  const comEl = document.getElementById('kpi-comision');
  if (comEl) comEl.textContent = '$' + comision.toLocaleString('es-AR');
}

// ── SIDEBAR DYNAMIC ───────────────────────────────────────────────────────
function renderCounts() {
  const statuses = ['Nuevo','Contactado','En gestión','Cerrado','Descartado'];
  document.getElementById('cnt-todos').textContent = S.crmLeads.length;
  statuses.forEach(s => {
    const el = document.getElementById('cnt-' + s);
    if (el) el.textContent = S.crmLeads.filter(l => l._status === s).length;
  });

  // FIX QWEN v2.8: contadores nuevos Contacto y Temperatura
  const cntContactTodos = document.getElementById('cnt-contact-todos');
  const cntWhatsapp     = document.getElementById('cnt-whatsapp');
  const cntEmail        = document.getElementById('cnt-email');
  const cntSinContacto  = document.getElementById('cnt-sin-contacto');
  const cntHeatTodos    = document.getElementById('cnt-heat-todos');
  const cntHot          = document.getElementById('cnt-hot');
  const cntWarm         = document.getElementById('cnt-warm');
  const cntCold         = document.getElementById('cnt-cold');

  if (cntContactTodos) cntContactTodos.textContent = S.crmLeads.length;
  if (cntWhatsapp)     cntWhatsapp.textContent     = S.crmLeads.filter(l => l._wa_url).length;
  const cntMessenger = document.getElementById('cnt-messenger');
  if (cntMessenger)    cntMessenger.textContent    = S.crmLeads.filter(l => l.fb_username || l.fb_author_id).length;
  if (cntEmail)        cntEmail.textContent        = S.crmLeads.filter(l => l.email || l.email_publico).length;
  if (cntSinContacto)  cntSinContacto.textContent  = S.crmLeads.filter(l => !l._wa_url && !(l.fb_username || l.fb_author_id) && !(l.email || l.email_publico)).length;
  if (cntHeatTodos)    cntHeatTodos.textContent    = S.crmLeads.length;
  if (cntHot)          cntHot.textContent          = S.crmLeads.filter(l => l._heat_label === 'hot').length;
  if (cntWarm)         cntWarm.textContent         = S.crmLeads.filter(l => l._heat_label === 'warm').length;
  if (cntCold)         cntCold.textContent         = S.crmLeads.filter(l => l._heat_label === 'cold').length;
}

function renderSidebar() {
  // Provincias
  const provs = [...new Set(S.crmLeads.map(l => l.provincia).filter(Boolean))].sort();
  const pfContainer = document.getElementById('prov-filters');
  pfContainer.innerHTML = \`
    <div class="filter-item \${S.provFilter==='todos'?'active':''}" onclick="setProvFilter('todos',this)">
      Todas <span class="filter-count">\${S.crmLeads.length}</span>
    </div>
    \${provs.map(p => \`
      <div class="filter-item \${S.provFilter===p?'active':''}" onclick="setProvFilter('\${p}',this)">
        \${p} <span class="filter-count">\${S.crmLeads.filter(l=>l.provincia===p).length}</span>
      </div>
    \`).join('')}\`;

  // Fuentes
  const srcs = [...new Set(S.crmLeads.map(l => l.source_label || l.source).filter(Boolean))].sort();
  const sfContainer = document.getElementById('source-filters');
  sfContainer.innerHTML = srcs.map(s => \`
    <div class="filter-item \${S.sourceFilter===s?'active':''}" onclick="setSourceFilter('\${s}',this)">
      \${s} <span class="filter-count">\${S.crmLeads.filter(l=>(l.source_label||l.source)===s).length}</span>
    </div>
  \`).join('');
}

function setProvFilter(val, el) {
  S.provFilter = val;
  document.querySelectorAll('#prov-filters .filter-item').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  applyFilters();
}

function setSourceFilter(val, el) {
  S.sourceFilter = val;
  document.querySelectorAll('#source-filters .filter-item').forEach(e => e.classList.remove('active'));
  if (el) el.classList.add('active');
  applyFilters();
}

// ── DETAIL MODAL ───────────────────────────────────────────────────────────
function openDetail(id) {
  const l = S.crmLeads.find(x => x.id === id);
  if (!l) return;
  S.currentId = id;

  document.getElementById('modal-title').textContent    = l._display_name;
  document.getElementById('modal-author').textContent   = l._display_name;
  document.getElementById('modal-provincia').textContent = l.provincia || '—';
  document.getElementById('modal-source').textContent   = l.source_label || l.source || '—';
  document.getElementById('modal-body').textContent     = cleanSnippet(l.body || l.title || '') || '—';
  document.getElementById('modal-notes').value          = l._notes || '';
  document.getElementById('modal-status-sel').value     = l._status || 'Nuevo';

  // M3: Si está Cerrado, mostrar campo monto
  const storedForMonto = DB.get(id);
  const montoField = document.getElementById('modal-monto-field');
  if (l._status === 'Cerrado') {
    montoField.style.display = 'block';
    document.getElementById('modal-monto').value = storedForMonto.monto || '';
    updateComision();
  } else {
    montoField.style.display = 'none';
  }

  // FORENSIC LOG: mostrar card de registro solo si estado=Cerrado
  const logCard = document.getElementById('forensic-log-card');
  if (logCard) {
    logCard.style.display = (l._status === 'Cerrado') ? 'block' : 'none';
  }

  // N1: Fetch Reddit bio async (busca contacto en bio del user)
  loadBioIfReddit(l);

  const url = document.getElementById('modal-url');
  url.href = l.url || '#';
  url.textContent = l.url ? 'Abrir enlace →' : 'Sin enlace';

  // M8: Link al perfil del autor (Reddit u/xxx → DM directo)
  const profileField = document.getElementById('modal-profile-field');
  const profileUrl = document.getElementById('modal-profile-url');
  const author = (l.persona || l.author || '').trim();
  const redditUser = stripUprefix(author);
  if (redditUser && (l.url || '').includes('reddit.com')) {
    profileUrl.href = 'https://www.reddit.com/user/' + redditUser + '/';
    profileField.style.display = 'block';
  } else {
    profileField.style.display = 'none';
  }

  const box = document.getElementById('modal-contact-box');
  const waBtn = document.getElementById('modal-wa-btn');
  const phoneLabel = document.getElementById('modal-phone-label');

  if (l._wa_state === 'validated_whatsapp') {
    b…14562 tokens truncated…eaders: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'text/html',
                'Accept-Language': 'es-AR,es;q=0.9',
              }
            });
            if (!r.ok) continue;
            const html = await r.text();
            debugHtmlSize = Math.max(debugHtmlSize, html.length);
            const resultBlocks = html.split('<div class="result ').slice(1);
            debugResultCount = Math.max(debugResultCount, resultBlocks.length);
            if (!debugFirstSnippet) {
              const firstBlock = resultBlocks[0] || '';
              const snipM = firstBlock.match(/<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)<\/a>/);
              if (snipM) debugFirstSnippet = snipM[1].replace(/<[^>]+>/g, ' ').trim().slice(0, 200);
            }

            // Extraer resultados de DDG (resultBlocks ya declarado arriba en debug)
            for (const block of resultBlocks.slice(0, 15)) {
              // Extraer title + url
              const titleMatch = block.match(/<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)<\/a>/);
              const snippetMatch = block.match(/<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)<\/a>/);

              if (!titleMatch) continue;

              let postUrl = titleMatch[1];
              // DDG wrap URLs en uddg= redirects, extraer URL real
              const uddgMatch = postUrl.match(/uddg=([^&]+)/);
              if (uddgMatch) {
                try { postUrl = decodeURIComponent(uddgMatch[1]); } catch (e) {}
              }
              const title = titleMatch[2].replace(/<[^>]+>/g, '').trim();
              const snippetHtml = snippetMatch ? snippetMatch[1] : '';
              const snippet = snippetHtml.replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();

              if (!snippet || snippet.length < 30) continue;

              // FILTRO CONTEXTUAL (GPT+H.AI): dolor + contacto en mismo snippet
              const hasPain = PAIN_KEYWORDS.test(snippet + ' ' + title);
              if (!hasPain) continue;

              const phones = [...new Set((snippet.match(AR_PHONE) || []).map(p => p.trim()))];
              const waMatches = [...snippet.matchAll(AR_WA)];
              const was = [...new Set(waMatches.map(m => (m[1] || m[2] || '').trim()).filter(Boolean))];
              const emails = [...new Set((snippet.match(EMAIL_RE) || [])
                .map(e => e.toLowerCase().trim())
                .filter(e => !SPAM_DOMAINS.some(d => e.includes(d))))];

              // Solo incluir si HAY contacto (no es lead sin contacto)
              if (phones.length === 0 && was.length === 0 && emails.length === 0) continue;

              // Determinar platform desde URL
              let platform = 'web';
              if (postUrl.includes('foromoto')) platform = 'ForoMoto';
              else if (postUrl.includes('lavoz')) platform = 'ClasificadosLaVoz';
              else if (postUrl.includes('demotores')) platform = 'Demotores';
              else if (postUrl.includes('olx')) platform = 'OLX';
              else if (postUrl.includes('reddit')) platform = 'Reddit';
              else if (postUrl.includes('facebook')) platform = 'Facebook';
              else if (postUrl.includes('taringa')) platform = 'Taringa';
              else {
                // Extraer dominio
                try { platform = new URL(postUrl).hostname.replace('www.', ''); } catch (e) {}
              }

              allLeads.push({
                id: 'foro_' + Math.abs(postUrl.split('').reduce((a, c) => ((a << 5) - a + c.charCodeAt(0)) | 0, 0)),
                source: 'ddg_foros_ar',
                source_label: platform,
                platform: platform,
                title: title.slice(0, 200),
                snippet: snippet.slice(0, 2000),
                url: postUrl,
                fecha_iso: '',
                score: 0,
                phone: phones[0] || '',
                whatsapp: was[0] || '',
                email: emails[0] || '',
                whatsapp_publico: was[0] || '',
                telefono_publico: phones[0] || '',
                email_publico: emails[0] || '',
                has_contact: true,
                contact_source: 'ddg_snippet',
              });
            }
          } catch (e) {
            // Continuar con siguiente query si una falla
            continue;
          }
        }

        return jsonResponse({
          ok: true,
          leads: allLeads,
          total: allLeads.length,
          sources_queried: QUERIES.length,
          debug: {
            queries: QUERIES,
            max_html_size: debugHtmlSize,
            max_results_per_query: debugResultCount,
            first_snippet_found: debugFirstSnippet,
            note: 'Si total=0 y max_results_per_query=0, DDG bloquea desde edge',
          },
        }, corsHeaders);
      } catch (err) {
        return jsonResponse({ ok: false, error: err.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/clasificar-webhook ─── Recibe eventos de clasific.ar
    // Eventos: report.completed, report.failed
    if (url.pathname === '/api/clasificar-webhook' && request.method === 'POST') {
      // Verificar secreto del webhook
      const sig = request.headers.get('x-clasificar-webhook-secret');
      if (!env.CLASIFICAR_WEBHOOK_SECRET || sig !== env.CLASIFICAR_WEBHOOK_SECRET) {
        return jsonResponse({ ok: false, error: 'invalid_secret' }, corsHeaders, 401);
      }
      try {
        const event = await request.json();
        const eventType = event.type || event.eventType || '';
        const reportData = event.data || event.report || {};
        const plate = reportData.plate || event.plate || '';

        console.log('Webhook clasific.ar:', eventType, 'plate:', plate);

        if (eventType === 'report.completed' && plate) {
          // Guardar reporte completo en KV para consulta posterior
          const reportKey = 'clasificar_report:' + plate.toUpperCase();
          await env.LEADX_KV.put(reportKey, JSON.stringify({
            plate: plate.toUpperCase(),
            status: 'completed',
            data: reportData,
            completed_at: new Date().toISOString(),
          }), { expirationTtl: 86400 * 7 }); // 7 dias TTL

          return jsonResponse({ ok: true, received: 'completed', plate }, corsHeaders);
        } else if (eventType === 'report.failed') {
          const reportKey = 'clasificar_report:' + plate.toUpperCase();
          await env.LEADX_KV.put(reportKey, JSON.stringify({
            plate: plate.toUpperCase(),
            status: 'failed',
            error: reportData.error || 'unknown',
            failed_at: new Date().toISOString(),
          }), { expirationTtl: 3600 });

          return jsonResponse({ ok: true, received: 'failed', plate }, corsHeaders);
        }

        // Evento desconocido — igual responder OK para que no reintente
        return jsonResponse({ ok: true, received: eventType, note: 'unhandled_event' }, corsHeaders);
      } catch (e) {
        console.error('Webhook error:', e.message);
        return jsonResponse({ ok: true, error: e.message }, corsHeaders); // OK para evitar retry
      }
    }

    // ─── GET /api/clasificar-webhook ─── Health check
    if (url.pathname === '/api/clasificar-webhook' && request.method === 'GET') {
      return jsonResponse({ ok: true, endpoint: 'clasificar-webhook', status: 'active' }, corsHeaders);
    }

    // ─── POST /api/clasificar-patente ─── Inicia busqueda asincrona en clasific.ar
    // Body: { "plate": "AB123CD" }
    // Responde inmediatamente con { ok: true, status: 'pending' }
    // El resultado llega via webhook y se guarda en KV
    // Despues consultar GET /api/clasificar-patente?plate=AB123CD para ver resultado
    if (url.pathname === '/api/clasificar-patente' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      if (!env.CLASIFICAR_API_KEY) {
        return jsonResponse({ ok: false, error: 'no_clasificar_key' }, corsHeaders, 500);
      }
      try {
        const body = await request.json();
        const plate = (body.plate || '').toUpperCase().trim();
        if (!plate || plate.length < 6) {
          return jsonResponse({ ok: false, error: 'invalid_plate' }, corsHeaders, 400);
        }

        // Marcar como pending en KV
        const pendingKey = 'clasificar_report:' + plate;
        await env.LEADX_KV.put(pendingKey, JSON.stringify({
          plate: plate,
          status: 'pending',
          requested_at: new Date().toISOString(),
        }), { expirationTtl: 3600 });

        // Disparar busqueda asincrona en clasific.ar
        const apiUrl = 'https://api.clasific.ar/v1/reports/';
        const apiRes = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'x-api-key': env.CLASIFICAR_API_KEY,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ plate: plate, type: 'intelligent' }),
        });

        const apiData = await apiRes.json().catch(() => ({}));

        return jsonResponse({
          ok: true,
          plate: plate,
          status: 'pending',
          api_status: apiRes.status,
          api_response: apiData,
          note: 'El resultado llegara via webhook. Consulta GET /api/clasificar-patente?plate=' + plate + ' en 30-60s',
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/clasificar-patente?plate=XXX ─── Lee resultado desde KV
    if (url.pathname === '/api/clasificar-patente' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      const plate = (url.searchParams.get('plate') || '').toUpperCase().trim();
      if (!plate) {
        return jsonResponse({ ok: false, error: 'missing_plate' }, corsHeaders, 400);
      }
      try {
        const reportKey = 'clasificar_report:' + plate;
        const raw = await env.LEADX_KV.get(reportKey);
        if (!raw) {
          return jsonResponse({ ok: false, error: 'no_report_yet', plate, status: 'never_requested' }, corsHeaders, 404);
        }
        const report = JSON.parse(raw);
        return jsonResponse({ ok: true, plate, ...report }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/clasificar-basic?plate=XXX ─── Datos basicos del vehiculo (sync, sin webhook)
    // Plan free: 200 consultas/mes
    if (url.pathname === '/api/clasificar-basic' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      if (!env.CLASIFICAR_API_KEY) {
        return jsonResponse({ ok: false, error: 'no_clasificar_key' }, corsHeaders, 500);
      }
      const plate = (url.searchParams.get('plate') || '').toUpperCase().trim();
      if (!plate) {
        return jsonResponse({ ok: false, error: 'missing_plate' }, corsHeaders, 400);
      }
      try {
        const apiUrl = 'https://api.clasific.ar/v1/vehicles/basic?plate=' + encodeURIComponent(plate);
        const apiRes = await fetch(apiUrl, {
          headers: { 'x-api-key': env.CLASIFICAR_API_KEY, 'Accept': 'application/json' },
        });
        const apiData = await apiRes.json();
        return jsonResponse({ ok: apiRes.ok, plate, api_status: apiRes.status, data: apiData }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/apify-facebook ─── Scrapea grupos de Facebook via Apify
    // Body: { "groupUrls": ["https://www.facebook.com/groups/XXX"], "maxPosts": 20 }
    // Usa cookies de FB almacenadas como secret para autenticar
    if (url.pathname === '/api/apify-facebook' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      if (!env.APIFY_TOKEN) {
        return jsonResponse({ ok: false, error: 'no_apify_token' }, corsHeaders, 500);
      }
      try {
        // Leer cookies de KV (refrescables via /cookies.html) con fallback a secret
        let cookiesStr = env.FB_COOKIES || '';
        let cookiesSource = 'secret';
        try {
          const raw = await env.LEADX_KV.get('fb_cookies');
          if (raw) {
            const data = JSON.parse(raw);
            if (data.cookies && Array.isArray(data.cookies) && data.cookies.length > 0) {
              cookiesStr = data.cookies.map(c => c.name + '=' + c.value).join('; ');
              cookiesSource = 'kv_' + (data.updated_at || '').slice(0, 10);
            }
          }
        } catch (e) {}
        if (!cookiesStr) {
          return jsonResponse({ ok: false, error: 'no_fb_cookies', hint: 'Ir a /cookies.html?key=SECRET para configurar' }, corsHeaders, 500);
        }
        const body = await request.json();
        const groupUrls = body.groupUrls || [
          'https://www.facebook.com/groups/276074287942602', // Defensas contra Multas AR
          'https://www.facebook.com/groups/1314803566577708', // Venta Santa Fe y Alrededores
        ];
        const maxPosts = body.maxPosts || 20;
        const fetchComments = body.fetchComments !== false;
        const maxComments = body.maxCommentsPerPost || 5;

        // Lanzar run en Apify
        const apifyInput = {
          startUrls: groupUrls,
          resultsLimit: maxPosts,
          maxPostsPerGroup: maxPosts,
          fetchComments: fetchComments,
          maxCommentsPerPost: maxComments,
          cookies: cookiesStr,
        };

        // Qwen fix: Pasar webhookUrl directamente en el body del run
        const runRes = await fetch('https://api.apify.com/v2/acts/uophWH4OrRO2TtXTT/runs?token=' + env.APIFY_TOKEN, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            ...apifyInput,
            webhookUrl: 'https://leadx.simondalmasso44.workers.dev/api/apify-webhook',
          }),
        });

        if (!runRes.ok) {
          const errText = await runRes.text();
          return jsonResponse({ ok: false, error: 'apify_failed', status: runRes.status, detail: errText.slice(0, 500) }, corsHeaders, 500);
        }

        const runData = await runRes.json();
        const runId = runData.data.id;
        const datasetId = runData.data.defaultDatasetId;

        // Fire & Forget - devolver runId inmediatamente
        return jsonResponse({
          ok: true,
          status: 'processing',
          run_id: runId,
          dataset_id: datasetId,
          webhook_configured: true,
          message: 'Apify procesando. Resultados via webhook automatico.',
          cookies_source: cookiesSource,
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── GET /cookies.html ─── UI para refrescar cookies FB
    if (url.pathname === '/cookies.html' || url.pathname === '/cookies') {
      const secret = url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return new Response('Unauthorized. Usa /cookies.html?key=TU_SECRET', { status: 401 });
      }
      return new Response(COOKIES_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }

    // ─── GET /api/cookies ─── Estado de cookies FB
    if (url.pathname === '/api/cookies' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret') || url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const raw = await env.LEADX_KV.get('fb_cookies');
        let status = 'never_set';
        let updatedAt = null;
        let cookieCount = 0;
        let expiresAt = null;
        let daysUntilExpiry = null;
        if (raw) {
          const data = JSON.parse(raw);
          updatedAt = data.updated_at;
          cookieCount = (data.cookies || []).length;
          // Buscar cookie xs (sesion critica)
          const xsCookie = (data.cookies || []).find(c => c.name === 'xs');
          if (xsCookie && xsCookie.expirationDate) {
            expiresAt = new Date(xsCookie.expirationDate * 1000).toISOString();
            daysUntilExpiry = Math.floor((xsCookie.expirationDate - Date.now() / 1000) / 86400);
          }
          status = daysUntilExpiry !== null ? (daysUntilExpiry > 0 ? 'valid' : 'expired') : 'no_xs';
        }
        return jsonResponse({
          ok: true,
          status: status,
          cookie_count: cookieCount,
          updated_at: updatedAt,
          xs_expires_at: expiresAt,
          days_until_expiry: daysUntilExpiry,
          recommendation: daysUntilExpiry !== null && daysUntilExpiry < 7
            ? 'REFRESCAR AHORA - cookies por vencer'
            : 'OK - refrescar en ' + (daysUntilExpiry || 14) + ' dias',
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/cookies ─── Guardar cookies FB nuevas
    if (url.pathname === '/api/cookies' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret') || url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const body = await request.json();
        let cookies = body.cookies || body;

        // Si viene como string, intentar parsear
        if (typeof cookies === 'string') {
          try { cookies = JSON.parse(cookies); } catch (e) {
            return jsonResponse({ ok: false, error: 'invalid_json_string' }, corsHeaders, 400);
          }
        }

        if (!Array.isArray(cookies)) {
          return jsonResponse({ ok: false, error: 'cookies_must_be_array' }, corsHeaders, 400);
        }

        // Filtrar solo cookies de facebook.com
        const fbCookies = cookies.filter(c => (c.domain || '').includes('facebook.com'));
        if (fbCookies.length === 0) {
          return jsonResponse({ ok: false, error: 'no_facebook_cookies_found' }, corsHeaders, 400);
        }

        // Guardar en KV (sin TTL - persisten hasta que se refresquen)
        const payload = {
          cookies: fbCookies,
          updated_at: new Date().toISOString(),
          source: body.source || 'manual',
        };
        await env.LEADX_KV.put('fb_cookies', JSON.stringify(payload));

        // Calcular info util para la respuesta
        const xsCookie = fbCookies.find(c => c.name === 'xs');
        let expiresAt = null;
        let daysUntilExpiry = null;
        if (xsCookie && xsCookie.expirationDate) {
          expiresAt = new Date(xsCookie.expirationDate * 1000).toISOString();
          daysUntilExpiry = Math.floor((xsCookie.expirationDate - Date.now() / 1000) / 86400);
        }

        return jsonResponse({
          ok: true,
          saved: fbCookies.length,
          xs_expires_at: expiresAt,
          days_until_expiry: daysUntilExpiry,
          updated_at: payload.updated_at,
          recommendation: 'Refrescar en ' + Math.min(daysUntilExpiry || 14, 14) + ' dias',
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/whatsapp-validate ─── Fire & Forget (Qwen P0 fix)
    // Body: { "phones": ["5491154541802"] }
    // Devuelve inmediatamente, resultados via /api/whatsapp-webhook
    if (url.pathname === '/api/whatsapp-validate' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret') || url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      if (!env.APIFY_TOKEN) {
        return jsonResponse({ ok: false, error: 'no_apify_token' }, corsHeaders, 500);
      }
      try {
        const body = await request.json();
        const phones = body.phones || [];
        if (!Array.isArray(phones) || phones.length === 0) {
          return jsonResponse({ ok: false, error: 'missing_phones' }, corsHeaders, 400);
        }

        // Fire & Forget: un run por telefono, devolver inmediatamente
        // FIX QWEN P0: Pasar webhookUrl como query param para que Apify
        // llame a /api/whatsapp-webhook cuando termine (sin polling).
        const webhookUrl = `${url.origin}/api/whatsapp-webhook`;
        const runIds = [];
        for (const phone of phones.slice(0, 5)) {
          try {
            const runRes = await fetch(
              `https://api.apify.com/v2/acts/devscrapper~whatsapp-number-validator/runs?token=${env.APIFY_TOKEN}&webhookUrl=${encodeURIComponent(webhookUrl)}`,
              {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phoneNumber: phone }),
              }
            );
            if (runRes.ok) {
              const runData = await runRes.json();
              runIds.push({ phone, runId: runData.data.id });
            }
          } catch (e) {}
        }

        return jsonResponse({
          ok: true,
          status: 'processing',
          runs: runIds,
          webhook_configured: true,
          message: 'Validacion en background. Resultados via webhook automatico.',
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/whatsapp-webhook ─── Recibe resultados de Apify WA validator
    if (url.pathname === '/api/whatsapp-webhook' && request.method === 'POST') {
      try {
        const body = await request.json();
        const results = body.results || body || [];
        for (const r of (Array.isArray(results) ? results : [results])) {
          if (r && r.phoneNumber) {
            const key = 'wa_val:' + r.phoneNumber;
            await env.LEADX_KV.put(key, JSON.stringify({
              phone: r.phoneNumber,
              isValid: r.isValid || false,
              exists: r.exists || false,
              validated_at: new Date().toISOString(),
            }), { expirationTtl: 86400 });
          }
        }
        return jsonResponse({ ok: true, received: Array.isArray(results) ? results.length : 1 }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: true, error: e.message }, corsHeaders);
      }
    }

    // ─── POST /api/apify-webhook ─── Recibe resultados de Apify Facebook scraper
    // FIX QWEN: filtro estricto de dolor vehicular + scoring dinámico (no hardcodear 50)
    if (url.pathname === '/api/apify-webhook' && request.method === 'POST') {
      try {
        const body = await request.json();
        const items = body.items || body.results || body || [];
        const leads = [];
        const seenAuthors = new Set(); // FIX ANTI-DUPLICADOS: 1 post por autor
        const AR_PHONE = /(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}/g;
        const EMAIL_RE = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;

        // FIX QWEN v2: Filtro de dolor + intención (adaptado a grupos de consulta/reclamo FB)
        const PAIN_KW = /multa|fotomulta|infracci[oó]n|forzar.barrera|peaje|deuda|libre.?deuda|transferencia|transferir|patente|08|c[eé]dula|veraz|registro.automotor|juez.de.faltas|vencimiento|prescripci[oó]n|papeles.al.d[ií]a|listo.para.transferir|sin.deuda|titular|reclamo|defender|negativa|evidencia|foto/i;
        const INTENT_KW = /consultar|sabe.del.tema|ayuda|recomiendan|se.puede|abonar|mitad|defender|negativa/i;

        for (const post of (Array.isArray(items) ? items : [])) {
          const text = post.text || post.postText || '';
          const author = post.authorName || post.author || '';
          const postUrl = post.url || post.postUrl || '';
          // FIX GEMINI Estrategia A: capturar authorId para botón de Messenger.
          // Apify trae authorId (numérico o pfbid...). m.me/{authorId} abre chat directo.
          const authorIdRaw = post.authorId || (post.user && post.user.id) || '';
          let fbUserId = '';
          if (authorIdRaw) {
            fbUserId = String(authorIdRaw).trim();
          }
          if (!text && !author) continue;

          // Filtro de entrada: exige dolor vehicular O intención de consulta/reclamo
          if (!PAIN_KW.test(text) && !INTENT_KW.test(text)) continue;

          // FIX ANTI-SPAM: bloquear posts de venta de cursos/seminarios (no son leads)
          const SPAM_KW = /seminario|curso|asincr[oó]nico|pack incluye|no te lo pierdas|cupos limitados/i;
          if (SPAM_KW.test(text)) continue;

          // FIX SIMON: bloquear OFERTAS de servicios gestoriales (son competidores, no leads).
          const SERVICE_OFFER_KW = /elimino\s+multas|saco\s+turnos|hago\s+informes|gestor[ií]a|gestor\s+automotor|ofrezco\s+mis\s+servicios|mis\s+servicios|consultanos|defendemos\s+tus\s+derechos|sacamos\s+turnos|realizamos\s+informes/i;
          if (SERVICE_OFFER_KW.test(text)) continue;

          // FIX SIMON v2: bloquear avisos de venta de autos sin dolor (no son leads para gestoría).
          // "se vende taxi", "consultar por privado" = aviso comercial, no persona con problema.
          const SALES_AD_KW = /se\s+vende\s+(taxi|auto|moto|camioneta|veh[ií]culo)|consultar\s+por\s+privado|consultar\s+privado/i;
          if (SALES_AD_KW.test(text)) continue;

          // FIX ANTI-DUPLICADOS: si el mismo autor ya tiene un post, solo quedarse con el de mayor score
          const authorKey = author.toLowerCase().trim();
          if (seenAuthors.has(authorKey)) continue;
          seenAuthors.add(authorKey);

          const phones = [...new Set((text.match(AR_PHONE) || []).map(p => p.trim()))];
          const emails = [...new Set((text.match(EMAIL_RE) || []).map(e => e.toLowerCase()))];
          const patenteMatch = text.match(/\\b([A-Za-z]{2}\\s?\\d{3}\\s?[A-Za-z]{2})\\b/i);

          // FIX SAKANA adaptado: regex contextual para capturar números después de keywords.
          // El AR_PHONE anterior solo captura si el número empieza con código de área AR.
          // Este regex captura números que vienen después de "whatsapp", "wsp", "celular", etc.
          // aunque no tengan el formato estándar. Complemento, no reemplazo.
          const WA_CONTEXT_RE = /(?:whatsapp|wsp|wapp|wp|wasap|contactame|escribime|mandame|llamame|tel[eé]fono|celular|cel|fijo)\s*[:\.]?\s*([+]?\d[\d\s\-\(\)]{8,15})/gi;
          let waMatch;
          while ((waMatch = WA_CONTEXT_RE.exec(text)) !== null) {
            const num = waMatch[1].trim();
            if (!phones.includes(num)) phones.push(num);
          }

          // FIX SAKANA: Extraer teléfonos y emails de COMENTARIOS del post.
          // En grupos de FB, los usuarios suelen dejar su WhatsApp en comentarios
          // respondiendo al post original. El post text rara vez tiene teléfono.
          const comments = post.comments || [];
          for (const c of (Array.isArray(comments) ? comments : [])) {
            // FIX GEMINI Bug #2: fallback de campos de comentario (Apify cambia estructura entre versiones)
            const commentText = c.text || c.message || c.commentText || c.body || '';
            // No extraer teléfono de comentarios de gestoras/competidores
            if (SERVICE_OFFER_KW.test(commentText) || /gestor[ií]a/i.test(commentText)) continue;
            // AR_PHONE estándar
            const commentPhones = (commentText.match(AR_PHONE) || []).map(p => p.trim());
            for (const cp of commentPhones) {
              if (!phones.includes(cp)) phones.push(cp);
            }
            // FIX SAKANA: regex contextual también en comentarios
            let cmWaMatch;
            const cmWaRe = /(?:whatsapp|wsp|wapp|wp|wasap|contactame|escribime|mandame|llamame|tel[eé]fono|celular|cel)\s*[:\.]?\s*([+]?\d[\d\s\-\(\)]{8,15})/gi;
            while ((cmWaMatch = cmWaRe.exec(commentText)) !== null) {
              const num = cmWaMatch[1].trim();
              if (!phones.includes(num)) phones.push(num);
            }
            const commentEmails = (commentText.match(EMAIL_RE) || []).map(e => e.toLowerCase());
            for (const ce of commentEmails) {
              if (!emails.includes(ce)) emails.push(ce);
            }
          }

          // Scoring dinámico adaptado a grupos de consulta
          let score = 30;
          const scoreExplain = ['+30 base'];
          if (/multa|fotomulta|infracci[oó]n|forzar.barrera|peaje/i.test(text)) { score += 25; scoreExplain.push('+25 multa/fotomulta'); }
          if (/transferencia|transferir|08|titular|papeles/i.test(text)) { score += 20; scoreExplain.push('+20 transferencia/08'); }
          if (/deuda|libre.deuda|vencimiento|prescripci[oó]n|monto|abonar/i.test(text)) { score += 20; scoreExplain.push('+20 deuda/prescripción'); }
          if (INTENT_KW.test(text)) { score += 15; scoreExplain.push('+15 intención de consulta'); }
          if (phones.length > 0 || emails.length > 0) { score += 20; scoreExplain.push('+20 tiene contacto'); }
          if (patenteMatch) { score += 15; scoreExplain.push('+15 patente detectada'); }
          score = Math.min(100, score);

          if (score < 45) continue;

          leads.push({
            id: 'fb_' + (post.id || postUrl.split('/').slice(-2)[0] || Math.random().toString(36).slice(2)),
            source: 'facebook_apify',
            source_label: 'Facebook',
            platform: 'Facebook',
            author: author,
            persona: author,
            title: text.slice(0, 200),
            snippet: text.slice(0, 3000),
            url: postUrl,
            fecha_iso: (post.timestamp || '').slice(0, 10),
            score: score,
            score_explain: scoreExplain,
            whatsapp_publico: phones[0] || '',
            telefono_publico: phones[0] || '',
            email_publico: emails[0] || '',
            has_contact: phones.length > 0 || emails.length > 0,
            contact_confidence: (phones.length > 0 || emails.length > 0) ? 90 : (author ? 30 : 0),
            pipeline_version: '4.0',
            fb_username: fbUserId || '',
            // FIX GEMINI Bug #2: preservar URLs de imágenes para que el script VLM las descargue
            image_urls: [...new Set([
              ...(Array.isArray(post.imageUrls) ? post.imageUrls : []),
              ...(Array.isArray(post.images) ? post.images : []),
              ...(Array.isArray(post.media) ? post.media.map(m => m.url || m.thumbnail || '') : []),
              ...(Array.isArray(post.attachments) ? post.attachments.map(a => a.url || '') : []),
              ...(post.imageUrl ? [post.imageUrl] : []),
            ].filter(Boolean))],
          });
        }

        // Merge con leads existentes en KV
        const prevRaw = await env.LEADX_KV.get('leads:live');
        let prevLeads = [];
        if (prevRaw) {
          try { prevLeads = JSON.parse(prevRaw).leads_all || []; } catch (e) {}
        }
        const prevById = new Map();
        prevLeads.forEach(l => prevById.set(l.id, l));
        // FIX GEMINI Bug #1: Deep merge preservando estado del CRM de Sergio.
        // Antes: leads.forEach(l => prevById.set(l.id, l)); // sobrescribía todo
        // Ahora: preserva _status, _notes, _monto, _wa_state, etc.
        leads.forEach(newLead => {
          const existing = prevById.get(newLead.id);
          if (existing) {
            prevById.set(newLead.id, {
              ...newLead,
              score: existing.score ?? newLead.score,
              status: existing.status ?? newLead.status,
              _status: existing._status ?? newLead._status,
              _notes: existing._notes ?? newLead._notes,
              _monto: existing._monto ?? newLead._monto,
              _wa_state: existing._wa_state ?? newLead._wa_state,
              _wa_e164: existing._wa_e164 ?? newLead._wa_e164,
              whatsapp_publico: existing.whatsapp_publico || newLead.whatsapp_publico,
              telefono_publico: existing.telefono_publico || newLead.telefono_publico,
              email_publico: existing.email_publico || newLead.email_publico,
            });
          } else {
            prevById.set(newLead.id, newLead);
          }
        });
        const merged = Array.from(prevById.values());
        merged.sort((a, b) => new Date(b.fecha_iso || 0).getTime() - new Date(a.fecha_iso || 0).getTime());
        const truncated = merged.slice(0, 500);

        await env.LEADX_KV.put('leads:live', JSON.stringify({
          leads_all: truncated,
          leads_hot: truncated.filter(l => (l.score || 0) >= 50),
          summary: { total_leads: truncated.length, hot_leads: truncated.filter(l => (l.score || 0) >= 50).length },
          meta: { version: '11.1', source: 'apify_webhook_filtered', generated_at: new Date().toISOString(), ingest_at: new Date().toISOString() }
        }));

        return jsonResponse({ ok: true, received: leads.length, merged: truncated.length, filtered_out: (Array.isArray(items) ? items.length : 0) - leads.length }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: true, error: e.message }, corsHeaders);
      }
    }

    // ─── POST /api/enrich-patente ─── Recibe patente extraída por VLM/OCR desde GH Actions
    // FIX GEMINI: lee leads:live (array unificado), busca por ID, deep merge, guarda.
    if (url.pathname === '/api/enrich-patente' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret') || request.headers.get('X-Ingest-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const payload = await request.json();
        if (!payload.lead_id || !payload.patentes || !Array.isArray(payload.patentes)) {
          return jsonResponse({ ok: false, error: 'invalid_payload' }, corsHeaders, 400);
        }
        const raw = await env.LEADX_KV.get('leads:live');
        if (!raw) return jsonResponse({ ok: false, error: 'kv_empty' }, corsHeaders, 404);
        const data = JSON.parse(raw);
        const leads = data.leads_all || [];
        const idx = leads.findIndex(l => l.id === payload.lead_id);
        if (idx === -1) return jsonResponse({ ok: false, error: 'lead_not_found' }, corsHeaders, 404);

        const existing = leads[idx];
        const patente = payload.patentes[0]?.patente || '';
        leads[idx] = {
          ...existing,
          patente: patente || existing.patente,
          score: Math.min(100, (existing.score || 0) + (payload.score_boost || 15)),
          score_explain: [...(existing.score_explain || []), `[VLM/OCR] Patente: ${patente} (+${payload.score_boost || 15})`],
          enrichment_timestamp: new Date().toISOString(),
          enrichment_type: 'vlm_patent',
          contacto_sugerido: (existing.telefono_publico || existing.whatsapp_publico) ? 'whatsapp' : (existing.fb_username ? 'messenger' : 'dnrpa_manual'),
        };
        data.leads_all = leads;
        data.leads_hot = leads.filter(l => (l.score || 0) >= 50);
        await env.LEADX_KV.put('leads:live', JSON.stringify(data));
        return jsonResponse({ ok: true, lead_id: payload.lead_id, patente: patente, new_score: leads[idx].score }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/analyze-acta ─── VLM On-Demand: Sergio arrastra foto del acta
    if (url.pathname === '/api/analyze-acta' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret') || request.headers.get('X-Ingest-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const payload = await request.json();
        const { lead_id, image_b64 } = payload;
        if (!lead_id || !image_b64) {
          return jsonResponse({ error: 'missing_params' }, corsHeaders, 400);
        }
        // Recuperar lead del KV
        const raw = await env.LEADX_KV.get('leads:live');
        if (!raw) return jsonResponse({ error: 'kv_empty' }, corsHeaders, 404);
        const data = JSON.parse(raw);
        const leads = data.leads_all || [];
        const idx = leads.findIndex(l => l.id === lead_id);
        if (idx === -1) return jsonResponse({ error: 'lead_not_found' }, corsHeaders, 404);
        const existingLead = leads[idx];

        // Llamar a z-ai vision API
        const zaiRes = await fetch('https://api.zai.co/v1/chat/completions', {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + (env.ZAI_API_KEY || ''), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: 'glm-4.6v',
            messages: [{
              role: 'user',
              content: [
                { type: 'text', text: 'Analiza esta acta de infracción de tránsito de Argentina. Extrae: 1) patente del vehículo, 2) ubicación/localidad donde ocurrió la infracción, 3) provincia. Responde SOLO en formato JSON: {"patente":"...","ubicacion":"...","provincia":"...","legal_warning":"breve análisis de si el radar podría tener fallas de homologación o señalización"}' },
                { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + image_b64 } }
              ]
            }],
            temperature: 0.1
          })
        });
        if (!zaiRes.ok) {
          return jsonResponse({ error: 'vlm_failed', detail: await zaiRes.text() }, corsHeaders, 502);
        }
        const zaiData = await zaiRes.json();
        let vlmText = zaiData.choices?.[0]?.message?.content || '';
        // Limpiar markdown si viene envuelto
        vlmText = vlmText.replace(/```json\s*/gi, '').replace(/```\s*$/g, '').trim();
        let analysis;
        try { analysis = JSON.parse(vlmText); } catch(e) { analysis = { patente: vlmText.substring(0, 50), ubicacion: '', provincia: '', legal_warning: '' }; }

        // CRUCE FORENSE: buscar historial de Sergio en esta ubicación
        let forensicText = 'Sin historial previo. Sergio debe documentar este caso para construir la base forense.';
        if (analysis.ubicacion) {
          const _cleanLoc = analysis.ubicacion.toLowerCase().replace(/\\s+/g, '_').replace(/[^a-z0-9_]/g, '');
          const _radarRaw = await env.LEADX_KV.get('forensic:radar:' + _cleanLoc);
          if (_radarRaw) {
            try {
              const _radar = JSON.parse(_radarRaw);
              if (_radar.cases && _radar.cases.length > 0) {
                const _rate = Math.round((_radar.stats.win_rate || 0) * 100);
                forensicText = '📊 HISTORIAL EN ESTE RADAR (' + _radar.stats.total_cases + ' casos):\\n' +
                  '• Tasa de éxito: ' + _rate + '% de descargos ganados.\\n' +
                  '• Honorario promedio: $' + Math.round(_radar.stats.avg_fee || 0).toLocaleString('es-AR') + '\\n' +
                  '• Argumento sugerido: "' + (_radar.cases[0].argument_used || 'Ley 12.217') + '"';
                analysis.confidence = 'alta';
              }
            } catch(e) {}
          }
        }
        analysis.legal_warning = forensicText;

        // Actualizar lead en KV
        leads[idx] = {
          ...existingLead,
          patente: analysis.patente || existingLead.patente,
          ubicacion_infraccion: analysis.ubicacion || existingLead.ubicacion_infraccion,
          score: Math.min(100, (existingLead.score || 0) + 15),
          score_explain: [...(existingLead.score_explain || []), '[VLM On-Demand] Acta analizada (+15)'],
        };
        data.leads_all = leads;
        data.leads_hot = leads.filter(l => (l.score || 0) >= 50);
        await env.LEADX_KV.put('leads:live', JSON.stringify(data));

        return jsonResponse({ ok: true, analysis, lead_phone: existingLead.telefono_publico || existingLead.whatsapp_publico || existingLead.fb_username || '' }, corsHeaders);
      } catch (e) {
        return jsonResponse({ error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/forensic-case ─── Registrador de Casos Resueltos (Forensic Intelligence)
    if (url.pathname === '/api/forensic-case' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret') || request.headers.get('X-Ingest-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const body = await request.json();
        const { lead_id, patente, ubicacion, result, argument_used, fee_charged } = body;
        if (!patente || !result) {
          return jsonResponse({ ok: false, error: 'missing_patente_or_result' }, corsHeaders, 400);
        }
        const cleanLoc = (ubicacion || 'desconocida').toLowerCase().replace(/\\s+/g, '_').replace(/[^a-z0-9_]/g, '');
        const radarKey = 'forensic:radar:' + cleanLoc;
        let radarData = { cases: [], stats: {} };
        const existing = await env.LEADX_KV.get(radarKey);
        if (existing) { try { radarData = JSON.parse(existing); } catch(e) {} }
        radarData.cases.unshift({
          lead_id: lead_id || '', patente: patente.toUpperCase(),
          result, argument_used: argument_used || 'No especificado',
          fee_charged: parseFloat(fee_charged) || 0, date: new Date().toISOString()
        });
        const total = radarData.cases.length;
        const won = radarData.cases.filter(c => c.result === 'ganado').length;
        const fees = radarData.cases.map(c => c.fee_charged).filter(f => f > 0);
        radarData.stats = {
          total_cases: total,
          win_rate: total > 0 ? (won / total) : 0,
          avg_fee: fees.length > 0 ? (fees.reduce((a, b) => a + b, 0) / fees.length) : 0,
          last_updated: new Date().toISOString()
        };
        await env.LEADX_KV.put(radarKey, JSON.stringify(radarData));
        return jsonResponse({ ok: true, stats: radarData.stats }, corsHeaders);
      } catch (err) {
        return jsonResponse({ ok: false, error: err.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/health ─── Estado del pipeline (GPT insight: observabilidad)
    if (url.pathname === '/api/health' && request.method === 'GET') {
      try {
        const raw = await env.LEADX_KV.get('leads:live');
        let leadCount = 0;
        let lastIngest = null;
        let freshnessMinutes = null;
        let stale = false;
        if (raw) {
          const data = JSON.parse(raw);
          leadCount = (data.leads_all || []).length;
          lastIngest = data.meta && (data.meta.ingest_at || data.meta.generated_at);
          if (lastIngest) {
            const lastDt = new Date(lastIngest);
            freshnessMinutes = Math.floor((Date.now() - lastDt.getTime()) / 60000);
            stale = freshnessMinutes > 120;
          }
        }
        return jsonResponse({
          pipeline_status: stale ? 'stale' : 'ok',
          last_successful_run_utc: lastIngest,
          last_ingest_utc: lastIngest,
          lead_count: leadCount,
          freshness_minutes: freshnessMinutes,
          stale: stale,
          cron_active: true,
          cron_schedule: '0 * * * *',
          checked_at: new Date().toISOString(),
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message, stale: true }, corsHeaders, 500);
      }
    }

    // ─── POST /api/cron-run ─── Forzar ejecucion del cron manualmente
    if (url.pathname === '/api/cron-run' && (request.method === 'POST' || request.method === 'GET')) {
      const secret = request.headers.get('X-Webhook-Secret') || url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const result = await runPipelineCron(env);
        return jsonResponse({ ok: true, ...result }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/enrich-all ─── Cruce de datos: busca contactos en perfiles Reddit
    // Para cada lead de Reddit sin contacto, scrapear bio + profile links
    if (url.pathname === '/api/enrich-all' && (request.method === 'POST' || request.method === 'GET')) {
      const secret = request.headers.get('X-Webhook-Secret') || url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        // Leer leads actuales
        const raw = await env.LEADX_KV.get('leads:live');
        if (!raw) return jsonResponse({ ok: false, error: 'no_leads' }, corsHeaders, 404);
        const data = JSON.parse(raw);
        const leads = data.leads_all || [];
        let enriched = 0;
        const AR_PHONE = /(?:\+54\s?9?\s?)?(?:11|341|351|261|221|381|299)\s?[-.\s]?\d{4}[-.\s]?\d{4}|\b15[-\s]?\d{4}[-\s]?\d{4}\b/g;
        const EMAIL_RE = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;

        for (const lead of leads) {
          // Solo Reddit leads sin contacto
          if (lead.platform !== 'Reddit') continue;
          if (lead.whatsapp_publico || lead.telefono_publico || lead.email_publico) continue;

          const persona = (lead.persona || '').replace('u/', '').replace('@', '').trim();
          if (!persona || persona === '(anónimo)' || persona.length < 3) continue;

          let allText = '';

          // 1. Scrapear comments.rss del usuario
          try {
            const rssRes = await fetch('https://www.reddit.com/user/' + encodeURIComponent(persona) + '/comments/.rss?limit=25', {
              headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
            });
            if (rssRes.ok) {
              const xml = await rssRes.text();
              const entries = xml.split('<entry>').slice(1);
              for (const entry of entries) {
                const contentM = entry.match(/<content[^>]*>([\s\S]*?)<\/content>/);
                if (contentM) {
                  allText += ' ' + contentM[1].replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&');
                }
              }
            }
          } catch (e) {}

          // 2. Scrapear perfil HTML para links externos
          try {
            const htmlRes = await fetch('https://old.reddit.com/user/' + encodeURIComponent(persona), {
              headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
            });
            if (htmlRes.ok) {
              const html = await htmlRes.text();
              const linkPattern = /href="(https?:\/\/(?:instagram\.com|facebook\.com|wa\.me|mercadolibre\.com\.ar)\/[^\s"]+)"/gi;
              const links = [...html.matchAll(linkPattern)].map(m => m[1]);
              allText += ' ' + links.join(' ');
            }
          } catch (e) {}

          if (!allText) continue;

          // Buscar teléfono
          const phones = [...new Set((allText.match(AR_PHONE) || []).map(p => p.trim()))];
          const emails = [...new Set((allText.match(EMAIL_RE) || [])
            .map(e => e.toLowerCase().trim())
            .filter(e => !e.includes('noreply') && !e.includes('example.com') && !e.includes('facebook.com')))];

          if (phones.length > 0 || emails.length > 0) {
            lead.telefono_publico = phones[0] || '';
            lead.whatsapp_publico = phones[0] || '';
            lead.email_publico = emails[0] || '';
            lead.has_contact = true;
            lead.contacto_publico = true;
            lead.score = Math.min(100, (lead.score || 0) + 30);
            lead.detected_signals = (lead.detected_signals || []).concat(['ENRICH_ALL']);
            enriched++;
          }

          // 3. Si todavia no hay contacto, probar shadow-osint (Linktree/solo.to)
          if (!lead.has_contact) {
            try {
              const cleanUser = persona.replace(/^u\//, '').replace(/^@/, '').trim();
              const shadowRes = await fetch('https://linktr.ee/' + encodeURIComponent(cleanUser), {
                headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
              });
              if (shadowRes.ok) {
                const shadowHtml = await shadowRes.text();
                const waMatch = shadowHtml.match(/wa\.me\/(549\d{10,11})/);
                const telMatch = shadowHtml.match(/tel:([+]?\d[\d\s\-]{8,15})/);
                const mailMatch = shadowHtml.match(/mailto:([^"\s]+@[^"\s]+)/);
                const arPhoneMatch = shadowHtml.match(/(?:\+54\s?9?\s?)?(?:11|341|351|261|221|381|299)\s?[-.\s]?\d{4}[-.\s]?\d{4}/);

                if (waMatch) {
                  lead.whatsapp_publico = waMatch[1];
                  lead.telefono_publico = waMatch[1];
                  lead.has_contact = true;
                  lead.contacto_publico = true;
                  lead.score = Math.min(100, (lead.score || 0) + 30);
                  lead.detected_signals = (lead.detected_signals || []).concat(['SHADOW_OSINT_LINKTREE']);
                  enriched++;
                } else if (telMatch || arPhoneMatch) {
                  const p = (telMatch && telMatch[1]) || (arPhoneMatch && arPhoneMatch[0]) || '';
                  lead.telefono_publico = p;
                  lead.whatsapp_publico = p;
                  lead.has_contact = true;
                  lead.contacto_publico = true;
                  lead.score = Math.min(100, (lead.score || 0) + 25);
                  lead.detected_signals = (lead.detected_signals || []).concat(['SHADOW_OSINT_LINKTREE']);
                  enriched++;
                } else if (mailMatch) {
                  lead.email_publico = mailMatch[1].toLowerCase();
                  lead.has_contact = true;
                  lead.contacto_publico = true;
                  lead.score = Math.min(100, (lead.score || 0) + 15);
                  lead.detected_signals = (lead.detected_signals || []).concat(['SHADOW_OSINT_LINKTREE']);
                  enriched++;
                }
              }
            } catch (e) {}
          }
        }

        // Guardar de vuelta en KV
        data.leads_all = leads;
        data.leads_hot = leads.filter(l => (l.score || 0) >= 60);
        data.meta.enriched_at = new Date().toISOString();
        data.meta.enriched_count = enriched;
        await env.LEADX_KV.put('leads:live', JSON.stringify(data));

        return jsonResponse({
          ok: true,
          enriched: enriched,
          total: leads.length,
          message: enriched + ' leads enriquecidos con contacto desde perfil Reddit'
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/reddit-profile-links ─── OSINT: extrae links de otras plataformas
    if (url.pathname === '/api/reddit-profile-links' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      const username = url.searchParams.get('user');
      if (!username) {
        return jsonResponse({ ok: false, error: 'missing_user' }, corsHeaders, 400);
      }
      try {
        const html = await fetch('https://old.reddit.com/user/' + encodeURIComponent(username), {
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html',
            'Accept-Language': 'es-AR,es;q=0.9',
          },
        }).then(r => r.text());
        const linkPattern = /href="(https?:\/\/(?:instagram\.com|facebook\.com|wa\.me|mercadolibre\.com\.ar|twitter\.com|x\.com|t\.me|youtube\.com)\/[^\s"]+)"/gi;
        const links = [...new Set([...html.matchAll(linkPattern)].map(m => m[1]))];
        return jsonResponse({ ok: true, username: username, links: links }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/shadow-osint ─── Busca username en Linktree/solo.to/t.me
    if (url.pathname === '/api/shadow-osint' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      const username = url.searchParams.get('user');
      if (!username) {
        return jsonResponse({ ok: false, error: 'missing_user' }, corsHeaders, 400);
      }

      const contacts = [];
      const targets = [
        { domain: 'linktr.ee', type: 'linktree' },
        { domain: 'solo.to', type: 'solo' },
        { domain: 't.me', type: 'telegram' },
      ];

      for (const t of targets) {
        try {
          const res = await fetch('https://' + t.domain + '/' + encodeURIComponent(username), {
            headers: {
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
              'Accept': 'text/html,application/xhtml+xml',
            },
          });
          if (!res.ok) continue;
          const html = await res.text();

          // Buscar wa.me directo
          const wa = html.match(/wa\.me\/(549\d{10,11})/);
          if (wa) {
            contacts.push({ whatsapp: wa[1], source: t.type });
            break;
          }

          // Buscar mailto:
          const mail = html.match(/mailto:([^"\s]+@[^"\s]+)/);
          if (mail) {
            contacts.push({ email: mail[1], source: t.type });
          }

          // Buscar tel:
          const tel = html.match(/tel:([+]?\d[\d\s\-]{8,15})/);
          if (tel) {
            contacts.push({ telefono: tel[1], source: t.type });
          }

          // Buscar telefono AR en el HTML
          const arPhone = html.match(/(?:\+54\s?9?\s?)?(?:11|341|351|261|221|381|299)\s?[-.\s]?\d{4}[-.\s]?\d{4}/);
          if (arPhone && contacts.length === 0) {
            contacts.push({ telefono: arPhone[0], source: t.type });
          }
        } catch (e) {}
      }

      return jsonResponse({
        ok: true,
        username: username,
        contacts: contacts,
        found: contacts.length > 0,
      }, corsHeaders);
    }

    // ─── GET /api/ventafe-debug ─── Debug VentaFe HTML
    if (url.pathname === '/api/ventafe-debug' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret') || url.searchParams.get('key') || '';
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const vfRes = await fetch('https://www.ventafe.com.ar/automoviles', {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
        });
        const html = await vfRes.text();
        const blocks = html.split('class="row item tipo-').slice(1);
        const vfPhoneRegex = /\(?0?(?:342|341|351|261|221|381|299|11)\)?[\s\-]?\d{6,10}/g;
        
        const results = [];
        for (const block of blocks.slice(0, 10)) {
          const text = block.replace(/<[^>]+>/g, ' ').replace(/&[a-z]+;/g, ' ').replace(/\s+/g, ' ').trim();
          const phones = text.match(vfPhoneRegex) || [];
          results.push({
            text_preview: text.substring(0, 100),
            phones: phones,
            has_phone: phones.length > 0
          });
        }
        
        return jsonResponse({
          ok: true,
          html_size: html.length,
          blocks: blocks.length,
          results: results
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── SPA fallback: any unknown non-API route → index.html ───
    if (env.ASSETS) {
      // Try the exact path first (e.g. /robots.txt), fallback to index.html for SPA routes
      const assetResponse = await env.ASSETS.fetch(request);
      if (assetResponse.status !== 404) return assetResponse;
      // SPA fallback: serve index.html for client-side routing
      const spaRequest = new Request(new URL('/index.html', request.url), request);
      return env.ASSETS.fetch(spaRequest);
    }

    // ─── 404 (only if ASSETS binding missing) ───
    return jsonResponse({ error: 'not_found', path: url.pathname }, corsHeaders, 404);
  },

  // Cron nativo cada 1h - scraping Reddit RSS desde edge IP (no bloqueada)
  // FIX SIMON 2026-07-09: Cron DESACTIVADO. Reddit scraper traía 100% basura.
  // Python pipeline (GH Actions cada 1h) es el único cerebro. Worker = proxy puro KV.
  // Para reactivar: descomentar el try/catch de abajo Y borrar early-return de runPipelineCron.
  async scheduled(event, env, ctx) {
    console.log('[CRON] DESACTIVADO 2026-07-09 (Reddit 0/11 utiles). Worker = proxy puro.');
    // try {
    //   await runPipelineCron(env);
    // } catch (e) {
    //   console.error('[CRON] ERROR:', e.message);
    // }
  }
};

// ─── Funcion standalone del pipeline (cron + /api/cron-run) ───
// FIX SIMON 2026-07-09: Reddit scraper DESACTIVADO en edge cron.
// MOTIVO: 0/11 leads Reddit eran accionables. Filtro AR no cortaba:
//   MusicaBR, crossout_es, ICVNL (México), phishing Chile, ventas usadas, VTV.
// Python pipeline (generate_payload.py) es el ÚNICO cerebro. Edge cron = proxy puro.
// Para reactivar: borrar este early-return + mejorar filtro AR (requerir "multa"+"auto/moto"+"AR").
async function runPipelineCron(env) {
  console.log('[CRON] Reddit scraper DESACTIVADO por Simon (0/11 utiles). Worker = proxy puro.');
  // Early-return: no scrapear nada. Solo preserva KV existente.
  const rawPreserve = await env.LEADX_KV.get('leads:live');
  let existingPreserve = { leads_all: [], leads_hot: [], meta: {} };
  if (rawPreserve) {
    try { existingPreserve = JSON.parse(rawPreserve); } catch (e) {}
  }
  return {
    ok: true,
    skipped: 'reddit_disabled_simon',
    existing: (existingPreserve.leads_all || []).length,
    note: 'Reddit scraper disabled 2026-07-09. Python pipeline is the only brain.'
  };

}

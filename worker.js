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
        <div class="kpi-sub">contactables directo</div>
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
      <a id="modal-wa-btn" class="btn-wa" href="#" target="_blank">
        💬 WhatsApp
      </a>
      <button id="modal-copy-tpl" class="btn-secondary" onclick="copyWaTemplate()" style="margin-left:8px">
        📋 Copiar mensaje
      </button>
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
// getUrlSecret() siempre devuelve 'LEGACY_SECRET_REMOVED' hardcodeado (uso interno, frontend read-only).

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
  document.querySelectorAll('#fc-todos, #fc-whatsapp, #fc-email, #fc-sin-contacto').forEach(e => e.classList.remove('active'));
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
    // FIX QWEN v2.8: filtro Contacto
    if (cf === 'whatsapp' && !l._wa_url) return false;
    if (cf === 'email' && !(l.email || l.email_publico)) return false;
    if (cf === 'sin_contacto' && (l._wa_url || l.email || l.email_publico)) return false;
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
  const withWa   = leads.filter(l => l._wa_url || l._wa_state === 'validated_whatsapp' || l._wa_state === 'normalized_contact').length;
  const enProc   = leads.filter(l => ['Contactado','En gestión'].includes(l._status)).length;
  const cerrados = leads.filter(l => l._status === 'Cerrado');
  const pct = getComisionPct() / 100;
  const comision = cerrados.reduce((sum, l) => {
    const stored = DB.get(l.id);
    return sum + (stored.monto || 0) * pct;
  }, 0);

  document.getElementById('kpi-total').textContent    = leads.length;
  document.getElementById('kpi-wa').textContent       = withWa;
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
  if (cntEmail)        cntEmail.textContent        = S.crmLeads.filter(l => l.email || l.email_publico).length;
  if (cntSinContacto)  cntSinContacto.textContent  = S.crmLeads.filter(l => !l._wa_url && !(l.email || l.email_publico)).length;
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
    box.classList.remove('no-contact');
    waBtn.href = l._wa_url;
    waBtn.style.display = 'inline-flex';
    waBtn.innerHTML = WA_ICON + ' <span style="font-size:13px;color:#25D366">WhatsApp</span>';
    phoneLabel.textContent = l._wa_display + ' (verificado)';
  } else if (l._wa_state === 'normalized_contact') {
    box.classList.remove('no-contact');
    waBtn.style.display = 'inline-flex';
    waBtn.href = '#';
    waBtn.innerHTML = WA_ICON_GRAY + ' <span style="font-size:13px">Validar</span>';
    waBtn.onclick = (e) => { e.preventDefault(); validateWaFromModal(); };
    phoneLabel.textContent = l._wa_display + ' (pendiente validación)';
  } else if (l._wa_state === 'not_whatsapp') {
    box.classList.remove('no-contact');
    waBtn.style.display = 'none';
    phoneLabel.textContent = l._wa_display + ' (no tiene WhatsApp)';
  } else {
    // invalid_format o sin telefono
    box.classList.add('no-contact');
    waBtn.style.display = 'none';
    phoneLabel.textContent = l._phone ? 'Teléfono inválido: ' + l._phone : 'Sin contacto directo — buscar por perfil';
    if (!l._phone) document.getElementById('modal-author').textContent = l._display_name + ' (sin contacto)';
  }

  document.getElementById('detailModal').classList.add('open');
}

function stripUprefix(s) {
  if (!s) return '';
  if (s.startsWith('/u/')) return s.slice(3);
  if (s.startsWith('u/')) return s.slice(2);
  return s;
}
function copyWaTemplate() {
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (!l) return;
  const persona = stripUprefix(l.persona || l.author || '');
  const problema = l.problem_summary || l.title || l._resumen || 'tu consulta';
  const tpl = 'Hola ' + (persona || '') + ', te contactamos de SinFotomultas. Vi que tenés una consulta sobre ' + problema + '. ¿Querés que te ayudemos a resolverlo? Consulta sin cargo.';
  navigator.clipboard.writeText(tpl).then(() => {
    const btn = document.getElementById('modal-copy-tpl');
    const orig = btn.textContent;
    btn.textContent = '✓ Copiado!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => alert('No se pudo copiar. Texto: ' + tpl));
}

function copyContactTemplate() {
  // N2: Guión DM no-spam para Reddit (Claude)
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (!l) return;
  const author = stripUprefix(l.persona || l.author || '');
  const problema = l.problem_summary || l.title || l._resumen || 'tu consulta vehicular';
  const tpl = 'Hola, vi tu publicación sobre ' + problema + '. Trabajo con un equipo que resuelve este tipo de consultas. ¿Querés que te cuente cómo funciona? Sin compromiso.';
  navigator.clipboard.writeText(tpl).then(() => {
    const btn = document.getElementById('modal-copy-dm');
    const orig = btn.textContent;
    btn.textContent = '✓ Copiado!';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  }).catch(() => alert('No se pudo copiar. Texto: ' + tpl));
}

// N1: Fetch Reddit bio desde Worker endpoint
async function fetchRedditBio(username) {
  if (!username) return null;
  try {
    const r = await fetch('/api/reddit-bio?user=' + encodeURIComponent(username));
    if (!r.ok) return null;
    const data = await r.json();
    return data;
  } catch (e) {
    return null;
  }
}

// Llamar bio fetch cuando se abre el modal con Reddit user
async function loadBioIfReddit(l) {
  const bioField = document.getElementById('modal-bio-field');
  const bioContent = document.getElementById('modal-bio-content');
  bioField.style.display = 'none';
  
  const author = (l.persona || l.author || '').trim();
  const redditUser = stripUprefix(author);
  
  if (!redditUser || !(l.url || '').includes('reddit.com')) return;
  
  // Mostrar loading
  bioField.style.display = 'block';
  bioContent.textContent = 'Buscando contacto en bio...';
  bioContent.style.background = '#FEF3C7';
  bioContent.style.borderColor = '#FDE68A';
  
  const bio = await fetchRedditBio(redditUser);
  if (!bio || !bio.ok) {
    bioField.style.display = 'none';
    return;
  }
  
  const contacts = [];
  if (bio.phone) contacts.push('📱 ' + bio.phone);
  if (bio.email) contacts.push('✉ ' + bio.email);
  if (bio.whatsapp) contacts.push('🟢 WhatsApp: ' + bio.whatsapp);
  
  if (contacts.length === 0) {
    bioField.style.display = 'none';
    return;
  }
  
  bioContent.innerHTML = contacts.join('<br>');
  bioContent.style.background = '#F0FDF4';
  bioContent.style.borderColor = '#BBF7D0';
  
  // Actualizar _phone y _wa_url del lead si encontramos contacto
  if (bio.whatsapp || bio.phone) {
    const num = bio.whatsapp || bio.phone;
    const digits = num.replace(/\D/g, '');
    const norm = digits.startsWith('54') ? digits : '54' + digits.replace(/^0/, '');
    l._phone = num;
    l._wa_url = 'https://wa.me/' + norm;
    // Actualizar botón WA en el modal
    const waBtn = document.getElementById('modal-wa-btn');
    waBtn.href = l._wa_url;
    waBtn.style.display = 'inline-flex';
    document.getElementById('modal-phone-label').textContent = num;
    document.getElementById('modal-contact-box').classList.remove('no-contact');
  }
}

// Abrir WhatsApp directamente sin validación Apify (fix Qwen pragmático).
// La validación era inestable (actor Apify a menudo cae) y Sergio puede validar
// manualmente al abrir el chat. Velocidad > precisión aquí.
async function validateWaFromModal() {
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (!l) { alert('Sin lead seleccionado'); return; }
  if (!l._wa_url && !l._wa_e164) {
    alert('Sin WhatsApp disponible para este lead');
    return;
  }

  // Si no hay _wa_url pero hay e164, construirlo al vuelo
  const waUrl = l._wa_url || (l._wa_e164
    ? 'https://wa.me/' + (l._wa_e164.startsWith('+') ? l._wa_e164.slice(1) : l._wa_e164)
    : '');

  if (!waUrl) {
    alert('Sin WhatsApp disponible para este lead');
    return;
  }

  // Abrir WhatsApp en nueva pestaña
  window.open(waUrl, '_blank');

  // Marcar como validado y contactado localmente (Qwen P0 v3.1)
  // Persistencia en localStorage via DB.set para que el estado sobreviva reloads
  if (l._wa_e164) setWaValidation(l._wa_e164, true);
  l._wa_state = 'validated_whatsapp';
  l._status = 'Contactado';
  DB.set(S.currentId, { ...DB.get(S.currentId), status: 'Contactado' });

  const waBtn = document.getElementById('modal-wa-btn');
  if (waBtn) {
    waBtn.innerHTML = WA_ICON + ' <span style="font-size:13px;color:#25D366">WhatsApp ✓</span>';
    waBtn.href = waUrl;
    waBtn.onclick = (e) => { e.preventDefault(); window.open(waUrl, '_blank'); };
  }
  const phoneLabel = document.getElementById('modal-phone-label');
  if (phoneLabel) phoneLabel.textContent = (l._wa_display || l._wa_e164 || '') + ' (abierto)';

  renderTable();
  renderKPIs();
}

async function validateWaFromTable(id) {
  const l = S.crmLeads.find(x => x.id === id);
  if (!l) return;
  S.currentId = id;
  await validateWaFromModal();
}

function getUrlSecret() {
  // FIX QWEN v2.9: Hardcodeado, sin prompts ni sessionStorage.
  // Uso interno (frontend read-only). Si en el futuro se necesita auth real,
  // agregar allowlist de IPs o proxy en el Worker.
  return 'LEGACY_SECRET_REMOVED';
}

function closeModal() {
  document.getElementById('detailModal').classList.remove('open');
  S.currentId = null;
}

function saveStatusFromModal() {
  if (!S.currentId) return;
  const status = document.getElementById('modal-status-sel').value;
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (!l) return;
  l._status = status;
  const stored = DB.get(S.currentId);
  DB.set(S.currentId, { ...stored, status });
  // M3: Mostrar campo monto solo si está Cerrado
  const montoField = document.getElementById('modal-monto-field');
  if (status === 'Cerrado') {
    montoField.style.display = 'block';
    document.getElementById('modal-monto').value = stored.monto || '';
    updateComision();
  } else {
    montoField.style.display = 'none';
  }
  renderKPIs();
  renderCounts();
}

function updateComision() {
  const monto = parseFloat(document.getElementById('modal-monto').value) || 0;
  const comision = monto * getComisionPct() / 100;
  document.getElementById('modal-comision').textContent = '$' + comision.toLocaleString('es-AR');
}

function saveMontoFromModal() {
  if (!S.currentId) return;
  const monto = parseFloat(document.getElementById('modal-monto').value) || 0;
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (l) l._monto = monto;
  const stored = DB.get(S.currentId);
  DB.set(S.currentId, { ...stored, monto });
  updateComision();
  renderKPIs();
}

function saveNotesFromModal() {
  if (!S.currentId) return;
  const notes = document.getElementById('modal-notes').value;
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (l) l._notes = notes;
  const stored = DB.get(S.currentId);
  DB.set(S.currentId, { ...stored, notes });
}

function saveAndClose() {
  saveStatusFromModal();
  saveNotesFromModal();
  closeModal();
  renderTable();
}

// ── ADD MANUAL ─────────────────────────────────────────────────────────────
function openAddModal() {
  document.getElementById('addModal').classList.add('open');
}

function closeAddModal() {
  document.getElementById('addModal').classList.remove('open');
}

function addManualCase() {
  const nombre = document.getElementById('add-nombre').value.trim();
  const phone  = document.getElementById('add-phone').value.trim();
  const prov   = document.getElementById('add-prov').value;
  const body   = document.getElementById('add-body').value.trim();

  if (!nombre) { alert('Completá el nombre'); return; }

  const id = 'manual_' + Date.now();
  const lead = {
    id,
    source:       'manual',
    source_label: 'Manual',
    author:       nombre,
    has_author:   true,
    provincia:    prov,
    body,
    title:        body.slice(0, 80),
    fecha_iso:    new Date().toISOString().slice(0, 10),
    phone,
    whatsapp:     phone,
    score:        50,
    _manual:      true,
    _status:      'Nuevo',
    _notes:       '',
    _phone:       phone,
    _wa_url:      buildWaUrl(phone),
    _display_name: nombre,
    _resumen:     body.slice(0, 200),
  };

  const manual = DB.getManual();
  manual.unshift(lead);
  DB.setManual(manual);
  S.crmLeads.unshift(lead);

  closeAddModal();
  ['add-nombre','add-phone','add-body'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('add-prov').value = '';

  applyFilters();
  renderSidebar();
  renderKPIs();
}

// ── N3: Settings helpers (comision configurable) ───────────────────────────
function getComisionPct() {
  try { return parseFloat(localStorage.getItem('crm_comision_pct')) || 15; }
  catch(e) { return 15; }
}
function setComisionPct(v) {
  localStorage.setItem('crm_comision_pct', String(v));
}
function openSettings() {
  document.getElementById('settings-comision').value = getComisionPct();
  document.getElementById('settingsModal').classList.add('open');
}
function closeSettings() {
  document.getElementById('settingsModal').classList.remove('open');
}
function saveSettings() {
  const v = parseFloat(document.getElementById('settings-comision').value);
  if (isNaN(v) || v < 0 || v > 100) { alert('Porcentaje inválido'); return; }
  setComisionPct(v);
  closeSettings();
  renderKPIs();
}

// ── INIT ───────────────────────────────────────────────────────────────────
document.getElementById('searchInput')?.addEventListener('input', () => {
  clearTimeout(window._st);
  window._st = setTimeout(applyFilters, 200);
});

document.getElementById('sortSel')?.addEventListener('change', applyFilters);

document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) {
      overlay.classList.remove('open');
    }
  });
});

loadLeads();
</script>
</body>
</html>
`;

// ─────────────────────────────────────────────────────────────
// WORKER PRINCIPAL
// ─────────────────────────────────────────────────────────────



function jsonResponse(data, corsHeaders, status = 200) {
  return new Response(JSON.stringify(data), {
    status: status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      ...corsHeaders,
    }
  });
}

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
        if (!data.leads_hot) data.leads_hot = (data.leads_all || []).filter(l => (l.score || 0) >= 50);
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
        const hot = leads.filter(l => (l.score || 0) >= 50);
        const urgent = leads.filter(l => (l.score || 0) >= 80);
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
        const newHot = body.leads_hot || newLeads.filter(l => (l.score || 0) >= 50);

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

        // GPT FIX 3: Deep merge - KV tiene prioridad en estado CRM
        const prevById = new Map();
        prevLeads.forEach(l => prevById.set(l.id, l));
        newLeads.forEach(newLead => {
          const existing = prevById.get(newLead.id);
          if (existing) {
            // Merge: Python trae datos frescos, KV preserva estado del CRM
            prevById.set(newLead.id, {
              ...newLead,                          // datos frescos de Python
              score: existing.score ?? newLead.score,  // KV prioridad
              status: existing.status ?? newLead.status,
              _status: existing._status ?? newLead._status,
              _notes: existing._notes ?? newLead._notes,
              _monto: existing._monto ?? newLead._monto,
              whatsapp_validated: existing.whatsapp_validated ?? newLead.whatsapp_validated,
              _wa_state: existing._wa_state ?? newLead._wa_state,
              _wa_e164: existing._wa_e164 ?? newLead._wa_e164,
              // Contacto: si Python encontro uno nuevo y KV no tiene, usar el nuevo
              whatsapp_publico: existing.whatsapp_publico || newLead.whatsapp_publico,
              telefono_publico: existing.telefono_publico || newLead.telefono_publico,
              email_publico: existing.email_publico || newLead.email_publico,
            });
          } else {
            prevById.set(newLead.id, newLead);
          }
        });
        const merged = Array.from(prevById.values());

        // FIX GEMINI: Decay temporal de leads (>7 días sin gestión pierden 5 pts/día).
        // Evita que el dashboard se llene de leads viejos "calientes" que nunca se contactaron.
        // Solo aplica a leads en estado 'Nuevo' o sin estado (no toca los que ya están en gestión).
        merged.forEach(l => {
          const ts = l.fecha_iso || l.discovery_timestamp;
          const leadDate = ts ? new Date(ts) : null;
          if (leadDate && !isNaN(leadDate.getTime())) {
            const ageDays = (Date.now() - leadDate.getTime()) / 86400000;
            if (ageDays > 7 && (l._status === 'Nuevo' || l.status === 'Nuevo' || !l._status)) {
              const decay = Math.floor((ageDays - 7) * 5);
              l.score = Math.max(0, (l.score || 0) - decay);
              l._decay_applied = decay;
              l._heat_label = l.score >= 70 ? 'hot' : l.score >= 40 ? 'warm' : 'cold';
            }
          }
        });

        // Truncate to 500 most recent
        merged.sort((a, b) => {
          const da = new Date(a.fecha_iso || a.discovery_timestamp || 0).getTime();
          const db = new Date(b.fecha_iso || b.discovery_timestamp || 0).getTime();
          return db - da;
        });
        const truncated = merged.slice(0, 500);

        const payload = {
          leads_all: truncated,
          leads_hot: truncated.filter(l => (l.score || 0) >= 50),
          summary: {
            total_leads: truncated.length,
            hot_leads: truncated.filter(l => (l.score || 0) >= 50).length,
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

    // ─── GET /api/kv ─── (auth required)
    if (url.pathname === '/api/kv' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ error: 'unauthorized' }, corsHeaders, 401);
      }
      const key = url.searchParams.get('key');
      if (!key) return jsonResponse({ error: 'missing_key' }, corsHeaders, 400);
      try {
        const raw = await env.LEADX_KV.get(key);
        if (raw === null) {
          return jsonResponse({ error: 'not_found' }, corsHeaders, 404);
        }
        return jsonResponse({ value: JSON.parse(raw) }, corsHeaders);
      } catch (e) {
        return jsonResponse({ error: e.message }, corsHeaders, 500);
      }
    }

    // ─── POST /api/kv ─── (auth required)
    if (url.pathname === '/api/kv' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ error: 'unauthorized' }, corsHeaders, 401);
      }
      try {
        const body = await request.json();
        const { key, value, ttl } = body;
        if (!key || value === undefined) {
          return jsonResponse({ error: 'missing_key_or_value' }, corsHeaders, 400);
        }
        const putOptions = ttl ? { expirationTtl: ttl } : {};
        await env.LEADX_KV.put(key, JSON.stringify(value), putOptions);
        return jsonResponse({ ok: true, key }, corsHeaders);
      } catch (e) {
        return jsonResponse({ error: e.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/ml-questions ─── ML Questions Radar via Cloudflare edge IP
    // (evita 403 de ML API desde GH Actions datacenter IPs)
    if (url.pathname === '/api/ml-questions' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ error: 'unauthorized' }, corsHeaders, 401);
      }

      const ML_BASE = "https://api.mercadolibre.com";
      const MULTA_KW = ["multa", "infraccion", "libre deuda", "deuda",
                        "fotomulta", "puede transferir", "transferencia",
                        "patente", "08", "cedula", "transferir"];
      const TITLE_Q = ["transferir urgente", "no puedo transferir",
                       "con multa", "deuda patente", "libre deuda",
                       "transferencia pendiente"];
      const MAX_ITEMS_PER_QUERY = 3;
      const MAX_TOTAL_ITEMS = 10;

      const allLeads = [];
      const seenItems = new Set();
      let totalProcessed = 0;

      const debugInfo = { fetches: [], errors: [] };
      const mlFetch = async (path) => {
        try {
          const r = await fetch(`${ML_BASE}${path}`, {
            headers: {
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
              "Accept": "application/json"
            }
          });
          debugInfo.fetches.push({ path: path.slice(0, 80), status: r.status });
          if (!r.ok) {
            const text = await r.text().catch(() => "");
            debugInfo.errors.push({ path: path.slice(0, 80), status: r.status, body: text.slice(0, 200) });
            return null;
          }
          return r.json();
        } catch (e) {
          debugInfo.errors.push({ path: path.slice(0, 80), error: e.message });
          return null;
        }
      };

      const processItem = async (item) => {
        if (!item || !item.id) return;
        if (seenItems.has(item.id)) return;
        seenItems.add(item.id);
        totalProcessed++;

        const qData = await mlFetch(
          `/questions/search?item=${item.id}&status=ANSWERED&limit=50`
        );
        if (!qData || !qData.questions || !qData.questions.length) return;

        // Fetch seller contact (1 call per item, opcional)
        let sellerContact = {};
        const sellerId = item.seller && item.seller.id;
        if (sellerId) {
          const sData = await mlFetch(`/users/${sellerId}`);
          if (sData) {
            const phone = sData.phone;
            const email = sData.email;
            if (phone && phone.number) {
              const digits = String(phone.area_code || "") + String(phone.number);
              sellerContact.phone = digits.replace(/\D/g, "");
            }
            if (email && !email.includes("mercadolibre") && !email.includes("noreply")) {
              sellerContact.email = email.toLowerCase().trim();
            }
            sellerContact.is_professional = (sData.tags || []).some(t =>
              ["car_dealer", "real_estate_agency", "meli_choice", "large_seller"].includes(t)
            );
            if (sData.nickname && !item.seller.nickname) {
              item.seller.nickname = sData.nickname;
            }
          }
        }

        for (const q of qData.questions) {
          const qText = (q.text || "").toLowerCase();
          if (!MULTA_KW.some(kw => qText.includes(kw))) continue;

          const hasContact = !!(sellerContact.phone || sellerContact.email);

          allLeads.push({
            id: `ml_q_${q.id || item.id}`,
            source: "mercadolibre_questions",
            source_label: "MercadoLibre",
            author: (item.seller && item.seller.nickname) || "",
            title: `[ML] ${(item.title || "").slice(0, 120)}`,
            snippet: `Pregunta: "${q.text}"\nRespuesta: "${(q.answer && q.answer.text) || ""}"\nAuto: ${item.title} - $${(item.price || 0).toLocaleString()}`.slice(0, 3000),
            url: item.permalink || "",
            fecha_iso: (q.date_created || "").slice(0, 10),
            provincia: (item.address && item.address.state_name) || "",
            platform: "MercadoLibre",
            score: 0,
            // Campos extra
            whatsapp_publico: sellerContact.phone || "",
            telefono_publico: sellerContact.phone || "",
            email_publico: sellerContact.email || "",
            seller_id: String(sellerId || ""),
            question_text: q.text || "",
            has_answer: !!(q.answer),
            price: item.price || 0,
            is_professional_seller: sellerContact.is_professional || false,
            contact_source: hasContact ? "ml_seller_profile" : "",
          });
        }
      };

      try {
        // Busqueda 1: titulos con keywords de multa (pre-filtrado, Claude fix)
        for (const q of TITLE_Q) {
          if (totalProcessed >= MAX_TOTAL_ITEMS) break;
          const data = await mlFetch(
            `/sites/MLA/search?q=${encodeURIComponent(q)}&category=MLA1744&sort=date_desc&limit=${MAX_ITEMS_PER_QUERY}`
          );
          if (data && data.results) {
            for (const item of data.results) {
              if (totalProcessed >= MAX_TOTAL_ITEMS) break;
              await processItem(item);
            }
          }
        }

        // Busqueda 2: autos recientes genericos (red mas amplia)
        if (totalProcessed < MAX_TOTAL_ITEMS) {
          const generic = await mlFetch(
            `/sites/MLA/search?category=MLA1744&sort=date_desc&limit=15`
          );
          if (generic && generic.results) {
            for (const item of generic.results.slice(0, MAX_TOTAL_ITEMS - totalProcessed)) {
              await processItem(item);
            }
          }
        }

        return jsonResponse({
          ok: true,
          leads: allLeads,
          total: allLeads.length,
          contactables: allLeads.filter(l => l.whatsapp_publico || l.email_publico).length,
          items_processed: seenItems.size,
          debug: debugInfo,
        }, corsHeaders);
      } catch (err) {
        return jsonResponse({ ok: false, error: err.message }, corsHeaders, 500);
      }
    }

    // ─── GET /api/reddit-bio ─── Multi-path Reddit user scraper
    // Intenta: about.json, comments.rss, submitted.rss, old.reddit HTML
    // Devuelve telefono/whatsapp/email si los encuentra en cualquier fuente
    if (url.pathname === '/api/reddit-bio' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }
      const username = url.searchParams.get('user');
      if (!username) {
        return jsonResponse({ ok: false, error: 'missing_user' }, corsHeaders, 400);
      }

      // Regex AR quirurgico (CHEVRON+QWEN consensus)
      const AR_PHONE = /(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}|\b15[-\s]?\d{4}[-\s]?\d{4}\b|\b0?(?:11|2\d{2}|3\d{2})[-\s]?\d{3,4}[-\s]?\d{4}\b/g;
      const AR_WA = /(?:wa\.me\/(\d{8,15})|whatsapp[:\s]+(\+?[\d\s\-]{8,15})|(?:wp|wpp|wsp|wapp)[:\s]+(\+?[\d\s\-]{8,15}))/gi;
      const EMAIL_RE = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;
      const SPAM_DOMAINS = ['mailinator', 'tempmail', 'guerrillamail', '10minutemail', 'noreply', 'example.com'];

      const headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/html, application/xml, */*',
        'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
      };

      const allText = []; // acumular texto de todas las fuentes
      let bio = '';
      let sourcesTried = [];

      // Path 1: /about.json (probablemente 403 pero intentar)
      try {
        const r1 = await fetch('https://www.reddit.com/user/' + encodeURIComponent(username) + '/about.json', { headers });
        sourcesTried.push('about.json:' + r1.status);
        if (r1.ok) {
          const data = await r1.json();
          const sub = (data && data.data && data.data.subreddit) || {};
          bio = (sub.public_description || '') + ' ' + (sub.description || '');
          allText.push(bio);
        }
      } catch (e) {}

      // Path 2: /comments/.rss (legacy RSS, a veces no bloqueado)
      if (!bio) {
        try {
          const r2 = await fetch('https://www.reddit.com/user/' + encodeURIComponent(username) + '/comments/.rss?limit=25', { headers });
          sourcesTried.push('comments.rss:' + r2.status);
          if (r2.ok) {
            const xml = await r2.text();
            // Extraer texto de entries del RSS
            const entries = xml.match(/<entry>([\s\S]*?)<\/entry>/g) || [];
            entries.forEach(e => {
              const content = (e.match(/<content[^>]*>([\s\S]*?)<\/content>/) || [])[1] || '';
              const cleaned = content.replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
              allText.push(cleaned);
            });
          }
        } catch (e) {}
      }

      // Path 3: /submitted/.rss (posts del user)
      if (!bio) {
        try {
          const r3 = await fetch('https://www.reddit.com/user/' + encodeURIComponent(username) + '/submitted/.rss?limit=25', { headers });
          sourcesTried.push('submitted.rss:' + r3.status);
          if (r3.ok) {
            const xml = await r3.text();
            const entries = xml.match(/<entry>([\s\S]*?)<\/entry>/g) || [];
            entries.forEach(e => {
              const content = (e.match(/<content[^>]*>([\s\S]*?)<\/content>/) || [])[1] || '';
              const cleaned = content.replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
              allText.push(cleaned);
            });
          }
        } catch (e) {}
      }

      // Combinar todo el texto y buscar contactos
      const fullText = allText.join(' \n ');
      const phones = [...new Set((fullText.match(AR_PHONE) || []).map(p => p.trim()))];
      const waMatches = [...fullText.matchAll(AR_WA)];
      const whatsapps = [...new Set(waMatches.map(m => (m[1] || m[2] || m[3] || '').trim()).filter(Boolean))];
      const emails = [...new Set((fullText.match(EMAIL_RE) || [])
        .map(e => e.toLowerCase().trim())
        .filter(e => !SPAM_DOMAINS.some(d => e.includes(d))))];

      return jsonResponse({
        ok: true,
        username: username,
        bio: (bio || fullText.slice(0, 500)).trim(),
        sources_tried: sourcesTried,
        phone: phones[0] || '',
        phones: phones,
        whatsapp: whatsapps[0] || '',
        whatsapps: whatsapps,
        email: emails[0] || '',
        emails: emails,
        has_contact: phones.length > 0 || whatsapps.length > 0 || emails.length > 0,
      }, corsHeaders);
    }

    // ─── GET /api/ddg-foromoto ─── ForoMoto + clasificados AR via DDG
    // Busca en foros AR con snippets que contengan dolor + contacto
    if (url.pathname === '/api/ddg-foromoto' && request.method === 'GET') {
      const secret = request.headers.get('X-Webhook-Secret');
      if (!env.INGEST_SECRET || secret !== env.INGEST_SECRET) {
        return jsonResponse({ ok: false, error: 'unauthorized' }, corsHeaders, 401);
      }

      // Queries para foros AR con intención + contacto
      // DDG tiene mala cobertura de site:foromoto, usar queries amplias con keywords AR
      const QUERIES = [
        'multa fotomulta argentina whatsapp celular "11-"',
        'no puedo transferir auto multa argentina telefono',
        'libre deuda falso argentina whatsapp contacto',
        'compre auto multas anteriores dueño argentina celular',
        'vendo auto multas pendientes argentina whatsapp',
        'me llego fotomulta argentina ayuda whatsapp',
      ];

      // Regex AR con códigos de área (Qwen consensus)
      const AR_PHONE = /(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}|\b15[-\s]?\d{4}[-\s]?\d{4}\b/g;
      const AR_WA = /wa\.me\/(\d{8,15})|(?:whatsapp|wp|wpp|wsp|wapp)[:\s]+(\+?[\d\s\-]{8,15})/gi;
      const EMAIL_RE = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;
      const SPAM_DOMAINS = ['mailinator', 'tempmail', 'guerrillamail', '10minutemail', 'noreply', 'example.com'];

      // Keywords de dolor (GPT insight: filtro contextual)
      const PAIN_KEYWORDS = /multa|fotomulta|infracci[oó]n|libre.deuda|transferencia|patente|08|c[eé]dula|veraz|registro.automotor|juez.de.faltas|peaje|telepeaje|deuda/i;

      const allLeads = [];

      try {
        let debugHtmlSize = 0;
        let debugFirstSnippet = '';
        let debugResultCount = 0;
        for (const query of QUERIES) {
          try {
            const ddgUrl = 'https://html.duckduckgo.com/html/?q=' + encodeURIComponent(query);
            const r = await fetch(ddgUrl, {
              headers: {
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
    if (url.pathname === '/api/apify-webhook' && request.method === 'POST') {
      try {
        const body = await request.json();
        const items = body.items || body.results || body || [];
        const leads = [];
        const AR_PHONE = /(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}/g;
        const EMAIL_RE = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;

        for (const post of (Array.isArray(items) ? items : [])) {
          const text = post.text || post.postText || '';
          const author = post.authorName || post.author || '';
          const postUrl = post.url || post.postUrl || '';
          if (!text && !author) continue;

          const phones = [...new Set((text.match(AR_PHONE) || []).map(p => p.trim()))];
          const emails = [...new Set((text.match(EMAIL_RE) || []).map(e => e.toLowerCase()))];

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
            score: 50,
            whatsapp_publico: phones[0] || '',
            telefono_publico: phones[0] || '',
            email_publico: emails[0] || '',
            has_contact: phones.length > 0 || emails.length > 0,
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
        leads.forEach(l => prevById.set(l.id, l));
        const merged = Array.from(prevById.values());
        merged.sort((a, b) => new Date(b.fecha_iso || 0).getTime() - new Date(a.fecha_iso || 0).getTime());
        const truncated = merged.slice(0, 500);

        await env.LEADX_KV.put('leads:live', JSON.stringify({
          leads_all: truncated,
          leads_hot: truncated.filter(l => (l.score || 0) >= 50),
          summary: { total_leads: truncated.length, hot_leads: truncated.filter(l => (l.score || 0) >= 50).length },
          meta: { version: '11.0', source: 'apify_webhook', generated_at: new Date().toISOString(), ingest_at: new Date().toISOString() }
        }));

        return jsonResponse({ ok: true, received: leads.length, merged: truncated.length }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: true, error: e.message }, corsHeaders);
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

    // ─── 404 ───
    return jsonResponse({ error: 'not_found', path: url.pathname }, corsHeaders, 404);
  },

  // Cron nativo cada 1h - scraping Reddit RSS desde edge IP (no bloqueada)
  async scheduled(event, env, ctx) {
    console.log('[CRON] Pipeline iniciado:', new Date().toISOString());
    try {
      await runPipelineCron(env);
    } catch (e) {
      console.error('[CRON] ERROR:', e.message);
    }
  }
};

// ─── Funcion standalone del pipeline (cron + /api/cron-run) ───
async function runPipelineCron(env) {
  const redditQueries = [
    'no puedo transferir multa argentina',
    'me llego multa fotomulta argentina',
    'libre deuda transferencia auto',
    'fotomulta reclamo argentina',
    'compre auto multas anteriores',
    'vendo auto multas pendientes',
    'cedula verde perdida transferir',
    'patente bloqueada registro automotor',
    'juez de faltas multa reclamo',
    'vendedor no entrego 08',
  ];
  const newLeads = [];
  const seenUrls = new Set();

  for (const query of redditQueries) {
    try {
      const rssUrl = 'https://www.reddit.com/search.rss?q=' + encodeURIComponent(query) + '&sort=new&limit=10&t=month';
      const rssRes = await fetch(rssUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          'Accept': 'application/atom+xml,application/xml,text/xml,*/*',
          'Accept-Language': 'es-AR,es;q=0.9',
        },
      });
      if (!rssRes.ok) {
        console.log('[CRON] RSS fail ' + query + ': ' + rssRes.status);
        continue;
      }
      const xml = await rssRes.text();
      const entries = xml.split('<entry>').slice(1);

      for (const entry of entries) {
        const titleM = entry.match(/<title[^>]*>([^<]+)<\/title>/);
        const linkM = entry.match(/<link[^>]*href="([^"]+)"/);
        const authorM = entry.match(/<name[^>]*>([^<]+)<\/name>/);
        const contentM = entry.match(/<content[^>]*>([\s\S]*?)<\/content>/);
        const updatedM = entry.match(/<updated[^>]*>([^<]+)<\/updated>/);

        if (!titleM || !linkM) continue;
        const url = linkM[1];
        if (seenUrls.has(url) || !url.includes('/comments/')) continue;
        seenUrls.add(url);

        const title = titleM[1].trim();
        const authorRaw = authorM ? authorM[1].trim() : '';
        let author = '';
        const uMatch = authorRaw.match(/u\/([A-Za-z0-9_\-:]{3,20})/);
        if (uMatch) author = uMatch[1];

        let body = '';
        if (contentM) {
          body = contentM[1].replace(/<[^>]+>/g, ' ')
            .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"').replace(/&#39;/g, "'")
            .replace(/&#x27;/g, "'").replace(/&#47;/g, '/')
            .replace(/&#x2F;/g, '/').replace(/&nbsp;/g, ' ')
            .replace(/&#8217;/g, "'").replace(/&#8230;/g, '...')
            .replace(/&#8220;/g, '"').replace(/&#8221;/g, '"')
            .replace(/&#8211;/g, '-').replace(/&#8212;/g, '--')
            .replace(/\s+/g, ' ').trim();
          // Fix encoding: caracteres cortados
          body = body.replace(/tran fer/gi, 'transfer')
            .replace(/Di puta/g, 'Disputa')
            .replace(/erencia/g, 'erencia')
            .replace(/conce ion/gi, 'concesion')
            .replace(/ervicio/gi, 'servicio')
            .replace(/comprobante corre /gi, 'comprobantes corre')
            .replace(/ituaci/gi, 'ituaci');
        }

        const fecha = updatedM ? updatedM[1].slice(0, 10) : '';
        const fullText = (title + ' ' + body).toLowerCase();

        const painKw = ['multa','multas','fotomulta','fotomultas','infraccion','infracciones',
          'infraccion','libre deuda','libredeuda','transferencia','transferir','patente',
          '08 firmado','cedula','veraz','registro automotor','juez de faltas','peaje','deuda','vencimiento',
          'auto','moto','vehiculo','vendo','compro','permuta'];
        if (!painKw.some(k => fullText.includes(k))) continue;

        // FIX GEMINI AUDIT: Filtro Reddit SOLO Argentina (mismo criterio que classify_and_score del Python).
        // Si no hay señal AR explícita en el texto, descartar el lead.
        const arKw = ['argentina','buenos aires','caba','capital federal','cordoba','cordoba',
          'santa fe','rosario','mendoza','entre rios','neuquen','salta','la plata','arba',
          'dnrpa','rentas','pba','gba','patente argentina','parana','tigre','avellaneda',
          'quilmes','moron','pilar'];
        if (!arKw.some(g => fullText.includes(g))) continue;

        // FIX GEMINI AUDIT v2: requiere señal vehicular ESPECÍFICA de dolor (no solo "auto/moto" genérico).
        // Evita que pasen posts random que mencionan "argentina" pero no son leads vehiculares.
        const painKwStrict = ['multa','multas','fotomulta','fotomultas','infraccion','infracciones',
          'infraccion','libre deuda','libredeuda','transferencia','transferir',
          '08 firmado','cedula','veraz','registro automotor','juez de faltas','peaje',
          'deuda','vencimiento','patente','no puedo transferir','me llego multa',
          'me cobraron','papeles al dia','listo para transferir'];
        if (!painKwStrict.some(k => fullText.includes(k))) continue;

        // Anti-junk
        const junkKw = ['renunciar','empleo','galaxy','tablet','licitacion','falsa competencia',
          'guardia roja','gracia inmerecida','euphoria','depre','ajuste de equilibrio','probabilit',
          'lovecraft','meteorito','paysandu','gaming','playstation','xbox'];
        if (junkKw.some(k => fullText.includes(k))) continue;
        const ptKw = ['nao','voce','comprei','vendi','carro','detran','cnh','obrigado','galera','deix','crever','belezura'];
        if (ptKw.filter(k => fullText.includes(k)).length >= 2) continue;

        let score = 40;
        const urgencyKw = ['urgente','hoy','ahora','recien','me llego','consulta','ayuda','necesito','no puedo'];
        if (urgencyKw.some(k => fullText.includes(k))) score += 20;
        const extremeKw = ['me llego','me cobraron','no puedo transferir','me retuvieron','necesito ayuda','alguien sabe','urgente'];
        if (extremeKw.some(k => fullText.includes(k))) score += 20;

        const arPhoneRegex = /(?:\+54\s?9?\s?)?(?:11|341|351|261|221|381|299)\s?[-.\s]?\d{4}[-.\s]?\d{4}|\b15[-\s]?\d{4}[-\s]?\d{4}\b/g;
        const waLinkRegex = /wa\.me\/(\d{8,15})/gi;
        const emailRegex = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;
        const spamDomains = ['mailinator','tempmail','guerrillamail','10minutemail','noreply','example.com','facebook.com'];

        const phones = [...new Set((body.match(arPhoneRegex) || []).map(p => p.trim()))];
        const waLinks = [...new Set([...body.matchAll(waLinkRegex)].map(m => m[1]))];
        const emails = [...new Set((body.match(emailRegex) || []).map(e => e.toLowerCase().trim()).filter(e => !spamDomains.some(d => e.includes(d))))];
        const hasContact = phones.length > 0 || waLinks.length > 0 || emails.length > 0;
        if (hasContact) score += 30;

        const arGeo = ['argentina','buenos aires','caba','cordoba','cordoba','rosario','santa fe','mendoza','tucuman','salta','neuquen','la plata'];
        if (arGeo.some(g => fullText.includes(g))) score += 15;

        const patenteMatch = body.match(/\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b/i);
        if (patenteMatch) score += 15;

        score = Math.max(0, Math.min(100, score));
        if (score < 40) continue;

        newLeads.push({
          id: 'reddit_' + url.split('/').slice(-2).join('_'),
          source: 'reddit_rss',
          source_label: 'Reddit',
          platform: 'Reddit',
          author: author,
          persona: author ? 'u/' + author : '(anonimo)',
          title: title.slice(0, 200),
          snippet: body.slice(0, 3000),
          quoted_text: body.slice(0, 300),
          url: url,
          fecha_iso: fecha,
          fecha_visible: fecha,
          score: score,
          whatsapp_publico: phones[0] || waLinks[0] || '',
          telefono_publico: phones[0] || '',
          email_publico: emails[0] || '',
          contacto_publico: hasContact,
          has_contact: hasContact,
          patente: patenteMatch ? patenteMatch[1].toUpperCase() : '',
          discovery_timestamp: new Date().toISOString(),
        });
      }
    } catch (e) {
      console.log('[CRON] Error query ' + query + ': ' + e.message);
    }
  }

  // FIX GEMINI ARQUITECTURA: Scraper VentaFe del Edge Cron ELIMINADO.
  // El Edge Cron del Worker ya NO scrapea VentaFe. Solo trae leads Reddit.
  // VentaFe queda exclusivamente a cargo del Python pipeline (generate_payload.py)
  // que tiene el filtro Sabueso (Fase 1 + Fase 2) y classify_and_score completo.
  // El Worker es ahora un proxy puro: lee/escribe KV, no genera leads propios de VentaFe.

  const raw = await env.LEADX_KV.get('leads:live');
  let existing = { leads_all: [], leads_hot: [], meta: {} };
  if (raw) {
    try { existing = JSON.parse(raw); } catch (e) {}
  }

  // Qwen fix: mergear por ID (no por URL) para que VentaFe no se pise
  const byId = new Map();
  for (const l of (existing.leads_all || [])) byId.set(l.id, l);
  for (const l of newLeads) byId.set(l.id, l);

  const merged = Array.from(byId.values());
  merged.sort((a, b) => (b.fecha_iso || '').localeCompare(a.fecha_iso || ''));
  const truncated = merged.slice(0, 500);

  if (truncated.length === 0 && (existing.leads_all || []).length > 0) {
    return { ok: true, skipped: 'anti_wipe', existing: (existing.leads_all || []).length };
  }

  const payload = {
    leads_all: truncated,
    leads_hot: truncated.filter(l => (l.score || 0) >= 60),
    leads_warm: truncated.filter(l => (l.score || 0) >= 40 && (l.score || 0) < 60),
    summary: {
      total_leads: truncated.length,
      hot_leads: truncated.filter(l => (l.score || 0) >= 60).length,
      with_whatsapp: truncated.filter(l => l.whatsapp_publico).length,
      with_email: truncated.filter(l => l.email_publico).length,
    },
    meta: {
      version: '11.0',
      source: 'cron_trigger_edge',
      generated_at: new Date().toISOString(),
      ingest_at: new Date().toISOString(),
      new_in_batch: newLeads.length,
    },
  };

  await env.LEADX_KV.put('leads:live', JSON.stringify(payload));
  return {
    ok: true,
    new_leads: newLeads.length,
    total: truncated.length,
    hot: payload.summary.hot_leads,
  };
}

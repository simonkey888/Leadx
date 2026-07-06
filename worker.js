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
  :root {
    --bg:       #F4F6F9;
    --surface:  #FFFFFF;
    --border:   #E1E8ED;
    --text:     #1A2332;
    --muted:    #6B7A8D;
    --primary:  #1B4FBB;
    --primary-h:#1640A0;
    --green:    #00875A;
    --green-h:  #006644;
    --orange:   #FF8B00;
    --red:      #DE350B;
    --purple:   #6554C0;
    --radius:   8px;
    --shadow:   0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.06);
    --shadow-lg:0 4px 16px rgba(0,0,0,.10);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
  }

  /* ── TOP BAR ── */
  .topbar {
    background: var(--primary);
    color: #fff;
    padding: 0 24px;
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 2px 8px rgba(0,0,0,.2);
  }
  .topbar-brand {
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -.3px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .topbar-brand span { opacity: .7; font-weight: 400; font-size: 13px; }
  .topbar-right {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 13px;
    opacity: .9;
  }
  .sync-btn {
    background: rgba(255,255,255,.15);
    border: 1px solid rgba(255,255,255,.3);
    color: #fff;
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: background .15s;
  }
  .sync-btn:hover { background: rgba(255,255,255,.25); }

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
  .filter-item:hover { background: #F0F4FF; color: var(--text); }
  .filter-item.active {
    background: #EEF2FF;
    border-left-color: var(--primary);
    color: var(--primary);
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
    background: #F8FAFC;
    border-bottom: 2px solid var(--border);
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
  tbody tr:hover { background: #F8FAFC; }
  td { padding: 12px 14px; vertical-align: middle; }
  .td-nombre { font-weight: 600; font-size: 13px; max-width: 160px; }
  .td-nombre small { display: block; font-weight: 400; color: var(--muted); font-size: 11px; margin-top: 2px; }
  .td-resumen { max-width: 260px; }
  .td-resumen p { font-size: 12px; color: var(--muted);
    overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; }

  /* ── STATUS BADGE ── */
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 9px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .badge-nuevo    { background: #EEF2FF; color: #3730A3; }
  .badge-contactado  { background: #FFF7E6; color: #92400E; }
  .badge-gestion  { background: #F0FDF4; color: #166534; }
  .badge-cerrado  { background: #ECFDF5; color: var(--green); }
  .badge-descartado { background: #FEF2F2; color: var(--red); }
  .kpi-value.purple { color: var(--purple); }
  .badge-hot { background: #FEF3C7; color: #92400E; margin-left: 4px; }
  .badge-warm { background: #DBEAFE; color: #1E40AF; margin-left: 4px; }

  /* Heat score row colors (GPT: 3 estados visuales) */
  tr.heat-hot { background: #FEF2F2 !important; }
  tr.heat-hot:hover { background: #FEE2E2 !important; }
  tr.heat-warm { background: #FFFBEB !important; }
  tr.heat-warm:hover { background: #FEF3C7 !important; }
  tr.heat-cold { background: var(--surface) !important; opacity: 0.6; }

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

  /* ── MODAL ── */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.4);
    z-index: 200;
    align-items: center;
    justify-content: center;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface);
    border-radius: 12px;
    width: 540px;
    max-width: 95vw;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: var(--shadow-lg);
    padding: 28px;
  }
  .modal h2 { font-size: 18px; margin-bottom: 20px; }
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
  }
  .modal-field textarea:focus { border-color: var(--primary); }
  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
  .btn-secondary {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 16px;
    border-radius: var(--radius);
    font-size: 13px;
    cursor: pointer;
  }
  .btn-secondary:hover { background: #F1F5F9; }
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
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 8px;
    padding: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .contact-box.no-contact {
    background: #FEF9C3;
    border-color: #FDE68A;
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
  </div>

  <!-- MAIN -->
  <div class="main">

    <!-- KPIs -->
    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-label">Total casos</div>
        <div class="kpi-value blue" id="kpi-total">—</div>
        <div class="kpi-sub">leads con contacto identificado</div>
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
      <label>Problema detectado</label>
      <div class="val" id="modal-body" style="font-size:13px;color:var(--muted);line-height:1.6"></div>
    </div>
    <div class="modal-field">
      <label>Ver post original</label>
      <a id="modal-url" href="#" target="_blank"
        style="font-size:12px;color:var(--primary)">Abrir enlace →</a>
    </div>
    <div class="modal-field" id="modal-profile-field" style="display:none">
      <label>Contactar al usuario (DM)</label>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <a id="modal-profile-url" href="#" target="_blank"
          style="font-size:12px;color:var(--orange)">Abrir perfil de Reddit →</a>
        <button id="modal-copy-dm" class="btn-secondary" onclick="copyDmTemplate()" style="font-size:11px;padding:4px 10px">
          📋 Copiar guion DM
        </button>
      </div>
      <small style="color:var(--muted);font-size:11px;margin-top:6px;display:block;line-height:1.4">
        ⚠️ Reddit banea autopromoción. Usar guion genuino: ofrecer info primero, NO vender. Solo derivar a WA si hay interés.
      </small>
    </div>
    <div class="modal-field" id="modal-bio-field" style="display:none">
      <label>Contacto extraído de bio Reddit</label>
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
      <label>WhatsApp / Teléfono</label>
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
const S = {
  allLeads:   [],   // todos los leads crudos de la API
  crmLeads:   [],   // leads con contacto o manual + leads manuales
  filtered:   [],
  statusFilter: 'todos',
  provFilter:   'todos',
  sourceFilter: 'todos',
  currentId:    null,
};

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
    _resumen: cleanText(title || body),
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

  // HEAT SCORE UNICO (GPT spec): intención + contacto + urgencia + geo + recencia
  const text = (title + ' ' + body).toLowerCase();
  let heat = 0;

  // INTENCION (0-40)
  if (/multa|fotomulta|infracci[oó]n/.test(text)) heat += 25;
  if (/transferencia|transferir|libre deuda|08 firmado/.test(text)) heat += 20;
  if (/necesito ayuda|urgente|no puedo|bloqueado/.test(text)) heat += 15;

  // CONTACTO (0-30)
  if (enriched._wa_state === 'validated_whatsapp') heat += 30;
  else if (enriched._wa_state === 'normalized_contact') heat += 15;
  if (email) heat += 10;

  // URGENCIA (0-20)
  if (/hoy|urgente|no puedo|bloqueado|vencimient/.test(text)) heat += 20;
  else if (/consulta|duda|pregunta/.test(text)) heat += 10;

  // GEOGRAFIA (0-10)
  const prov = (l.provincia || '').toLowerCase();
  if (prov && prov !== 'unknown' && prov !== 'desconocida') heat += 10;
  else if (/argentina|buenos aires|caba|cordoba|córdoba|rosario|santa fe|mendoza/.test(text)) heat += 5;

  // RECENCIA (bonus)
  if (l.fecha_iso) {
    const days = Math.floor((Date.now() - new Date(l.fecha_iso).getTime()) / 86400000);
    if (days <= 3) heat += 5;
    else if (days <= 7) heat += 2;
  }

  enriched._heat_score = Math.min(100, heat);

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
  let digits = String(raw).replace(/\\D/g, '');
  if (!digits) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  if (digits.startsWith('54')) digits = digits.slice(2);
  if (digits.startsWith('0')) digits = digits.slice(1);
  if (digits.startsWith('9') && digits.length === 11) digits = digits.slice(1);
  if (digits.length !== 10) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  if (!/^(11|2\\d|3\\d)/.test(digits)) return { state: 'invalid_format', e164: '', display: '', waUrl: '' };
  let mobile = digits;
  if (digits.startsWith('11')) mobile = '9' + digits;
  return {
    state: 'normalized_contact',
    e164: '+549' + mobile,
    display: '+' + mobile.slice(0, 2) + ' ' + mobile.slice(2, 6) + ' ' + mobile.slice(6),
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

function applyFilters() {
  const q   = (document.getElementById('searchInput')?.value || '').toLowerCase();
  const pv  = S.provFilter;
  const sf  = S.sourceFilter;

  S.filtered = S.crmLeads.filter(l => {
    if (S.statusFilter !== 'todos' && l._status !== S.statusFilter) return false;
    if (pv !== 'todos' && (l.provincia || '') !== pv) return false;
    if (sf !== 'todos' && (l.source_label || l.source || '') !== sf) return false;
    if (q) {
      const hay = \`\${l._display_name} \${l.provincia} \${l._resumen} \${l.source_label}\`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const sort = document.getElementById('sortSel')?.value || 'heat';
  S.filtered.sort((a, b) => {
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
    <tr onclick="openDetail('\${l.id}')" style="cursor:pointer" class="heat-\${l._heat_label}">
      <td class="td-nombre">
        \${l._heat_label === 'hot' ? '🔥 ' : l._heat_label === 'warm' ? '⚡ ' : ''}
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
            ? \`<a class="btn-wa-big" href="\${l._wa_url}" target="_blank" title="WhatsApp verificado">🟢</a>\`
            : l._wa_state === 'normalized_contact'
              ? \`<button class="btn-wa-pending" onclick="validateWaFromTable('\${l.id}')" title="Validar WhatsApp">⚪</button>\`
              : l._wa_state === 'not_whatsapp'
                ? \`<span class="wa-none" title="No tiene WhatsApp">❌</span>\`
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
  const withWa   = leads.filter(l => l._wa_url).length;
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
  document.getElementById('modal-body').textContent     = l.body || l.title || '—';
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
    waBtn.textContent = '💬 WhatsApp ✓';
    phoneLabel.textContent = l._wa_display + ' (verificado)';
  } else if (l._wa_state === 'normalized_contact') {
    box.classList.remove('no-contact');
    waBtn.style.display = 'inline-flex';
    waBtn.href = '#';
    waBtn.textContent = '⏳ Validar WhatsApp';
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

function copyDmTemplate() {
  // N2: Guión DM no-spam para Reddit (Claude)
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (!l) return;
  const author = stripUprefix(l.persona || l.author || '');
  const problema = l.problem_summary || l.title || l._resumen || 'tu consulta vehicular';
  const tpl = 'Hola u/' + (author || '') + ', vi tu consulta sobre ' + problema +
    '. Trabajo con un equipo legal que resuelve esto regularmente. ¿Querés que te cuente cómo funciona? Sin compromiso.';
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

// Validar WhatsApp via Worker (Apify WA validator)
async function validateWaFromModal() {
  const l = S.crmLeads.find(x => x.id === S.currentId);
  if (!l || l._wa_state !== 'normalized_contact') return;
  if (!l._wa_e164) { alert('Sin teléfono para validar'); return; }
  const phone = l._wa_e164.startsWith('+') ? l._wa_e164.slice(1) : l._wa_e164;
  const waBtn = document.getElementById('modal-wa-btn');
  const orig = waBtn.textContent;
  waBtn.textContent = '⏳ Validando...';
  waBtn.onclick = null;
  try {
    const r = await fetch('/api/whatsapp-validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Webhook-Secret': getUrlSecret() },
      body: JSON.stringify({ phones: [phone] })
    });
    const d = await r.json();
    if (d.ok && d.results && d.results.length > 0) {
      const isValid = d.results[0].isValid;
      setWaValidation(l._wa_e164, isValid);
      l._wa_state = isValid ? 'validated_whatsapp' : 'not_whatsapp';
      if (isValid) {
        waBtn.textContent = '💬 WhatsApp ✓';
        waBtn.href = l._wa_url;
        document.getElementById('modal-phone-label').textContent = l._wa_display + ' (verificado)';
      } else {
        waBtn.style.display = 'none';
        document.getElementById('modal-phone-label').textContent = l._wa_display + ' (no tiene WhatsApp)';
      }
      renderTable();
      renderKPIs();
    } else {
      alert('Error validando: ' + (d.error || '?'));
      waBtn.textContent = orig;
    }
  } catch (e) {
    alert('Error: ' + e.message);
    waBtn.textContent = orig;
  }
}

async function validateWaFromTable(id) {
  const l = S.crmLeads.find(x => x.id === id);
  if (!l) return;
  S.currentId = id;
  await validateWaFromModal();
}

function getUrlSecret() {
  return new URLSearchParams(location.search).get('key') || '';
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

        const runRes = await fetch('https://api.apify.com/v2/acts/uophWH4OrRO2TtXTT/runs?token=' + env.APIFY_TOKEN, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(apifyInput),
        });

        if (!runRes.ok) {
          const errText = await runRes.text();
          return jsonResponse({ ok: false, error: 'apify_failed', status: runRes.status, detail: errText.slice(0, 500) }, corsHeaders, 500);
        }

        const runData = await runRes.json();
        const runId = runData.data.id;
        const datasetId = runData.data.defaultDatasetId;

        // Polling: esperar hasta 90s a que el run termine
        let finalStatus = 'RUNNING';
        for (let i = 0; i < 18; i++) {
          await new Promise(r => setTimeout(r, 5000));
          const statusRes = await fetch('https://api.apify.com/v2/actor-runs/' + runId + '?token=' + env.APIFY_TOKEN);
          const statusData = await statusRes.json();
          finalStatus = statusData.data.status;
          if (finalStatus === 'SUCCEEDED' || finalStatus === 'FAILED' || finalStatus === 'ABORTED') break;
        }

        if (finalStatus !== 'SUCCEEDED') {
          return jsonResponse({ ok: false, error: 'apify_run_' + finalStatus.toLowerCase(), runId }, corsHeaders, 500);
        }

        // Obtener resultados del dataset
        const resultsRes = await fetch('https://api.apify.com/v2/datasets/' + datasetId + '/items?token=' + env.APIFY_TOKEN);
        const results = await resultsRes.json();

        // Filtrar y normalizar leads
        const PAIN_KEYWORDS = /multa|fotomulta|infracci[oó]n|libre.deuda|transferencia|patente|08|c[eé]dula|veraz|registro.automotor|juez.de.faltas|peaje|deuda|radicad|consulta|ayuda|reclam/i;
        const AR_PHONE = /(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}|\b15[-\s]?\d{4}[-\s]?\d{4}\b/g;
        const EMAIL_RE = /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g;
        const SPAM_DOMAINS = ['mailinator', 'tempmail', 'guerrillamail', '10minutemail', 'noreply', 'example.com', 'facebook.com'];

        const leads = [];
        for (const post of results) {
          const text = post.text || post.postText || '';
          const author = post.authorName || post.author || '';
          const postUrl = post.url || post.postUrl || '';
          if (!text && !author) continue;

          const hasPain = PAIN_KEYWORDS.test(text);
          if (!hasPain) continue;

          // Buscar contacto en el texto del post
          const phones = [...new Set((text.match(AR_PHONE) || []).map(p => p.trim()))];
          const emails = [...new Set((text.match(EMAIL_RE) || [])
            .map(e => e.toLowerCase().trim())
            .filter(e => !SPAM_DOMAINS.some(d => e.includes(d))))];

          // Buscar en comments también
          let commentsText = '';
          if (post.comments && Array.isArray(post.comments)) {
            commentsText = post.comments.map(c => (c.text || c.commentText || '') + ' ' + (c.commenterName || c.author || '')).join(' ');
          }
          const commentsPhones = [...new Set((commentsText.match(AR_PHONE) || []).map(p => p.trim()))];
          const commentsEmails = [...new Set((commentsText.match(EMAIL_RE) || [])
            .map(e => e.toLowerCase().trim())
            .filter(e => !SPAM_DOMAINS.some(d => e.includes(d))))];

          const allPhones = [...new Set([...phones, ...commentsPhones])];
          const allEmails = [...new Set([...emails, ...commentsEmails])];

          leads.push({
            id: 'fb_' + (post.id || postUrl.split('/').slice(-2)[0] || Math.random().toString(36).slice(2)),
            source: 'facebook_apify',
            source_label: 'Facebook',
            platform: 'Facebook',
            author: author,
            persona: author,
            title: text.slice(0, 200),
            snippet: (text + (commentsText ? ' | Comments: ' + commentsText : '')).slice(0, 3000),
            url: postUrl,
            fecha_iso: (post.timestamp || post.creationDate || '').slice(0, 10),
            score: 50,
            whatsapp_publico: allPhones[0] || '',
            telefono_publico: allPhones[0] || '',
            email_publico: allEmails[0] || '',
            has_contact: allPhones.length > 0 || allEmails.length > 0,
            contact_source: allPhones.length > 0 ? 'fb_post_or_comment' : '',
            comments_count: (post.comments || []).length,
          });
        }

        return jsonResponse({
          ok: true,
          total: leads.length,
          leads: leads,
          raw_results_count: results.length,
          run_id: runId,
          dataset_id: datasetId,
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

    // ─── POST /api/whatsapp-validate ─── Valida si telefonos tienen WhatsApp
    // Body: { "phones": ["5491154541802", "5491160065724"] }
    if (url.pathname === '/api/whatsapp-validate' && request.method === 'POST') {
      const secret = request.headers.get('X-Webhook-Secret');
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

        // Lanzar un run por cada telefono (el actor acepta 1 a la vez)
        const results = [];
        for (const phone of phones.slice(0, 10)) { // max 10 por request
          try {
            const runRes = await fetch('https://api.apify.com/v2/acts/devscrapper~whatsapp-number-validator/runs?token=' + env.APIFY_TOKEN, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ phoneNumber: phone }),
            });
            if (!runRes.ok) {
              results.push({ phone, isValid: false, error: 'apify_' + runRes.status });
              continue;
            }
            const runData = await runRes.json();
            const runId = runData.data.id;
            const datasetId = runData.data.defaultDatasetId;

            // Polling hasta 30s
            let finalStatus = 'RUNNING';
            for (let i = 0; i < 6; i++) {
              await new Promise(r => setTimeout(r, 5000));
              const statusRes = await fetch('https://api.apify.com/v2/actor-runs/' + runId + '?token=' + env.APIFY_TOKEN);
              const statusData = await statusRes.json();
              finalStatus = statusData.data.status;
              if (finalStatus === 'SUCCEEDED' || finalStatus === 'FAILED') break;
            }

            if (finalStatus === 'SUCCEEDED') {
              const itemsRes = await fetch('https://api.apify.com/v2/datasets/' + datasetId + '/items?token=' + env.APIFY_TOKEN);
              const items = await itemsRes.json();
              if (items.length > 0) {
                results.push({
                  phone: phone,
                  isValid: items[0].isValid || false,
                  exists: items[0].exists || false,
                  status: items[0].status || 'unknown',
                });
              } else {
                results.push({ phone, isValid: false, error: 'no_results' });
              }
            } else {
              results.push({ phone, isValid: false, error: 'run_' + finalStatus.toLowerCase() });
            }
          } catch (e) {
            results.push({ phone, isValid: false, error: e.message });
          }
        }

        return jsonResponse({
          ok: true,
          total: results.length,
          valid_count: results.filter(r => r.isValid).length,
          results: results,
        }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
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
      // Ejecutar pipeline inline (misma logica que scheduled handler)
      try {
        const result = await runPipelineCron(env);
        return jsonResponse({ ok: true, ...result }, corsHeaders);
      } catch (e) {
        return jsonResponse({ ok: false, error: e.message }, corsHeaders, 500);
      }
    }

    // ─── 404 ───
    return jsonResponse({ error: 'not_found', path: url.pathname }, corsHeaders, 404);
  },

  // ─── CRON TRIGGER cada 1h (GPT: scheduling en Worker, no GH Actions) ───
  async scheduled(event, env, ctx) {
    console.log('[CRON] Pipeline iniciado:', new Date().toISOString());
    try {
      await runPipelineCron(env);
    } catch (e) {
      console.error('[CRON] ERROR:', e.message);
    }
  }
};

// ─── Funcion standalone del pipeline (compartida por cron y /api/cron-run) ───
async function runPipelineCron(env) {
  const redditQueries = [
    'no puedo transferir multa argentina',
    'me llego multa fotomulta argentina',
    'libre deuda transferencia auto',
    'fotomulta reclamo argentina',
    'compre auto multas anteriores',
  ];

  const newLeads = [];
  const seenUrls = new Set();

  for (const query of redditQueries) {
    try {
      const rssUrl = 'https://www.reddit.com/search.rss?q=' + encodeURIComponent(query) + '&sort=new&limit=10&t=month';
      const rssRes = await fetch(rssUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
          'Accept': 'application/atom+xml, application/xml, text/xml, */*',
          'Accept-Language': 'es-AR,es;q=0.9',
        },
      });

      if (!rssRes.ok) continue;
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
          body = contentM[1].replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
        }
        const fecha = updatedM ? updatedM[1].slice(0, 10) : '';
        const fullText = (title + ' ' + body).toLowerCase();

        const painKw = ['multa','multas','fotomulta','fotomultas','infraccion','infracciones','infracción','libre deuda','transferencia','transferir','patente','08 firmado','cedula','veraz','registro automotor','juez de faltas','peaje','deuda','vencimiento'];
        if (!painKw.some(k => fullText.includes(k))) continue;

        let score = 40;
        const urgencyKw = ['urgente','hoy','ahora','recien','me llego','me llegue','consulta','ayuda','necesito','no puedo','me retuvieron'];
        if (urgencyKw.some(k => fullText.includes(k))) score += 20;
        const extremeKw = ['me llego','me llegue','me cobraron','me quieren cobrar','no puedo transferir','me retuvieron','necesito ayuda','alguien sabe','urgente'];
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

        const arGeo = ['argentina','buenos aires','caba','cordoba','córdoba','rosario','santa fe','mendoza','tucuman','tucumán','salta','neuquen','la plata'];
        if (arGeo.some(g => fullText.includes(g))) score += 15;

        const patenteMatch = body.match(/\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b/i);
        if (patenteMatch) score += 15;

        score = Math.max(0, Math.min(100, score));
        if (score < 40) continue;

        newLeads.push({
          id: 'reddit_' + url.split('/').slice(-2)[0],
          source: 'reddit_rss', source_label: 'Reddit', platform: 'Reddit',
          author: author, persona: author ? 'u/' + author : '(anonimo)',
          title: title.slice(0, 200), snippet: body.slice(0, 3000),
          url: url, fecha_iso: fecha, score: score,
          whatsapp_publico: phones[0] || waLinks[0] || '',
          telefono_publico: phones[0] || '',
          email_publico: emails[0] || '',
          has_contact: hasContact,
          patente: patenteMatch ? patenteMatch[1].toUpperCase() : '',
          timestamp: new Date().toISOString(),
        });
      }
    } catch (e) {}
  }

  const raw = await env.LEADX_KV.get('leads:live');
  let existing = { leads_all: [], leads_hot: [], meta: {} };
  if (raw) { try { existing = JSON.parse(raw); } catch (e) {} }

  const byUrl = new Map();
  for (const l of (existing.leads_all || [])) byUrl.set(l.url || l.id, l);
  for (const l of newLeads) byUrl.set(l.url || l.id, l);
  const merged = Array.from(byUrl.values());
  merged.sort((a, b) => (b.fecha_iso || '').localeCompare(a.fecha_iso || ''));
  const truncated = merged.slice(0, 500);

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
      version: '11.0', source: 'cron_trigger',
      generated_at: new Date().toISOString(),
      ingest_at: new Date().toISOString(),
      new_in_batch: newLeads.length,
    },
  };

  if (truncated.length === 0 && (existing.leads_all || []).length > 0) {
    return { ok: true, skipped: 'anti_wipe', existing: (existing.leads_all || []).length };
  }

  await env.LEADX_KV.put('leads:live', JSON.stringify(payload));
  return { ok: true, new_leads: newLeads.length, total: truncated.length, hot: payload.summary.hot_leads };
}

const COOKIES_HTML = `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LeadX — Refrescador de Cookies FB</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0e1a; color: #e2e8f0; padding: 20px; max-width: 800px; margin: 0 auto; }
  h1 { color: #38bdf8; margin-bottom: 8px; }
  .subtitle { color: #64748b; font-size: 13px; margin-bottom: 30px; }
  .card { background: #1e293b; border: 1px solid #334155; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
  .status { font-size: 14px; }
  .status-ok { color: #10b981; }
  .status-warn { color: #fbbf24; }
  .status-err { color: #f87171; }
  textarea { width: 100%; height: 200px; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px; resize: vertical; }
  button { background: #0ea5e9; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; margin-right: 8px; }
  button:hover { background: #0284c7; }
  button.test { background: #6554C0; }
  button.test:hover { background: #4c3a9e; }
  .info { font-size: 12px; color: #94a3b8; margin-top: 8px; line-height: 1.6; }
  .info code { background: #0f172a; padding: 2px 6px; border-radius: 3px; color: #fbbf24; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-top: 12px; }
  .stat { background: #0f172a; padding: 12px; border-radius: 6px; }
  .stat-label { font-size: 11px; color: #64748b; text-transform: uppercase; }
  .stat-value { font-size: 18px; font-weight: 700; margin-top: 4px; }
  #result { margin-top: 12px; padding: 12px; border-radius: 6px; font-size: 13px; display: none; }
  .result-ok { background: #064e3b; color: #6ee7b7; }
  .result-err { background: #7f1d1d; color: #fca5a5; }
  a { color: #38bdf8; }
</style>
</head>
<body>
  <h1>🍪 Refrescador de Cookies FB</h1>
  <div class="subtitle">LeadX — mantener sesión Facebook activa para Apify scraper</div>

  <div class="card">
    <div class="status" id="status">Cargando estado...</div>
    <div class="stats" id="stats"></div>
  </div>

  <div class="card">
    <h3 style="margin-bottom:12px">Pegar cookies nuevas</h3>
    <textarea id="cookiesInput" placeholder='Pegá acá el JSON exportado de Cookie-Editor (Chrome). Ejemplo:&#10;[&#10;  {"domain":".facebook.com","name":"xs","value":"35%3A..."},&#10;  {"domain":".facebook.com","name":"c_user","value":"USER_ID_EXAMPLE"},&#10;  ...&#10;]'></textarea>
    <div style="margin-top:12px">
      <button onclick="saveCookies()">💾 Guardar cookies</button>
      <button class="test" onclick="testCookies()">🧪 Probar cookies</button>
      <button onclick="loadStatus()" style="background:#475569">↻ Refrescar estado</button>
    </div>
    <div id="result"></div>
  </div>

  <div class="card">
    <div class="info">
      <strong>¿Cómo conseguir las cookies?</strong><br>
      1. Instalá la extensión <a href="https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm" target="_blank">Cookie-Editor</a> en Chrome<br>
      2. Iniciá sesión en <a href="https://www.facebook.com" target="_blank">facebook.com</a> con tu cuenta<br>
      3. Abrí Cookie-Editor (ícono de cookie arriba a la derecha)<br>
      4. Click en "Export" → "Export as JSON"<br>
      5. Pegá el JSON acá arriba → "Guardar cookies"
    </div>
  </div>

  <div class="card">
    <div class="info">
      <strong>¿Cada cuánto refrescar?</strong><br>
      • Cada <strong>7-14 días</strong> (preventivo)<br>
      • Si Apify devuelve 0 resultados (cookies vencidas)<br>
      • Si Facebook te desloguea de tu browser<br>
      • La cookie <code>xs</code> (sesión crítica) caduca en ~6 meses<br>
      • Facebook puede invalidarla antes si detecta scraping
    </div>
  </div>

<script>
const SECRET = new URLSearchParams(location.search).get('key') || '';

async function loadStatus() {
  document.getElementById('status').innerHTML = 'Cargando...';
  try {
    const r = await fetch('/api/cookies?key=' + SECRET);
    const d = await r.json();
    if (!d.ok) {
      document.getElementById('status').innerHTML = '<span class="status-err">Error: ' + (d.error || '?') + '</span>';
      return;
    }
    let statusClass = 'status-ok';
    let statusText = '✓ Cookies válidas';
    if (d.status === 'never_set') { statusClass = 'status-err'; statusText = '✗ Sin cookies guardadas'; }
    else if (d.status === 'expired') { statusClass = 'status-err'; statusText = '✗ Cookies VENCIDAS - refrescar ahora'; }
    else if (d.status === 'no_xs') { statusClass = 'status-warn'; statusText = '⚠ Falta cookie xs (sesión)'; }
    else if (d.days_until_expiry < 7) { statusClass = 'status-warn'; statusText = '⚠ Por vencer en ' + d.days_until_expiry + ' días'; }

    document.getElementById('status').innerHTML = '<span class="' + statusClass + '">' + statusText + '</span>';
    document.getElementById('stats').innerHTML = \`
      <div class="stat"><div class="stat-label">Cookies guardadas</div><div class="stat-value">\${d.cookie_count || 0}</div></div>
      <div class="stat"><div class="stat-label">Última actualización</div><div class="stat-value" style="font-size:13px">\${d.updated_at ? new Date(d.updated_at).toLocaleString('es-AR') : '—'}</div></div>
      <div class="stat"><div class="stat-label">Cookie xs vence</div><div class="stat-value" style="font-size:13px">\${d.xs_expires_at ? new Date(d.xs_expires_at).toLocaleDateString('es-AR') : '—'}</div></div>
      <div class="stat"><div class="stat-label">Días restantes</div><div class="stat-value">\${d.days_until_expiry !== null ? d.days_until_expiry : '—'}</div></div>
    \`;
}
loadStatus();
</script>
</body>
</html>`;

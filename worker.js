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
        <option value="fecha">↓ Más reciente</option>
        <option value="score">↓ Mayor urgencia</option>
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
  // Adaptar field names de mi pipeline (snake_case) a lo que el CRM espera
  const persona = l.persona || l.author || '';
  const wa = l.whatsapp_publico || l.whatsapp || '';
  const phone = l.telefono_publico || l.phone || wa;
  const email = l.email_publico || l.email || '';
  const title = l.problem_summary || l.title || '';
  const body = l.quoted_text || l.snippet || l.body || title;
  const url = l.source_url || l.url || '#';
  const platform = l.platform || l.source_label || l.source || '';
  return {
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
    _wa_url: buildWaUrl(phone || extractPhone(body) || ''),
    _display_name: (persona && persona !== '(anónimo)') ? persona : 'Sin nombre',
    _resumen: cleanText(title || body),
  };
}

function extractPhone(text) {
  const m = text.match(/(?:\\+54|0054)?[\\s\\-]?(?:9[\\s\\-]?)?(?:11|[2-9]\\d{2,3})[\\s\\-]?\\d{4}[\\s\\-]?\\d{4}/);
  return m ? m[0].trim() : '';
}

function buildWaUrl(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\\D/g, '');
  if (!digits) return '';
  const norm = digits.startsWith('54') ? digits : '54' + digits.replace(/^0/, '');
  return \`https://wa.me/\${norm}\`;
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

  const sort = document.getElementById('sortSel')?.value || 'fecha';
  S.filtered.sort((a, b) => {
    if (sort === 'score')    return (b.score || 0) - (a.score || 0);
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
    <tr onclick="openDetail('\${l.id}')" style="cursor:pointer">
      <td class="td-nombre">
        \${escH(l._display_name)}
        <small>\${escH(l.fecha_iso || '—')}</small>
      </td>
      <td>
        <span class="source-tag">\${escH(l.source_label || l.source || '—')}</span>
      </td>
      <td>\${escH(l.provincia || '—')}</td>
      <td class="td-resumen"><p>\${escH(l._resumen)}</p></td>
      <td>
        <span class="badge badge-\${cssStatus(l._status)}">\${l._status}</span>
        \${l.score >= 70 ? '<span class="badge badge-hot" title="Hot lead">🔥</span>' : ''}
        \${l.score >= 50 && l.score < 70 ? '<span class="badge badge-warm" title="Warm lead">⚡</span>' : ''}
      </td>
      <td>
        <div class="actions" onclick="event.stopPropagation()">
          \${l._wa_url
            ? \`<a class="btn-wa" href="\${l._wa_url}" target="_blank">💬</a>\`
            : \`<span style="font-size:11px;color:var(--muted)">Sin WA</span>\`
          }
          <button class="btn-icon" onclick="openDetail('\${l.id}')">📝</button>
        </div>
      </td>
    </tr>
  \`).join('');

  document.getElementById('tableContainer').innerHTML = \`
    <table>
      <thead>
        <tr>
          <th>Nombre / Usuario</th>
          <th>Fuente</th>
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

  if (l._wa_url) {
    box.classList.remove('no-contact');
    waBtn.href = l._wa_url;
    waBtn.style.display = 'inline-flex';
    phoneLabel.textContent = l._phone || 'WhatsApp disponible';
  } else {
    box.classList.add('no-contact');
    waBtn.style.display = 'none';
    phoneLabel.textContent = 'Sin contacto directo — buscar por perfil';
    document.getElementById('modal-author').textContent = l._display_name + ' (sin contacto)';
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
      const QUERIES = [
        'site:foromoto.com.ar multa OR fotomulta whatsapp OR celular OR "11-"',
        'site:foromoto.com.ar infraccion OR patente telefono OR contacto',
        'site:clasificados.lavoz.com.ar automovil OR auto telefono whatsapp',
        'site:demotores.com.ar particular vende whatsapp OR celular',
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
            const resultBlocks = html.split(/<div class="result[^"]*"/).slice(1);
            debugResultCount = Math.max(debugResultCount, resultBlocks.length);
            if (!debugFirstSnippet) {
              const firstBlock = resultBlocks[0] || '';
              const snipM = firstBlock.match(/<a[^>]*class="result__snippet"[^>]*>([\s\S]*?)<\/a>/);
              if (snipM) debugFirstSnippet = snipM[1].replace(/<[^>]+>/g, ' ').trim().slice(0, 200);
            }

            // Extraer resultados de DDG (cada resultado es un <a class="result__a"> y <a class="result__snippet">)
            const resultBlocks = html.split(/<div class="result[^"]*"/).slice(1);

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

              // Determinar platform
              let platform = 'web';
              if (postUrl.includes('foromoto')) platform = 'ForoMoto';
              else if (postUrl.includes('lavoz')) platform = 'ClasificadosLaVoz';
              else if (postUrl.includes('demotores')) platform = 'Demotores';
              else if (postUrl.includes('olx')) platform = 'OLX';

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

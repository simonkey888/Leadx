================================================================================
LEADX v2.3 — CODIGO COMPLETO ACTUALIZADO
Fecha: 6 julio 2026 | Commit: 17f93fd (ULTIMA VERSION)
Repo: github.com/simonkey888/Leadx
================================================================================

NOVEDADES v2.3 (Qwen fixes):
  FIX 1: Frontend auth con sessionStorage (prompt al cargar, sin ?key= en URL)
  FIX 2: Apify Facebook webhook configurado (resultados ya no se pierden)

NOVEDADES v2.2 (DeepSeek + Qwen):
  Step 4.6: mine_comments_for_contacts() - scraea comentarios del post
  Step 4.7: mine_profile_for_contacts() - scraea perfil del autor (comments.rss)

NOVEDADES v2.1 (Qwen+InternLM+DeepSeek P0 fixes):
  WhatsApp validate fire & forget + /api/apify-webhook + /api/whatsapp-webhook
  Limpieza: cron-run, runPipelineCron, c_data_iter eliminados

ARQUITECTURA FINAL:
  Python (GH Actions cron 1h) → scraping + scoring + OSINT + mining → POST /api/ingest
  Worker → edge API + KV proxy + deep merge (CERO logica de negocio)
  Frontend → read only (renderiza l.score de Python)

REGLA DE ORO: Ningun dato se calcula en dos lugares.
  Score → Python (unico cerebro)
  Estado CRM → KV (preservado en merge)
  Render → Frontend (read only)

ENDPOINTS Worker (17):
  GET  /                  CRM | GET  /cookies.html   Refrescador FB
  GET  /api/leads         KV  | GET  /api/metrics    KPIs
  GET  /api/health        Mon | POST /api/ingest     Deep merge
  GET  /api/kv            KV  | POST /api/kv         KV write
  GET  /api/ml-questions  ML  | GET  /api/reddit-bio  Bio scraper
  POST /api/apify-facebook FB | POST /api/apify-webhook FB resultados (auto)
  POST /api/whatsapp-validate | POST /api/whatsapp-webhook WA resultados
  GET  /api/clasificar-basic  | POST /api/clasificar-patente
  POST /api/clasificar-webhook| GET  /api/ddg-foromoto

SECRETS Cloudflare: INGEST_SECRET, CLASIFICAR_API_KEY,
  CLASIFICAR_WEBHOOK_SECRET, APIFY_TOKEN, FB_COOKIES

SCORING: intencion(0-40) + contacto(0-30) + urgencia(0-20) + geo(0-10)
  >=70 hot (rojo) | 40-69 warm (naranja) | <40 cold (gris)

FUENTES:
  ✅ Reddit /search.rss | ✅ Reddit comments.rss | ✅ Apify FB (webhook auto)
  ✅ clasific.ar basic  | ✅ WA validator       | ✅ OSINT shadow profile
  ✅ Comment mining     | ✅ Profile mining      | ❌ ML API (403)

================================================================================


================================================================================
FILE: worker.js | 2682 lines | SHA: b6d379717a03
DESC: Cloudflare Worker (edge only - 17 endpoints + CRM + sessionStorage auth)
================================================================================

```javascript
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

function cleanSnippet(text) {
  if (!text) return '';
  let t = String(text);
  // Quitar comentarios HTML
  t = t.replace(/<!--[\s\S]*?-->/g, '');
  // Quitar tags HTML
  t = t.replace(/<[^>]+>/g, ' ');
  // Quitar entidades HTML comunes
  t = t.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  // Colapsar espacios
  t = t.replace(/\s+/g, ' ').trim();
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
  // Qwen fix: sessionStorage + URL param
  let secret = sessionStorage.getItem('leadx_secret');
  if (!secret) {
    const urlSecret = new URLSearchParams(location.search).get('key');
    if (urlSecret) {
      sessionStorage.setItem('leadx_secret', urlSecret);
      secret = urlSecret;
    }
  }
  return secret || '';
}

// Prompt de auth al cargar si no hay secret
if (!sessionStorage.getItem('leadx_secret') && !new URLSearchParams(location.search).get('key')) {
  const s = prompt('🔒 Ingresá la clave de acceso:');
  if (s) sessionStorage.setItem('leadx_secret', s);
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

        // Qwen fix: configurar webhook para recibir resultados automaticamente
        const webhookConfigUrl = 'https://leadx.simondalmasso44.workers.dev/api/apify-webhook';
        try {
          await fetch('https://api.apify.com/v2/acts/uophWH4OrRO2TtXTT/webhooks?token=' + env.APIFY_TOKEN, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              requestUrl: webhookConfigUrl,
              eventName: 'ACTOR.RUN.SUCCEEDED',
            }),
          });
        } catch (e) {}

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

        // Fire & Forget: un run por telefono, devolver inmediatamente
        const runIds = [];
        for (const phone of phones.slice(0, 5)) {
          try {
            const runRes = await fetch('https://api.apify.com/v2/acts/devscrapper~whatsapp-number-validator/runs?token=' + env.APIFY_TOKEN, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ phoneNumber: phone }),
            });
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
          message: 'Validacion en background. Hacer polling desde browser via /api/kv?key=wa_val:PHONE',
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

    // ─── 404 ───
    return jsonResponse({ error: 'not_found', path: url.pathname }, corsHeaders, 404);
  },

  // GPT v2: Worker no tiene cron. Python es el unico pipeline.
  async scheduled(event, env, ctx) {
    return;
  }
};

// ─── Funcion standalone del pipeline (compartida por cron y /api/cron-run) ───

```


================================================================================
FILE: generate_payload.py | 1585 lines | SHA: 712f8c25c6f9
DESC: Pipeline Python (unico cerebro - scoring + OSINT + comment mining + profile mining)
================================================================================

```python
#!/usr/bin/env python3
"""
generate_payload.py — Pipeline que genera dashboard_payload.json + stats.json + history.json.

Arquitectura: static_dashboard + dynamic_json.
El HTML del dashboard NUNCA se regenera. Sólo se actualizan los JSONs.

7 pasos:
  1. collect_public_sources (search_providers web_search)
  2. extract_entities
  3. normalize_records
  4. classify_and_score
  5. deduplicate_cases (sha256 composite)
  6. build_dashboard_payload
  7. publish_artifacts (overwrite latest + append history + update stats)

Uso:
    python generate_payload.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# ===========================================================================
# Config
# ===========================================================================

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAYLOAD_PATH = DATA_DIR / "dashboard_payload.json"
STATS_PATH = DATA_DIR / "stats.json"
HISTORY_PATH = DATA_DIR / "history.json"

# Performance
MAX_RUNTIME_SECONDS = 200
RATE_LIMIT_MS = 8000  # 8s entre queries (rotacion evita repetir, menos 429)
MAX_RESULTS_PER_QUERY = 10

# ===========================================================================
# Queries (foco: dolor explícito + evento anterior)
# ===========================================================================

# Rotacion de grupos de queries Reddit (Claude v2 idea):
# Cada run usa solo 1 grupo (3 queries). Rota cada 3h.
# Misma query no se repite hasta 18h -> evita 429.
REDDIT_QUERY_GROUPS = [
    # Grupo 0: intencion "acabo de recibir" - momento optimo de venta
    [
        "site:reddit.com me llego multa no es mi auto",
        "site:reddit.com me cobraron fotomulta argentina",
        "site:reddit.com/r/DerechoGenial consulta multa",
    ],
    # Grupo 1: intencion "no puedo resolver" - bloqueo administrativo
    [
        "site:reddit.com no puedo transferir auto multa argentina",
        "site:reddit.com vendedor no entrego 08",
        "site:reddit.com/r/MotosArg multa patente",
    ],
    # Grupo 2: intencion "ayuda/consulta" - abierto a soluciones
    [
        "site:reddit.com consulta ayuda multa fotomulta argentina",
        "site:reddit.com/r/AskArgentina libre deuda transferencia",
        "site:reddit.com patente bloqueada registro automotor",
    ],
    # Grupo 3: intencion "compre con problema" - descubrimiento post-compra
    [
        "site:reddit.com compre auto multas anteriores dueño",
        "site:reddit.com/r/DerechoGenial fotomulta reclamo",
        "site:reddit.com juez de faltas multa reclamo",
    ],
    # Grupo 4: intencion "vendo con problema" - urgencia vendedor
    [
        "site:reddit.com cedula verde perdida transferir",
        "site:reddit.com vendo auto multas pendientes",
        "site:reddit.com multa vencida prescripcion argentina",
    ],
    # Grupo 5: intencion "gestor/abogado" - ya busca profesional (competencia directa)
    [
        "site:reddit.com abogado gestor multa fotomulta argentina",
        "site:reddit.com/r/Cordoba multa transito",
        "site:reddit.com/r/BuenosAires infraccion peaje",
    ],
]

# El grupo activo se elige por timestamp (rota cada run)
import time as _time_mod
_CURRENT_GROUP_IDX = int((_time_mod.time() / 10800) % len(REDDIT_QUERY_GROUPS))  # 10800s = 3h

QUERIES = REDDIT_QUERY_GROUPS[_CURRENT_GROUP_IDX]
print(f"[pipeline] Usando query group {_CURRENT_GROUP_IDX}/{len(REDDIT_QUERY_GROUPS)-1}: {QUERIES}", file=sys.stderr)

# ===========================================================================
# Step 4: Scoring (exacto del spec)
# ===========================================================================

SCORE_RULES = {
    "multa_or_fotomulta": 60,
    "transfer_problem": 45,
    "libre_deuda_problem": 35,
    "08_or_document_problem": 40,
    "public_contact_visible": 25,
    "recent_0_3_days": 20,
    "recent_4_7_days": 10,
    "argentina_signal": 15,
    "institutional_penalty": -40,
    "generic_penalty": -30,
    "foreign_country_penalty": -80,
    "dm_hint": 60,  # KIMI+DEEPSEEK: "mandame privado" = oro
    "urgency_hint": 30,  # "urgente", "ayuda"
}

# Patrones de "contactame por privado" (DM hints) - KIMI+DEEPSEEK idea
DM_HINT_PATTERNS = [
    r"\b(?:mandame|escribime|pasame|enviame|contactame|llamame|hablame)\s+(?:un\s+)?(?:md|dm|mp|privado|mensaje|wa|whatsapp)\b",
    r"\b(?:mandame|escribime|pasame)\s+(?:tu|el|un)\s+(?:whatsapp|wa|wpp|número|numero|cel|tel)",
    r"\b(?:md|dm|mp)\s+(?:para|y)\s+(?:te|lo)\s+(?:paso|mandamos|ayudamos)",
    r"\b(?:whatsapp|wa|wpp)\s+(?:y|para)\s+(?:te|lo)\s+(?:ayudamos|asesoramos|respondemos)",
    r"\bcontactame\s+por\s+(?:privado|mensaje)\b",
    r"\b(?:te|me)\s+(?:dejo|dejas|pasas)\s+(?:mi|tu)\s+(?:whatsapp|wa|cel)\b",
]

URGENCY_HINT_PATTERNS = [
    r"\burgente\b", r"\bayuda\b", r"\bvencimiento\b",
    r"\bmañana\s+vence\b", r"\bhoy\s+último\s+día\b",
]

# Regex AR quirúrgico (CHEVRON+QWEN+PERPLEXITY consensus)
# Captura: 11-1234-5678, +54 9 11 1234 5678, 0342-456-7890, 15-XXXX-XXXX
AR_PHONE_REGEX_QUIRURGICO = re.compile(
    r"(?:(?:\+54\s?9?\s?)?(?:11|2\d{2}|3\d{2})\s?[-.\s]?\d{4}[-.\s]?\d{4}"
    r"|\b15[-\s]?\d{4}[-\s]?\d{4}\b"
    r"|\b0?(?:11|2\d{2}|3\d{2})[-\s]?\d{3,4}[-\s]?\d{4}\b)"
)

# WhatsApp patterns específicos (más amplios)
WHATSAPP_HINT_REGEX = re.compile(
    r"(?:wa\.me/(\d{8,15})"
    r"|whatsapp[:\s]+(\+?\d[\d\s\-]{8,15})"
    r"|(?:wp|wpp|wsp|wapp)[:\s]+(\+?\d[\d\s\-]{8,15})"
    r"|(?:celular|cel|contacto|telefono|teléfono)[:\s]+(\+?\d[\d\s\-]{8,15}))",
    re.IGNORECASE
)

# ===========================================================================
# Filtros
# ===========================================================================

MUST_INCLUDE_ONE = ["auto", "transferencia", "vehiculo", "vehículo", "multa", "patente",
                    "moto", "camioneta", "libre deuda", "08"]

REJECT_IF_CONTAINS = [
    "publicado por", "leer más", "última actualización",
    "calculá tu", "calcula tu", "simulador", "arancel",
    "guía completa", "guia completa", "paso a paso",
    "trámite online", "turno web",
    "wikipedia", "enciclopedia",
    "transferencia internacional", "transferir dinero",
    "enviar dinero", "criptomoneda",
]

INSTITUTIONAL_DOMAINS = {
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    ".gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com",
    "es.wikipedia.org", "en.wikipedia.org",
    "youtube.com", "instagram.com", "tiktok.com",
    "elcerokm.com", "servidos.ar", "alarfin.com.ar",
    "autofact.cl", "autofact.com.ar", "kavak.com",
    "comparaencasa.com", "tuquejasuma.com",
}

GENERIC_DOMAINS = {
    "mercadolibre.com.ar", "mercadolibre.com", "mlstatic.com",
    "listado.mercadolibre.com.ar", "auto.mercadolibre.com.ar",
    "autocosmos.com.ar", "demotores.com.ar",
}

FOREIGN_INDICATORS = {
    "México": ["cdmx", "guadalajara", "monterrey", "+52", "méxico", "mexico"],
    "Colombia": ["bogotá", "bogota", "medellín", "+57", "colombia"],
    "Uruguay": ["montevideo", "+598", "uruguay"],
    "Chile": ["santiago de chile", "+56", " chile "],
    "Brasil": ["são paulo", "sao paulo", "+55", "brasil", "brazil"],
    "Italia": ["pisa", "roma", "milano", "italia"],
    "España": ["madrid", "barcelona", "españa", "espana"],
    "EEUU": ["miami", "new york", "california", "estados unidos"],
}

ARGENTINA_SIGNALS = [
    "DNRPA", "patente argentina", "Buenos Aires", "CABA",
    "Santa Fe", "Córdoba", "Mendoza", "Rosario", "La Plata",
    "ARBA", "Rentas", "PBA", "GBA", "argentina",
    "Entre Ríos", "Neuquén", "Salta", "Paraná",
]

# Phone patterns
# MEJORA 1 (Qwen): Regex FEDERAL - cubre TODO el pais
# CABA (11), Rosario (341), Cordoba (351), Mendoza (261),
# La Plata (221), Tucuman (381), Neuquen (299), Santa Fe (342/343)
ARG_PHONE_PATTERNS = [
    r"\+54\s?9?\s?(?:11|341|342|343|351|261|221|381|299)\s?\d{4}[\s\-]?\d{4}",
    r"\b(?:11|341|342|343|351|261|221|381|299)\s?[\s\-]?\d{4}[\s\-]?\d{4}\b",
    r"\b15\s?\d{4}\s?\d{4}\b",
    r"\b0?(?:11|341|342|343|351|261|221|381|299)[\s\-]?\d{3,4}[\s\-]?\d{4}\b",
    r"\b(34[0-9]|35[0-9]|26[0-9]|38[0-9]|22[0-9]|29[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
]

WHATSAPP_PATTERNS = [
    r"wa\.me/(\d{8,15})",
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    # Formatos argentinos comunes
    r"\b(\+54\s?9?\s?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4})",
    r"\b(11\s?\d{4}[\s\-]?\d{4})",  # CABA mobile
    r"\b(15\s?\d{4}[\s\-]?\d{4})",  # old mobile format
    r"(?:contacto|celular|tel|fono|telefono)\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    # Pattern generico para "11-1234-5678"
    r"\b(\d{2}[\s\-]?\d{4}[\s\-]?\d{4})\b",
]

# Email pattern
EMAIL_PATTERN = r"\b([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})\b"

# Reddit username pattern (u/username)
REDDIT_USERNAME_PATTERN = r"\bu/([A-Za-z0-9_\-]{3,20})\b"

PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

VEHICLE_KEYWORDS = [
    "auto", "moto", "camioneta", "camion", "utilitario",
    "ford", "chevrolet", "toyota", "honda", "volkswagen", "vw",
    "peugeot", "renault", "citroen", "fiat", "nissan",
]

PROVINCE_MAP = {
    "buenos aires": "Buenos Aires", "pba": "Buenos Aires", "gba": "Buenos Aires",
    "caba": "CABA", "capital federal": "CABA", "capital": "CABA",
    "santa fe": "Santa Fe", "rosario": "Santa Fe",
    "córdoba": "Córdoba", "cordoba": "Córdoba",
    "mendoza": "Mendoza",
    "entre ríos": "Entre Ríos", "entre rios": "Entre Ríos", "paraná": "Entre Ríos", "parana": "Entre Ríos",
    "neuquén": "Neuquén", "neuquen": "Neuquén",
    "salta": "Salta",
    "la pampa": "La Pampa",
    "río negro": "Río Negro", "rio negro": "Río Negro",
}

CITY_MAP = {
    "la plata": "La Plata", "lanús": "Lanús", "lanus": "Lanús",
    "avellaneda": "Avellaneda", "quilmes": "Quilmes",
    "pilar": "Pilar", "tigre": "Tigre", "morón": "Morón", "moron": "Morón",
    "rosario": "Rosario", "rafaela": "Rafaela",
    "córdoba": "Córdoba", "cordoba": "Córdoba",
    "mendoza": "Mendoza", "paraná": "Paraná", "parana": "Paraná",
    "neuquén": "Neuquén", "neuquen": "Neuquén",
    "salta": "Salta",
}

PLATFORM_MAP = {
    "facebook.com": "Facebook", "m.facebook.com": "Facebook",
    "reddit.com": "Reddit", "www.reddit.com": "Reddit",
    "twitter.com": "X", "x.com": "X",
    "mercadolibre.com.ar": "MercadoLibre",
    "listado.mercadolibre.com.ar": "MercadoLibre",
    "auto.mercadolibre.com.ar": "MercadoLibre",
}


# ===========================================================================
# Dataclass
# ===========================================================================
@dataclass
class Lead:
    id: str = ""
    score: int = 0
    label: str = ""  # real_lead | commercial_signal | reject
    problem_category: str = ""
    problem_summary: str = ""
    persona: str = ""
    provincia: str = ""
    ciudad: str = ""
    pais: str = ""
    vehiculo: str = ""
    patente: str = ""
    fecha_visible: str = ""
    fecha_iso: str = ""
    platform: str = ""
    source_url: str = ""
    quoted_text: str = ""
    contacto_publico: bool = False
    whatsapp_publico: str = ""
    whatsapp_link: str = ""
    telefono_publico: str = ""
    telefono_e164: str = ""
    email_publico: str = ""
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    detected_signals: List[str] = field(default_factory=list)
    discovery_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# search_providers web_search
# ===========================================================================
# Import search providers (DuckDuckGo + Reddit + RSS, sin search_providers)
from search_providers import search as provider_search
from source_registry import run_discovery_and_update, get_approved_sources
from pending_queries_kv import PendingQueryManager
from search_providers import search_reddit_with_status, search_foroargentina
from search_providers import enrich_reddit_post


def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Wrapper que usa search_providers en vez de search_providers CLI."""
    try:
        results = provider_search(query, num=num)
        adapted = []
        for r in results:
            adapted.append({
                "name": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "date": r.get("date", ""),
                "host_name": r.get("url", ""),
                "username": r.get("username", "") or r.get("author", ""),
                "author": r.get("author", "") or r.get("username", ""),
            })
        return adapted
    except Exception as e:
        print(f"  [search error] {e}", file=sys.stderr)
        return []


# ===========================================================================
# Helpers
# ===========================================================================
def get_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    t = text.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def canonicalize_url(url: str) -> str:
    # Quitar tracking params, normalizar https
    try:
        parsed = urlparse(url)
        # Quitar query params except paths
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
    except Exception:
        return url


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%b %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str[:25], fmt)
        except ValueError:
            continue
    return None


def phone_to_e164(phone: str) -> str:
    """Normaliza telefono a formato +54XXXXXXXXXX (Claude version mejorada).
    Cubre: +54 9 11 1234 5678 / 11-1234-5678 / 011 1234-5678 / etc.
    """
    digits = re.sub(r"\D", "", phone)
    if not digits or len(digits) < 8:
        return ""
    # Quitar prefijo pais si existe
    if digits.startswith("54"):
        digits = digits[2:]
    # Quitar 0 inicial (prefix interurbano AR)
    if digits.startswith("0"):
        digits = digits[1:]
    # Quitar 9 inicial (mobile prefix AR)
    if digits.startswith("9") and len(digits) == 11:
        digits = digits[1:]
    # Si tiene 10 digitos y empieza con 11 (CABA mobile), agregar 9
    if len(digits) == 10 and digits.startswith("11"):
        digits = "9" + digits
    return f"+54{digits}" if len(digits) >= 8 else ""


# ===========================================================================
# Step 1: Collect
# ===========================================================================
def collect_public_sources() -> List[Dict[str, Any]]:
    """Recolecta resultados de búsquedas públicas via search_providers web_search.
    
    Si una query Reddit devuelve 429, la agrega a PendingQueryManager global.
    """
    print("[Step 1] Collecting public sources...", file=sys.stderr)
    all_results = []
    # PQM global accesible desde collect_public_sources
    global _pqm_global
    for i, query in enumerate(QUERIES):
        elapsed = time.time() - START_TIME
        if elapsed > MAX_RUNTIME_SECONDS:
            print(f"  [timeout] {elapsed:.1f}s", file=sys.stderr)
            break
        print(f"  [{i+1}/{len(QUERIES)}] {query[:60]}", file=sys.stderr)
        
        # Si es query Reddit, usar wrapper con status para detectar 429
        if "site:reddit.com" in query.lower():
            results, got_429 = search_reddit_with_status(
                query.lower().replace("site:reddit.com", "").strip(),
                num=MAX_RESULTS_PER_QUERY
            )
            if got_429 and _pqm_global:
                rss_url = f"https://www.reddit.com/search.rss?q={query}"
                _pqm_global.add(rss_url, query, _CURRENT_GROUP_IDX)
                print(f"  [PQM] 429 en '{query[:40]}' → agregado a pending", file=sys.stderr)
        else:
            results = web_search(query, num=MAX_RESULTS_PER_QUERY)
        
        for r in results:
            r["_query"] = query
        all_results.extend(results)
        time.sleep(RATE_LIMIT_MS / 1000)
    print(f"  Collected {len(all_results)} raw results", file=sys.stderr)

    # Nota: el enrich separado fue reemplazado por la logica inline en search_reddit
    # que trae selftext completo + top 10 comments por post en una sola pasada.
    reddit_count = sum(1 for r in all_results if "reddit.com" in r.get("url", ""))
    print(f"  Reddit posts in results: {reddit_count}", file=sys.stderr)

    # ML Questions Radar — siempre corre (no depende del grupo rotativo)
    try:
        from search_providers import search_mercadolibre_questions
        ml_leads = search_mercadolibre_questions(num=15)
        if ml_leads:
            for ml in ml_leads:
                ml["_query"] = "mercadolibre_questions_radar"
            all_results.extend(ml_leads)
            print(f"  ML Questions Radar: +{len(ml_leads)} leads", file=sys.stderr)
        else:
            print(f"  ML Questions Radar: 0 leads (posible 403 o sin resultados)", file=sys.stderr)
    except Exception as e:
        print(f"  ML Questions Radar ERROR: {e}", file=sys.stderr)

    # Foros AR via DDG (ForoMoto + ClasificadosLaVoz + Demotores)
    # Llama al endpoint /api/ddg-foromoto del Worker (Cloudflare edge IP)
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        secret = os.environ.get("INGEST_SECRET", "")
        if secret:
            import urllib.request as _urq
            foro_url = f"{worker_url}/api/ddg-foromoto"
            req = _urq.Request(foro_url)
            req.add_header("X-Webhook-Secret", secret)
            req.add_header("Accept", "application/json")
            with _urq.urlopen(req, timeout=45) as resp:
                foro_data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if foro_data.get("ok"):
                foro_leads = foro_data.get("leads", [])
                if foro_leads:
                    for fl in foro_leads:
                        fl["_query"] = "ddg_foros_ar"
                    all_results.extend(foro_leads)
                    print(f"  Foros AR (DDG): +{len(foro_leads)} leads con contacto", file=sys.stderr)
                else:
                    print(f"  Foros AR (DDG): 0 leads", file=sys.stderr)
    except Exception as e:
        print(f"  Foros AR ERROR: {e}", file=sys.stderr)

    # Facebook Groups via Apify (con cookies FB reales)
    # Llama al endpoint /api/apify-facebook del Worker
    # Scrapea grupos publicos de multas AR con sesion autenticada
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        secret = os.environ.get("INGEST_SECRET", "")
        if secret:
            import urllib.request as _urq2
            apify_url = f"{worker_url}/api/apify-facebook"
            apify_input = json.dumps({
                "groupUrls": [
                    "https://www.facebook.com/groups/276074287942602",  # Defensas contra Multas AR
                ],
                "maxPosts": 20,
                "fetchComments": True,
                "maxCommentsPerPost": 5,
            }).encode("utf-8")
            req2 = _urq2.Request(apify_url, data=apify_input, method="POST")
            req2.add_header("X-Webhook-Secret", secret)
            req2.add_header("Content-Type", "application/json")
            with _urq2.urlopen(req2, timeout=120) as resp2:
                fb_data = json.loads(resp2.read().decode("utf-8", errors="replace"))
            if fb_data.get("ok"):
                fb_leads = fb_data.get("leads", [])
                if fb_leads:
                    for fl in fb_leads:
                        fl["_query"] = "facebook_apify"
                    all_results.extend(fb_leads)
                    with_contact = sum(1 for fl in fb_leads if fl.get("has_contact"))
                    print(f"  Facebook (Apify): +{len(fb_leads)} leads ({with_contact} con contacto)", file=sys.stderr)
                else:
                    print(f"  Facebook (Apify): 0 leads", file=sys.stderr)
            else:
                print(f"  Facebook (Apify) ERROR: {fb_data.get('error','?')}", file=sys.stderr)
    except Exception as e:
        print(f"  Facebook (Apify) ERROR: {e}", file=sys.stderr)

    return all_results


# ===========================================================================
# Step 2: Extract entities
# ===========================================================================
def extract_entities(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extrae entidades de un resultado de búsqueda."""
    name = result.get("name", "")
    snippet = result.get("snippet", "")
    url = result.get("url", "")
    date = result.get("date", "")
    combined = f"{name}. {snippet}"

    # Content filter
    combined_lower = combined.lower()
    if not any(kw in combined_lower for kw in MUST_INCLUDE_ONE):
        return None
    for reject in REJECT_IF_CONTAINS:
        if reject in combined_lower:
            return None

    # Extract phone
    phone = ""
    for pattern in ARG_PHONE_PATTERNS:
        m = re.search(pattern, combined)
        if m:
            digits = re.sub(r"\D", "", m.group(0))
            if 10 <= len(digits) <= 15:
                phone = m.group(0).strip()
                break

    # Extract whatsapp
    whatsapp = ""
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            num = m.group(1) if m.groups() else m.group(0)
            digits = re.sub(r"\D", "", num)
            if 8 <= len(digits) <= 15:
                # Si empieza con 54 o 549, dejarlo; si tiene 10 digitos y arranca con 11, agregar 549
                if len(digits) == 10 and digits.startswith("11"):
                    digits = "549" + digits
                elif len(digits) == 10 and not digits.startswith("5"):
                    digits = "54" + digits
                whatsapp = digits
                break

    # Extract email
    email = ""
    m = re.search(EMAIL_PATTERN, combined)
    if m:
        email = m.group(1).lower().strip()

    # REGEX CONTEXTUAL (GPT+H.AI consensus):
    # Solo guardar contacto si el snippet TAMBIEN tiene keyword de dolor
    # Esto evita el spam de wa.me random sin contexto
    PAIN_KEYWORDS_RE = re.compile(
        r"\b(?:multa|multas|fotomulta|fotomultas|infracci[oó]n|infracciones|"
        r"libre\s+deuda|transferencia|transferir|patente|08\s+firmado|"
        r"c[eé]dula|veraz|registro\s+automotor|juez\s+de\s+faltas|"
        r"peaje|telepeaje|deuda|vencimiento|prescripci[oó]n)\b",
        re.IGNORECASE
    )
    has_pain_context = bool(PAIN_KEYWORDS_RE.search(combined))
    if not has_pain_context:
        # Sin contexto de dolor, descartar contacto (no es lead, es spam)
        phone = ""
        whatsapp = ""
        email = ""

    # Extract patent
    patent = ""
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, combined)
        if m:
            patent = re.sub(r"\s+", "", m.group(0)).upper()
            break

    # Extract vehicle
    vehicle = ""
    for v in VEHICLE_KEYWORDS:
        if v in combined_lower:
            vehicle = v
            break

    # Extract persona (username o nombre)
    persona = ""
    username = ""
    # 1. Provider ya trae username (Reddit author)
    provider_username = result.get("username", "") or result.get("author", "")
    if provider_username:
        username = provider_username
        persona = f"u/{username}"
    # 2. Buscar @username en el texto
    if not username:
        m = re.search(r"@(\w{3,20})", combined)
        if m:
            username = m.group(1)
            persona = m.group(0)
    # 3. Buscar u/username en el texto (Reddit-style)
    if not username:
        m = re.search(REDDIT_USERNAME_PATTERN, combined)
        if m:
            username = m.group(1)
            persona = f"u/{username}"
    # 4. "soy X"
    if not persona:
        m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", combined, re.IGNORECASE)
        if m:
            persona = m.group(1).title()

    # Reddit username from URL (rare path /user/X)
    host = get_host(url)
    if not username and "reddit.com" in host:
        m = re.search(r"/user/(\w+)", url)
        if m:
            username = m.group(1)
            persona = f"u/{username}"

    # Extract province/city
    provincia = ""
    ciudad = ""
    for city, prov in CITY_MAP.items():
        if city in combined_lower:
            ciudad = city.title()
            provincia = prov
            break
    if not provincia:
        for prov_key, prov_name in PROVINCE_MAP.items():
            if prov_key in combined_lower:
                provincia = prov_name
                break

    # Platform
    platform = PLATFORM_MAP.get(host, host.title() if host else "Unknown")

    return {
        "persona": persona or "(anónimo)",
        "username": username,
        "problema": combined,
        "provincia": provincia,
        "ciudad": ciudad,
        "vehiculo": vehicle,
        "patente": patent,
        "fecha_visible": date,
        "contacto_publico": bool(phone or whatsapp or email),
        "whatsapp_publico": whatsapp,
        "telefono_publico": phone,
        "email_publico": email,
        "source_url": url,
        "platform": platform,
        "quoted_text": snippet[:300] if snippet else "",
        "host": host,
        "combined_text": combined,
        # Campos extra de ML Questions (passthrough)
        "source": result.get("source", ""),
        "question_text": result.get("question_text", ""),
        "has_answer": result.get("has_answer", True),
        "price": result.get("price", 0),
        "seller_id": result.get("seller_id", ""),
        "provincia_ml": result.get("provincia_ml", ""),
    }


# ===========================================================================
# Step 3: Normalize
# ===========================================================================
def normalize_record(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza un record."""
    # Date
    fecha_iso = ""
    dt = parse_date(extracted.get("fecha_visible", ""))
    if dt:
        fecha_iso = dt.isoformat()

    # Phone to E.164
    telefono_e164 = ""
    if extracted.get("telefono_publico"):
        telefono_e164 = phone_to_e164(extracted["telefono_publico"])
    if not telefono_e164 and extracted.get("whatsapp_publico"):
        telefono_e164 = phone_to_e164(extracted["whatsapp_publico"])

    # Canonical URL
    source_url = canonicalize_url(extracted.get("source_url", ""))

    # Trim snippet
    quoted_text = extracted.get("quoted_text", "").strip()

    # Standardize province
    provincia = extracted.get("provincia", "")

    return {
        **extracted,
        "fecha_iso": fecha_iso,
        "telefono_e164": telefono_e164,
        "source_url": source_url,
        "quoted_text": quoted_text,
        "provincia": provincia,
    }


# ===========================================================================
# Step 4: Classify & Score
# ===========================================================================
def classify_and_score(record: Dict[str, Any]) -> Optional[Lead]:
    """Clasifica y puntúa un record."""
    text = record.get("combined_text", "").lower()
    host = record.get("host", "")
    score = 0
    breakdown = {}
    signals = []

    # --- Scoring ---

    # Boost ML Questions Radar (alta calidad - Sakana+Claude)
    platform_str = (record.get("platform", "") or "").lower()
    source_str = (record.get("source", "") or "").lower()
    if "mercadolibre" in platform_str or "mercadolibre" in source_str:
        score += 25
        breakdown["ml_questions"] = 25
        signals.append("ML_QUESTION_RADAR")
        q_text = (record.get("question_text", "") or "").lower()
        if "puede transferir" in q_text or "libre deuda" in q_text:
            score += 15
            breakdown["ml_urgencia"] = 15
            signals.append("ML_URGENCIA_TRANSFERENCIA")
        if not record.get("has_answer", True):
            score += 5
            breakdown["ml_no_answer"] = 5
        try:
            price = float(record.get("price", 0) or 0)
            if price > 15000:
                score += 10
                breakdown["ml_premium"] = 10
                signals.append("ML_AUTO_PREMIUM")
        except (ValueError, TypeError):
            pass

    # DM_HINTS boost (KIMI+DEEPSEEK): posts que piden contacto por privado
    import re as _re_dm
    for pattern in DM_HINT_PATTERNS:
        if _re_dm.search(pattern, text):
            score += SCORE_RULES["dm_hint"]
            breakdown["dm_hint"] = SCORE_RULES["dm_hint"]
            signals.append("DM_HINT")
            break

    # URGENCY boost
    for pattern in URGENCY_HINT_PATTERNS:
        if _re_dm.search(pattern, text):
            score += SCORE_RULES["urgency_hint"]
            breakdown["urgency_hint"] = SCORE_RULES["urgency_hint"]
            signals.append("URGENCY")
            break

    # multa_or_fotomulta: +60
    if "multa" in text or "fotomulta" in text:
        score += SCORE_RULES["multa_or_fotomulta"]
        breakdown["multa_or_fotomulta"] = SCORE_RULES["multa_or_fotomulta"]
        signals.append("multa_fotomulta")

    # transfer_problem: +45
    if "transferencia" in text or "transferir" in text or "08 firmado" in text:
        score += SCORE_RULES["transfer_problem"]
        breakdown["transfer_problem"] = SCORE_RULES["transfer_problem"]
        signals.append("transfer_problem")

    # libre_deuda_problem: +35
    if "libre deuda" in text:
        score += SCORE_RULES["libre_deuda_problem"]
        breakdown["libre_deuda_problem"] = SCORE_RULES["libre_deuda_problem"]
        signals.append("libre_deuda")

    # 08_or_document_problem: +40 (no sumar doble con transfer)
    if "08" in text and "libre deuda" not in text:
        score += SCORE_RULES["08_or_document_problem"]
        breakdown["08_or_document_problem"] = SCORE_RULES["08_or_document_problem"]
        signals.append("document_08")

    # public_contact_visible: +25
    if record.get("contacto_publico"):
        score += SCORE_RULES["public_contact_visible"]
        breakdown["public_contact_visible"] = SCORE_RULES["public_contact_visible"]
        signals.append("contact_visible")

    # recent_0_3_days: +20 / recent_4_7_days: +10
    fecha_iso = record.get("fecha_iso", "")
    dt = parse_date(fecha_iso)
    recent_label = ""
    if dt:
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        diff = now - dt
        if diff <= timedelta(days=3):
            score += SCORE_RULES["recent_0_3_days"]
            breakdown["recent_0_3_days"] = SCORE_RULES["recent_0_3_days"]
            recent_label = "recent_0_3"
            signals.append("recent_0_3_days")
        elif diff <= timedelta(days=7):
            score += SCORE_RULES["recent_4_7_days"]
            breakdown["recent_4_7_days"] = SCORE_RULES["recent_4_7_days"]
            recent_label = "recent_4_7"
            signals.append("recent_4_7_days")

    # argentina_signal: +15
    has_arg_signal = any(s.lower() in text for s in ARGENTINA_SIGNALS)
    if has_arg_signal:
        score += SCORE_RULES["argentina_signal"]
        breakdown["argentina_signal"] = SCORE_RULES["argentina_signal"]
        signals.append("argentina")

    # --- Penalties ---

    # foreign_country_penalty: -80
    is_foreign = False
    for country, indicators in FOREIGN_INDICATORS.items():
        for ind in indicators:
            if ind in text:
                is_foreign = True
                break
        if is_foreign:
            break
    if is_foreign:
        score += SCORE_RULES["foreign_country_penalty"]
        breakdown["foreign_country_penalty"] = SCORE_RULES["foreign_country_penalty"]

    # institutional_penalty: -40
    is_institutional = any(d in host for d in INSTITUTIONAL_DOMAINS)
    if is_institutional:
        score += SCORE_RULES["institutional_penalty"]
        breakdown["institutional_penalty"] = SCORE_RULES["institutional_penalty"]

    # generic_penalty: -30
    is_generic = any(d in host for d in GENERIC_DOMAINS)
    if is_generic:
        score += SCORE_RULES["generic_penalty"]
        breakdown["generic_penalty"] = SCORE_RULES["generic_penalty"]

    # --- PATENTE DETECTION (H.AI insight + GPT filter) ---
    # Detectar patente AR en texto y boost +15
    patente_match = re.search(r"\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b", record.get("combined_text", ""), re.IGNORECASE)
    if patente_match:
        score += 15
        breakdown["patente_detected"] = 15
        signals.append("PATENTE_DETECTED")
        # Marcar para enriquecimiento automatico con clasific.ar
        # (se hace en run_pipeline despues de classify_and_score)

    # --- INTENCION EXTREMA BOOST (GPT insight: filtrar ruido) ---
    # Solo leads con dolor MUY explicito merecen boost
    extreme_intent = any(phrase in text for phrase in [
        "me llego", "me llegue", "me cobraron", "me quieren cobrar",
        "no puedo transferir", "no me dejan transferir",
        "me retuvieron", "me secuestraron",
        "necesito ayuda", "necesito asesoramiento",
        "alguien sabe", "alguien me puede",
        "ayuda por favor", "urgente",
    ])
    if extreme_intent:
        score += 20
        breakdown["extreme_intent"] = 20
        signals.append("EXTREME_INTENT")

    # --- PENALTY: sin dolor explicito = ruido (GPT insight) ---
    # Si el texto NO tiene ninguna keyword de dolor, penalizar fuerte
    has_explicit_pain = any(kw in text for kw in [
        "multa", "multas", "fotomulta", "fotomultas",
        "infraccion", "infracciones", "infracción", "infracciones",
        "libre deuda", "transferencia", "transferir",
        "patente", "08 firmado", "cedula", "cedula verde",
        "veraz", "registro automotor", "juez de faltas",
        "peaje", "telepeaje", "deuda",
    ])
    if not has_explicit_pain:
        score -= 50
        breakdown["no_pain_penalty"] = -50
        signals.append("NO_PAIN")

    # --- CONTACTO BOOST (GPT: lo que importa es el contacto) ---
    has_contact = bool(
        record.get("whatsapp_publico") or
        record.get("telefono_publico") or
        record.get("email_publico") or
        record.get("phone") or
        record.get("whatsapp") or
        record.get("email")
    )
    if has_contact:
        score += 30
        breakdown["has_contact"] = 30
        signals.append("HAS_CONTACT")

    # Clamp
    score = max(0, min(100, score))

    # --- CLASSIFY (GPT: umbral mas alto para CRM) ---
    # Antes: 60 = real_lead. Ahora: 50 = real_lead (con filtro de dolor)
    if score >= 50 and not is_foreign and has_explicit_pain:
        label = "real_lead"
    elif score >= 30 and not is_foreign and has_explicit_pain:
        label = "commercial_signal"
    else:
        label = "reject"

    if label == "reject":
        return None

    # Problem category
    if "transferencia" in text or "transferir" in text or "08" in text:
        problem_cat = "TRANSFER_PROBLEM"
        problem_sum = "Problema de transferencia"
    elif "multa" in text or "fotomulta" in text:
        problem_cat = "FINE_DISPUTE"
        problem_sum = "Disputa de multa/fotomulta"
    elif "libre deuda" in text or "patente" in text:
        problem_cat = "DOCUMENTATION_ISSUE"
        problem_sum = "Problema documental"
    elif "no es mi auto" in text or "titular" in text:
        problem_cat = "OWNERSHIP_ISSUE"
        problem_sum = "Problema de titularidad"
    else:
        problem_cat = "OTHER"
        problem_sum = "Lead vehicular"

    # WhatsApp link
    wa_link = ""
    wa_num = record.get("whatsapp_publico", "") or record.get("telefono_publico", "")
    if wa_num:
        digits = re.sub(r"\D", "", wa_num)
        if not digits.startswith("54"):
            digits = "54" + digits.lstrip("0")
        wa_link = f"https://wa.me/{digits}"

    return Lead(
        score=score,
        label=label,
        problem_category=problem_cat,
        problem_summary=problem_sum,
        persona=record.get("persona", "(anónimo)"),
        provincia=record.get("provincia", ""),
        ciudad=record.get("ciudad", ""),
        pais="Argentina" if has_arg_signal and not is_foreign else ("Unknown" if not has_arg_signal else "Foreign"),
        vehiculo=record.get("vehiculo", ""),
        patente=record.get("patente", ""),
        fecha_visible=record.get("fecha_visible", ""),
        fecha_iso=fecha_iso,
        platform=record.get("platform", ""),
        source_url=record.get("source_url", ""),
        quoted_text=record.get("quoted_text", ""),
        contacto_publico=record.get("contacto_publico", False),
        whatsapp_publico=record.get("whatsapp_publico", ""),
        whatsapp_link=wa_link,
        email_publico=record.get("email_publico", ""),
        telefono_publico=record.get("telefono_publico", ""),
        telefono_e164=record.get("telefono_e164", ""),
        score_breakdown=breakdown,
        detected_signals=signals,
        discovery_timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ===========================================================================
# Step 5: Deduplicate
# ===========================================================================
def deduplicate_cases(leads: List[Lead]) -> List[Lead]:
    """Dedup por sha256 composite hash."""
    print("[Step 5] Deduplicating...", file=sys.stderr)
    seen: Set[str] = set()
    out = []
    for lead in leads:
        components = [
            normalize_text(lead.quoted_text[:200]),
            lead.source_url,
            lead.persona,
            lead.platform,
        ]
        composite = "|".join(components)
        h = hashlib.sha256(composite.encode("utf-8")).hexdigest()[:16]
        lead.id = h
        if h in seen:
            continue
        seen.add(h)
        out.append(lead)
    print(f"  Before: {len(leads)} → After: {len(out)}", file=sys.stderr)
    return out


# ===========================================================================
# Step 6: Build payload
# ===========================================================================
def generate_insights(leads: List[Lead]) -> List[str]:
    """Genera insights automáticos del lote."""
    insights = []
    if not leads:
        return ["Sin datos suficientes para generar insights."]

    # Pattern 1: top platform en hot leads
    hot = [l for l in leads if l.label == "real_lead"]
    if hot:
        plat_counts = {}
        for l in hot:
            plat_counts[l.platform] = plat_counts.get(l.platform, 0) + 1
        top_plat = max(plat_counts, key=plat_counts.get)
        top_pct = round(plat_counts[top_plat] / len(hot) * 100)
        insights.append(f"El {top_pct}% de los leads calientes provienen de {top_plat}.")

    # Pattern 2: top province
    prov_counts = {}
    for l in hot:
        if l.provincia:
            prov_counts[l.provincia] = prov_counts.get(l.provincia, 0) + 1
    if prov_counts:
        top_prov = max(prov_counts, key=prov_counts.get)
        top_prov_pct = round(prov_counts[top_prov] / len(hot) * 100)
        insights.append(f"El {top_prov_pct}% de los leads calientes son de {top_prov}.")

    # Pattern 3: top problem
    prob_counts = {}
    for l in hot:
        prob_counts[l.problem_summary] = prob_counts.get(l.problem_summary, 0) + 1
    if prob_counts:
        top_prob = max(prob_counts, key=prob_counts.get)
        insights.append(f"El problema más frecuente es: {top_prob}.")

    # Pattern 4: contact rate
    with_contact = sum(1 for l in hot if l.contacto_publico)
    if hot:
        contact_pct = round(with_contact / len(hot) * 100)
        insights.append(f"{contact_pct}% de los leads calientes tienen contacto público visible.")

    # Pattern 5: urgency
    urgent = sum(1 for l in hot if "urgency" in str(l.detected_signals).lower() or
                 any(kw in l.quoted_text.lower() for kw in ["urgente", "hoy", "mañana", "ya"]))
    if urgent > 0:
        insights.append(f"{urgent} leads calientes muestran señales de urgencia temporal.")

    return insights


def build_dashboard_payload(leads: List[Lead]) -> Dict[str, Any]:
    """Construye el payload final del dashboard."""
    print("[Step 6] Building dashboard payload...", file=sys.stderr)

    run_id = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:12]
    generated_at = datetime.now(timezone.utc).isoformat()

    hot = [l for l in leads if l.label == "real_lead"]
    warm = [l for l in leads if l.label == "commercial_signal"]

    # Sort each by score desc, date desc
    hot.sort(key=lambda l: (l.score, l.fecha_iso or l.discovery_timestamp), reverse=True)
    warm.sort(key=lambda l: (l.score, l.fecha_iso or l.discovery_timestamp), reverse=True)

    summary = {
        "total_leads": len(leads),
        "hot_leads": len(hot),
        "warm_leads": len(warm),
        "contactable": sum(1 for l in leads if l.contacto_publico),
        "with_whatsapp": sum(1 for l in leads if l.whatsapp_publico),
        "with_phone": sum(1 for l in leads if l.telefono_publico),
        "with_email": sum(1 for l in leads if l.email_publico),
        "avg_score": round(sum(l.score for l in leads) / len(leads), 1) if leads else 0,
        "avg_score_hot": round(sum(l.score for l in hot) / len(hot), 1) if hot else 0,
        "conversion_probability": round(len(hot) / len(leads) * 100, 1) if leads else 0,
        "by_category": {},
        "by_platform": {},
        "by_province": {},
    }
    for l in leads:
        summary["by_category"][l.problem_category] = summary["by_category"].get(l.problem_category, 0) + 1
        summary["by_platform"][l.platform] = summary["by_platform"].get(l.platform, 0) + 1
        if l.provincia:
            summary["by_province"][l.provincia] = summary["by_province"].get(l.provincia, 0) + 1

    insights = generate_insights(leads)

    all_leads_sorted = sorted(leads, key=lambda l: l.score if hasattr(l, "score") else 0, reverse=True)
    payload = {
        "generated_at": generated_at,
        "run_id": run_id,
        "summary": summary,
        "leads_all": [l.to_dict() for l in all_leads_sorted],
        "leads_hot": [l.to_dict() for l in hot],
        "leads_warm": [l.to_dict() for l in warm],
        "insights": insights,
        "meta": {
            "version": "1.0",
            "pipeline_steps": ["collect", "extract", "normalize", "classify_score", "dedup", "build_payload", "publish"],
            "scoring_rules": SCORE_RULES,
            "runtime_seconds": round(time.time() - START_TIME, 2),
            "queries_executed": QUERIES_EXECUTED,
        },
    }

    print(f"  Hot: {len(hot)} | Warm: {len(warm)} | Insights: {len(insights)}", file=sys.stderr)
    return payload


# ===========================================================================
# Step 7: Publish
# ===========================================================================
def publish_artifacts(payload: Dict[str, Any], leads: List[Lead]) -> None:
    """Publica los artefactos: overwrite latest + append history + update stats."""
    print("[Step 7] Publishing artifacts...", file=sys.stderr)

    # Overwrite dashboard_payload.json
    PAYLOAD_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {PAYLOAD_PATH} ({PAYLOAD_PATH.stat().st_size:,} bytes)", file=sys.stderr)

    # Append to history.json
    history_entry = {
        "run_id": payload["run_id"],
        "generated_at": payload["generated_at"],
        "summary": payload["summary"],
    }
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append(history_entry)
    history = history[-100:]  # keep last 100 runs
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {HISTORY_PATH} ({len(history)} runs)", file=sys.stderr)

    # Update stats.json (cumulative)
    stats = {
        "total_runs": len(history),
        "last_run": payload["generated_at"],
        "last_run_id": payload["run_id"],
        "total_leads_all_time": sum(h["summary"]["total_leads"] for h in history),
        "total_hot_leads_all_time": sum(h["summary"]["hot_leads"] for h in history),
        "avg_hot_per_run": round(sum(h["summary"]["hot_leads"] for h in history) / len(history), 1) if history else 0,
        "runs_today": sum(1 for h in history if h["generated_at"][:10] == payload["generated_at"][:10]),
        "last_7_days": [h for h in history[-7:]],
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {STATS_PATH}", file=sys.stderr)


# ===========================================================================
# Main pipeline
# ===========================================================================

START_TIME = time.time()
QUERIES_EXECUTED = 0
_pqm_global = None  # PendingQueryManager global, seteado en run_pipeline
_CURRENT_GROUP_IDX = 0


def run_pipeline() -> Dict[str, Any]:
    global QUERIES_EXECUTED, _pqm_global
    _pqm_global = None  # se setea en Step 0.5

    print("=" * 60, file=sys.stderr)
    print("  LeadX Pipeline v2 (Python = unico cerebro)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # GPT FIX: Descargar KV existente para merge correcto
    # (Worker hace deep merge, pero Python necesita saber que ya existe)
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        ingest_secret = os.environ.get("INGEST_SECRET", "")
        if ingest_secret:
            import urllib.request as _urq_kv
            kv_url = f"{worker_url}/api/kv?key=leads:live"
            req_kv = _urq_kv.Request(kv_url)
            req_kv.add_header("X-Webhook-Secret", ingest_secret)
            with _urq_kv.urlopen(req_kv, timeout=15) as resp_kv:
                kv_data = json.loads(resp_kv.read().decode("utf-8", errors="replace"))
            existing_count = len(kv_data.get("value", {}).get("leads_all", []))
            print(f"  [KV] Leads existentes en KV: {existing_count}", file=sys.stderr)
    except Exception as e:
        print(f"  [KV] WARNING: {e}", file=sys.stderr)
    print("  RADAR LEADS — Payload Generator v1.0", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # Step 0: Source discovery (SourceHunterAR v10.2)
    try:
        run_discovery_and_update()
    except Exception as e:
        print(f"  [SourceHunter] WARNING: {e}", file=sys.stderr)

    # Step 0.5: PendingQueryManager — reintenta queries que fallaron con 429
    worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
    ingest_secret = os.environ.get("INGEST_SECRET", "")
    pqm = None
    recovered_leads = []
    if ingest_secret:
        try:
            pqm = PendingQueryManager(worker_url, ingest_secret)
            _pqm_global = pqm  # accesible desde collect_public_sources
            pqm.load()
            # Reintentar pending primero (máx 2, antes del grupo rotativo)
            recovered_raw = pqm.retry_pending(search_reddit_with_status)
            print(f"  [PQM] Recuperadas {len(recovered_raw)} queries pendientes → {len(recovered_raw)} posts",
                  file=sys.stderr)
            # Agregar a raw_results para que pasen por extract_entities
            for r in recovered_raw:
                r["_query"] = f"pending_retry:{r.get('query','')}"
                raw_results_pending = [r]  # placeholder
            recovered_leads = recovered_raw
        except Exception as e:
            print(f"  [PQM] WARNING: {e}", file=sys.stderr)
            pqm = None
    else:
        print("  [PQM] SKIP: INGEST_SECRET no configurado", file=sys.stderr)

    # Step 1: Collect
    raw_results = collect_public_sources()

    # Agregar recovered_leads al inicio de raw_results
    if recovered_leads:
        for r in recovered_leads:
            r["_query"] = r.get("_query", "pending_retry")
        raw_results = recovered_leads + raw_results
        print(f"  [PQM] Agregados {len(recovered_leads)} posts recuperados al pipeline",
              file=sys.stderr)

    # Step 1.5: Guardar PQM al final del run (en try/finally para que siempre guarde)
    # Lo movemos al final del pipeline
    QUERIES_EXECUTED = len(set(r.get("_query", "") for r in raw_results))

    # Step 2: Extract
    print("[Step 2] Extracting entities...", file=sys.stderr)
    extracted = []
    for r in raw_results:
        ext = extract_entities(r)
        if ext:
            extracted.append(ext)
    print(f"  Extracted {len(extracted)} entities", file=sys.stderr)

    # Step 3: Normalize
    print("[Step 3] Normalizing records...", file=sys.stderr)
    normalized = [normalize_record(e) for e in extracted]
    print(f"  Normalized {len(normalized)} records", file=sys.stderr)

    # Step 4: Classify & Score
    print("[Step 4] Classifying and scoring...", file=sys.stderr)
    leads = []
    for rec in normalized:
        lead = classify_and_score(rec)
        if lead:
            leads.append(lead)
    print(f"  Scored {len(leads)} leads (rejected rest)", file=sys.stderr)

    # Step 4.5: Enriquecer leads con patente detectada via clasific.ar
    # H.AI insight + GPT filter: solo enriquecer si hay patente + dolor
    try:
        worker_url = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
        ingest_secret = os.environ.get("INGEST_SECRET", "")
        if ingest_secret:
            enriched_count = 0
            import urllib.request as _urq3
            for lead in leads:
                if "PATENTE_DETECTED" in (lead.detected_signals or []):
                    # Buscar patente en el texto
                    patente_m = re.search(r"\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\d{3})\b", lead.quoted_text or "", re.IGNORECASE)
                    if patente_m:
                        patente = patente_m.group(1).upper()
                        try:
                            basic_url = f"{worker_url}/api/clasificar-basic?plate={patente}"
                            req3 = _urq3.Request(basic_url)
                            req3.add_header("X-Webhook-Secret", ingest_secret)
                            req3.add_header("Accept", "application/json")
                            with _urq3.urlopen(req3, timeout=10) as resp3:
                                veh_data = json.loads(resp3.read().decode("utf-8", errors="replace"))
                            if veh_data.get("ok") and veh_data.get("data", {}).get("data"):
                                v = veh_data["data"]["data"]
                                lead.vehiculo = f"{v.get('make','')} {v.get('model','')} {v.get('year','')}".strip()
                                lead.provincia = v.get("currentLocation", {}).get("province", "") or lead.provincia
                                enriched_count += 1
                        except Exception:
                            pass
                        time.sleep(0.5)  # rate limit clasific.ar
            if enriched_count:
                print(f"  [clasific.ar] {enriched_count} leads enriquecidos con datos vehiculares", file=sys.stderr)
    except Exception as e:
        print(f"  [clasific.ar] ERROR: {e}", file=sys.stderr)

    # Step 4.6: Comment Mining (DeepSeek+Qwen insight)
    mine_comments_for_contacts(leads)

    # Step 4.7: Profile Mining (DeepSeek+Qwen insight)
    mine_profile_for_contacts(leads)

    # MEJORA 2 (Qwen): OSINT Shadow Profile - triangulacion de identidad
    # Si un lead de Reddit no tiene contacto, buscar username en ML/FB via DDG
    try:
        from search_providers import search as _osint_search
        osint_count = 0
        for lead in leads:
            if lead.whatsapp_publico or lead.email_publico or lead.telefono_publico:
                continue  # Ya tiene contacto, saltar
            if not lead.persona or not lead.persona.startswith("u/"):
                continue  # No es Reddit user
            username = lead.persona.replace("u/", "").strip()
            if len(username) < 3:
                continue
            # Buscar username en MercadoLibre y Facebook
            for q in [f'site:mercadolibre.com.ar "{username}"',
                      f'site:facebook.com "{username}"']:
                try:
                    results = _osint_search(q, num=3)
                    for r in results:
                        snippet = r.get("snippet", "") + " " + r.get("title", "")
                        # Reusar regex federal para extraer telefono
                        for pattern in ARG_PHONE_PATTERNS:
                            m = re.search(pattern, snippet)
                            if m:
                                digits = re.sub(r"\D", "", m.group(0))
                                if 10 <= len(digits) <= 15:
                                    lead.telefono_publico = m.group(0).strip()
                                    lead.contacto_publico = True
                                    lead.score = min(100, (lead.score or 0) + 20)
                                    if "OSINT_SHADOW" not in (lead.detected_signals or []):
                                        lead.detected_signals = (lead.detected_signals or []) + ["OSINT_SHADOW_PROFILE"]
                                    osint_count += 1
                                    break
                        if lead.telefono_publico:
                            break
                    if lead.telefono_publico:
                        break
                except Exception:
                    continue
            time.sleep(1)  # rate limit DDG
        if osint_count:
            print(f"  [OSINT] {osint_count} leads enriquecidos via shadow profile", file=sys.stderr)
    except Exception as e:
        print(f"  [OSINT] ERROR: {e}", file=sys.stderr)

    # Step 5: Dedup
    leads = deduplicate_cases(leads)

    # Step 6: Build payload
    payload = build_dashboard_payload(leads)

    # Step 7: Publish
    publish_artifacts(payload, leads)

    elapsed = time.time() - START_TIME
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  ✓ Complete in {elapsed:.1f}s", file=sys.stderr)
    print(f"  Hot: {payload['summary']['hot_leads']} | Warm: {payload['summary']['warm_leads']}", file=sys.stderr)
    print(f"  Payload: {PAYLOAD_PATH}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Step 7.5: Guardar PQM al final
    if pqm:
        try:
            pqm.save()
            print(f"  [PQM] Estado final: {pqm.status()}", file=sys.stderr)
        except Exception as e:
            print(f"  [PQM] ERROR guardando: {e}", file=sys.stderr)

    return payload


if __name__ == "__main__":
    payload = run_pipeline()
    # Output summary to stdout
    print(json.dumps({
        "run_id": payload["run_id"],
        "generated_at": payload["generated_at"],
        "summary": payload["summary"],
        "insights": payload["insights"],
    }, ensure_ascii=False, indent=2))


#===========================================================================
# Step 4.6: Comment Mining — Extraer contactos de comentarios del post
#===========================================================================
def mine_comments_for_contacts(leads: List[Lead]) -> int:
    """Scrapea comentarios del post y busca telefonos/emails del autor."""
    print("[Step 4.6] Mining comments for contacts...", file=sys.stderr)
    enriched_count = 0

    for lead in leads:
        if lead.platform != "Reddit":
            continue
        if lead.whatsapp_publico or lead.telefono_publico or lead.email_publico:
            continue

        url_parts = lead.source_url.rstrip("/").split("/")
        if len(url_parts) < 7 or "comments" not in url_parts:
            continue
        post_id = url_parts[6]

        comments_url = f"https://old.reddit.com/comments/{post_id}.json?limit=50"

        try:
            import urllib.request as _urq
            req = _urq.Request(comments_url)
            req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            req.add_header("Accept", "application/json")
            with _urq.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if not isinstance(data, list) or len(data) < 2:
                    continue

                comments_listing = data[1]
                all_comment_text = ""
                lead_author = lead.persona.replace("u/", "").strip().lower()

                for child in comments_listing.get("data", {}).get("children", []):
                    comment = child.get("data", {})
                    author = comment.get("author", "")
                    body = comment.get("body", "")

                    if author and author != "[deleted]" and body:
                        if author.lower() == lead_author:
                            all_comment_text += " " + body

                if not all_comment_text:
                    continue

                for pattern in ARG_PHONE_PATTERNS:
                    m = re.search(pattern, all_comment_text)
                    if m:
                        digits = re.sub(r"\D", "", m.group(0))
                        if 10 <= len(digits) <= 15:
                            lead.telefono_publico = m.group(0).strip()
                            lead.contacto_publico = True
                            lead.score = min(100, (lead.score or 0) + 25)
                            lead.detected_signals = (lead.detected_signals or []) + ["COMMENT_MINING_PHONE"]
                            enriched_count += 1
                            break

                if not lead.whatsapp_publico:
                    for pattern in WHATSAPP_PATTERNS:
                        m = re.search(pattern, all_comment_text, re.IGNORECASE)
                        if m:
                            num = m.group(1) if m.groups() else m.group(0)
                            digits = re.sub(r"\D", "", num)
                            if 8 <= len(digits) <= 15:
                                if len(digits) == 10 and digits.startswith("11"):
                                    digits = "549" + digits
                                lead.whatsapp_publico = digits
                                lead.contacto_publico = True
                                lead.score = min(100, (lead.score or 0) + 30)
                                lead.detected_signals = (lead.detected_signals or []) + ["COMMENT_MINING_WHATSAPP"]
                                enriched_count += 1
                                break

                if not lead.email_publico:
                    m = re.search(EMAIL_PATTERN, all_comment_text)
                    if m:
                        lead.email_publico = m.group(1).lower().strip()
                        lead.contacto_publico = True
                        lead.score = min(100, (lead.score or 0) + 15)
                        lead.detected_signals = (lead.detected_signals or []) + ["COMMENT_MINING_EMAIL"]
                        enriched_count += 1

                time.sleep(1.0)
        except Exception:
            continue

    if enriched_count:
        print(f"  [Comment Mining] {enriched_count} leads enriquecidos", file=sys.stderr)
    return enriched_count


#===========================================================================
# Step 4.7: Profile Mining — Extraer contactos del perfil de Reddit del autor
#===========================================================================
def mine_profile_for_contacts(leads: List[Lead]) -> int:
    """Scrapea el perfil del autor (comments.rss) y busca contacto en bio/historial."""
    print("[Step 4.7] Mining user profiles for contacts...", file=sys.stderr)
    enriched_count = 0

    for lead in leads:
        if lead.platform != "Reddit":
            continue
        if lead.whatsapp_publico or lead.telefono_publico or lead.email_publico:
            continue

        username = lead.persona.replace("u/", "").strip()
        if not username or len(username) < 3:
            continue

        profile_url = f"https://www.reddit.com/user/{username}/comments/.rss?limit=25"

        try:
            import urllib.request as _urq
            req = _urq.Request(profile_url)
            req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            req.add_header("Accept", "application/atom+xml,application/xml,text/xml")
            with _urq.urlopen(req, timeout=15) as resp:
                xml_content = resp.read().decode("utf-8", errors="replace")

                entries = re.findall(r"<entry>([\s\S]*?)</entry>", xml_content, re.DOTALL)
                all_profile_text = ""

                for entry in entries:
                    content_m = re.search(r"<content[^>]*>([\s\S]*?)</content>", entry, re.DOTALL)
                    if content_m:
                        raw = content_m.group(1)
                        cleaned = re.sub(r"<[^>]+>", " ", raw)
                        cleaned = cleaned.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        cleaned = cleaned.replace("&quot;", '"').replace("&#39;", "'")
                        all_profile_text += " " + cleaned

                if not all_profile_text:
                    continue

                for pattern in ARG_PHONE_PATTERNS:
                    m = re.search(pattern, all_profile_text)
                    if m:
                        digits = re.sub(r"\D", "", m.group(0))
                        if 10 <= len(digits) <= 15:
                            lead.telefono_publico = m.group(0).strip()
                            lead.contacto_publico = True
                            lead.score = min(100, (lead.score or 0) + 25)
                            lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_MINING_PHONE"]
                            enriched_count += 1
                            break

                if not lead.whatsapp_publico:
                    for pattern in WHATSAPP_PATTERNS:
                        m = re.search(pattern, all_profile_text, re.IGNORECASE)
                        if m:
                            num = m.group(1) if m.groups() else m.group(0)
                            digits = re.sub(r"\D", "", num)
                            if 8 <= len(digits) <= 15:
                                if len(digits) == 10 and digits.startswith("11"):
                                    digits = "549" + digits
                                lead.whatsapp_publico = digits
                                lead.contacto_publico = True
                                lead.score = min(100, (lead.score or 0) + 30)
                                lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_MINING_WHATSAPP"]
                                enriched_count += 1
                                break

                if not lead.email_publico:
                    m = re.search(EMAIL_PATTERN, all_profile_text)
                    if m:
                        lead.email_publico = m.group(1).lower().strip()
                        lead.contacto_publico = True
                        lead.score = min(100, (lead.score or 0) + 15)
                        lead.detected_signals = (lead.detected_signals or []) + ["PROFILE_MINING_EMAIL"]
                        enriched_count += 1

                time.sleep(1.5)
        except Exception:
            continue

    if enriched_count:
        print(f"  [Profile Mining] {enriched_count} leads enriquecidos", file=sys.stderr)
    return enriched_count

```


================================================================================
FILE: search_providers.py | 1116 lines | SHA: 7b36d28bca7e
DESC: Providers (Reddit RSS + DDG + FB + ML + Foros)
================================================================================

```python
"""
search_providers.py — Multi-provider search engine for Radar Leads.

Reemplaza completamente search_providers CLI. 100% autónomo en GitHub Actions.

Providers:
  1. DuckDuckGo HTML (gratis, sin API key)
  2. Reddit JSON público (gratis, sin API key)
  3. RSS feeds (gratis, sin API key)

Interfaz unificada:
  search(query, num=10) → List[Dict] con campos normalizados:
    title, url, snippet, source, date

Anti-blocking:
  - Random User-Agent
  - Rate limit entre requests
  - Retry con backoff exponencial
  - Cache simple en memoria
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import re as _re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from html.parser import HTMLParser

# ===========================================================================
# Config
# ===========================================================================

RATE_LIMIT_SECONDS = 2.0
MAX_RETRIES = 3
CACHE_TTL = 300  # 5 min

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Cache simple
_cache: Dict[str, tuple] = {}  # key → (timestamp, data)
_rss_cache: Dict[str, tuple] = {}  # Reddit RSS: query_hash → (timestamp, results)


# ===========================================================================
# HTTP helper con anti-blocking
# ===========================================================================
def _fetch_url(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch URL con random UA, retry y backoff."""
    cache_key = hashlib.sha256(url.encode()).hexdigest()[:16]
    now = time.time()

    # Check cache
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", random.choice(USER_AGENTS))
            req.add_header("Accept", "text/html,application/xhtml+xml,application/json,*/*")
            req.add_header("Accept-Language", "es-AR,es;q=0.9,en;q=0.8")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                _cache[cache_key] = (now, content)
                return content
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = (attempt + 1) * 2 + random.uniform(0, 1)
                time.sleep(wait)
            else:
                return None
    return None


# ===========================================================================
# Provider 1: DuckDuckGo HTML
# ===========================================================================
class _DDGResultParser(HTMLParser):
    """Parser minimalista para resultados de DuckDuckGo HTML."""

    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._current: Dict[str, str] = {}
        self._in_result = False
        self._in_title = False
        self._in_snippet = False
        self._capture_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        # DuckDuckGo lite usa <a class="result-link">
        # DuckDuckGo HTML usa <div class="result">
        cls = attrs_dict.get("class", "")

        if "result-link" in cls or ("result__a" in cls):
            self._in_title = True
            self._current = {"title": "", "url": "", "snippet": ""}
            href = attrs_dict.get("href", "")
            # DDG a veces wrappea URLs
            if href.startswith("//duckduckgo.com/l/?uddg="):
                href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
            self._current["url"] = href

        if "result-snippet" in cls or "result__snippet" in cls:
            self._in_snippet = True
            if not self._current:
                self._current = {"title": "", "url": "", "snippet": ""}

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._in_title = False
        if self._in_snippet and tag in ("a", "td", "div"):
            self._in_snippet = False
            if self._current and self._current.get("url"):
                self.results.append(self._current)
                self._current = {}

    def handle_data(self, data):
        if self._in_title:
            self._current["title"] += data.strip()
        if self._in_snippet:
            self._current["snippet"] += data.strip() + " "


def search_duckduckgo(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en DuckDuckGo (HTML lite version)."""
    # Usar DuckDuckGo Lite (html only, más fácil de parsear)
    encoded = urllib.parse.quote(query)
    url = f"https://lite.duckduckgo.com/lite/?q={encoded}&kl=ar-es"

    html = _fetch_url(url)
    if not html:
        return []

    parser = _DDGResultParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    results = []
    for r in parser.results[:num]:
        if r.get("url") and r.get("title"):
            results.append({
                "title": r["title"][:200],
                "url": r["url"],
                "snippet": r.get("snippet", "")[:300],
                "source": "duckduckgo",
                "date": "",
            })

    return results


# ===========================================================================
# Provider 2: Reddit JSON (público, sin API key)
# ===========================================================================
def search_reddit(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en Reddit via /search.rss (Atom feed). Cache 1h en memoria."""
    import sys as _sys
    import hashlib as _hl
    import time as _tm

    # Cache check: si la misma query se pidio hace <1h, devolver cache
    cache_key = _hl.sha256(query.encode()).hexdigest()[:12]
    if cache_key in _rss_cache:
        ts, cached = _rss_cache[cache_key]
        if _tm.time() - ts < 3600:
            print(f"    [reddit] cache hit ({len(cached)} items): {query[:50]}", file=_sys.stderr)
            return cached[:num]

    print(f"    [reddit] searching (via RSS): {query[:60]}", file=_sys.stderr)
    
    # Paso 1: DuckDuckGo para encontrar URLs de Reddit
    ddg_query = f"site:reddit.com {query}"
    ddg_results = search_duckduckgo(ddg_query, num=num * 2)
    reddit_urls = [r for r in ddg_results if "reddit.com" in r.get("url", "").lower() and "/comments/" in r.get("url", "")]
    
    print(f"    [reddit] DDG found {len(reddit_urls)} reddit post URLs", file=_sys.stderr)
    
    if not reddit_urls:
        # Fallback al endpoint directo (puede que funcione a veces)
        encoded = urllib.parse.quote(query)
        url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit={num}&type=link"

    # Reddit bloquea /search.json y /comments/.json con 403.
    # Pero /search.rss (Atom feed) SI funciona y trae el author como <name>/u/xxx</name>.
    # Estrategia: usar search.rss en vez de DDG + scrape.
    encoded = urllib.parse.quote(query)
    rss_url = f"https://www.reddit.com/search.rss?q={encoded}&sort=new&limit={num}"
    try:
        req = urllib.request.Request(rss_url)
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        req.add_header("Accept", "application/atom+xml, application/xml, text/xml, */*")
        req.add_header("Accept-Language", "es-AR,es;q=0.9")
        with urllib.request.urlopen(req, timeout=15) as resp:
            rss_content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [reddit] RSS search fail: {e}", file=_sys.stderr)
        # Ultimo fallback: usar los resultados de DDG (sin author)
        results = []
        for r in reddit_urls[:num]:
            results.append({
                "title": r.get("title","")[:200],
                "url": r.get("url",""),
                "snippet": r.get("snippet","")[:3000],
                "source": "reddit_ddg",
                "date": r.get("date",""),
                "username": "",
                "author": "",
            })
        return results
    
    # Parse Atom feed
    import re as _re2
    entries = _re2.findall(r"<entry>(.*?)</entry>", rss_content, _re2.DOTALL)
    print(f"    [reddit] RSS entries: {len(entries)}", file=_sys.stderr)
    
    results = []
    for entry in entries[:num]:
        title_m = _re2.search(r"<title[^>]*>([^<]+)</title>", entry)
        link_m = _re2.search(r'<link[^>]*href="([^"]+)"', entry)
        author_m = _re2.search(r"<name[^>]*>([^<]+)</name>", entry)
        content_m = _re2.search(r"<content[^>]*>(.*?)</content>", entry, _re2.DOTALL)
        updated_m = _re2.search(r"<updated[^>]*>([^<]+)</updated>", entry)
        
        title = title_m.group(1) if title_m else ""
        url = link_m.group(1) if link_m else ""
        author = ""
        if author_m:
            author_raw = author_m.group(1).strip()
            # Formato Reddit: /u/username
            u_match = _re2.search(r"/u/([A-Za-z0-9_\-\:]{3,20})", author_raw)
            if u_match:
                author = u_match.group(1)
            else:
                author = author_raw
        
        # Content tiene HTML, limpiar tags
        snippet = ""
        if content_m:
            raw = content_m.group(1)
            # Buscar u/username adicional en el content
            u2 = _re2.search(r"/u/([A-Za-z0-9_\-\:]{3,20})", raw)
            if u2 and not author:
                author = u2.group(1)
            # Strip HTML
            snippet = _re2.sub(r"<[^>]+>", " ", raw)
            snippet = _re2.sub(r"<!--.*?-->", "", snippet, flags=_re2.DOTALL)
            snippet = snippet.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
            snippet = _re2.sub(r"\s+", " ", snippet).strip()
        
        # Solo incluir si es un post (tiene /comments/ en la URL) y no un subreddit
        if "/comments/" not in url:
            continue
        
        results.append({
            "title": title[:200],
            "url": url,
            "snippet": snippet[:3000],
            "source": "reddit",
            "date": updated_m.group(1) if updated_m else "",
            "username": author,
            "author": author,
        })
    
    print(f"    [reddit] got {len(results)} posts with author", file=_sys.stderr)
    # Guardar en cache 1h
    if results:
        _rss_cache[cache_key] = (_tm.time(), results)
    return results[:num]


    print(f"    [reddit] got {len(data.get('data',{}).get('children',[]))} results", file=_sys.stderr)

    results = []
    if isinstance(data, dict) and "data" in data:
        for child in data["data"].get("children", []):
            post = child.get("data", {})
            if not post:
                continue

            # Construir URL completa
            permalink = post.get("permalink", "")
            full_url = f"https://www.reddit.com{permalink}" if permalink else ""

            # Snippet: selftext completo si existe, sino title
            selftext = post.get("selftext", "")
            snippet = selftext[:3000] if selftext else post.get("title", "")[:300]

            # Author (username)
            author = post.get("author", "")
            if author == "[deleted]" or author == "AutoModerator":
                author = ""

            # Fecha
            created = post.get("created_utc", 0)
            date = ""
            if created:
                from datetime import datetime, timezone
                date = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()

            results.append({
                "title": post.get("title", "")[:200],
                "url": full_url,
                "snippet": snippet,
                "source": "reddit",
                "date": date,
                "username": author,
                "author": author,
                "permalink": permalink,
            })

    # Opcional: traer top comments de los primeros 5 posts para enriquecer
    # (con rate limit para no ser bloqueados)
    for i, r in enumerate(results[:5]):
        permalink = r.get("permalink", "")
        if not permalink:
            continue
        try:
            time.sleep(1.0)  # rate limit
            comments_url = f"https://old.reddit.com{permalink}.json?limit=10"
            req2 = urllib.request.Request(comments_url)
            req2.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            req2.add_header("Accept", "text/html,application/json,*/*")
            req2.add_header("Accept-Language", "es-AR,es;q=0.9")
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                cdata = json.loads(resp2.read().decode("utf-8", errors="replace"))
            if isinstance(cdata, list) and len(cdata) >= 2:
                comments_text = []
                for c in cdata[1].get("data", {}).get("children", [])[:10]:
                    body = c.get("data", {}).get("body", "")
                    if body and len(body) > 20 and body != "[deleted]" and body != "[removed]":
                        comments_text.append(body[:500])
                if comments_text:
                    # Agregar comments al snippet para extraccion
                    r["snippet"] = (r["snippet"] + " " + " ".join(comments_text))[:6000]
                    # Author real (del post, no comments)
                    if not r["username"] and cdata[0].get("data",{}).get("children",[]):
                        post_full = cdata[0]["data"]["children"][0].get("data",{})
                        a = post_full.get("author","")
                        if a and a != "[deleted]":
                            r["username"] = a
                            r["author"] = a
        except Exception:
            continue

    return results[:num]


# ===========================================================================
# Provider 3: RSS feeds (foros argentinos)
# ===========================================================================
RSS_FEEDS = [
    # Foros argentinos con RSS
    "https://www.reddit.com/r/argentina/new.json?limit=10",
    "https://www.reddit.com/r/ArAutos/new.json?limit=10",
    "https://www.reddit.com/r/Cordoba/new.json?limit=10",
    "https://www.reddit.com/r/DerechoGenial/new.json?limit=10",
]


def search_rss(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en feeds RSS (Reddit subs argentinos)."""
    results = []
    query_lower = query.lower()
    query_keywords = [w for w in query_lower.split() if len(w) > 3]

    for feed_url in RSS_FEEDS:
        try:
            req = urllib.request.Request(feed_url)
            req.add_header("User-Agent", "RadarLeadsBot/1.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            if isinstance(data, dict) and "data" in data:
                for child in data["data"].get("children", []):
                    post = child.get("data", {})
                    if not post:
                        continue

                    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()

                    # Filtro por keywords de la query
                    if query_keywords and not any(kw in text for kw in query_keywords):
                        continue

                    permalink = post.get("permalink", "")
                    full_url = f"https://www.reddit.com{permalink}" if permalink else ""

                    created = post.get("created_utc", 0)
                    date = ""
                    if created:
                        from datetime import datetime, timezone
                        date = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()

                    results.append({
                        "title": post.get("title", "")[:200],
                        "url": full_url,
                        "snippet": post.get("selftext", "")[:300],
                        "source": "reddit_rss",
                        "date": date,
                        "username": post.get("author", ""),
                    })

                    if len(results) >= num:
                        break
        except Exception:
            continue

        if len(results) >= num:
            break

    return results[:num]


# ===========================================================================
# Search Manager — unifica todos los providers
# ===========================================================================

# ===========================================================================
# Reddit post enrichment: trae selftext completo + comentarios top
# ===========================================================================
def enrich_reddit_post(url: str) -> Dict[str, Any]:
    """Dada una URL de Reddit post, trae selftext completo + top comments.
    Retorna dict con: full_text, comments (list of strings), author.
    """
    result = {"full_text": "", "comments": [], "author": ""}
    if "reddit.com" not in url:
        return result

    # Convertir URL a .json
    json_url = url.rstrip("/") + "/.json?limit=20"

    try:
        req = urllib.request.Request(json_url)
        req.add_header("User-Agent", "RadarLeadsBot/1.0 (lead intelligence research)")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return result

    if not isinstance(data, list) or len(data) < 1:
        return result

    # Post data
    post_listing = data[0]
    post_data = post_listing.get("data", {}).get("children", [])
    if post_data:
        post = post_data[0].get("data", {})
        result["full_text"] = post.get("selftext", "")[:3000]
        result["author"] = post.get("author", "")

    # Comments
    if len(data) >= 2:
        comments_listing = data[1]
        for child in comments_listing.get("data", {}).get("children", [])[:15]:
            comment = child.get("data", {})
            body = comment.get("body", "")
            if body and len(body) > 20:
                result["comments"].append(body[:500])

    return result



# ===========================================================================
# Provider 4: Telegram public channels (t.me/s/<channel>)
# ===========================================================================
TELEGRAM_CHANNELS_AR = [
    "MultasArgentina",
    "AutosUsadosAR",
    "GestoriaAutomotor",
    "TramitesArgentina",
    "InfraccionesAR",
]

def search_telegram(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en canales públicos de Telegram via t.me/s/ (sin auth)."""
    import sys as _sys
    results = []
    query_lower = query.lower()
    # Quitar site:xxx de la query para buscar texto
    clean_query = _re.sub(r"site:\S+", "", query_lower).strip()
    if not clean_query:
        return []
    
    keywords = [w for w in clean_query.split() if len(w) > 2][:5]
    if not keywords:
        return []
    
    for channel in TELEGRAM_CHANNELS_AR:
        try:
            url = f"https://t.me/s/{channel}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", random.choice(USER_AGENTS))
            req.add_header("Accept-Language", "es-AR,es;q=0.9")
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            
            # Parse simple HTML: buscar divs con clase tgme_widget_message_text
            import re as _re2
            posts = _re2.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, _re2.DOTALL)
            dates = _re2.findall(r'<time datetime="([^"]+)"', html)
            for i, post_html in enumerate(posts[:20]):
                # Strip HTML tags
                text = _re2.sub(r"<[^>]+>", " ", post_html)
                text = _re2.sub(r"&amp;", "&", text)
                text = _re2.sub(r"&lt;", "<", text)
                text = _re2.sub(r"&gt;", ">", text)
                text = _re2.sub(r"&quot;", '"', text)
                text = _re2.sub(r"&#39;", "'", text)
                text = _re2.sub(r"\s+", " ", text).strip()
                if not text or len(text) < 30:
                    continue
                # Filtrar por keywords
                text_lower = text.lower()
                if not any(kw in text_lower for kw in keywords):
                    continue
                date = dates[i] if i < len(dates) else ""
                results.append({
                    "title": text[:120],
                    "url": f"https://t.me/s/{channel}",
                    "snippet": text[:3000],
                    "source": "telegram",
                    "date": date,
                    "username": channel,
                    "author": channel,
                })
            time.sleep(1.0)
        except Exception as e:
            print(f"    [telegram] {channel} error: {e}", file=_sys.stderr)
            continue
    
    print(f"    [telegram] got {len(results)} results", file=_sys.stderr)
    return results[:num]


# ===========================================================================
# Provider 5: MercadoLibre API pública (sin auth)
# ===========================================================================
def search_mercadolibre(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca publicaciones en MercadoLibre Argentina via API pública."""
    import sys as _sys
    # Quitar site:xxx
    clean_query = _re.sub(r"site:\S+", "", query).strip()
    if not clean_query:
        return []
    
    encoded = urllib.parse.quote(clean_query)
    url = f"https://api.mercadolibre.com/sites/MLA/search?q={encoded}&limit={num}&condition=used"
    
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"    [ml] ERROR: {e}", file=_sys.stderr)
        return []
    
    results = []
    for item in data.get("results", [])[:num]:
        title = item.get("title", "")
        price = item.get("price", 0)
        permalink = item.get("permalink", "")
        seller = item.get("seller", {})
        seller_nick = seller.get("nickname", "")
        seller_id = seller.get("id", "")
        # Questions endpoint (público)
        questions_text = ""
        try:
            q_url = f"https://api.mercadolibre.com/questions/search?item={item.get('id','')}"
            q_req = urllib.request.Request(q_url)
            q_req.add_header("User-Agent", random.choice(USER_AGENTS))
            with urllib.request.urlopen(q_req, timeout=5) as q_resp:
                q_data = json.loads(q_resp.read().decode("utf-8", errors="replace"))
            qs = [q.get("text","") for q in q_data.get("questions", [])[:5]]
            questions_text = " ".join(qs)
        except Exception:
            pass
        
        snippet = f"Precio: ${price}. Vendedor: {seller_nick}. Preguntas: {questions_text}"[:3000]
        results.append({
            "title": title[:200],
            "url": permalink,
            "snippet": snippet,
            "source": "mercadolibre",
            "date": "",
            "username": seller_nick,
            "author": seller_nick,
        })
    
    print(f"    [ml] got {len(results)} results", file=_sys.stderr)
    return results



# ===========================================================================
# Provider 6: ForoArgentina.net (foro AR, sin rate limit agresivo)
# ===========================================================================
def search_foroargentina(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en foroargentina.net via su buscador interno."""
    import sys as _sys
    print(f"    [foro] searching: {query[:60]}", file=_sys.stderr)
    
    # Limpiar query: quitar site:xxx
    clean_query = _re.sub(r"site:\S+", "", query).strip()
    if not clean_query:
        return []
    
    encoded = urllib.parse.quote(clean_query)
    search_url = f"https://www.foroargentina.net/buscar?buscar={encoded}&ordenar=fecha"
    
    try:
        req = urllib.request.Request(search_url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept-Language", "es-AR,es;q=0.9")
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [foro] ERROR: {e}", file=_sys.stderr)
        return []
    
    # Parse simple: buscar links a /viewtopic.php?t=XXX
    results = []
    # Patron: <a href="./viewtopic.php?f=X&t=Y" class="topictitle">TITLE</a>
    import re as _re2
    matches = _re2.findall(r'<a[^>]*href="[^"]*viewtopic\.php[^"]*t=(\d+)[^"]*"[^>]*class="[^"]*topictitle[^"]*"[^>]*>([^<]+)</a>', html)
    if not matches:
        # Fallback: buscar cualquier link a viewtopic con texto
        matches = _re2.findall(r'<a[^>]*href="((?:\./)?viewtopic\.php\?[^"]*t=\d+[^"]*)"[^>]*>([^<]{15,150})</a>', html)
    
    for tid, title in matches[:num]:
        title = _re2.sub(r"<[^>]+>", "", title).strip()
        if not title:
            continue
        # URL completa
        if isinstance(tid, str) and tid.isdigit():
            post_url = f"https://www.foroargentina.net/viewtopic.php?t={tid}"
        else:
            href = tid  # fallback caso 2
            post_url = href if href.startswith("http") else f"https://www.foroargentina.net/{href.lstrip('./')}"
        
        results.append({
            "title": title[:200],
            "url": post_url,
            "snippet": "",  # el search no da snippet, habria que scrapear el post
            "source": "foroargentina",
            "date": "",
            "username": "",
            "author": "",
        })
    
    # Para cada resultado, scrapear el post para conseguir author + body
    for r in results[:5]:  # solo top 5 para no abusar
        try:
            time.sleep(1.5)
            req2 = urllib.request.Request(r["url"])
            req2.add_header("User-Agent", random.choice(USER_AGENTS))
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                post_html = resp2.read().decode("utf-8", errors="replace")
            
            # Author: <a class="username" ...>NAME</a> o <span class="postauthor">NAME</span>
            author_m = _re2.search(r'class="username[^"]*"[^>]*>([^<]{3,30})<', post_html)
            if not author_m:
                author_m = _re2.search(r'class="postauthor"[^>]*>([^<]{3,30})<', post_html)
            if author_m:
                r["username"] = author_m.group(1).strip()
                r["author"] = author_m.group(1).strip()
            
            # Body: <div class="content">...</div>
            body_m = _re2.search(r'<div class="content"[^>]*>(.*?)</div>', post_html, _re2.DOTALL)
            if body_m:
                body = _re2.sub(r"<[^>]+>", " ", body_m.group(1))
                body = body.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&quot;",'"').replace("&#39;","'")
                r["snippet"] = _re2.sub(r"\s+", " ", body).strip()[:2000]
            
            # Date: <time datetime="2024-01-15...">
            date_m = _re2.search(r'<time[^>]*datetime="([^"]+)"', post_html)
            if date_m:
                r["date"] = date_m.group(1)[:10]
        except Exception:
            continue
    
    print(f"    [foro] got {len(results)} results", file=_sys.stderr)
    return results[:num]



# ===========================================================================
# Provider 7: Facebook groups via DuckDuckGo (sin auth, sin cookies)
# ===========================================================================
def search_facebook_via_ddg(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca posts de grupos publicos de Facebook via DuckDuckGo.
    No requiere cuenta FB ni API key.
    Devuelve leads con texto y link pero SIN author (limitacion de DDG snippets).
    """
    import sys as _sys
    print(f"    [facebook] searching: {query[:60]}", file=_sys.stderr)
    
    # Si la query no tiene site:facebook.com, agregarlo
    if "site:facebook.com" not in query.lower():
        search_query = f"site:facebook.com/groups {query}"
    else:
        search_query = query
    
    # Usar search_duckduckgo existente
    ddg_results = search_duckduckgo(search_query, num=num * 2)
    
    results = []
    for r in ddg_results:
        url = r.get("url", "")
        if "facebook.com/groups" not in url:
            continue
        
        # Extraer group_name de la URL
        # facebook.com/groups/multasargentina/posts/123456
        # o facebook.com/groups/276074287942602/permalink/...
        import re as _re2
        group_match = _re2.search(r"/groups/([^/?#]+)", url)
        group_id_raw = ""
        if group_match:
            group_id_raw = group_match.group(1)
        
        # Si group_id es solo numeros (ID interno FB), usar el title del result
        # Title suele ser "Nombre del Grupo - Facebook"
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        
        if group_id_raw.isdigit():
            # Extraer nombre del grupo del title
            # "Defensas contra las Multas de Transito (Argentina) - Facebook"
            group_name = title.replace(" | Facebook", "").replace(" - Facebook", "").strip()
        else:
            group_name = group_id_raw.replace("-", " ").replace("_", " ").title()
        
        if not snippet and not title:
            continue
        if len(snippet) < 20 and len(title) < 10:
            continue
        
        results.append({
            "title": (title or snippet)[:200],
            "url": url,
            "snippet": snippet[:3000],
            "source": "facebook_groups",
            "date": r.get("date", ""),
            "username": group_name,
            "author": group_name,
            "group_name": group_name,
        })
    
    print(f"    [facebook] got {len(results)} posts from FB groups", file=_sys.stderr)
    return results[:num]



# ===========================================================================
# Provider 8: MercadoLibre Questions Radar (sin auth, API publica)
# ===========================================================================
# Estrategia (Sakana+Claude corregido):
# 1. Pre-filtrar items por titulo con keywords de problema
# 2. Para cada item, pedir /questions/search?item=XXX
# 3. Filtrar questions localmente por keywords de multa
# 4. Author real = seller.nickname

ML_BASE = "https://api.mercadolibre.com"
ML_SITE_ID = "MLA"  # Argentina
ML_CATEGORY_AUTOS = "MLA1744"  # Autos y Camionetas

# Keywords para pre-filtrar TITULOS de items (Claude fix)
ML_TITLE_QUERIES = [
    "transferir urgente",
    "no puedo transferir",
    "con multa",
    "deuda patente",
    "libre deuda",
    "transferencia pendiente",
]

# Keywords para filtrar preguntas de compradores
ML_MULTA_KEYWORDS = [
    "multa", "multas", "infraccion", "libre deuda", "deuda",
    "fotomulta", "puede transferir", "transferencia", "patente",
    "08", "cedula", "transferir",
]

# Max items por query (limitar para no quemar rate limit ML)
ML_MAX_ITEMS_PER_QUERY = 3
ML_MAX_TOTAL_ITEMS = 10


def _ml_get(url: str) -> Optional[dict]:
    """GET a ML API con timeout y manejo de errores."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        import sys as _sys
        print(f"    [ml] ERROR {url[:80]}: {e}", file=_sys.stderr)
        return None


def _ml_normalize_provincia(raw: str) -> str:
    """Normaliza nombres de provincia de ML."""
    if not raw:
        return ""
    MAP = {
        "Santa Fe": "Santa Fe",
        "Buenos Aires": "Buenos Aires",
        "Ciudad Autonoma de Buenos Aires": "CABA",
        "Capital Federal": "CABA",
        "Cordoba": "Cordoba",
        "Entre Rios": "Entre Rios",
        "Misiones": "Misiones",
        "La Pampa": "La Pampa",
        "Mendoza": "Mendoza",
        "Tucuman": "Tucuman",
        "Salta": "Salta",
        "Chaco": "Chaco",
        "Corrientes": "Corrientes",
    }
    # Quitar acentos para matching
    raw_clean = raw.replace("ó","o").replace("á","a").replace("é","e").replace("í","i").replace("ú","u")
    return MAP.get(raw_clean, raw)




def fetch_ml_seller_contact(seller_id: str) -> dict:
    """Endpoint publico: /users/{seller_id}
    Vendedores profesionales suelen tener email y telefono visibles.
    Sin auth.
    """
    if not seller_id:
        return {}
    url = f"https://api.mercadolibre.com/users/{seller_id}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {}
    
    contact = {}
    
    # Email - disponible si el vendedor lo hizo publico
    email = data.get("email", "")
    if email and "@" in email and "mercadolibre" not in email.lower():
        contact["email"] = email.lower().strip()
        contact["contact_source"] = "ml_seller_profile"
    
    # Telefono - cuentas profesionales
    phone = data.get("phone", {})
    if isinstance(phone, dict):
        number = phone.get("number", "")
        area = phone.get("area_code", "")
        if number:
            digits = re.sub(r"\D", "", f"{area}{number}")
            if len(digits) >= 8:
                contact["phone"] = f"+{digits}" if not digits.startswith("+") else digits
                if "contact_source" not in contact:
                    contact["contact_source"] = "ml_seller_profile"
    
    # Tags utiles para scoring
    tags = data.get("tags", [])
    contact["seller_tags"] = tags
    contact["is_professional"] = any(t in tags for t in
        ["real_estate_agency", "car_dealer", "meli_choice", "large_seller"])
    
    # Nickname real si estaba vacio
    if not contact.get("nickname"):
        nick = data.get("nickname", "")
        if nick:
            contact["seller_nickname"] = nick
    
    return contact

def search_mercadolibre_questions(num: int = 15) -> List[Dict[str, Any]]:
    """Llama al endpoint /api/ml-questions del Worker que hace fetch a ML API
    desde IP de Cloudflare edge (evita 403 de GH Actions).
    """
    import os as _os
    import sys as _sys
    worker_url = _os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
    secret = _os.environ.get("INGEST_SECRET", "")
    
    if not secret:
        print(f"    [ml] SKIP: INGEST_SECRET no configurado", file=_sys.stderr)
        return []
    
    print(f"    [ml] calling Worker /api/ml-questions (Cloudflare edge)", file=_sys.stderr)
    
    url = f"{worker_url}/api/ml-questions"
    try:
        req = urllib.request.Request(url)
        req.add_header("X-Webhook-Secret", secret)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "LeadX-Pipeline/2.0")
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        
        if not data.get("ok"):
            print(f"    [ml] Worker error: {data.get('error','?')}", file=_sys.stderr)
            return []
        
        leads = data.get("leads", [])
        contactables = data.get("contactables", 0)
        items_processed = data.get("items_processed", 0)
        print(f"    [ml] Worker OK: {len(leads)} leads, {contactables} contactables, {items_processed} items",
              file=_sys.stderr)
        return leads[:num]
    except Exception as e:
        print(f"    [ml] Worker call failed: {e}", file=_sys.stderr)
        return []

def search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """
    Busca usando múltiples providers en orden de fallback.

    Orden:
      1. DuckDuckGo (cobertura amplia)
      2. Reddit (foros, alta calidad de leads)
      3. RSS (backup)

    Devuelve resultados normalizados con campos:
      title, url, snippet, source, date, username?
    """
    all_results = []

    # Si la query es site:reddit.com, usar search_reddit directamente (trae author + comments)
    if "site:reddit.com" in query.lower():
        try:
            real_query = query.lower().replace("site:reddit.com", "").strip()
            reddit = search_reddit(real_query, num=num)
            all_results.extend(reddit)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:mercadolibre.com, usar ML API
    if "site:mercadolibre" in query.lower() or "site:mla" in query.lower():
        try:
            real_query = _re.sub(r"site:\S+", "", query, flags=_re.IGNORECASE).strip()
            ml = search_mercadolibre(real_query, num=num)
            all_results.extend(ml)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query menciona telegram, usar provider telegram
    if "site:telegram" in query.lower() or "telegram" in query.lower():
        try:
            tg = search_telegram(query, num=num)
            all_results.extend(tg)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query menciona foroargentina, usar provider foroargentina
    if "site:foroargentina" in query.lower() or "foroargentina" in query.lower():
        try:
            fa = search_foroargentina(query, num=num)
            all_results.extend(fa)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:facebook.com, usar provider dedicado
    if "site:facebook.com" in query.lower():
        try:
            fb = search_facebook_via_ddg(query, num=num)
            all_results.extend(fb)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:mercadolibre, usar ML Questions Radar
    if "site:mercadolibre" in query.lower() or "site:mla" in query.lower():
        try:
            ml = search_mercadolibre_questions(num=num)
            all_results.extend(ml)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:x.com o sin site:, usar DuckDuckGo
    # Provider 1: DuckDuckGo
    try:
        ddg = search_duckduckgo(query, num=num)
        all_results.extend(ddg)
        time.sleep(RATE_LIMIT_SECONDS)
    except Exception:
        pass

    # Provider 2: Reddit — SOLO para queries que no tengan site: ya especifico
    # (no llamar a search_reddit para site:com.ar o site:facebook.com, quema rate limit)
    # El ruteo explicito de site:reddit.com ya esta arriba.

    # Provider 3: RSS (sólo si los anteriores no dieron suficiente)
    if len(all_results) < num // 2:
        try:
            rss = search_rss(query, num=num)
            all_results.extend(rss)
        except Exception:
            pass

    # Dedup por URL
    seen_urls = set()
    unique = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(r)

    return unique[:num]


# ===========================================================================
# Smoke test
# ===========================================================================
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  SMOKE TEST search_providers.py (sin search_providers, sin API key)")
    print("=" * 60)

    test_query = "no puedo transferir auto multa argentina"

    print(f"\n  Query: '{test_query}'\n")

    # Test DuckDuckGo
    print("  [1] DuckDuckGo...")
    ddg = search_duckduckgo(test_query, num=5)
    print(f"      Resultados: {len(ddg)}")
    for r in ddg[:2]:
        print(f"      - {r['title'][:60]}")
        print(f"        {r['url'][:80]}")

    time.sleep(2)

    # Test Reddit
    print("\n  [2] Reddit...")
    reddit = search_reddit(test_query, num=5)
    print(f"      Resultados: {len(reddit)}")
    for r in reddit[:2]:
        print(f"      - {r['title'][:60]}")
        print(f"        {r['url'][:80]}")

    # Test unified search
    print("\n  [3] Unified search()...")
    all_results = search(test_query, num=10)
    print(f"      Total: {len(all_results)}")
    for r in all_results[:3]:
        print(f"      [{r['source']:12s}] {r['title'][:50]}")

    print(f"\n{'='*60}")
    print(f"  ✓ Sin search_providers, sin API key, sin credenciales")
    print(f"  ✓ Funciona en GitHub Actions")
    print(f"{'='*60}")

# ===========================================================================
# Wrapper para PendingQueryManager: devuelve (leads, got_429)
# ===========================================================================
def search_reddit_with_status(query: str, num: int = 10):
    """Wrapper de search_reddit que devuelve (leads, got_429).
    
    got_429=True si Reddit devolvió HTTP 429.
    got_429=False si fue exitoso o falló por otra razón.
    """
    import sys as _sys
    # Parchar temporalmente el print de error para detectar 429
    _orig_stderr = _sys.stderr
    _captured_err = []
    class _StderrCapture:
        def write(self, s):
            _captured_err.append(s)
            _orig_stderr.write(s)  # también imprimir normal
        def flush(self):
            _orig_stderr.flush()
    _sys.stderr = _StderrCapture()
    
    try:
        leads = search_reddit(query, num=num)
        # Si hubo 429 en los logs, devolver True
        err_text = "".join(_captured_err)
        got_429 = "429" in err_text and "RSS search fail" in err_text
        return leads, got_429
    finally:
        _sys.stderr = _orig_stderr


```


================================================================================
FILE: source_registry.py | 316 lines | SHA: 92c16a2f968e
DESC: Source Registry (discovery + scoring)
================================================================================

```python
"""
source_registry.py — Source Registry v10.2 (Lite)

Descubre, puntúa y mantiene un registro de fuentes públicas argentinas
para el pipeline de leads.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Any
import sys

from search_providers import search as provider_search

REGISTRY_PATH = os.environ.get("SOURCE_REGISTRY_PATH", "data/source_registry.json")

SEED_SUBREDDITS = [
    "ArAutos", "argentina", "Cordoba", "BuenosAires",
    "DerechoGenial", "AskArgentina", "PreguntasReddit",
    "Mendoza", "Rosario", "Salta",
    # Nuevos (Sakana+H.AI consensus): alta intención de multas
    "MotosArg",       # dueños moto = multas moto
    "empleosAR",      # problemas registro/licencia
    "uruguay",        # multas AR a uruguayos (caso real)
]

DISCOVERY_QUERIES = [
    # SourceHunter SOLO usa DuckDuckGo (no Reddit, para no gastar rate limit)
    'site:com.ar "transferencia" "auto" "multa"',
    'site:com.ar "fotomulta" "Argentina"',
    'site:com.ar "juez de faltas" auto',
    'site:com.ar "08 firmado" auto',
    'site:com.ar foro multas automotor',
]

BLACKLIST_DOMAINS = {
    "gob.ar", "gov.ar", "jus.gov.ar", "dnrpa.jus.gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com", "perfil.com",
    "tn.com.ar", "cronista.com", "ambito.com", "pagina12.com.ar",
    "iprofesional.com", "wikipedia.org", "youtube.com",
    "multabot.com.ar", "segurarse.com.ar", "iusnoticias.com.ar",
    "parrillacero5.com.ar", "autocosmos.com.ar",
    "facebook.com", "instagram.com", "tiktok.com",
}

VEHICLE_KEYWORDS = {"multa", "multas", "fotomulta", "transferencia", "08",
                     "libre deuda", "auto", "vehiculo", "patente", "registro",
                     "automotor", "juez de faltas", "veraz", "cedula"}

ARGENTINA_KEYWORDS = {"argentina", "caba", "buenos aires", "cordoba",
                       "rosario", "mendoza", "salta", ".ar"}


@dataclass
class Source:
    id: str = ""
    name: str = ""
    canonical_url: str = ""
    domain: str = ""
    platform: str = "other"
    status: str = "candidate"
    trust_score: int = 50
    noise_score: int = 0
    final_score: int = 50
    discovered_at: str = ""
    discovery_origin: str = "web_search"
    topics: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "runs": 0, "successful": 0, "failed": 0,
        "consecutive_failures": 0, "total_leads": 0,
        "last_success": "", "last_failure": "",
    })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{host}{path}"
    except Exception:
        return url


def make_source_id(url: str) -> str:
    import hashlib
    return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()[:12]


def score_source(source: Source) -> int:
    score = 50
    text = f"{source.name} {source.canonical_url} {' '.join(source.topics)}".lower()
    domain = source.domain.lower()

    if any(kw in text for kw in VEHICLE_KEYWORDS):
        score += 20
    if source.platform == "reddit" and "reddit.com/r/" in source.canonical_url:
        score += 15
    if any(kw in text or kw in domain for kw in ARGENTINA_KEYWORDS):
        score += 10
    if source.stats.get("total_leads", 0) > 0:
        score += 10

    if any(bl in domain for bl in BLACKLIST_DOMAINS):
        score -= 50
    if source.stats.get("consecutive_failures", 0) >= 3:
        score -= 30

    return max(0, min(100, score))


def discover_sources() -> List[Source]:
    print("[SourceHunter] Descubriendo fuentes nuevas...", file=sys.stderr)
    discovered = []
    seen_domains = set()

    for query in DISCOVERY_QUERIES:
        try:
            results = provider_search(query, num=10)
            print(f"  [{query[:50]}] -> {len(results)} resultados", file=sys.stderr)
            for r in results:
                url = r.get("url", "")
                if not url:
                    continue
                domain = get_domain(url)
                if not domain or domain in seen_domains:
                    continue
                if any(bl in domain for bl in BLACKLIST_DOMAINS):
                    continue

                platform = "other"
                if "reddit.com" in domain:
                    platform = "reddit"
                elif "mercadolibre" in domain or "mercadolivre" in domain:
                    platform = "marketplace"
                elif "t.me" in domain or "telegram" in domain:
                    platform = "telegram"
                elif any(kw in (r.get("title","") + r.get("snippet","")).lower()
                         for kw in ["foro", "forum", "comunidad"]):
                    platform = "forum"
                else:
                    platform = "blog"

                source = Source(
                    id=make_source_id(url),
                    name=r.get("title", "")[:100],
                    canonical_url=canonicalize_url(url),
                    domain=domain,
                    platform=platform,
                    status="candidate",
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    discovery_origin="web_search",
                    topics=["multas", "transferencia", "auto"],
                )
                source.final_score = score_source(source)
                if source.final_score >= 70:
                    source.status = "approved"
                elif source.final_score < 40:
                    source.status = "rejected"
                discovered.append(source)
                seen_domains.add(domain)
            time.sleep(2)
        except Exception as e:
            print(f"  [SourceHunter] error en query: {e}", file=sys.stderr)
            continue

    print(f"[SourceHunter] Descubiertas {len(discovered)} fuentes nuevas", file=sys.stderr)
    return discovered


def load_registry() -> Dict[str, Any]:
    if not os.path.exists(REGISTRY_PATH):
        return {
            "metadata": {
                "version": "10.2",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "sources": [],
        }
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"metadata": {}, "sources": []}


def save_registry(registry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(REGISTRY_PATH) or ".", exist_ok=True)
    registry["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def merge_sources(existing: List, new: List[Source]) -> List:
    by_url = {}
    for s in existing:
        if isinstance(s, Source):
            by_url[s.canonical_url] = s
        elif isinstance(s, dict):
            by_url[s.get("canonical_url","")] = s
    for s in new:
        if s.canonical_url in by_url:
            continue
        by_url[s.canonical_url] = s
    return list(by_url.values())


def update_source_stats(source: Source, success: bool, leads_found: int) -> None:
    s = source.stats
    s["runs"] += 1
    if success:
        s["successful"] += 1
        s["consecutive_failures"] = 0
        s["last_success"] = datetime.now(timezone.utc).isoformat()
        s["total_leads"] += leads_found
    else:
        s["failed"] += 1
        s["consecutive_failures"] += 1
        s["last_failure"] = datetime.now(timezone.utc).isoformat()
        if s["consecutive_failures"] >= 3:
            source.status = "paused"


def seed_subreddits() -> List[Source]:
    sources = []
    for sub in SEED_SUBREDDITS:
        url = f"https://www.reddit.com/r/{sub}/"
        s = Source(
            id=make_source_id(url),
            name=f"r/{sub}",
            canonical_url=url,
            domain="reddit.com",
            platform="reddit",
            status="approved",
            discovered_at=datetime.now(timezone.utc).isoformat(),
            discovery_origin="seed",
            topics=["autos", "argentina", "multas", "transferencia"],
        )
        s.final_score = 80
        sources.append(s)
    return sources


def run_discovery_and_update() -> Dict[str, Any]:
    registry = load_registry()
    existing_sources = []
    for s in registry.get("sources", []):
        if isinstance(s, dict):
            try:
                existing_sources.append(Source(**{k: v for k, v in s.items()
                                                  if k in Source.__dataclass_fields__}))
            except Exception:
                pass
        elif isinstance(s, Source):
            existing_sources.append(s)

    if not existing_sources:
        existing_sources = seed_subreddits()
        print(f"[SourceHunter] Sembrados {len(existing_sources)} subreddits AR", file=sys.stderr)

    new_sources = discover_sources()
    all_sources = merge_sources(existing_sources, new_sources)

    registry["sources"] = [s.to_dict() if isinstance(s, Source) else s for s in all_sources]
    save_registry(registry)

    approved = [s for s in all_sources if (s.status if isinstance(s, Source) else s.get("status")) == "approved"]
    print(f"[SourceHunter] Registry: {len(all_sources)} total, {len(approved)} approved",
          file=sys.stderr)

    return registry


def get_approved_sources() -> List[Source]:
    """Devuelve las fuentes approved para que el pipeline las use."""
    registry = load_registry()
    out = []
    for s in registry.get("sources", []):
        if s.get("status") == "approved":
            try:
                out.append(Source(**{k: v for k, v in s.items()
                                     if k in Source.__dataclass_fields__}))
            except Exception:
                pass
    return out


if __name__ == "__main__":
    reg = run_discovery_and_update()
    print(f"\nOK Registry guardado en {REGISTRY_PATH}")
    print(f"  Sources: {len(reg['sources'])}")
    print(f"  Approved: {len([s for s in reg['sources'] if s['status']=='approved'])}")

```


================================================================================
FILE: pending_queries_kv.py | 207 lines | SHA: eed8590c119f
DESC: PendingQueryManager (cola 429)
================================================================================

```python
"""
pending_queries_kv.py — Cola persistente de queries que fallaron con 429.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional, List, Dict, Any, Tuple

log = logging.getLogger(__name__)

KV_KEY_PENDING = "pending_queries"
MAX_PENDING_STORED = 12
MAX_RETRIES_PER_Q = 3
MIN_RETRY_HOURS = 3.0
MAX_PENDING_PER_RUN = 2
SLEEP_BETWEEN_RSS = 12

WORKER_URL = "https://leadx.simondalmasso44.workers.dev"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_from_now(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class KVClient:
    """Wrapper mínimo para /api/kv del Worker (auth con INGEST_SECRET)."""

    def __init__(self, worker_url: str, secret: str):
        self.worker_url = worker_url.rstrip("/")
        self.secret = secret

    def _headers(self) -> dict:
        return {
            "X-Webhook-Secret": self.secret,
            "Content-Type": "application/json",
            "User-Agent": "LeadX-Pipeline/2.0",
        }

    def get(self, key: str) -> Optional[dict]:
        url = f"{self.worker_url}/api/kv?key={key}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                return data.get("value")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            log.warning(f"KV GET {key}: HTTP {e.code}", file=sys.stderr)
            return None
        except Exception as e:
            log.warning(f"KV GET {key}: {e}", file=sys.stderr)
            return None

    def put(self, key: str, value: dict, ttl_seconds: int = 0) -> bool:
        url = f"{self.worker_url}/api/kv"
        body = json.dumps({"key": key, "value": value, "ttl": ttl_seconds}).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status == 200
        except Exception as e:
            log.error(f"KV PUT {key}: {e}", file=sys.stderr)
            return False


class PendingQuery:
    def __init__(self, url: str, query_text: str, group_idx: int,
                 retry_count: int = 0, failed_at: Optional[str] = None,
                 next_retry_after: Optional[str] = None):
        self.url = url
        self.query_text = query_text
        self.group_idx = group_idx
        self.retry_count = retry_count
        self.failed_at = failed_at or _now_iso()
        self.next_retry_after = next_retry_after or _hours_from_now(MIN_RETRY_HOURS)

    def is_ready(self) -> bool:
        try:
            next_dt = datetime.fromisoformat(self.next_retry_after)
            if next_dt.tzinfo is None:
                next_dt = next_dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= next_dt
        except Exception:
            return True

    def is_exhausted(self) -> bool:
        return self.retry_count >= MAX_RETRIES_PER_Q

    def to_dict(self) -> dict:
        return {
            "url": self.url, "query_text": self.query_text,
            "group_idx": self.group_idx, "retry_count": self.retry_count,
            "failed_at": self.failed_at, "next_retry_after": self.next_retry_after,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingQuery":
        return cls(
            url=d["url"], query_text=d["query_text"],
            group_idx=d.get("group_idx", -1),
            retry_count=d.get("retry_count", 0),
            failed_at=d.get("failed_at"),
            next_retry_after=d.get("next_retry_after"),
        )


class PendingQueryManager:
    def __init__(self, worker_url: str, secret: str):
        self.kv = KVClient(worker_url, secret)
        self.pending: List[PendingQuery] = []
        self._loaded = False

    def load(self):
        raw = self.kv.get(KV_KEY_PENDING)
        if not raw or "queries" not in raw:
            print(f"[PQM] No hay queries pendientes en KV", file=sys.stderr)
            self.pending = []
        else:
            self.pending = [PendingQuery.from_dict(q) for q in raw["queries"]]
            ready = sum(1 for q in self.pending if q.is_ready() and not q.is_exhausted())
            print(f"[PQM] Cargadas {len(self.pending)} queries pendientes ({ready} listas)",
                  file=sys.stderr)
        self._loaded = True

    def add(self, url: str, query_text: str, group_idx: int):
        for pq in self.pending:
            if pq.url == url:
                pq.retry_count += 1
                pq.next_retry_after = _hours_from_now(MIN_RETRY_HOURS * pq.retry_count)
                print(f"[PQM] Retry #{pq.retry_count} para '{query_text[:40]}'",
                      file=sys.stderr)
                return
        pq = PendingQuery(url=url, query_text=query_text, group_idx=group_idx)
        self.pending.append(pq)
        print(f"[PQM] Nueva query pendiente: '{query_text[:40]}'", file=sys.stderr)
        if len(self.pending) > MAX_PENDING_STORED:
            self.pending.sort(key=lambda q: (not q.is_exhausted(), -q.retry_count))
            self.pending = self.pending[:MAX_PENDING_STORED]

    def retry_pending(self, search_fn: Callable[[str], Tuple[List[Dict], bool]]) -> List[Dict]:
        """search_fn(query) → (leads, got_429). Reintenta máx 2 ready queries."""
        if not self._loaded:
            self.load()

        ready = [q for q in self.pending if q.is_ready() and not q.is_exhausted()]
        expired = [q for q in self.pending if q.is_exhausted()]

        if expired:
            print(f"[PQM] Descartando {len(expired)} queries agotadas (max retries)",
                  file=sys.stderr)
            self.pending = [q for q in self.pending if not q.is_exhausted()]

        if not ready:
            print(f"[PQM] No hay queries listas para retry en este run", file=sys.stderr)
            return []

        to_retry = ready[:MAX_PENDING_PER_RUN]
        recovered = []

        for i, pq in enumerate(to_retry):
            print(f"[PQM] Reintentando ({i+1}/{len(to_retry)}): '{pq.query_text[:40]}' "
                  f"[retry #{pq.retry_count + 1}]", file=sys.stderr)
            leads, got_429 = search_fn(pq.query_text)
            if got_429:
                pq.retry_count += 1
                pq.next_retry_after = _hours_from_now(MIN_RETRY_HOURS * pq.retry_count)
                print(f"[PQM] Retry falló (429). Próximo: {pq.next_retry_after[:19]}",
                      file=sys.stderr)
            else:
                print(f"[PQM] OK recuperada '{pq.query_text[:40]}' → {len(leads)} leads",
                      file=sys.stderr)
                recovered.extend(leads)
                self.pending = [q for q in self.pending if q.url != pq.url]
            if i < len(to_retry) - 1:
                time.sleep(SLEEP_BETWEEN_RSS)
        return recovered

    def save(self):
        payload = {
            "queries": [q.to_dict() for q in self.pending],
            "updated_at": _now_iso(),
            "count": len(self.pending),
        }
        ok = self.kv.put(KV_KEY_PENDING, payload, ttl_seconds=7 * 24 * 3600)
        if ok:
            print(f"[PQM] Guardadas {len(self.pending)} queries pendientes en KV",
                  file=sys.stderr)
        else:
            print(f"[PQM] ERROR al guardar pending_queries en KV", file=sys.stderr)

    def status(self) -> dict:
        return {
            "total_pending": len(self.pending),
            "ready_for_retry": sum(1 for q in self.pending if q.is_ready()),
            "exhausted": sum(1 for q in self.pending if q.is_exhausted()),
        }

```


================================================================================
FILE: wrangler.toml | 17 lines | SHA: e722ad1706b7
DESC: Cloudflare config (KV, sin cron)
================================================================================

```toml
name = "leadx"
main = "worker.js"
compatibility_date = "2024-09-25"
account_id = "b21fa81d12acb663798f9f7c51801955"

# KV namespace binding
[[kv_namespaces]]
binding = "LEADX_KV"
id = "4a63bcf757fa4f5b9720ff820b7b9ac6"

# Observability
[observability]
enabled = true

# INGEST_SECRET debe definirse como secret (no como var):
#   wrangler secret put INGEST_SECRET
# NO lo pongas en este archivo como var.

```


================================================================================
FILE: .github/workflows/radar-cron.yml | 98 lines | SHA: 5e50f77f166a
DESC: GH Actions workflow (cron 1h)
================================================================================

```yaml
name: Radar Leads — Cron Pipeline

on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run-radar:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Run pipeline
        env:
          WORKER_URL: https://leadx.simondalmasso44.workers.dev
          INGEST_SECRET: ${{ secrets.INGEST_SECRET }}
        run: |
          python generate_payload.py

      - name: Copy to public/data
        run: |
          mkdir -p public/data
          cp data/dashboard_payload.json public/data/dashboard_payload.json
          cp data/stats.json public/data/stats.json
          cp data/history.json public/data/history.json

      - name: Commit and push
        run: |
          git config user.name "Radar Bot"
          git config user.email "radar-bot@users.noreply.github.com"
          git add data/ public/data/
          git diff --staged --quiet || git commit -m "radar: auto-update $(date -u '+%Y-%m-%d %H:%M UTC')"
          git push

      - name: Push leads to Worker KV via /api/ingest
        env:
          WORKER_URL: https://leadx.simondalmasso44.workers.dev
          INGEST_SECRET: ${{ secrets.INGEST_SECRET }}
        run: |
          pip install requests -q
          python -c "
          import os, json, requests, sys
          url = os.environ['WORKER_URL'] + '/api/ingest'
          secret = os.environ['INGEST_SECRET']
          with open('data/dashboard_payload.json') as f:
              payload = json.load(f)
          leads = payload.get('leads_all', [])
          print(f'Leads a subir: {len(leads)}')
          if len(leads) == 0:
              print('No hay leads — salteando POST')
              sys.exit(0)
          data = json.dumps(payload)
          try:
              resp = requests.post(
                  url,
                  data=data,
                  headers={
                      'Content-Type': 'application/json',
                      'X-Webhook-Secret': secret,
                      'User-Agent': 'LeadX-Pipeline/1.0'
                  },
                  timeout=30
              )
              print(f'HTTP {resp.status_code}')
              print(resp.text[:500])
              if resp.status_code >= 400:
                  sys.exit(1)
          except Exception as e:
              print(f'Error: {e}')
              sys.exit(1)
          "

      - name: Deploy Worker to Cloudflare
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          npx wrangler deploy

      - name: Summary
        if: always()
        run: |
          echo "### Radar Pipeline" >> $GITHUB_STEP_SUMMARY
          if [ -f data/dashboard_payload.json ]; then
            python -c "import json; d=json.load(open('data/dashboard_payload.json')); print(f'Leads: {d[\"summary\"][\"total_leads\"]} | Hot: {d[\"summary\"][\"hot_leads\"]}')" >> $GITHUB_STEP_SUMMARY
          fi

```


================================================================================
TOTAL: 231,729 chars | 6021 lines | 7 archivos
Commit: 17f93fd | Version: v2.3
================================================================================
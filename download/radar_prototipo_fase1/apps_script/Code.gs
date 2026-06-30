/**
 * Radar de Oportunidades — Apps Script Web App (Code.gs)
 *
 * Este script se despliega como Web App en Google Apps Script y recibe POST
 * HTTP desde `webhook_uploader.py` (Python) para appendar casos a la Sheet.
 *
 * Despliegue:
 *   1. Abrir la Sheet: https://docs.google.com/spreadsheets/d/1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0/edit
 *   2. Extensiones > Apps Script
 *   3. Pegar este código
 *   4. Implementar > Nueva implementación > Tipo: App web
 *      - Ejecutar como: Yo (tu cuenta)
 *      - Quién puede acceder: Cualquiera (con el link)
 *   5. Copiar URL de implementación (termina en /exec)
 *   6. Setear en la máquina del operador:
 *      export RADAR_WEBHOOK_URL=https://script.google.com/macros/s/<DEPLOY_ID>/exec
 *
 * Compliance:
 *   - El script sólo escribe en la Sheet especificada, no lee otras Sheets
 *   - No expone datos: sólo acepta POST con payload JSON
 *   - El acceso queda logueado en el execution log de Apps Script
 */

const SHEET_ID = "1jLeM6k_Q10JBNFSn46TCoz7dgVdnOS79lyIPO283xE0";
const SHEET_NAME = "cases";

/**
 * Append batch cases to Google Sheets
 */
function appendCases(cases) {
  const sheet = SpreadsheetApp.openById(SHEET_ID).getSheetByName(SHEET_NAME);

  // Si la hoja no existe, crearla
  if (!sheet) {
    const ss = SpreadsheetApp.openById(SHEET_ID);
    const newSheet = ss.insertSheet(SHEET_NAME);
    ensureHeaders(newSheet);
    return appendCasesToSheet(newSheet, cases);
  }

  // Asegurar headers si la hoja está vacía
  if (sheet.getLastRow() === 0) {
    ensureHeaders(sheet);
  }

  return appendCasesToSheet(sheet, cases);
}

/**
 * Asegura que la fila 1 tenga los headers correctos
 */
function ensureHeaders(sheet) {
  const headers = [
    "case_id", "timestamp", "name_or_alias", "profile_url", "patent",
    "vehicle_type", "jurisdiction", "locality", "problem_type", "year",
    "amount", "score", "priority_level", "source_name", "source_url",
    "evidence_text", "whatsapp_number", "whatsapp_link", "status", "review_state"
  ];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
}

/**
 * Append cases to a sheet que ya tiene headers
 */
function appendCasesToSheet(sheet, cases) {
  const rows = cases.map(c => [
    c.case_id || "",
    new Date().toISOString(),
    c.name_or_alias || "",
    c.profile_url || "",
    c.patent || "",
    c.vehicle_type || "",
    c.jurisdiction || "",
    c.locality || "",
    c.problem_type || "",
    c.year || "",
    c.amount || "",
    c.score || 0,
    computePriority(c.score),
    c.source_name || "",
    c.source_url || "",
    c.evidence_text || "",
    c.whatsapp_number || "",
    buildWhatsApp(c.whatsapp_number),
    "new",
    "pending_review"
  ]);

  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length)
        .setValues(rows);

  return rows.length;
}

/**
 * Priority scoring
 */
function computePriority(score) {
  if (score >= 80) return "critical";
  if (score >= 60) return "high";
  if (score >= 40) return "medium";
  return "low";
}

/**
 * WhatsApp link builder
 */
function buildWhatsApp(number) {
  if (!number) return "";
  // Normalizar: sólo dígitos
  const normalized = String(number).replace(/\D/g, "");
  if (!normalized) return "";
  return "https://wa.me/" + normalized;
}

/**
 * Entry point for GLM webhook-style push
 * Recibe: { "cases": [ {case_id, ...}, ... ] }
 * Devuelve: "OK" | "NO_CASES" | "ERROR: <msg>"
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput("ERROR: no post data");
    }

    const payload = JSON.parse(e.postData.contents);

    if (!payload.cases || !Array.isArray(payload.cases) || payload.cases.length === 0) {
      return ContentService.createTextOutput("NO_CASES");
    }

    const appended = appendCases(payload.cases);

    // Log en execution log de Apps Script (visible en el editor)
    console.log(`Appended ${appended} cases from webhook push`);

    return ContentService.createTextOutput("OK");
  } catch (err) {
    console.error("Error en doPost:", err);
    return ContentService.createTextOutput("ERROR: " + err.message);
  }
}

/**
 * Test manual desde el editor de Apps Script
 */
function testDoPost() {
  const mockEvent = {
    postData: {
      contents: JSON.stringify({
        cases: [
          {
            case_id: "test-001",
            timestamp: "2026-06-30T10:00:00-03:00",
            name_or_alias: "Test User",
            profile_url: "https://example.com/user/1",
            patent: "ABC123",
            vehicle_type: "auto",
            jurisdiction: "CABA",
            locality: "Caballito",
            problem_type: "fotomulta",
            year: 2020,
            amount: 18500,
            score: 82,
            source_name: "facebook_public_groups",
            source_url: "https://example.com/post/abc",
            evidence_text: "Test evidence text",
            whatsapp_number: "541155551234"
          }
        ]
      })
    }
  };
  const result = doPost(mockEvent);
  Logger.log("Resultado: " + result.getContent());
}

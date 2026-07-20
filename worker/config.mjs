export const RELEASE = "leadx-multiline-v1";
export const HEALTH_DATA_KEY = "leads:live";
export const HEALTH_KV_TIMEOUT_MS = 2 * 1000;
export const SESSION_COOKIE = "leadx_session";
export const SESSION_IDLE_MS = 20 * 60 * 1000;
export const SESSION_ABSOLUTE_MS = 8 * 60 * 60 * 1000;
export const SESSION_RENEW_MIN_MS = 60 * 1000;
export const MAX_LOGIN_BYTES = 4096;
export const MAX_INGEST_BYTES = 2 * 1024 * 1024;
export const MAX_LEADS = 500;
export const VERTICALS = new Set(["fotomultas", "repuestos_agricolas"]);

export const STATUS_VALUES = new Set([
  "Nuevo", "Contactado", "Calificado", "Propuesta", "Ganado", "Perdido",
  "Revisado", "En gestión", "Esperando respuesta", "Cerrado", "Descartado",
]);
export const PRIORITY_VALUES = new Set(["Alta", "Media", "Baja"]);
export const CRM_FIELDS = [
  "status", "priority", "notes", "owner", "assigned_to", "amount", "contacted_at",
  "next_action_at", "last_activity_at", "resolution", "resolution_reason", "history",
  "updated_at", "version", "_status", "_priority", "_notes", "_monto", "_history", "whatsapp_confirmed",
];

export const API_METHODS = new Map([
  ["/api/auth/login", ["POST"]], ["/api/auth/session", ["GET"]], ["/api/auth/activity", ["POST"]],
  ["/api/auth/logout", ["POST"]], ["/api/leads", ["GET"]], ["/api/metrics", ["GET"]],
  ["/api/ingest", ["POST"]], ["/api/health", ["GET"]],
]);

export const REMOVED_PATHS = new Set([
  "/api/kv", "/api/ml-questions", "/api/reddit-bio", "/api/ddg-foromoto",
  "/api/clasificar-webhook", "/api/clasificar-patente", "/api/clasificar-basic",
  "/api/apify-facebook", "/cookies", "/cookies.html", "/api/cookies",
  "/api/whatsapp-validate", "/api/whatsapp-webhook", "/api/apify-webhook",
  "/api/enrich-patente", "/api/analyze-acta", "/api/forensic-case", "/api/cron-run",
  "/api/enrich-all", "/api/reddit-profile-links", "/api/shadow-osint", "/api/ventafe-debug",
]);

export function demoLeads(now = Date.now(), vertical = "fotomultas") {
  const ago = (ms) => new Date(now - ms).toISOString();
  const fines = [
    { id: "demo_001", score: 95, persona: "Carlos Demo", provincia: "Santa Fe", platform: "Foro ficticio", source: "demo", source_label: "Foro ficticio", title: "Multa de moto comprada usada", snippet: "Compré una moto usada y apareció una multa anterior. ¿Cómo puedo regularizarla?", vehiculo: "moto", fecha_iso: ago(6 * 3600000), _status: "Nuevo", _priority: "Alta", _isDemo: true },
    { id: "demo_002", score: 88, persona: "María Ejemplo", provincia: "CABA", platform: "Consulta ficticia", source: "demo", source_label: "Consulta ficticia", title: "Transferencia bloqueada por multas", snippet: "La transferencia quedó bloqueada por infracciones que no reconozco.", vehiculo: "moto", fecha_iso: ago(2 * 3600000), _status: "Nuevo", _priority: "Alta", _isDemo: true },
    { id: "demo_003", score: 75, persona: "Juan Prueba", provincia: "Buenos Aires", platform: "Foro ficticio", source: "demo", source_label: "Foro ficticio", title: "Multas del titular anterior", snippet: "La camioneta conserva dos multas del dueño anterior y necesito transferirla.", vehiculo: "camioneta", fecha_iso: ago(86400000), _status: "Contactado", _priority: "Alta", _isDemo: true },
    { id: "demo_004", score: 70, persona: "Ana Ficticia", provincia: "Entre Ríos", platform: "Consulta ficticia", source: "demo", source_label: "Consulta ficticia", title: "Infracción asociada al primer dueño", snippet: "Apareció una infracción del primer titular y no sé cómo presentar el descargo.", vehiculo: "auto", fecha_iso: ago(4 * 3600000), _status: "Nuevo", _priority: "Media", _isDemo: true },
    { id: "demo_005", score: 65, persona: "Pedro Muestra", provincia: "CABA", platform: "Foro ficticio", source: "demo", source_label: "Foro ficticio", title: "Fotomulta por velocidad", snippet: "Recibí una fotomulta por una diferencia mínima de velocidad permitida.", vehiculo: "auto", fecha_iso: ago(12 * 3600000), _status: "En gestión", _priority: "Media", _isDemo: true },
    { id: "demo_006", score: 55, persona: "Lucía Ficticia", provincia: "Misiones", platform: "Consulta ficticia", source: "demo", source_label: "Consulta ficticia", title: "Prescripción de radar móvil", snippet: "Necesito saber qué documentación revisar para evaluar la prescripción.", vehiculo: "auto", fecha_iso: ago(18 * 3600000), _status: "Nuevo", _priority: "Media", _isDemo: true },
    { id: "demo_007", score: 50, persona: "Roberto Demo", provincia: "Santa Fe", platform: "Foro ficticio", source: "demo", source_label: "Foro ficticio", title: "Dominio cargado incorrectamente", snippet: "La infracción parece corresponder a otro vehículo con un dominio similar.", vehiculo: "auto", fecha_iso: ago(2 * 86400000), _status: "Cerrado", _priority: "Baja", _isDemo: true },
    { id: "demo_008", score: 45, persona: "Patricia Ejemplo", provincia: "Corrientes", platform: "Consulta ficticia", source: "demo", source_label: "Consulta ficticia", title: "Infracciones ausentes en la consulta", snippet: "Una oficina informa deuda pero el portal de consulta no muestra infracciones.", fecha_iso: ago(3 * 86400000), _status: "Revisado", _priority: "Baja", _isDemo: true },
    { id: "demo_009", score: 40, persona: "Diego Prueba", provincia: "Buenos Aires", platform: "Foro ficticio", source: "demo", source_label: "Foro ficticio", title: "Descargo por multas antiguas", snippet: "Quiero ordenar varias multas antiguas antes de iniciar una transferencia.", vehiculo: "moto", fecha_iso: ago(5 * 86400000), _status: "Descartado", _priority: "Baja", _isDemo: true },
    { id: "demo_010", score: 35, persona: "Sandra Prueba", provincia: "CABA", platform: "Consulta ficticia", source: "demo", source_label: "Consulta ficticia", title: "VTV y regularización", snippet: "Necesito regularizar VTV e infracciones antes de renovar documentación.", vehiculo: "auto", fecha_iso: ago(7 * 86400000), _status: "Nuevo", _priority: "Baja", _isDemo: true },
    { id: "demo_011", score: 80, persona: "Fernando Demo", provincia: "Santa Fe", platform: "Foro ficticio", source: "demo", source_label: "Foro ficticio", title: "Infracción en ruta provincial", snippet: "Recibí un acta en una ruta provincial y necesito revisar su información.", vehiculo: "camioneta", fecha_iso: ago(8 * 3600000), _status: "Nuevo", _priority: "Alta", _isDemo: true },
    { id: "demo_012", score: 60, persona: "Carolina Muestra", provincia: "Entre Ríos", platform: "Consulta ficticia", source: "demo", source_label: "Consulta ficticia", title: "Retención con grúa municipal", snippet: "El vehículo fue retirado por una grúa y necesito identificar los pasos de regularización.", vehiculo: "auto", fecha_iso: ago(14 * 3600000), _status: "Esperando respuesta", _priority: "Media", _isDemo: true },
  ].map((lead, index) => ({ ...lead, vertical: "fotomultas", name: lead.persona, province: lead.provincia, status: lead._status, priority: lead._priority, channel: "whatsapp", assigned_to: index % 3 ? "Sin asignar" : "Equipo comercial", created_at: lead.fecha_iso, vertical_data: { plate: `DE${100 + index}MO`, municipality: ["Santa Fe", "Rosario", "Córdoba"][index % 3], violation_type: ["Exceso de velocidad", "Semáforo en rojo", "Estacionamiento"][index % 3], estimated_amount: 120000 + index * 7500, due_date: "2026-08-10" }, phone: `+54 9 342 555 ${String(1100 + index).padStart(4, "0")}`, whatsapp_confirmed: true }));
  if (vertical === "fotomultas") return fines;
  const brands = ["Case IH", "New Holland", "Case IH", "New Holland"];
  const machines = ["Cosechadora", "Tractor", "Sembradora", "Pulverizadora"];
  return fines.map((lead, index) => ({ ...lead, id: `demo_repuestos_${index + 1}`, vertical: "repuestos_agricolas", title: "Consulta ficticia de repuesto agrícola", snippet: ["Busca disponibilidad inmediata para la próxima campaña.", "Solicita cotización y plazo de entrega del repuesto.", "Necesita reemplazo urgente para volver a trabajar."][index % 3], vertical_data: { brand: brands[index % 4], machine_type: machines[index % 4], model: ["Axial-Flow 7130", "T7.245", "Precision 500", "Patriot 350"][index % 4], part_number: `FX-${87312000 + index * 17}`, quantity: index % 3 + 1, urgency: ["alta", "media", "baja"][index % 3] } }));
}

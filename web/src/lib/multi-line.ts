import type {
  CommercialLeadStatus,
  Lead,
  LeadChannel,
  LeadFilters,
  LeadPriority,
  LeadVertical,
  LeadVerticalData,
} from "../types";

export const VERTICAL_OPTIONS: ReadonlyArray<{ value: LeadVertical; label: string; shortLabel: string }> = [
  { value: "fotomultas", label: "Fotomultas", shortLabel: "Fotomultas" },
  { value: "repuestos_agricolas", label: "Repuestos agrícolas", shortLabel: "Repuestos" },
];

export const EMPTY_FILTERS: LeadFilters = {
  status: "todos",
  priority: "todos",
  province: "",
  channel: "",
  assigned: "",
  date: "todos",
  municipality: "",
  violationType: "",
  plate: "",
  brand: "",
  machineType: "",
  partNumber: "",
  urgency: "",
};

const VALID_VERTICALS = new Set<LeadVertical>(["fotomultas", "repuestos_agricolas"]);
const STATUS_MAP: Record<string, CommercialLeadStatus> = {
  nuevo: "Nuevo",
  revisado: "Calificado",
  contactado: "Contactado",
  "en gestión": "Propuesta",
  "en gestion": "Propuesta",
  "esperando respuesta": "Propuesta",
  calificado: "Calificado",
  propuesta: "Propuesta",
  cerrado: "Ganado",
  ganado: "Ganado",
  descartado: "Perdido",
  perdido: "Perdido",
};
const PRIORITY_MAP: Record<string, LeadPriority> = {
  alta: "Alta", high: "Alta", media: "Media", medium: "Media", baja: "Baja", low: "Baja",
};

export function parseVertical(value: string | null | undefined): LeadVertical | null {
  return value && VALID_VERTICALS.has(value as LeadVertical) ? value as LeadVertical : null;
}

export function verticalLabel(vertical: LeadVertical): string {
  return VERTICAL_OPTIONS.find((option) => option.value === vertical)?.label || "Fotomultas";
}

export function canonicalStatus(value: unknown): CommercialLeadStatus {
  const key = typeof value === "string" ? value.trim().toLocaleLowerCase("es") : "";
  return STATUS_MAP[key] || "Nuevo";
}

export function canonicalPriority(value: unknown, score = 0): LeadPriority {
  const key = typeof value === "string" ? value.trim().toLocaleLowerCase("es") : "";
  if (PRIORITY_MAP[key]) return PRIORITY_MAP[key];
  if (score >= 70) return "Alta";
  if (score >= 40) return "Media";
  return "Baja";
}

function inferChannel(lead: Lead): LeadChannel {
  const direct = String(lead.channel || "").toLocaleLowerCase("es");
  if (["whatsapp", "messenger", "email", "telefono", "web", "otro"].includes(direct)) return direct as LeadChannel;
  if (lead.whatsapp_publico) return "whatsapp";
  if (lead.fb_username || lead.fb_author_id || String(lead.platform || lead.source || "").toLowerCase().includes("facebook")) return "messenger";
  if (lead.email_publico || lead.email) return "email";
  if (lead.telefono_publico || lead.telefono || lead.phone) return "telefono";
  return "web";
}

function normalizeVerticalData(lead: Lead, vertical: LeadVertical): LeadVerticalData {
  const source = lead.vertical_data && typeof lead.vertical_data === "object" ? { ...lead.vertical_data } : {};
  if (vertical === "fotomultas") {
    if (!source.plate && lead.patente) source.plate = lead.patente;
    if (!source.municipality && lead.ciudad) source.municipality = lead.ciudad;
    if (!source.violation_type && lead.problem_category) source.violation_type = lead.problem_category;
  }
  return source;
}

export function normalizeLead(input: Lead): Lead {
  const vertical = parseVertical(input.vertical) || "fotomultas";
  const score = Number(input._heat_score ?? input.score ?? 0);
  const name = input.name || input.persona || input.author || "Sin nombre";
  const province = input.province || input.provincia || "";
  const phone = input.phone || input.whatsapp_publico || input.telefono_publico || input.telefono || "";
  const createdAt = input.created_at || input.first_seen_at || input.discovery_timestamp || input.fecha_iso || input.fecha_visible;
  const assignedTo = input.assigned_to || input.owner || "Sin asignar";
  return {
    ...input,
    vertical,
    vertical_data: normalizeVerticalData(input, vertical),
    name,
    persona: input.persona || name,
    province,
    provincia: input.provincia || province,
    phone,
    channel: inferChannel(input),
    assigned_to: assignedTo,
    status: canonicalStatus(input.status || input._status),
    priority: canonicalPriority(input.priority || input._priority, score),
    created_at: createdAt,
  };
}

export function normalizeLeads(leads: Lead[]): Lead[] { return leads.map(normalizeLead); }
export function leadName(lead: Lead): string { return lead.name || lead.persona || lead.author || "Sin nombre"; }
export function leadProvince(lead: Lead): string { return lead.province || lead.provincia || "—"; }
export function leadPhone(lead: Lead): string { return lead.phone || lead.whatsapp_publico || lead.telefono_publico || lead.telefono || ""; }
export function leadChannel(lead: Lead): LeadChannel { return inferChannel(lead); }
export function leadAssigned(lead: Lead): string { return lead.assigned_to || lead.owner || "Sin asignar"; }
export function leadCreatedAt(lead: Lead): string | undefined { return lead.created_at || lead.first_seen_at || lead.discovery_timestamp || lead.fecha_iso || lead.fecha_visible; }
export function leadStatus(lead: Lead): CommercialLeadStatus { return canonicalStatus(lead.status || lead._status); }
export function leadPriority(lead: Lead): LeadPriority { return canonicalPriority(lead.priority || lead._priority, Number(lead._heat_score ?? lead.score ?? 0)); }

export type LeadPotential = "Convertido" | "Muy alto" | "Alto" | "Medio" | "Bajo" | "No viable";

const STATUS_POTENTIAL: Record<CommercialLeadStatus, number> = {
  Ganado: 100,
  Propuesta: 90,
  Calificado: 75,
  Contactado: 55,
  Nuevo: 35,
  Perdido: 0,
};

const PRIORITY_POTENTIAL: Record<LeadPriority, number> = { Alta: 100, Media: 60, Baja: 25 };

export function leadPotentialScore(lead: Lead): number {
  const status = leadStatus(lead);
  if (status === "Ganado") return 100;
  if (status === "Perdido") return 0;
  const rawScore = Number(lead.score ?? lead._heat_score);
  const score = Number.isFinite(rawScore) ? Math.max(0, Math.min(100, rawScore)) : STATUS_POTENTIAL[status];
  return Math.round(STATUS_POTENTIAL[status] * 0.65 + score * 0.25 + PRIORITY_POTENTIAL[leadPriority(lead)] * 0.1);
}

export function leadPotential(lead: Lead): LeadPotential {
  const status = leadStatus(lead);
  if (status === "Ganado") return "Convertido";
  if (status === "Perdido") return "No viable";
  const score = leadPotentialScore(lead);
  if (score >= 85) return "Muy alto";
  if (score >= 65) return "Alto";
  if (score >= 40) return "Medio";
  return "Bajo";
}

function compact(parts: Array<string | number | undefined>): string {
  return parts.filter((part) => part !== undefined && String(part).trim() !== "").join(" · ");
}

export function leadContext(lead: Lead): string {
  const data = lead.vertical_data || {};
  if ((lead.vertical || "fotomultas") === "repuestos_agricolas") {
    return compact([data.brand, data.machine_type, data.part_number]) || lead.title || "Consulta de repuestos";
  }
  return compact([data.plate || lead.patente, data.municipality || lead.ciudad]) || lead.title || "Consulta de fotomultas";
}

export function searchableText(lead: Lead): string {
  return [leadName(lead), leadProvince(lead), leadPhone(lead), lead.channel, leadAssigned(lead), lead.title, lead.snippet, ...Object.values(lead.vertical_data || {})]
    .filter((value) => value !== undefined).join(" ").toLocaleLowerCase("es");
}

export function computeKpis(leads: Lead[]): { total: number; nuevos: number; calificados: number; perdidos: number } {
  const statuses = leads.map(leadStatus);
  return {
    total: leads.length,
    nuevos: statuses.filter((status) => status === "Nuevo").length,
    calificados: statuses.filter((status) => status === "Calificado").length,
    perdidos: statuses.filter((status) => status === "Perdido").length,
  };
}

function withinDate(lead: Lead, range: LeadFilters["date"], now = Date.now()): boolean {
  if (range === "todos") return true;
  const raw = leadCreatedAt(lead);
  if (!raw) return false;
  const timestamp = Date.parse(raw);
  if (!Number.isFinite(timestamp)) return false;
  const days = range === "7d" ? 7 : range === "30d" ? 30 : 90;
  return timestamp >= now - days * 86_400_000;
}

function includesInsensitive(value: unknown, query: string): boolean {
  return String(value || "").toLocaleLowerCase("es").includes(query.toLocaleLowerCase("es"));
}

export function filterLeads(leads: Lead[], vertical: LeadVertical, search: string, filters: LeadFilters, now = Date.now()): Lead[] {
  const query = search.trim().toLocaleLowerCase("es");
  return leads.filter((lead) => {
    const normalized = normalizeLead(lead);
    if (normalized.vertical !== vertical) return false;
    if (query && !searchableText(normalized).includes(query)) return false;
    if (filters.status !== "todos" && leadStatus(normalized) !== filters.status) return false;
    if (filters.priority !== "todos" && leadPriority(normalized) !== filters.priority) return false;
    if (filters.province && leadProvince(normalized) !== filters.province) return false;
    if (filters.channel && leadChannel(normalized) !== filters.channel) return false;
    if (filters.assigned && leadAssigned(normalized) !== filters.assigned) return false;
    if (!withinDate(normalized, filters.date, now)) return false;
    const data = normalized.vertical_data || {};
    if (vertical === "fotomultas") {
      if (filters.municipality && data.municipality !== filters.municipality) return false;
      if (filters.violationType && data.violation_type !== filters.violationType) return false;
      if (filters.plate && !includesInsensitive(data.plate, filters.plate)) return false;
    } else {
      if (filters.brand && data.brand !== filters.brand) return false;
      if (filters.machineType && data.machine_type !== filters.machineType) return false;
      if (filters.partNumber && !includesInsensitive(data.part_number, filters.partNumber)) return false;
      if (filters.urgency && String(data.urgency || "").toLocaleLowerCase("es") !== filters.urgency.toLocaleLowerCase("es")) return false;
    }
    return true;
  });
}

export function contextualFilterLabels(vertical: LeadVertical): string[] {
  return vertical === "fotomultas" ? ["Municipio", "Tipo de infracción", "Patente"] : ["Marca", "Tipo de máquina", "Número de pieza", "Urgencia"];
}

export function normalizeArgentinePhone(value: string): string | null {
  let digits = String(value || "").replace(/\D/g, "");
  if (!digits) return null;
  if (digits.startsWith("00")) digits = digits.slice(2);
  const domestic = digits.match(/^0(\d{2,4})15(\d{6,8})$/);
  if (domestic) digits = `549${domestic[1]}${domestic[2]}`;
  else if (digits.startsWith("54")) {
    let local = digits.slice(2).replace(/^0/, "");
    const with15 = local.match(/^(\d{2,4})15(\d{6,8})$/);
    if (with15) local = `9${with15[1]}${with15[2]}`;
    else if (/^\d{10}$/.test(local)) local = `9${local}`;
    digits = `54${local}`;
  } else {
    digits = digits.replace(/^0/, "");
    const with15 = digits.match(/^(\d{2,4})15(\d{6,8})$/);
    if (with15) digits = `${with15[1]}${with15[2]}`;
    if (/^\d{10}$/.test(digits)) digits = `549${digits}`;
    else if (/^9\d{10}$/.test(digits)) digits = `54${digits}`;
  }
  return /^549\d{10}$/.test(digits) ? digits : null;
}

export function whatsappMessage(vertical: LeadVertical): string {
  return vertical === "repuestos_agricolas"
    ? "Hola, te contacto por tu consulta sobre repuestos agrícolas."
    : "Hola, te contacto por tu consulta relacionada con fotomultas.";
}

export function whatsappUrl(lead: Lead): string | null {
  const normalized = normalizeLead(lead);
  const phone = normalizeArgentinePhone(leadPhone(normalized));
  const confirmed = normalized.whatsapp_confirmed === true || Boolean(normalized.whatsapp_publico) || (leadChannel(normalized) === "whatsapp" && Boolean(phone));
  if (!phone || !confirmed || leadChannel(normalized) === "messenger") return null;
  return `https://wa.me/${phone}?text=${encodeURIComponent(whatsappMessage(normalized.vertical || "fotomultas"))}`;
}

export function formatPhone(value: string): string {
  const normalized = normalizeArgentinePhone(value);
  if (!normalized) return value || "—";
  const local = normalized.slice(3);
  const areaLength = local.startsWith("11") ? 2 : 3;
  const area = local.slice(0, areaLength);
  const subscriber = local.slice(areaLength);
  const split = subscriber.length === 8 ? 4 : Math.max(3, subscriber.length - 4);
  return `+54 9 ${area} ${subscriber.slice(0, split)}-${subscriber.slice(split)}`;
}

import type { Lead, LeadHistoryEntry } from "../types";
import { leadStatus } from "./multi-line";

export type LeadContactState = "CONTACTADO" | "NO CONTACTADO";

const CONTACTED_STAGES = new Set(["Contactado", "Calificado", "Propuesta", "Ganado"]);
const CONTACT_PATTERN = /\b(contactad[oa]|contacto|llamad[oa]|whatsapp|mensaje|respondio|respondió|seguimiento)\b/i;

function historyShowsContact(entries: LeadHistoryEntry[] | undefined): boolean {
  return Boolean(entries?.some((entry) => CONTACT_PATTERN.test(`${entry.action || ""} ${entry.detail || ""}`)));
}

export function leadContactState(lead: Lead): LeadContactState {
  if (typeof lead.contacted_at === "string" && lead.contacted_at.trim()) return "CONTACTADO";
  if (CONTACTED_STAGES.has(leadStatus(lead))) return "CONTACTADO";
  if (historyShowsContact(lead.history) || historyShowsContact(lead._history)) return "CONTACTADO";
  return "NO CONTACTADO";
}

export function contactStateExplanation(lead: Lead): string {
  return leadContactState(lead) === "CONTACTADO"
    ? "Derivado del estado o de actividad comercial registrada por el servidor."
    : "Sin contacto registrado por el servidor ni en el historial existente.";
}

import type { Lead } from "../types";

type CrmPatch = Partial<Pick<Lead,
  "_status" | "status" | "_priority" | "priority" | "_notes" | "notes" | "_monto" | "amount" |
  "assigned_to" | "owner" | "contacted_at" | "next_action_at" | "last_activity_at" |
  "history" | "_history" | "whatsapp_confirmed"
>>;

interface CrmState { [leadId: string]: CrmPatch; }
let memoryState: CrmState = {};

export function loadCrmState(): CrmState { return memoryState; }
export function saveCrmState(state: CrmState): void { memoryState = state; }
export function mergeCrmState(leads: Lead[]): Lead[] { const state = loadCrmState(); return leads.map((lead) => ({ ...lead, ...(state[lead.id] || {}) })); }
export function updateLeadCrm(leadId: string, patch: Partial<CrmPatch>): void { const state = loadCrmState(); state[leadId] = { ...state[leadId], ...patch }; saveCrmState(state); }
export function clearCrmState(): void { memoryState = {}; }

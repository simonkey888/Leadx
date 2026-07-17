import type { Lead, LeadStatus } from "../types";

interface CrmState {
  [leadId: string]: { _status?: LeadStatus; _notes?: string; _monto?: number };
}

let memoryState: CrmState = {};

export function loadCrmState(): CrmState {
  return memoryState;
}

export function saveCrmState(state: CrmState): void {
  memoryState = state;
}

export function mergeCrmState(leads: Lead[]): Lead[] {
  const state = loadCrmState();
  return leads.map((l) => ({ ...l, ...(state[l.id] || {}) }));
}

export function updateLeadCrm(leadId: string, patch: Partial<CrmState[string]>): void {
  const state = loadCrmState();
  state[leadId] = { ...state[leadId], ...patch };
  saveCrmState(state);
}

export function clearCrmState(): void {
  memoryState = {};
}

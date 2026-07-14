import type { Lead, LeadStatus } from "../types";

const STORAGE_KEY = "leadx_crm_state_v1";

interface CrmState {
  [leadId: string]: { _status?: LeadStatus; _notes?: string; _monto?: number };
}

export function loadCrmState(): CrmState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

export function saveCrmState(state: CrmState): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch {}
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
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
}

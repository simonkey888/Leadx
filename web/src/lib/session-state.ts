import type { Lead, SessionInfo } from "../types";

export interface SafeDemoSnapshot {
  leads: Lead[];
  session: SessionInfo;
  isDemo: true;
  selectedLead: null;
  meta: { generated_at: string; source: "demo-session-reset" };
}

export function purgeRealSessionState(
  demoLeads: Lead[],
  clearPrivateState: () => void,
  now = Date.now(),
): SafeDemoSnapshot {
  clearPrivateState();
  return {
    leads: demoLeads.map((lead) => ({ ...lead, _isDemo: true })),
    session: { authenticated: false, mode: "demo" },
    isDemo: true,
    selectedLead: null,
    meta: { generated_at: new Date(now).toISOString(), source: "demo-session-reset" },
  };
}

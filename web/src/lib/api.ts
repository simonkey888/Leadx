import type { Lead, LeadVertical, SessionInfo } from "../types";
import { DEMO_LEADS } from "../demo-leads";
import { normalizeLeads } from "./multi-line";

const API_BASE = "";

export class SessionExpiredError extends Error {
  constructor() { super("session_expired"); this.name = "SessionExpiredError"; }
}

export async function fetchLeads(authenticated: boolean, vertical: LeadVertical, userActivity = false): Promise<{ leads: Lead[]; meta: Record<string, string>; isDemo: boolean }> {
  if (!authenticated) {
    const leads = normalizeLeads(DEMO_LEADS).filter((lead) => lead.vertical === vertical).map((lead) => ({ ...lead, _isDemo: true }));
    return { leads, meta: { version: "demo-multiline-v1", source: "demo", generated_at: new Date().toISOString() }, isDemo: true };
  }
  const params = new URLSearchParams({ limit: "200", vertical });
  const res = await fetch(`${API_BASE}/api/leads?${params}`, {
    credentials: "include",
    headers: { Accept: "application/json", ...(userActivity ? { "X-LeadX-Activity": "user" } : {}) },
  });
  if (res.status === 401) throw new SessionExpiredError();
  if (!res.ok) throw new Error(`API ${res.status}`);
  const data = await res.json();
  return { leads: normalizeLeads(data.leads_all || []), meta: data.meta || {}, isDemo: false };
}

export async function login(password: string): Promise<{ ok: boolean; error?: string; status?: number }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
  if (res.status === 429) return { ok: false, error: "Demasiados intentos. Esperá 1 minuto.", status: 429 };
  if (!res.ok) { const data = await res.json().catch(() => ({})); return { ok: false, error: data.error || "Contraseña incorrecta", status: res.status }; }
  return { ok: true };
}

export async function importPrivateLeads(payload: unknown): Promise<{ status: string; total: number; imported: number; inserted: number; updated: number }> {
  const res = await fetch(`${API_BASE}/api/admin/import`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-LeadX-Activity": "user" },
    body: JSON.stringify(payload),
  });
  if (res.status === 401) throw new SessionExpiredError();
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.reason || body.error || `Importación rechazada (${res.status})`);
  return body;
}

export async function logout(): Promise<void> { await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" }); }

export async function checkSession(): Promise<SessionInfo> {
  try { const res = await fetch(`${API_BASE}/api/auth/session`, { credentials: "include" }); return res.ok ? await res.json() : { authenticated: false, mode: "demo" }; }
  catch { return { authenticated: false, mode: "demo" }; }
}

export async function continueSession(): Promise<SessionInfo> {
  const res = await fetch(`${API_BASE}/api/auth/activity`, { method: "POST", credentials: "include", headers: { "X-LeadX-Activity": "user" } });
  if (res.status === 401) throw new SessionExpiredError();
  if (!res.ok) throw new Error(`API ${res.status}`);
  return { authenticated: true, mode: "real", ...(await res.json()) };
}

export function relativeTime(lead: Lead): string {
  const ts = lead.created_at || lead.first_seen_at || lead.discovery_timestamp || lead.fecha_iso || lead.fecha_visible;
  if (!ts) return "—";
  const date = new Date(ts); if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return "hace instantes";
  const minutes = Math.floor(seconds / 60); if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60); if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24); if (days < 7) return `hace ${days} d`;
  return `hace ${Math.floor(days / 7)} sem`;
}

export function getWhatsAppUrl(lead: Lead): string | null {
  if (lead._isDemo) return null;
  const phone = lead.whatsapp_publico || lead.telefono_publico || lead.telefono || lead.phone || "";
  const digits = phone.replace(/\D/g, "");
  return digits.length >= 8 ? `https://wa.me/${digits}` : null;
}
export function getMessengerUrl(lead: Lead): string | null { if (lead._isDemo) return null; const id = lead.fb_author_id || lead.fb_username; return id ? `https://m.me/${encodeURIComponent(id)}` : null; }
export function getEmailUrl(lead: Lead): string | null { if (lead._isDemo) return null; const email = lead.email_publico || lead.email; return email ? `mailto:${encodeURIComponent(email)}` : null; }

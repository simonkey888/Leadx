import type { Lead, SessionInfo } from "../types";
import { DEMO_LEADS } from "../demo-leads";

const API_BASE = "";

export async function fetchLeads(authenticated: boolean): Promise<{ leads: Lead[]; meta: any; isDemo: boolean }> {
  if (!authenticated) {
    // PUBLIC MODE — return demo leads, never call /api/leads for real data
    return {
      leads: DEMO_LEADS.map((l) => ({ ...l, _isDemo: true })),
      meta: { version: "demo-v1", source: "demo", generated_at: new Date().toISOString() },
      isDemo: true,
    };
  }

  // AUTHENTICATED MODE — fetch real leads with session cookie
  const res = await fetch(`${API_BASE}/api/leads?limit=200`, {
    credentials: "include",
    headers: { "Accept": "application/json" },
  });

  if (res.status === 401) {
    // Session expired — fallback to demo
    return {
      leads: DEMO_LEADS.map((l) => ({ ...l, _isDemo: true })),
      meta: { version: "demo-v1", source: "demo-fallback" },
      isDemo: true,
    };
  }

  if (!res.ok) throw new Error(`API ${res.status}`);
  const data = await res.json();
  return {
    leads: data.leads_all || [],
    meta: data.meta || {},
    isDemo: false,
  };
}

export async function login(password: string): Promise<{ ok: boolean; error?: string; status?: number }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });

  if (res.status === 429) return { ok: false, error: "Demasiados intentos. Esperá 1 minuto.", status: 429 };
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return { ok: false, error: data.error || "Contraseña incorrecta", status: res.status };
  }
  return { ok: true };
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function checkSession(): Promise<SessionInfo> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/session`, { credentials: "include" });
    if (!res.ok) return { authenticated: false, mode: "demo" };
    return await res.json();
  } catch {
    return { authenticated: false, mode: "demo" };
  }
}

export function relativeTime(lead: Lead): string {
  const ts = lead.first_seen_at || lead.discovery_timestamp || lead.fecha_iso || lead.fecha_visible;
  if (!ts) return "—";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return "hace instantes";
  const min = Math.floor(sec / 60);
  if (min < 60) return `hace ${min} min`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `hace ${hr} h`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `hace ${day} d`;
  const wk = Math.floor(day / 7);
  return `hace ${wk} sem`;
}

export function getWhatsAppUrl(lead: Lead): string | null {
  const phone = lead.whatsapp_publico || lead.telefono_publico || lead.telefono || lead.phone || "";
  if (!phone) return null;
  return `https://wa.me/${phone.replace(/\D/g, "")}`;
}

export function getMessengerUrl(lead: Lead): string | null {
  const id = lead.fb_author_id || lead.fb_username;
  if (!id) return null;
  return `https://m.me/${id}`;
}

export function getEmailUrl(lead: Lead): string | null {
  const email = lead.email_publico || lead.email;
  if (!email) return null;
  return `mailto:${email}`;
}

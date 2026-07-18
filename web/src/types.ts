export type Vertical = "fotomultas" | "repuestos_agricolas";
export type LeadStatus = "Nuevo" | "Contactado" | "Calificado" | "Propuesta" | "Ganado" | "Perdido";
export type LeadPriority = "Alta" | "Media" | "Baja";
export type ContactFilter = "todos" | "whatsapp" | "messenger" | "email" | "sin_contacto";
export type HeatFilter = "todos" | "hot" | "warm" | "cold";
export type HeatLabel = "hot" | "warm" | "cold";

export interface VerticalData {
  plate?: string; municipality?: string; violation_type?: string; estimated_amount?: number; due_date?: string;
  brand?: string; machine_type?: string; model?: string; part_number?: string; quantity?: number; urgency?: string;
}

export interface Lead {
  id: string; vertical?: Vertical; name?: string; province?: string; phone?: string; channel?: string;
  assigned_to?: string; status?: string; priority?: string; created_at?: string; vertical_data?: VerticalData;
  score: number; persona: string; provincia?: string; telefono?: string; telefono_publico?: string; whatsapp_publico?: string;
  platform?: string; source?: string; source_label?: string; source_url?: string; title?: string; snippet?: string;
  fecha_iso?: string; first_seen_at?: string; discovery_timestamp?: string; fecha_visible?: string;
  email?: string; email_publico?: string; fb_username?: string; fb_author_id?: string; whatsapp_confirmed?: boolean;
  _status?: LeadStatus; _priority?: LeadPriority; _notes?: string; _monto?: number; _isDemo?: boolean; _heat_label?: HeatLabel; _heat_score?: number;
  notes?: string; amount?: number; owner?: string; history?: unknown[]; [key: string]: unknown;
}

export interface SessionInfo { authenticated: boolean; mode: "demo" | "real"; idleExpiresAt?: number; absoluteExpiresAt?: number; }

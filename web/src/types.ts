export interface Lead {
  id: string;
  score: number;
  label?: string;
  problem_category?: string;
  problem_summary?: string;
  persona: string;
  author?: string;
  provincia?: string;
  ciudad?: string;
  vehiculo?: string;
  patente?: string;
  fecha_visible?: string;
  fecha_iso?: string;
  first_seen_at?: string;
  discovery_timestamp?: string;
  platform?: string;
  source?: string;
  source_label?: string;
  source_url?: string;
  title?: string;
  snippet?: string;
  quoted_text?: string;
  telefono_publico?: string;
  whatsapp_publico?: string;
  telefono?: string;
  phone?: string;
  email_publico?: string;
  email?: string;
  fb_username?: string;
  fb_author_id?: string;
  image_urls?: string[];
  score_explain?: string[];
  _status?: LeadStatus;
  _notes?: string;
  _monto?: number;
  _heat_label?: HeatLabel;
  _heat_score?: number;
  _isDemo?: boolean;
}

export type LeadStatus = "Nuevo" | "Contactado" | "En gestión" | "Cerrado" | "Descartado";
export type HeatLabel = "hot" | "warm" | "cold";
export type ContactFilter = "todos" | "whatsapp" | "messenger" | "email" | "sin_contacto";
export type HeatFilter = "todos" | "hot" | "warm" | "cold";

export interface SessionInfo {
  authenticated: boolean;
  mode: "demo" | "real";
}

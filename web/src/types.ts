export type LeadVertical = "fotomultas" | "repuestos_agricolas";

export type CommercialLeadStatus = "Nuevo" | "Contactado" | "Calificado" | "Propuesta" | "Ganado" | "Perdido";
export type LegacyLeadStatus = "Revisado" | "En gestión" | "Esperando respuesta" | "Cerrado" | "Descartado";
export type LeadStatus = CommercialLeadStatus | LegacyLeadStatus;
export type LeadPriority = "Alta" | "Media" | "Baja";
export type HeatLabel = "hot" | "warm" | "cold";
export type LeadChannel = "whatsapp" | "messenger" | "email" | "telefono" | "web" | "otro";
export type ContactFilter = "todos" | "whatsapp" | "messenger" | "email" | "sin_contacto";
export type HeatFilter = "todos" | "hot" | "warm" | "cold";

export interface LeadVerticalData {
  plate?: string;
  municipality?: string;
  violation_type?: string;
  estimated_amount?: number;
  due_date?: string;
  brand?: string;
  machine_type?: string;
  model?: string;
  part_number?: string;
  quantity?: number;
  urgency?: LeadPriority | "alta" | "media" | "baja";
  [key: string]: string | number | boolean | undefined;
}

export interface LeadHistoryEntry {
  at?: string;
  action?: string;
  detail?: string;
}

export interface Lead {
  id: string;
  score?: number;
  vertical?: LeadVertical;
  vertical_data?: LeadVerticalData;

  name?: string;
  province?: string;
  phone?: string;
  channel?: LeadChannel | string;
  assigned_to?: string;
  status?: LeadStatus | string;
  priority?: LeadPriority | string;
  created_at?: string;
  whatsapp_confirmed?: boolean;
  history?: LeadHistoryEntry[];

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
  email_publico?: string;
  email?: string;
  fb_username?: string;
  fb_author_id?: string;
  image_urls?: string[];
  score_explain?: string[];
  owner?: string;
  amount?: number;
  notes?: string;
  contacted_at?: string;
  next_action_at?: string;
  last_activity_at?: string;

  _status?: LeadStatus;
  _priority?: LeadPriority;
  _notes?: string;
  _monto?: number;
  _heat_label?: HeatLabel;
  _heat_score?: number;
  _isDemo?: boolean;
  _history?: LeadHistoryEntry[];
}

export interface LeadFilters {
  status: CommercialLeadStatus | "todos";
  priority: LeadPriority | "todos";
  province: string;
  channel: string;
  assigned: string;
  date: "todos" | "7d" | "30d" | "90d";
  municipality: string;
  violationType: string;
  plate: string;
  brand: string;
  machineType: string;
  partNumber: string;
  urgency: string;
}

export interface SessionInfo {
  authenticated: boolean;
  mode: "demo" | "real";
  idleExpiresAt?: number;
  absoluteExpiresAt?: number;
}

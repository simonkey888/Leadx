import type { Lead, ContactFilter, HeatFilter, LeadStatus } from "../types";

interface Props {
  leads: Lead[];
  search: string; setSearch: (s: string) => void;
  statusFilter: LeadStatus | "todos"; setStatusFilter: (s: LeadStatus | "todos") => void;
  contactFilter: ContactFilter; setContactFilter: (c: ContactFilter) => void;
  heatFilter: HeatFilter; setHeatFilter: (h: HeatFilter) => void;
}

const STATUSES: (LeadStatus | "todos")[] = ["Nuevo", "Contactado", "En gestión", "Cerrado", "Descartado"];

export function Filters({ leads, search, setSearch, statusFilter, setStatusFilter, contactFilter, setContactFilter, heatFilter, setHeatFilter }: Props) {
  const count = (filter: string): number => leads.filter((l) => {
    if (filter === "todos") return true;
    if (filter === "whatsapp") return !!(l.whatsapp_publico || l.telefono_publico || l.telefono || l.phone);
    if (filter === "messenger") return !!(l.fb_username || l.fb_author_id);
    if (filter === "email") return !!(l.email_publico || l.email);
    if (filter === "sin_contacto") return !(l.whatsapp_publico || l.telefono_publico || l.telefono || l.phone || l.fb_username || l.fb_author_id || l.email_publico || l.email);
    if (filter === "hot") return (l._heat_score ?? l.score ?? 0) >= 70;
    if (filter === "warm") { const s = l._heat_score ?? l.score ?? 0; return s >= 40 && s < 70; }
    if (filter === "cold") return (l._heat_score ?? l.score ?? 0) < 40;
    return l._status === filter;
  }).length;

  return (
    <div className="filters">
      <input type="search" className="filters__search" placeholder="Buscar por nombre, provincia, problema…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Buscar leads" />
      <div className="filters__group">
        <span className="filters__label">Estado</span>
        <button className={`filter-chip ${statusFilter === "todos" ? "filter-chip--active" : ""}`} onClick={() => setStatusFilter("todos")}>Todos <span className="filter-chip__count">{count("todos")}</span></button>
        {STATUSES.filter((s) => s !== "todos").map((s) => (
          <button key={s} className={`filter-chip ${statusFilter === s ? "filter-chip--active" : ""}`} onClick={() => setStatusFilter(s)}>{s} <span className="filter-chip__count">{count(s)}</span></button>
        ))}
      </div>
      <div className="filters__group">
        <span className="filters__label">Contacto</span>
        {(["todos", "whatsapp", "messenger", "email", "sin_contacto"] as ContactFilter[]).map((c) => (
          <button key={c} className={`filter-chip ${contactFilter === c ? "filter-chip--active" : ""}`} onClick={() => setContactFilter(c)}>{labelContact(c)} <span className="filter-chip__count">{count(c)}</span></button>
        ))}
      </div>
      <div className="filters__group">
        <span className="filters__label">Prioridad</span>
        {(["todos", "hot", "warm", "cold"] as HeatFilter[]).map((h) => (
          <button key={h} className={`filter-chip ${heatFilter === h ? "filter-chip--active" : ""}`} onClick={() => setHeatFilter(h)}>{labelHeat(h)} <span className="filter-chip__count">{count(h)}</span></button>
        ))}
      </div>
    </div>
  );
}

function labelContact(c: ContactFilter): string { return c === "todos" ? "Todos" : c === "sin_contacto" ? "Sin contacto" : c === "whatsapp" ? "WhatsApp" : c === "messenger" ? "Messenger" : "Email"; }
function labelHeat(h: HeatFilter): string { return h === "todos" ? "Todas" : h === "hot" ? "Alta" : h === "warm" ? "Media" : "Baja"; }

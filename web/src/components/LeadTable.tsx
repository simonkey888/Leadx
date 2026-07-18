import { CalendarDays } from "lucide-react";
import type { Lead } from "../types";
import { leadAssigned, leadChannel, leadContext, leadCreatedAt, leadName, leadProvince } from "../lib/multi-line";
import { relativeTime } from "../lib/api";
import { Badge } from "./Badge";
import { PhoneWhatsApp } from "./PhoneWhatsApp";

interface Props { leads: Lead[]; selectedId?: string; onSelect: (lead: Lead) => void; onActivity?: () => void; }
const channelLabel: Record<string, string> = { whatsapp: "WhatsApp", messenger: "Messenger", email: "Email", telefono: "Teléfono", web: "Web", otro: "Otro" };

export function LeadTable({ leads, selectedId, onSelect, onActivity }: Props) {
  if (leads.length === 0) return <div className="empty">No hay leads que coincidan con los filtros.</div>;
  return (
    <section className="lead-table" aria-label="Tabla de leads">
      <div className="lead-table__head" aria-hidden="true">
        <span>#</span><span>Lead</span><span>Provincia</span><span>Teléfono</span><span>Canal</span><span>Asignado a</span><span>Estado</span><span>Creado</span>
      </div>
      <div className="lead-list" role="list" aria-label="Lista de leads">
        {leads.map((lead, index) => (
          <article key={lead.id} role="listitem" tabIndex={0} className={`lead-row ${selectedId === lead.id ? "lead-row--selected" : ""}`}
            onClick={() => { onActivity?.(); onSelect(lead); }}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onActivity?.(); onSelect(lead); } }}>
            <span className="lead-row__index">{String(index + 1).padStart(2, "0")}</span>
            <div className="lead-row__identity"><strong>{leadName(lead)}</strong><span>{leadContext(lead)}</span></div>
            <span className="lead-row__province">{leadProvince(lead)}</span>
            <div className="lead-row__phone"><PhoneWhatsApp lead={lead} compact onActivity={onActivity} /></div>
            <span className="lead-row__channel">{channelLabel[leadChannel(lead)] || leadChannel(lead)}</span>
            <span className="lead-row__assigned">{leadAssigned(lead)}</span>
            <span className="lead-row__status"><Badge lead={lead} /></span>
            <span className="lead-row__created" title={leadCreatedAt(lead)}><CalendarDays size={13} aria-hidden="true" />{relativeTime(lead)}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

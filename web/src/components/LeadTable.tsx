import { CalendarDays } from "lucide-react";
import type { Lead } from "../types";
import { leadAssigned, leadChannel, leadContext, leadName, leadProvince } from "../lib/multi-line";
import { relativeTime } from "../lib/api";
import { Badge } from "./Badge";
import { PhoneWhatsApp } from "./PhoneWhatsApp";

interface Props { leads: Lead[]; selectedId?: string; onSelect: (lead: Lead) => void; onActivity?: () => void; }
const channelLabel: Record<string, string> = { whatsapp: "WhatsApp", messenger: "Messenger", email: "Email", telefono: "Teléfono", web: "Web", otro: "Otro" };

export function LeadTable({ leads, selectedId, onSelect, onActivity }: Props) {
  if (leads.length === 0) return <div className="empty">No hay leads que coincidan con los filtros.</div>;
  const select = (lead: Lead) => { onActivity?.(); onSelect(lead); };
  return (
    <section className="table-shell" aria-label="Tabla de leads">
      <table className="lead-table">
        <thead><tr><th>#</th><th>Lead</th><th>Provincia</th><th>Teléfono</th><th>Canal</th><th>Asignado a</th><th>Estado</th><th>Creado</th></tr></thead>
        <tbody>{leads.map((lead, index) => (
          <tr key={lead.id} tabIndex={0} className={selectedId === lead.id ? "lead-row--selected" : ""} onClick={() => select(lead)}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(lead); } }}>
            <td className="lead-index">{String(index + 1).padStart(2, "0")}</td>
            <td><strong>{leadName(lead)}</strong><small>{leadContext(lead)}</small></td>
            <td>{leadProvince(lead)}</td>
            <td><PhoneWhatsApp lead={lead} compact onActivity={onActivity} /></td>
            <td>{channelLabel[leadChannel(lead)] || leadChannel(lead)}</td>
            <td>{leadAssigned(lead)}</td>
            <td><Badge lead={lead} /></td>
            <td><span className="created-cell"><CalendarDays size={13} aria-hidden="true" />{relativeTime(lead)}</span></td>
          </tr>
        ))}</tbody>
      </table>

      <div className="mobile-cards" role="list" aria-label="Lista de leads">
        {leads.map((lead) => (
          <article key={lead.id} role="listitem" tabIndex={0} className={`lead-card ${selectedId === lead.id ? "lead-card--selected" : ""}`}
            onClick={() => select(lead)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(lead); } }}>
            <div className="card-head"><div><strong>{leadName(lead)}</strong><small>{leadContext(lead)}</small></div><Badge lead={lead} /></div>
            <div className="card-meta"><span>{leadProvince(lead)}</span><span>{channelLabel[leadChannel(lead)] || leadChannel(lead)}</span></div>
            <div className="card-assigned">Asignado a {leadAssigned(lead)} · {relativeTime(lead)}</div>
            <div className="card-phone"><PhoneWhatsApp lead={lead} compact onActivity={onActivity} /></div>
          </article>
        ))}
      </div>
    </section>
  );
}

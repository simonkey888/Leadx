import { CalendarDays } from "lucide-react";
import type { Lead } from "../types";
import { leadChannel, leadContext, leadName, leadProvince } from "../lib/multi-line";
import { relativeTime } from "../lib/api";
import { Badge } from "./Badge";
import { ContactStatusBadge } from "./ContactStatusBadge";
import { PhoneWhatsApp } from "./PhoneWhatsApp";
import { PotentialBadge } from "./PotentialBadge";

interface Props { leads: Lead[]; selectedId?: string; onSelect: (lead: Lead) => void; onActivity?: () => void; }
const channelLabel: Record<string, string> = { whatsapp: "WhatsApp", messenger: "Messenger", email: "Email", telefono: "Teléfono", web: "Web", otro: "Otro" };
const tempLabel: Record<string, string> = { MUY_CALIENTE: "Muy caliente", CALIENTE: "Caliente", TIBIO: "Tibio", FRIO: "Frío", DESCARTADO: "Descartado" };

export function LeadTable({ leads, selectedId, onSelect, onActivity }: Props) {
  if (leads.length === 0) return <div className="empty">No hay leads que coincidan con los filtros.</div>;
  const select = (lead: Lead) => { onActivity?.(); onSelect(lead); };
  const isAgro = leads.some((lead) => lead.vertical === "repuestos_agricolas");
  return (
    <section className="table-shell" aria-label="Tabla de leads">
      <table className="lead-table">
        <thead><tr><th>Lead</th><th>Provincia</th><th>Teléfono</th>{isAgro ? <><th>Temperatura</th><th>Próxima acción</th></> : <th>Canal</th>}<th>Potencial</th><th>Creado</th></tr></thead>
        <tbody>{leads.map((lead) => (
          <tr key={lead.id} tabIndex={0} className={selectedId === lead.id ? "lead-row--selected" : ""} onClick={() => select(lead)}
            onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(lead); } }}>
            <td><strong>{lead.company || leadName(lead)}</strong><small>{lead.contact_name ? `${lead.contact_name} · ${leadContext(lead)}` : leadContext(lead)}</small></td>
            <td>{leadProvince(lead)}</td>
            <td><PhoneWhatsApp lead={lead} compact onActivity={onActivity} /></td>
            {isAgro ? <><td><span className={`temperature temperature--${String(lead.temperature || "FRIO").toLowerCase()}`}>{tempLabel[String(lead.temperature || "FRIO")] || lead.temperature || "Frío"}</span></td><td><small className="next-action-cell">{lead.next_action || "Definir próxima acción"}</small></td></> : <td>{channelLabel[leadChannel(lead)] || leadChannel(lead)}</td>}
            <td><span className="commercial-signals"><PotentialBadge lead={lead} /><ContactStatusBadge lead={lead} /></span></td>
            <td><span className="created-cell"><CalendarDays size={13} aria-hidden="true" />{relativeTime(lead)}</span></td>
          </tr>
        ))}</tbody>
      </table>

      <div className="mobile-cards" role="list" aria-label="Lista de leads">
        {leads.map((lead) => (
          <article key={lead.id} role="listitem" tabIndex={0} className={`lead-card ${selectedId === lead.id ? "lead-card--selected" : ""}`}
            onClick={() => select(lead)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(lead); } }}>
            <div className="card-head"><div><strong>{lead.company || leadName(lead)}</strong><small>{lead.contact_name ? `${lead.contact_name} · ${leadContext(lead)}` : leadContext(lead)}</small></div><Badge lead={lead} /></div>
            <div className="card-meta"><span>{leadProvince(lead)}</span><span>{isAgro ? (tempLabel[String(lead.temperature || "FRIO")] || "Frío") : (channelLabel[leadChannel(lead)] || leadChannel(lead))}</span></div>
            {isAgro && <p className="card-next-action"><strong>Próxima acción:</strong> {lead.next_action || "Definir"}</p>}
            <div className="card-potential"><span className="commercial-signals"><PotentialBadge lead={lead} /><ContactStatusBadge lead={lead} /></span><span>{relativeTime(lead)}</span></div>
            <div className="card-phone"><PhoneWhatsApp lead={lead} compact onActivity={onActivity} /></div>
          </article>
        ))}
      </div>
    </section>
  );
}

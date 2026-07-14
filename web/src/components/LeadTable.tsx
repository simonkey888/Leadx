import { MapPin, Clock, Facebook, Globe } from "lucide-react";
import type { Lead } from "../types";
import { relativeTime } from "../lib/api";
import { Badge } from "./Badge";
import { Actions } from "./Actions";

export function LeadTable({ leads }: { leads: Lead[] }) {
  if (leads.length === 0) {
    return <div className="empty">No hay leads que coincidan con los filtros</div>;
  }
  return (
    <div className="table-wrap">
      <table className="table" aria-label="Lista de leads">
        <thead>
          <tr>
            <th scope="col">Lead</th>
            <th scope="col">Estado · Prioridad</th>
            <th scope="col">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => (
            <tr key={lead.id}>
              <td>
                <div className="lead-cell">
                  <div className="lead-cell__name">{lead.persona || "Sin nombre"}</div>
                  <div className="lead-cell__meta">
                    {lead.provincia && <><MapPin size={12} aria-hidden="true" />{lead.provincia}</>}
                    <SourceIcon lead={lead} />
                    <Clock size={12} aria-hidden="true" />{relativeTime(lead)}
                  </div>
                  <div className="lead-cell__problem">{lead.title || lead.snippet || "—"}</div>
                </div>
              </td>
              <td><Badge lead={lead} /></td>
              <td><Actions lead={lead} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceIcon({ lead }: { lead: Lead }) {
  const src = (lead.source || lead.platform || "").toLowerCase();
  if (src.includes("facebook")) return <><Facebook size={12} aria-hidden="true" />Facebook</>;
  if (src.includes("reddit")) return <><Globe size={12} aria-hidden="true" />Reddit</>;
  return <><Globe size={12} aria-hidden="true" />{lead.source_label || lead.platform || "—"}</>;
}

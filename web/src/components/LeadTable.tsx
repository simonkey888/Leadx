import { Clock, Facebook, Globe, MapPin } from "lucide-react";
import type { Lead } from "../types";
import { relativeTime } from "../lib/api";
import { Badge } from "./Badge";
import { Actions } from "./Actions";

interface Props {
  leads: Lead[];
  selectedId?: string;
  onSelect: (lead: Lead) => void;
  onActivity?: () => void;
}

export function LeadTable({ leads, selectedId, onSelect, onActivity }: Props) {
  if (leads.length === 0) return <div className="empty">No hay leads que coincidan con los filtros.</div>;
  return (
    <div className="lead-list" role="list" aria-label="Lista de leads">
      {leads.map((lead) => (
        <article
          key={lead.id}
          role="listitem"
          tabIndex={0}
          className={`lead-row ${selectedId === lead.id ? "lead-row--selected" : ""}`}
          onClick={() => { onActivity?.(); onSelect(lead); }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault(); onActivity?.(); onSelect(lead);
            }
          }}
        >
          <div className="lead-row__main">
            <div className="lead-row__heading">
              <strong>{lead.persona || "Sin nombre"}</strong>
              <span className="lead-row__time">{relativeTime(lead)}</span>
            </div>
            <div className="lead-row__meta">
              {lead.provincia && <><MapPin size={13} aria-hidden="true" />{lead.provincia}<span>·</span></>}
              <Source lead={lead} />
              <span className="desktop-only">· <Clock size={13} aria-hidden="true" />{relativeTime(lead)}</span>
            </div>
            <p className="lead-row__problem">{lead.snippet || lead.title || "Sin descripción"}</p>
          </div>
          <div className="lead-row__badge"><Badge lead={lead} /></div>
          <div className="lead-row__actions"><Actions lead={lead} labels onActivity={onActivity} /></div>
        </article>
      ))}
    </div>
  );
}

function Source({ lead }: { lead: Lead }) {
  const source = (lead.source || lead.platform || "").toLowerCase();
  if (source.includes("facebook")) return <><Facebook size={13} aria-hidden="true" />Facebook</>;
  return <><Globe size={13} aria-hidden="true" />{lead.source_label || lead.platform || "Web"}</>;
}

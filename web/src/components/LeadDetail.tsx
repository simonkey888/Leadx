import { ArrowLeft, CalendarDays, ExternalLink, MapPin, X } from "lucide-react";
import type { Lead } from "../types";
import { relativeTime } from "../lib/api";
import { Actions } from "./Actions";
import { Badge } from "./Badge";

export function LeadDetail({ lead, onClose, onActivity }: { lead: Lead; onClose: () => void; onActivity?: () => void }) {
  const date = lead.first_seen_at || lead.discovery_timestamp || lead.fecha_iso || lead.fecha_visible;
  return (
    <div className="detail-layer" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="lead-detail" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <header className="lead-detail__header">
          <button className="icon-button lead-detail__back" onClick={onClose} aria-label="Volver"><ArrowLeft size={20} /></button>
          <div><span className="eyebrow">Detalle del lead</span><h2 id="detail-title">{lead.persona || "Sin nombre"}</h2></div>
          <button className="icon-button lead-detail__close" onClick={onClose} aria-label="Cerrar"><X size={20} /></button>
        </header>
        <div className="lead-detail__body">
          <Badge lead={lead} />
          <div className="detail-meta">
            {lead.provincia && <span><MapPin size={15} />{lead.provincia}</span>}
            <span><CalendarDays size={15} />{relativeTime(lead)}</span>
          </div>
          {date && <time className="exact-date" dateTime={new Date(date).toISOString()}>{new Date(date).toLocaleString("es-AR")}</time>}
          <section><h3>Problema</h3><p className="detail-problem">{lead.snippet || lead.quoted_text || lead.title || "Sin descripción"}</p></section>
          {(lead.telefono_publico || lead.whatsapp_publico || lead.email_publico || lead.email) && (
            <section><h3>Contacto</h3><p>{lead.telefono_publico || lead.whatsapp_publico || lead.email_publico || lead.email}</p></section>
          )}
          {lead.source_url && <a className="source-link" href={lead.source_url} target="_blank" rel="noopener noreferrer" onClick={onActivity}>Abrir publicación original <ExternalLink size={15} /></a>}
        </div>
        <footer className="lead-detail__footer"><Actions lead={lead} labels onActivity={onActivity} /></footer>
      </aside>
    </div>
  );
}

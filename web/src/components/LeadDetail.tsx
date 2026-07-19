import { ArrowLeft, CalendarDays, ExternalLink, MapPin, X } from "lucide-react";
import type { Lead } from "../types";
import { contactStateExplanation } from "../lib/contact-state";
import { leadAssigned, leadChannel, leadCreatedAt, leadName, leadPriority, leadProvince, verticalLabel } from "../lib/multi-line";
import { relativeTime } from "../lib/api";
import { Actions } from "./Actions";
import { Badge } from "./Badge";
import { ContactStatusBadge } from "./ContactStatusBadge";
import { PhoneWhatsApp } from "./PhoneWhatsApp";

const money = new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 });
const channelLabel: Record<string, string> = { whatsapp: "WhatsApp", messenger: "Messenger", email: "Email", telefono: "Teléfono", web: "Web", otro: "Otro" };
const tempLabel: Record<string, string> = { MUY_CALIENTE: "Muy caliente", CALIENTE: "Caliente", TIBIO: "Tibio", FRIO: "Frío", DESCARTADO: "Descartado" };

export function LeadDetail({ lead, onClose, onActivity }: { lead: Lead; onClose: () => void; onActivity?: () => void }) {
  const date = leadCreatedAt(lead);
  const sourceUrl = lead._isDemo ? null : lead.source_url;
  const data = lead.vertical_data || {};
  const history = lead.history || lead._history || [];
  const amount = lead._monto ?? lead.amount ?? (typeof data.estimated_amount === "number" ? data.estimated_amount : undefined);
  const agro = lead.vertical === "repuestos_agricolas";
  return (
    <div className="detail-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="lead-detail" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <header className="lead-detail__header">
          <button className="icon-button lead-detail__back" onClick={onClose} aria-label="Volver"><ArrowLeft size={20} /></button>
          <div><span className="eyebrow">{verticalLabel(lead.vertical || "fotomultas")}</span><h2 id="detail-title">{lead.company || leadName(lead)}</h2>{agro && lead.contact_name && <p>{lead.contact_name}</p>}</div>
          <button className="icon-button lead-detail__close" onClick={onClose} aria-label="Cerrar"><X size={20} /></button>
        </header>
        <div className="lead-detail__body">
          <div className="detail-badges"><Badge lead={lead} /><ContactStatusBadge lead={lead} /><span className="priority-caption">Prioridad {leadPriority(lead)}</span>{agro && <span className="priority-caption">{tempLabel[String(lead.temperature || "FRIO")] || lead.temperature || "Frío"}</span>}</div>
          <div className="contact-state-panel">
            <div><strong>Seguimiento de contacto</strong><p>{lead._isDemo ? "Estado ficticio de demostración. No modifica ningún registro." : contactStateExplanation(lead)}</p></div>
            <button type="button" className="btn contact-state-action" disabled title="Requiere persistencia segura en el backend">Marcar como contactado</button>
          </div>
          <div className="detail-contact-card"><PhoneWhatsApp lead={lead} onActivity={onActivity} /><span>{channelLabel[leadChannel(lead)] || leadChannel(lead)}</span></div>
          <div className="detail-meta"><span><MapPin size={15} aria-hidden="true" />{leadProvince(lead)}</span><span><CalendarDays size={15} aria-hidden="true" />{relativeTime(lead)}</span><span>Asignado a {leadAssigned(lead)}</span></div>
          {date && <time className="exact-date" dateTime={new Date(date).toISOString()}>{new Date(date).toLocaleString("es-AR")}</time>}
          <section><h3>Contexto</h3><p className="detail-problem">{lead.snippet || lead.quoted_text || lead.title || "Sin descripción"}</p></section>
          {agro && <>
            <section><h3>Lectura comercial</h3><p>{lead.commercial_reading || "Sin lectura comercial registrada."}</p></section>
            <section><h3>Próxima acción</h3><p>{lead.next_action || "Sin próxima acción definida."}</p></section>
            {lead.literal_response && <section><h3>Respuesta literal</h3><p>{lead.literal_response}</p></section>}
            {lead.suggested_message && <section><h3>Mensaje sugerido</h3><p>{lead.suggested_message}</p></section>}
            {lead.reengagement_message && <section><h3>Reencare</h3><p>{lead.reengagement_message}</p></section>}
            <section><h3>Calificación</h3><dl className="detail-grid"><Field label="Temperatura" value={tempLabel[String(lead.temperature || "FRIO")] || lead.temperature} /><Field label="Score potencial" value={lead.potential_score ?? lead.score} /><Field label="Bucket ejecutivo" value={lead.executive_bucket} /><Field label="Estado de respuesta" value={lead.response_state} /><Field label="Capacidad de compra" value={lead.purchase_capacity} /><Field label="Autoridad de decisión" value={lead.decision_authority} /></dl></section>
            <section><h3>Interés</h3><p>{lead.products_interest?.join(" · ") || "Sin productos de interés definidos."}</p></section>
            {lead.missing_information && <section><h3>Información faltante</h3><p>{lead.missing_information}</p></section>}
          </>}
          <section><h3>Datos de la línea</h3><dl className="detail-grid">{agro ? <><Field label="Marca" value={data.brand} /><Field label="Tipo de máquina" value={data.machine_type} /><Field label="Modelo" value={data.model} /><Field label="Número de pieza" value={data.part_number} /><Field label="Cantidad" value={data.quantity} /><Field label="Urgencia" value={data.urgency} /></> : <><Field label="Patente" value={data.plate || lead.patente} /><Field label="Municipio" value={data.municipality || lead.ciudad} /><Field label="Tipo de infracción" value={data.violation_type || lead.problem_category} /><Field label="Monto estimado" value={typeof data.estimated_amount === "number" ? money.format(data.estimated_amount) : undefined} /><Field label="Vencimiento" value={data.due_date} /></>}</dl></section>
          <section><h3>Notas</h3><p>{lead._notes || lead.notes || "Sin notas registradas."}</p></section>
          {!agro && <section><h3>Monto</h3><p>{typeof amount === "number" ? money.format(amount) : "Sin monto registrado."}</p></section>}
          <section><h3>Historial</h3>{history.length > 0 ? <ol className="history-list">{history.map((entry, index) => <li key={`${entry.at || "event"}-${index}`}><strong>{entry.action || "Actividad"}</strong><span>{entry.detail || entry.at || "Seguimiento registrado"}</span></li>)}</ol> : <p>Sin actividad adicional registrada.</p>}</section>
          {sourceUrl ? <a className="source-link" href={sourceUrl} target="_blank" rel="noopener noreferrer" onClick={onActivity}>Abrir fuente original <ExternalLink size={15} /></a> : lead._isDemo ? <p className="demo-action-note">Todos los datos visibles en este modo son ficticios.</p> : null}
        </div>
        <footer className="lead-detail__footer"><Actions lead={lead} labels onActivity={onActivity} /></footer>
      </aside>
    </div>
  );
}

function Field({ label, value }: { label: string; value: unknown }) {
  if (value === undefined || value === null || String(value).trim() === "") return null;
  return <div><dt>{label}</dt><dd>{String(value)}</dd></div>;
}

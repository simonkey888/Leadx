import { Mail, Send } from "lucide-react";
import type { Lead } from "../types";
import { getWhatsAppUrl, getMessengerUrl, getEmailUrl } from "../lib/api";
import { WhatsAppIcon } from "./WhatsAppIcon";

export function Actions({ lead, labels = false, onActivity }: { lead: Lead; labels?: boolean; onActivity?: () => void }) {
  if (lead._isDemo) {
    return (
      <div className="actions actions--demo" onClick={(event) => event.stopPropagation()} aria-label="Acciones simuladas">
        <button type="button" className="action-btn action-btn--disabled" disabled title="Acción disponible con datos reales"><WhatsAppIcon size={16} />{labels && <span>WhatsApp</span>}</button>
        <button type="button" className="action-btn action-btn--disabled" disabled title="Acción disponible con datos reales"><Send size={16} aria-hidden="true" />{labels && <span>Facebook</span>}</button>
        <button type="button" className="action-btn action-btn--disabled" disabled title="Acción disponible con datos reales"><Mail size={16} aria-hidden="true" />{labels && <span>Email</span>}</button>
        {labels && <span className="demo-action-note">Acciones disponibles con datos reales</span>}
      </div>
    );
  }
  const wa = getWhatsAppUrl(lead); const messenger = getMessengerUrl(lead); const email = getEmailUrl(lead);
  return (
    <div className="actions" onClick={(event) => event.stopPropagation()}>
      <a href={wa || "#"} target={wa ? "_blank" : undefined} rel={wa ? "noopener noreferrer" : undefined} className={`action-btn action-btn--wa ${!wa ? "action-btn--disabled" : ""}`} aria-label={wa ? "WhatsApp" : "Sin WhatsApp"} title="WhatsApp" onClick={(event) => { if (!wa) event.preventDefault(); else onActivity?.(); }}><WhatsAppIcon size={16} />{labels && <span>WhatsApp</span>}</a>
      <a href={messenger || "#"} target={messenger ? "_blank" : undefined} rel={messenger ? "noopener noreferrer" : undefined} className={`action-btn action-btn--messenger ${!messenger ? "action-btn--disabled" : ""}`} aria-label={messenger ? "Messenger" : "Sin Messenger"} title="Messenger" onClick={(event) => { if (!messenger) event.preventDefault(); else onActivity?.(); }}><Send size={16} aria-hidden="true" />{labels && <span>Facebook</span>}</a>
      <a href={email || "#"} className={`action-btn action-btn--email ${!email ? "action-btn--disabled" : ""}`} aria-label={email ? "Email" : "Sin email"} title="Email" onClick={(event) => { if (!email) event.preventDefault(); else onActivity?.(); }}><Mail size={16} aria-hidden="true" />{labels && <span>Email</span>}</a>
    </div>
  );
}

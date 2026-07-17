import { MessageCircle, Mail, Send } from "lucide-react";
import type { Lead } from "../types";
import { getWhatsAppUrl, getMessengerUrl, getEmailUrl } from "../lib/api";

export function Actions({ lead, labels = false, onActivity }: { lead: Lead; labels?: boolean; onActivity?: () => void }) {
  const wa = getWhatsAppUrl(lead);
  const msg = getMessengerUrl(lead);
  const email = getEmailUrl(lead);

  return (
    <div className="actions" onClick={(event) => event.stopPropagation()}>
      <a href={wa || "#"} target={wa ? "_blank" : undefined} rel={wa ? "noopener noreferrer" : undefined}
         className={`action-btn action-btn--wa ${!wa ? "action-btn--disabled" : ""}`}
         aria-label={wa ? "WhatsApp" : "Sin WhatsApp"} title="WhatsApp"
         onClick={(e) => { if (!wa) e.preventDefault(); else onActivity?.(); }}>
        <MessageCircle size={16} aria-hidden="true" />
        {labels && <span>WhatsApp</span>}
      </a>
      <a href={msg || "#"} target={msg ? "_blank" : undefined} rel={msg ? "noopener noreferrer" : undefined}
         className={`action-btn action-btn--messenger ${!msg ? "action-btn--disabled" : ""}`}
         aria-label={msg ? "Messenger" : "Sin Messenger"} title="Messenger"
         onClick={(e) => { if (!msg) e.preventDefault(); else onActivity?.(); }}>
        <Send size={16} aria-hidden="true" />
        {labels && <span>Facebook</span>}
      </a>
      <a href={email || "#"}
         className={`action-btn action-btn--email ${!email ? "action-btn--disabled" : ""}`}
         aria-label={email ? "Email" : "Sin email"} title="Email"
         onClick={(e) => { if (!email) e.preventDefault(); else onActivity?.(); }}>
        <Mail size={16} aria-hidden="true" />
        {labels && <span>Email</span>}
      </a>
    </div>
  );
}

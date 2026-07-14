import { MessageCircle, Mail, Send } from "lucide-react";
import type { Lead } from "../types";
import { getWhatsAppUrl, getMessengerUrl, getEmailUrl } from "../lib/api";

export function Actions({ lead }: { lead: Lead }) {
  const wa = getWhatsAppUrl(lead);
  const msg = getMessengerUrl(lead);
  const email = getEmailUrl(lead);

  return (
    <div className="actions">
      <a href={wa || "#"} target={wa ? "_blank" : undefined} rel={wa ? "noopener noreferrer" : undefined}
         className={`action-btn action-btn--wa ${!wa ? "action-btn--disabled" : ""}`}
         aria-label={wa ? "WhatsApp" : "Sin WhatsApp"} title="WhatsApp"
         onClick={(e) => { if (!wa) e.preventDefault(); }}>
        <MessageCircle size={16} aria-hidden="true" />
      </a>
      <a href={msg || "#"} target={msg ? "_blank" : undefined} rel={msg ? "noopener noreferrer" : undefined}
         className={`action-btn action-btn--messenger ${!msg ? "action-btn--disabled" : ""}`}
         aria-label={msg ? "Messenger" : "Sin Messenger"} title="Messenger"
         onClick={(e) => { if (!msg) e.preventDefault(); }}>
        <Send size={16} aria-hidden="true" />
      </a>
      <a href={email || "#"}
         className={`action-btn action-btn--email ${!email ? "action-btn--disabled" : ""}`}
         aria-label={email ? "Email" : "Sin email"} title="Email"
         onClick={(e) => { if (!email) e.preventDefault(); }}>
        <Mail size={16} aria-hidden="true" />
      </a>
    </div>
  );
}

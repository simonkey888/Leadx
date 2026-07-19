import { MessageCircle } from "lucide-react";
import type { Lead } from "../types";
import { formatPhone, leadName, leadPhone, whatsappUrl } from "../lib/multi-line";

export function PhoneWhatsApp({ lead, compact = false, onActivity }: { lead: Lead; compact?: boolean; onActivity?: () => void }) {
  const phone = leadPhone(lead);
  const availableUrl = whatsappUrl(lead);
  const url = lead._isDemo ? null : availableUrl;
  const demoDisabled = lead._isDemo === true && Boolean(availableUrl);
  return (
    <span className={`phone-wa ${compact ? "phone-wa--compact" : ""}`}>
      <span className="phone-wa__number">{formatPhone(phone)}</span>
      {url && (
        <a className="phone-wa__button" href={url} target="_blank" rel="noopener noreferrer" title="Abrir WhatsApp"
          aria-label={`Abrir WhatsApp de ${leadName(lead)}`} onClick={(event) => { event.stopPropagation(); onActivity?.(); }}>
          <MessageCircle size={15} aria-hidden="true" /><span className="phone-wa__label">WhatsApp</span>
        </a>
      )}
      {demoDisabled && (
        <button type="button" className="phone-wa__button phone-wa__button--disabled" disabled title="WhatsApp deshabilitado en modo demo"
          aria-label={`WhatsApp deshabilitado para ${leadName(lead)} porque el lead es ficticio`} onClick={(event) => event.stopPropagation()}>
          <MessageCircle size={15} aria-hidden="true" /><span className="phone-wa__label">WhatsApp</span>
        </button>
      )}
    </span>
  );
}

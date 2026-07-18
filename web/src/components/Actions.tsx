import { MessageCircle } from "lucide-react";
import type { Lead } from "../types";
import { getWhatsAppUrl } from "../lib/api";

export function Actions({ lead, labels=false, onActivity }: { lead:Lead; labels?:boolean; onActivity?:()=>void }) {
  const wa=getWhatsAppUrl(lead);
  if(!wa) return null;
  return <a className="wa-button" href={wa} target="_blank" rel="noopener noreferrer" title="Abrir WhatsApp"
    aria-label={`Abrir WhatsApp de ${lead.name||lead.persona||"lead"}`} onClick={e=>{e.stopPropagation();onActivity?.();}}>
    <MessageCircle size={16} aria-hidden="true" />{labels&&<span>WhatsApp</span>}
  </a>;
}

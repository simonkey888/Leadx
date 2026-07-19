import type { Lead } from "../types";
import { leadContactState } from "../lib/contact-state";

export function ContactStatusBadge({ lead }: { lead: Lead }) {
  const state = leadContactState(lead);
  return (
    <span className={`contact-state contact-state--${state === "CONTACTADO" ? "yes" : "no"}`}>
      <span className="contact-state__dot" aria-hidden="true" />
      {state}
    </span>
  );
}

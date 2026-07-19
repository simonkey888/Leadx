import type { Lead } from "../types";
import { leadPriority, leadStatus } from "../lib/multi-line";

export function Badge({ lead }: { lead: Lead }) {
  const status = leadStatus(lead);
  const priority = leadPriority(lead);
  return (
    <span className={`badge badge--${status.toLocaleLowerCase("es").replaceAll(" ", "-")}`} title={`Estado: ${status} · Prioridad: ${priority}`}>
      <span className="badge__dot" aria-hidden="true" /><span>{status}</span><span className="badge__sep">·</span><span>{priority}</span>
    </span>
  );
}

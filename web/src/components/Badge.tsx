import type { Lead } from "../types";
import { heatLabel, heatLabelEs, statusLabel } from "../lib/heatmap";

export function Badge({ lead }: { lead: Lead }) {
  const hl = heatLabel(lead);
  const status = statusLabel(lead);
  return (
    <span className={`badge badge--${hl}`} title={`Estado: ${status} · Prioridad: ${heatLabelEs(hl)}`}>
      <span className="badge__dot" aria-hidden="true" />
      <span className="badge__status">{status}</span>
      <span className="badge__sep">·</span>
      <span>{heatLabelEs(hl)}</span>
    </span>
  );
}

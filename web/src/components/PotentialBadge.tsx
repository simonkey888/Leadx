import type { Lead } from "../types";
import { leadPotential } from "../lib/multi-line";

export function PotentialBadge({ lead }: { lead: Lead }) {
  const potential = leadPotential(lead);
  const modifier = {
    Convertido: "ganado",
    "Muy alto": "ganado",
    Alto: "calificado",
    Medio: "propuesta",
    Bajo: "nuevo",
    "No viable": "perdido",
  }[potential];
  return (
    <span className={`badge badge--${modifier}`} title={`Potencial de conversión: ${potential}`}>
      <span className="badge__dot" aria-hidden="true" />
      {potential}
    </span>
  );
}

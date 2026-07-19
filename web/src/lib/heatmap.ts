import type { Lead, HeatLabel } from "../types";

export function heatLabel(lead: Lead): HeatLabel {
  if (lead._heat_label) return lead._heat_label;
  const score = lead._heat_score ?? lead.score ?? 0;
  if (score >= 70) return "hot";
  if (score >= 40) return "warm";
  return "cold";
}

export function heatLabelEs(label: HeatLabel): string {
  return label === "hot" ? "Alta" : label === "warm" ? "Media" : "Baja";
}

export function statusLabel(lead: Lead): string {
  return lead._status || "Nuevo";
}

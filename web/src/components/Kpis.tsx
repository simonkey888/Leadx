import type { Lead } from "../types";
import { computeKpis } from "../lib/multi-line";

export function Kpis({ leads }: { leads: Lead[] }) {
  const kpis = computeKpis(leads);
  return (
    <section className="kpis" aria-label="Indicadores de la línea activa">
      <div className="kpi"><span className="kpi__label">Total de leads</span><strong className="kpi__value">{kpis.total}</strong><small>línea activa</small></div>
      <div className="kpi"><span className="kpi__label">Nuevos</span><strong className="kpi__value">{kpis.nuevos}</strong><small>por contactar</small></div>
      <div className="kpi"><span className="kpi__label">Calificados</span><strong className="kpi__value">{kpis.calificados}</strong><small>oportunidad validada</small></div>
      <div className="kpi"><span className="kpi__label">Perdidos</span><strong className="kpi__value">{kpis.perdidos}</strong><small>fuera de gestión</small></div>
    </section>
  );
}

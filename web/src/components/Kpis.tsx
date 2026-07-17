import type { Lead } from "../types";

export function Kpis({ leads }: { leads: Lead[] }) {
  const total = leads.length;
  const hot = leads.filter((l) => (l._heat_score ?? l.score ?? 0) >= 70).length;
  const contactable = leads.filter((l) => l.whatsapp_publico || l.telefono_publico || l.telefono || l.phone || l.fb_username || l.fb_author_id || l.email_publico || l.email).length;
  const enProc = leads.filter((l) => l._status === "Contactado" || l._status === "En gestión").length;

  return (
    <div className="kpis">
      <div className="kpi"><div className="kpi__label">Total</div><div className="kpi__value">{total}</div></div>
      <div className="kpi"><div className="kpi__label">Alta prioridad</div><div className="kpi__value">{hot}</div></div>
      <div className="kpi"><div className="kpi__label">Contactables</div><div className="kpi__value">{contactable}</div></div>
      <div className="kpi"><div className="kpi__label">En gestión</div><div className="kpi__value">{enProc}</div></div>
    </div>
  );
}

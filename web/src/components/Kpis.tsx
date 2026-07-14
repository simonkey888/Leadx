import type { Lead } from "../types";

export function Kpis({ leads }: { leads: Lead[] }) {
  const total = leads.length;
  const hot = leads.filter((l) => (l._heat_score ?? l.score ?? 0) >= 70).length;
  const conWa = leads.filter((l) => l.whatsapp_publico || l.telefono_publico || l.telefono || l.phone).length;
  const conMsg = leads.filter((l) => l.fb_username || l.fb_author_id).length;
  const enProc = leads.filter((l) => l._status === "Contactado" || l._status === "En gestión").length;
  const cerrados = leads.filter((l) => l._status === "Cerrado").length;

  return (
    <div className="kpis">
      <div className="kpi"><div className="kpi__label">Total casos</div><div className="kpi__value kpi__value--blue">{total}</div><div className="kpi__sub">contactos identificados</div></div>
      <div className="kpi"><div className="kpi__label">Calientes</div><div className="kpi__value kpi__value--orange">{hot}</div><div className="kpi__sub">prioridad alta</div></div>
      <div className="kpi"><div className="kpi__label">Con WhatsApp</div><div className="kpi__value kpi__value--green">{conWa}</div><div className="kpi__sub">teléfono directo</div></div>
      <div className="kpi"><div className="kpi__label">Con Messenger</div><div className="kpi__value kpi__value--blue">{conMsg}</div><div className="kpi__sub">botón m.me</div></div>
      <div className="kpi"><div className="kpi__label">En proceso</div><div className="kpi__value kpi__value--orange">{enProc}</div><div className="kpi__sub">activos</div></div>
      <div className="kpi"><div className="kpi__label">Cerrados</div><div className="kpi__value kpi__value--green">{cerrados}</div><div className="kpi__sub">resueltos</div></div>
    </div>
  );
}

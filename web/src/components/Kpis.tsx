import type { Lead } from "../types";
export function Kpis({leads}:{leads:Lead[]}){const count=(s:string)=>leads.filter(l=>(l._status||l.status)===s).length;return <div className="kpis" aria-label="Indicadores de la línea">
  <div className="kpi"><span>Total de leads</span><strong>{leads.length}</strong><small>línea activa</small></div>
  <div className="kpi"><span>Nuevos</span><strong>{count("Nuevo")}</strong><small>por contactar</small></div>
  <div className="kpi"><span>Calificados</span><strong>{count("Calificado")}</strong><small>oportunidades</small></div>
  <div className="kpi"><span>Perdidos</span><strong>{count("Perdido")}</strong><small>sin avance</small></div>
 </div>}

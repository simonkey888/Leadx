import { SlidersHorizontal, X } from "lucide-react";
import type { Lead, ContactFilter, HeatFilter, LeadStatus } from "../types";

interface Props {
  leads: Lead[];
  search: string; setSearch: (value: string) => void;
  statusFilter: LeadStatus | "todos"; setStatusFilter: (value: LeadStatus | "todos") => void;
  contactFilter: ContactFilter; setContactFilter: (value: ContactFilter) => void;
  heatFilter: HeatFilter; setHeatFilter: (value: HeatFilter) => void;
  provinceFilter: string; setProvinceFilter: (value: string) => void;
  sourceFilter: string; setSourceFilter: (value: string) => void;
  sort: string; setSort: (value: string) => void;
  onActivity?: () => void;
}

export function Filters(props: Props) {
  const provinces = [...new Set(props.leads.map((lead) => lead.provincia).filter(Boolean))].sort() as string[];
  const sources = [...new Set(props.leads.map((lead) => lead.source_label || lead.platform).filter(Boolean))].sort() as string[];
  const activeCount = [props.statusFilter, props.contactFilter, props.heatFilter].filter((value) => value !== "todos").length
    + Number(Boolean(props.provinceFilter)) + Number(Boolean(props.sourceFilter));

  const clear = () => {
    props.setStatusFilter("todos"); props.setContactFilter("todos"); props.setHeatFilter("todos");
    props.setProvinceFilter(""); props.setSourceFilter(""); props.onActivity?.();
  };

  return (
    <div className="filter-area">
      <div className="toolbar">
        <input type="search" className="search" placeholder="Buscar nombre, problema o provincia…" value={props.search}
          onChange={(event) => { props.setSearch(event.target.value); props.onActivity?.(); }} aria-label="Buscar leads" />
        <button className="control-button filter-trigger" onClick={() => document.body.classList.add("filters-open")}>
          <SlidersHorizontal size={17} />Filtros{activeCount > 0 && <span>{activeCount}</span>}
        </button>
        <label className="sort-control"><span className="sr-only">Ordenar</span>
          <select value={props.sort} onChange={(event) => { props.setSort(event.target.value); props.onActivity?.(); }}>
            <option value="priority">Prioridad</option><option value="recent">Más recientes</option><option value="name">Nombre</option>
          </select>
        </label>
      </div>
      <div className="filters-sheet" role="region" aria-label="Filtros">
        <div className="sheet-header"><div><span className="eyebrow">Refinar lista</span><h2>Filtros</h2></div>
          <button className="icon-button mobile-only" onClick={() => document.body.classList.remove("filters-open")} aria-label="Cerrar filtros"><X size={20} /></button>
        </div>
        <div className="filter-grid">
          <Select label="Estado" value={props.statusFilter} onChange={(value) => { props.setStatusFilter(value); props.onActivity?.(); }} options={["todos", "Nuevo", "Contactado", "En gestión", "Cerrado", "Descartado"]} />
          <Select label="Prioridad" value={props.heatFilter} onChange={(value) => { props.setHeatFilter(value); props.onActivity?.(); }} options={["todos", "hot", "warm", "cold"]} labels={{ hot: "Alta", warm: "Media", cold: "Baja" }} />
          <Select label="Contacto" value={props.contactFilter} onChange={(value) => { props.setContactFilter(value); props.onActivity?.(); }} options={["todos", "whatsapp", "messenger", "email", "sin_contacto"]} labels={{ messenger: "Facebook", sin_contacto: "Sin contacto" }} />
          <Select label="Provincia" value={props.provinceFilter} onChange={(value) => { props.setProvinceFilter(value); props.onActivity?.(); }} options={["", ...provinces]} labels={{ "": "Todas" }} />
          <Select label="Fuente" value={props.sourceFilter} onChange={(value) => { props.setSourceFilter(value); props.onActivity?.(); }} options={["", ...sources]} labels={{ "": "Todas" }} />
        </div>
        <div className="sheet-actions"><button className="btn" onClick={clear}>Limpiar</button>
          <button className="btn btn--primary mobile-only" onClick={() => document.body.classList.remove("filters-open")}>Ver resultados</button></div>
      </div>
    </div>
  );
}

function Select<T extends string>({ label, value, onChange, options, labels = {} }: {
  label: string; value: T; onChange: (value: T) => void; options: T[]; labels?: Record<string, string>;
}) {
  return <label className="filter-field"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value as T)}>
    {options.map((option) => <option key={option || "all"} value={option}>{labels[option] || (option === "todos" ? "Todos" : option)}</option>)}
  </select></label>;
}

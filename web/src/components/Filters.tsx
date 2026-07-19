import type { Dispatch, SetStateAction } from "react";
import { Download, SlidersHorizontal, X } from "lucide-react";
import type { Lead, LeadFilters, LeadVertical } from "../types";
import { EMPTY_FILTERS, leadAssigned, leadChannel, leadProvince } from "../lib/multi-line";

interface Props {
  vertical: LeadVertical;
  leads: Lead[];
  search: string;
  setSearch: (value: string) => void;
  filters: LeadFilters;
  setFilters: Dispatch<SetStateAction<LeadFilters>>;
  sort: string;
  setSort: (value: string) => void;
  onExport: () => void;
  onActivity?: () => void;
}

const unique = (values: Array<string | undefined>) => [...new Set(values.filter((value): value is string => Boolean(value && value.trim())))].sort((a, b) => a.localeCompare(b, "es"));

export function Filters(props: Props) {
  const provinces = unique(props.leads.map(leadProvince));
  const channels = unique(props.leads.map(leadChannel));
  const assigned = unique(props.leads.map(leadAssigned));
  const data = props.leads.map((lead) => lead.vertical_data || {});
  const municipalities = unique(data.map((entry) => String(entry.municipality || "")));
  const violationTypes = unique(data.map((entry) => String(entry.violation_type || "")));
  const brands = unique(data.map((entry) => String(entry.brand || "")));
  const machineTypes = unique(data.map((entry) => String(entry.machine_type || "")));
  const urgencies = unique(data.map((entry) => String(entry.urgency || "")));
  const activeCount = Object.entries(props.filters).filter(([key, value]) => value && value !== "todos" && !(key === "date" && value === "todos")).length;

  const update = <K extends keyof LeadFilters>(key: K, value: LeadFilters[K]) => {
    props.setFilters((current) => ({ ...current, [key]: value }));
    props.onActivity?.();
  };

  const clear = () => { props.setFilters({ ...EMPTY_FILTERS }); props.onActivity?.(); };

  return (
    <section className="filter-area" aria-label="Búsqueda y filtros">
      <div className="toolbar">
        <input type="search" className="search"
          placeholder={props.vertical === "fotomultas" ? "Buscar nombre, patente, municipio…" : "Buscar nombre, marca, máquina, pieza…"}
          value={props.search} onChange={(event) => { props.setSearch(event.target.value); props.onActivity?.(); }} aria-label="Buscar leads" />
        <button type="button" className="control-button filter-trigger" aria-haspopup="dialog" onClick={() => document.body.classList.add("filters-open")}>
          <SlidersHorizontal size={17} aria-hidden="true" /> Filtros {activeCount > 0 && <span>{activeCount}</span>}
        </button>
        <label className="sort-control"><span className="sr-only">Ordenar</span>
          <select value={props.sort} onChange={(event) => { props.setSort(event.target.value); props.onActivity?.(); }}>
            <option value="potential">Mayor potencial</option><option value="recent">Más recientes</option><option value="priority">Prioridad</option><option value="name">Nombre</option>
          </select>
        </label>
        <button type="button" className="control-button export-button" onClick={props.onExport} disabled={props.leads.length === 0}>
          <Download size={16} aria-hidden="true" /> Exportar
        </button>
      </div>

      <button type="button" className="filters-backdrop" onClick={() => document.body.classList.remove("filters-open")} aria-label="Cerrar filtros" />
      <div className="filters-sheet" role="dialog" aria-modal="true" aria-label="Filtros">
        <div className="sheet-header">
          <div><span className="eyebrow">Refinar lista</span><h2>Filtros</h2></div>
          <button type="button" className="icon-button" onClick={() => document.body.classList.remove("filters-open")} aria-label="Cerrar filtros"><X size={20} /></button>
        </div>
        <div className="filter-grid">
          <Select label="Etapa comercial" value={props.filters.status} onChange={(value) => update("status", value)} options={["todos", "Ganado", "Propuesta", "Calificado", "Contactado", "Nuevo", "Perdido"]} />
          <Select label="Prioridad" value={props.filters.priority} onChange={(value) => update("priority", value)} options={["todos", "Alta", "Media", "Baja"]} />
          <Select label="Provincia" value={props.filters.province} onChange={(value) => update("province", value)} options={["", ...provinces]} labels={{ "": "Todas" }} />
          <Select label="Canal" value={props.filters.channel} onChange={(value) => update("channel", value)} options={["", ...channels]} labels={{ "": "Todos", whatsapp: "WhatsApp", messenger: "Messenger", email: "Email", telefono: "Teléfono", web: "Web" }} />
          <Select label="Asignado a" value={props.filters.assigned} onChange={(value) => update("assigned", value)} options={["", ...assigned]} labels={{ "": "Todos" }} />
          <Select label="Fecha" value={props.filters.date} onChange={(value) => update("date", value)} options={["todos", "7d", "30d", "90d"]} labels={{ todos: "Cualquier fecha", "7d": "Últimos 7 días", "30d": "Últimos 30 días", "90d": "Últimos 90 días" }} />

          {props.vertical === "fotomultas" ? (
            <>
              <Select label="Municipio" value={props.filters.municipality} onChange={(value) => update("municipality", value)} options={["", ...municipalities]} labels={{ "": "Todos" }} />
              <Select label="Tipo de infracción" value={props.filters.violationType} onChange={(value) => update("violationType", value)} options={["", ...violationTypes]} labels={{ "": "Todas" }} />
              <TextFilter label="Patente" value={props.filters.plate} onChange={(value) => update("plate", value)} placeholder="Ej. AA000AA" />
            </>
          ) : (
            <>
              <Select label="Marca" value={props.filters.brand} onChange={(value) => update("brand", value)} options={["", ...brands]} labels={{ "": "Todas" }} />
              <Select label="Tipo de máquina" value={props.filters.machineType} onChange={(value) => update("machineType", value)} options={["", ...machineTypes]} labels={{ "": "Todos" }} />
              <TextFilter label="Número de pieza" value={props.filters.partNumber} onChange={(value) => update("partNumber", value)} placeholder="Ej. CIH-87312345" />
              <Select label="Urgencia" value={props.filters.urgency} onChange={(value) => update("urgency", value)} options={["", ...urgencies]} labels={{ "": "Todas", alta: "Alta", media: "Media", baja: "Baja" }} />
            </>
          )}
        </div>
        <div className="sheet-actions"><button type="button" className="btn" onClick={clear}>Limpiar</button>
          <button type="button" className="btn btn--primary" onClick={() => document.body.classList.remove("filters-open")}>Ver resultados</button></div>
      </div>
    </section>
  );
}

function Select<T extends string>({ label, value, onChange, options, labels = {} }: { label: string; value: T; onChange: (value: T) => void; options: T[]; labels?: Record<string, string> }) {
  return <label className="filter-field"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value as T)}>
    {options.map((option) => <option key={option || "all"} value={option}>{labels[option] || (option === "todos" ? "Todos" : option)}</option>)}
  </select></label>;
}

function TextFilter({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (value: string) => void; placeholder: string }) {
  return <label className="filter-field"><span>{label}</span><input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /></label>;
}

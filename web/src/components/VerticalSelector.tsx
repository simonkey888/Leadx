import type { LeadVertical } from "../types";
import { VERTICAL_OPTIONS } from "../lib/multi-line";

export function VerticalSelector({ value, onChange }: { value: LeadVertical; onChange: (value: LeadVertical) => void }) {
  return (
    <nav className="segmented-control" aria-label="Línea comercial">
      {VERTICAL_OPTIONS.map((option) => (
        <button key={option.value} type="button" className={`segmented-option ${value === option.value ? "active" : ""}`}
          aria-pressed={value === option.value} onClick={() => onChange(option.value)}>
          <span className="segmented-option__full">{option.label}</span><span className="segmented-option__short">{option.shortLabel}</span>
        </button>
      ))}
    </nav>
  );
}

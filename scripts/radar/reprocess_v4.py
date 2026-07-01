"""
reprocess_v4.py — Re-procesa los raw search results de v4 con la clasificación v4.1.
"""
import json
import sys
sys.path.insert(0, '/home/z/my-project/scripts/radar')
from radar_v4 import build_lead_from_result_v4, dedup_by_post_link, extract_arg_phone_strict, extract_whatsapp_strict, detect_country, REJECT_COUNTRIES, MUST_MATCH, PREFERRED_PROVINCES

# Cargar raw search results
with open('/home/z/my-project/download/radar_v4_raw_search.json') as f:
    raw_results = json.load(f)

print(f"Loaded {len(raw_results)} raw results", file=sys.stderr)

all_leads = []
rejected_by_country = 0
rejected_no_must_match = 0

for r in raw_results:
    combined = f"{r.get('name', '')}. {r.get('snippet', '')}"
    phone_preview = extract_arg_phone_strict(combined) or extract_whatsapp_strict(combined)
    country_preview = detect_country(combined, r.get('url', ''), phone_preview)
    if country_preview in REJECT_COUNTRIES.values():
        rejected_by_country += 1
        continue

    combined_lower = combined.lower()
    matched_must_preview = [kw for kw in MUST_MATCH if kw in combined_lower]
    if not matched_must_preview:
        rejected_no_must_match += 1
        continue

    lead = build_lead_from_result_v4(r, r.get('_query', ''), r.get('_query_category', ''))
    if lead is None:
        continue
    all_leads.append(lead)

print(f"Rejected by country: {rejected_by_country}", file=sys.stderr)
print(f"Rejected no must_match: {rejected_no_must_match}", file=sys.stderr)
print(f"Total leads: {len(all_leads)}", file=sys.stderr)

# Dedup
all_leads = dedup_by_post_link(all_leads)
print(f"After dedup: {len(all_leads)}", file=sys.stderr)

# Separar
real_leads = [l for l in all_leads if l.category == "real_lead"]
commercial_signals = [l for l in all_leads if l.category == "commercial_signal"]

# Sort
real_leads.sort(key=lambda l: (l.commercial_score, l.urgency_score, l.confidence), reverse=True)
commercial_signals.sort(key=lambda l: (l.commercial_score, l.urgency_score, l.confidence), reverse=True)

print(f"\nREAL LEADS (dolor explícito): {len(real_leads)}", file=sys.stderr)
print(f"COMMERCIAL SIGNALS: {len(commercial_signals)}", file=sys.stderr)

# Stats por lead_reason
reason_stats = {}
for l in all_leads:
    reason_stats[l.lead_reason] = reason_stats.get(l.lead_reason, 0) + 1

print(f"\nDistribución por lead_reason:", file=sys.stderr)
for reason, count in sorted(reason_stats.items(), key=lambda x: -x[1]):
    print(f"  {reason:35s} {count:3d}", file=sys.stderr)

# Print top real_leads
if real_leads:
    print(f"\nTOP 10 REAL LEADS:", file=sys.stderr)
    for i, l in enumerate(real_leads[:10], 1):
        wa = " [+WA]" if l.possible_whatsapp else ""
        ph = " [+TEL]" if l.possible_phone else ""
        print(f"  {i:2d}. [C={l.commercial_score:3d} U={l.urgency_score:3d} Conf={l.confidence:3d}] {l.lead_reason:35s} | {l.platform:15s} | {l.quoted_text[:50]}{wa}{ph}", file=sys.stderr)

# Guardar output actualizado
import time
output = {
    "project": "Radar de Oportunidades v4.1",
    "version": "4.1",
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "mission": "Detector de DOLOR EXPLÍCITO — clasificación ampliada v4.1",
    "summary": {
        "total_search_results": len(raw_results),
        "rejected_by_country": rejected_by_country,
        "rejected_no_must_match": rejected_no_must_match,
        "real_leads_found": len(real_leads),
        "commercial_signals_found": len(commercial_signals),
        "total_leads": len(all_leads),
        "success_real_leads_met": len(real_leads) >= 10,
        "reason_stats": reason_stats,
    },
    "real_leads": [l.to_dict() for l in real_leads],
    "commercial_signals": [l.to_dict() for l in commercial_signals],
}

with open('/home/z/my-project/download/radar_v4_output.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✓ Output guardado en /home/z/my-project/download/radar_v4_output.json", file=sys.stderr)

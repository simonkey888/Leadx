#!/usr/bin/env python3
"""Purge all VentaFe leads from KV — Simon's order at 7:50 AM.
VentaFe is 100% useless (all car sellers, no pain).

KV structure: leads:live = { leads_all:[...], leads_hot:[...], leads_warm:[...], summary:{}, meta:{} }
"""
import json
import urllib.request
from datetime import datetime, timezone

WORKER = "https://leadx.simondalmasso44.workers.dev"
SECRET = "LEGACY_SECRET_REMOVED"

def req(method, path, body=None):
    headers = {
        "X-Webhook-Secret": SECRET,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (leadx-purge)",
    }
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(f"{WORKER}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())

# 1. Read current
data = req("GET", "/api/kv?key=leads:live")
val = data["value"]
print(f"Before: leads_all={len(val.get('leads_all', []))} | hot={len(val.get('leads_hot', []))} | warm={len(val.get('leads_warm', []))}")

# 2. Filter VentaFe everywhere
def filter_out_vf(arr):
    return [l for l in (arr or []) if (l.get("source") or l.get("platform")) != "VentaFe"]

before_all = len(val.get("leads_all", []))
val["leads_all"] = filter_out_vf(val.get("leads_all"))
val["leads_hot"] = filter_out_vf(val.get("leads_hot"))
val["leads_warm"] = filter_out_vf(val.get("leads_warm"))

after_all = len(val["leads_all"])
print(f"Purged: {before_all - after_all} VentaFe leads")
print(f"After:  leads_all={len(val['leads_all'])} | hot={len(val['leads_hot'])} | warm={len(val['leads_warm'])}")

# 3. Recompute summary
def has_contact(l):
    return bool(l.get("telefono") or l.get("phone") or l.get("fb_username") or l.get("fb_author_id"))
def has_email(l):
    return bool(l.get("email"))
val["summary"] = {
    "total_leads": len(val["leads_all"]),
    "hot_leads": len(val["leads_hot"]),
    "with_whatsapp": sum(1 for l in val["leads_all"] if has_contact(l)),
    "with_email": sum(1 for l in val["leads_all"] if has_email(l)),
}
val["meta"] = {
    "version": "11.1",
    "source": "manual_purge_ventafe",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "ingest_at": datetime.now(timezone.utc).isoformat(),
    "purged_ventafe": before_all - after_all,
}
print(f"Summary: {val['summary']}")

# 4. Write back
req("POST", "/api/kv", {"key": "leads:live", "value": val})
print("✅ KV updated.")

# 5. Verify via /api/leads
verify = req("GET", "/api/leads?limit=200")
print(f"Verify: total={verify.get('summary', {}).get('total_leads')} | hot={verify.get('summary', {}).get('hot_leads')} | wa={verify.get('summary', {}).get('with_whatsapp')}")
sources = {}
for l in verify.get("leads_all", []):
    s = l.get("source") or l.get("platform") or "?"
    sources[s] = sources.get(s, 0) + 1
print(f"Sources: {sources}")

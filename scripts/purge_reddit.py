#!/usr/bin/env python3
"""Purge all Reddit leads from KV — Simon order 7:55 AM.
Reddit edge cron brings 100% off-topic (MusicaBR, crossout_es, phishing Chile, etc.).
0/11 accionables. Same fate as VentaFe."""
import json
import urllib.request
from datetime import datetime, timezone

WORKER = "https://leadx.simondalmasso44.workers.dev"
SECRET = "LEGACY_SECRET_REMOVED"

def req(method, path, body=None):
    headers = {
        "X-Webhook-Secret": SECRET,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (leadx-purge-reddit)",
    }
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(f"{WORKER}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())

# 1. Read current
data = req("GET", "/api/kv?key=leads:live")
val = data["value"]
before = len(val.get("leads_all", []))
print(f"Before: leads_all={before} | hot={len(val.get('leads_hot', []))}")

# 2. Filter Reddit everywhere
def filter_out_reddit(arr):
    return [l for l in (arr or []) if (l.get("source") or l.get("platform")) != "reddit_rss"]

val["leads_all"] = filter_out_reddit(val.get("leads_all"))
val["leads_hot"] = filter_out_reddit(val.get("leads_hot"))
val["leads_warm"] = filter_out_reddit(val.get("leads_warm"))

after = len(val["leads_all"])
print(f"Purged: {before - after} Reddit leads")
print(f"After:  leads_all={len(val['leads_all'])} | hot={len(val['leads_hot'])}")

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
    "version": "11.2",
    "source": "manual_purge_reddit",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "ingest_at": datetime.now(timezone.utc).isoformat(),
    "purged_reddit": before - after,
}
print(f"Summary: {val['summary']}")

# 4. Write back
req("POST", "/api/kv", {"key": "leads:live", "value": val})
print("KV updated.")

# 5. Verify
verify = req("GET", "/api/leads?limit=200")
print(f"Verify: total={verify['summary']['total_leads']} | hot={verify['summary']['hot_leads']} | wa={verify['summary']['with_whatsapp']}")
sources = {}
for l in verify.get("leads_all", []):
    s = l.get("source") or l.get("platform") or "?"
    sources[s] = sources.get(s, 0) + 1
print(f"Sources: {sources}")

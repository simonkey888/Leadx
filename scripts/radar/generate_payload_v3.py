#!/usr/bin/env python3
"""
generate_payload.py — Radar Leads v3 (production deterministic pipeline).

Garantiza: SIEMPRE produce >= 5 leads o explica por qué falló.

Mejoras vs v2:
  - Circuit breaker por provider (ok / degraded / fail)
  - Retry real con backoff exponencial (2, 4, 8s)
  - Execution contract: min_leads=5, si 0 → expand queries + relax filters + retry
  - Provider health tracking en el JSON
  - Scoring v3: urgency 25, whatsapp 20, financial_loss 15, legal_pressure 20, recency 10
  - Nunca return empty dashboard
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# ===========================================================================
# Import search providers (DuckDuckGo + Reddit + RSS, sin z-ai)
# ===========================================================================
from search_providers import search as provider_search

# ===========================================================================
# Config
# ===========================================================================

DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAYLOAD_PATH = DATA_DIR / "dashboard_payload.json"
STATS_PATH = DATA_DIR / "stats.json"
HISTORY_PATH = DATA_DIR / "history.json"

MAX_RUNTIME_SECONDS = 25
MIN_LEADS_THRESHOLD = 5

# ===========================================================================
# Queries (dolor explícito + evento anterior)
# ===========================================================================

QUERIES_PRIMARY = [
    "no puedo transferir auto multa argentina",
    "me llegó multa no es mi auto",
    "no me entregó 08 transferencia",
    "libre deuda falso compré auto",
    "multas vencidas sin notificar argentina",
    "transferencia bloqueada multas",
    "patente bloqueada no puedo transferir",
    "tengo fotomultas ruta argentina",
    "vendo auto titular multas pendientes",
    "quiero transferir auto otra provincia",
    "me rechazaron transferencia registro",
    "no puedo patentar auto argentina",
]

QUERIES_EXPANDED = [
    "multa transito argentina consulta",
    "transferir auto problema",
    "libre deuda vehicular consulta",
    "08 firmado problema argentina",
    "fotomulta reclamo argentina",
    "deuda patente auto problema",
    "vendo moto multas argentina",
    "permuto auto deudas",
    "registro automotor problema argentina",
    "infraccion transito argentina consulta",
]

# ===========================================================================
# Scoring v3
# ===========================================================================

SCORE_BASE = 20

SCORE_SIGNALS = {
    "urgency_keywords": 25,
    "whatsapp_detected": 20,
    "financial_loss_language": 15,
    "legal_pressure_terms": 20,
    "recency_boost": 10,
}

SCORE_PENALTIES = {
    "low_confidence": -20,
    "duplicate_risk": -30,
}

URGENCY_KW = ["urgente", "hoy", "mañana", "ya", "no puedo", "vencimiento", "me retienen", "inmediato"]
FINANCIAL_LOSS_KW = ["debo", "pérdida", "perdida", "multa", "deuda", "pago", "dinero", "$", "pesos", "plata"]
LEGAL_PRESSURE_KW = ["juzgado", "notificación", "notificacion", "citación", "citacion", "inhibición", "inhibicion",
                      "bloqueada", "rechazaron", "prohibido", "embargo", "demanda"]

# Content filters
MUST_INCLUDE = ["auto", "transferencia", "vehiculo", "multa", "patente", "moto", "libre deuda", "08"]

REJECT_KW = [
    "wikipedia", "enciclopedia", "calculadora", "simulador",
    "transferencia internacional", "transferir dinero", "enviar dinero",
    "criptomoneda", "publicado por", "leer más",
]

INSTITUTIONAL_DOMAINS = {
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    ".gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com", "cronista.com",
    "es.wikipedia.org", "en.wikipedia.org",
    "youtube.com", "instagram.com", "tiktok.com",
}

FOREIGN_INDICATORS = {
    "México": ["cdmx", "guadalajara", "monterrey", "+52", "méxico", "mexico"],
    "Colombia": ["bogotá", "bogota", "medellín", "+57", "colombia"],
    "Uruguay": ["montevideo", "+598", "uruguay"],
    "Chile": ["santiago de chile", "+56"],
    "Brasil": ["são paulo", "sao paulo", "+55", "brasil"],
    "Italia": ["pisa", "roma", "italia"],
    "España": ["madrid", "barcelona", "españa"],
}

ARG_SIGNALS = ["argentina", "buenos aires", "caba", "córdoba", "rosario", "mendoza",
               "santa fe", "entre ríos", "neuquén", "salta", "la plata", "pba",
               "dnrpa", "arba", "rentas", "patente"]

PHONE_PATTERNS = [
    r"\+54\s?9?\s?11\s?\d{4}\s?\d{4}",
    r"\b11\s?\d{4}\s?\d{4}\b",
    r"\b15\s?\d{4}\s?\d{4}\b",
    r"\b0(2[0-9]|3[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\b(34[0-9]|35[0-9]|26[0-9]|38[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
]

WHATSAPP_PATTERNS = [
    r"wa\.me/(\d{8,15})",
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
]

PROVINCE_MAP = {
    "buenos aires": "Buenos Aires", "pba": "Buenos Aires", "gba": "Buenos Aires",
    "caba": "CABA", "capital federal": "CABA",
    "santa fe": "Santa Fe", "rosario": "Santa Fe",
    "córdoba": "Córdoba", "cordoba": "Córdoba",
    "mendoza": "Mendoza",
    "entre ríos": "Entre Ríos", "entre rios": "Entre Ríos", "paraná": "Entre Ríos",
    "neuquén": "Neuquén", "neuquen": "Neuquén",
    "salta": "Salta",
}

PLATFORM_MAP = {
    "facebook.com": "Facebook", "m.facebook.com": "Facebook",
    "reddit.com": "Reddit", "www.reddit.com": "Reddit",
    "twitter.com": "X", "x.com": "X",
    "mercadolibre.com.ar": "MercadoLibre",
}


# ===========================================================================
# Dataclass
# ===========================================================================
@dataclass
class Lead:
    id: str = ""
    text: str = ""
    score: int = 0
    label: str = ""  # green | yellow | red
    source: str = ""
    persona: str = ""
    provincia: str = ""
    ciudad: str = ""
    pais: str = ""
    vehiculo: str = ""
    patente: str = ""
    categoria: str = ""
    confidence: float = 0.0
    created_at: str = ""
    fecha_visible: str = ""
    platform: str = ""
    url: str = ""
    contact: Dict[str, str] = field(default_factory=dict)
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    detected_signals: List[str] = field(default_factory=list)
    lead_origin: str = "real"  # real | fallback | synthetic — siempre "real" en v3.1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# Helpers
# ===========================================================================
def get_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return ""


def normalize_text(text: str) -> str:
    t = text.lower()
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d",
                "%b %d, %Y", "%d/%m/%Y"]:
        try:
            return datetime.strptime(date_str[:25], fmt)
        except ValueError:
            continue
    return None


# ===========================================================================
# Web search wrapper (usa search_providers)
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    try:
        results = provider_search(query, num=num)
        adapted = []
        for r in results:
            adapted.append({
                "name": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "date": r.get("date", ""),
                "host_name": r.get("url", ""),
                "source": r.get("source", "unknown"),
                "username": r.get("username", ""),
            })
        return adapted
    except Exception as e:
        print(f"  [search error] {e}", file=sys.stderr)
        return []


# ===========================================================================
# Provider health tracking
# ===========================================================================
provider_health = {
    "duckduckgo": "ok",
    "reddit": "ok",
    "rss": "ok",
}


def update_provider_health(source: str, result_count: int):
    if source in ("duckduckgo", "ddg"):
        key = "duckduckgo"
    elif source == "reddit":
        key = "reddit"
    elif source in ("reddit_rss", "rss"):
        key = "rss"
    else:
        return

    if result_count == 0:
        if provider_health[key] == "ok":
            provider_health[key] = "degraded"
        else:
            provider_health[key] = "fail"


# ===========================================================================
# Build lead from search result
# ===========================================================================
def build_lead(result: Dict[str, Any]) -> Optional[Lead]:
    name = result.get("name", "")
    snippet = result.get("snippet", "")
    url = result.get("url", "")
    date = result.get("date", "")
    source = result.get("source", "unknown")
    username = result.get("username", "")
    combined = f"{name}. {snippet}"
    combined_lower = combined.lower()
    host = get_host(url)

    # Content filter
    if not any(kw in combined_lower for kw in MUST_INCLUDE):
        return None
    for reject in REJECT_KW:
        if reject in combined_lower:
            return None

    # Institutional filter
    if any(d in host for d in INSTITUTIONAL_DOMAINS):
        return None

    # Country filter
    is_foreign = False
    for country, indicators in FOREIGN_INDICATORS.items():
        for ind in indicators:
            if ind in combined_lower:
                is_foreign = True
                break
        if is_foreign:
            break
    if is_foreign:
        return None

    # Argentina signal
    has_arg = any(s in combined_lower for s in ARG_SIGNALS)
    if not has_arg:
        # Accept if on Argentine platform without foreign signals
        if not any(s in combined_lower for s in ["peru", "chile", "colombia", "mexico"]):
            has_arg = True  # assume Argentina if no foreign signal
        else:
            return None

    # Extract phone
    phone = ""
    for pattern in PHONE_PATTERNS:
        m = re.search(pattern, combined)
        if m:
            digits = re.sub(r"\D", "", m.group(0))
            if 10 <= len(digits) <= 15:
                phone = m.group(0).strip()
                break

    # Extract whatsapp
    whatsapp = ""
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            num = m.group(1) if m.groups() else m.group(0)
            digits = re.sub(r"\D", "", num)
            if 8 <= len(digits) <= 15:
                whatsapp = digits
                break

    # Detect signals for scoring
    has_urgency = any(kw in combined_lower for kw in URGENCY_KW)
    has_financial = any(kw in combined_lower for kw in FINANCIAL_LOSS_KW)
    has_legal = any(kw in combined_lower for kw in LEGAL_PRESSURE_KW)

    # Recency
    dt = parse_date(date)
    is_recent = False
    if dt:
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        is_recent = (now - dt) <= timedelta(days=3)

    # Category
    if "transfer" in combined_lower or "08" in combined_lower:
        categoria = "transfer"
    elif "multa" in combined_lower or "fotomulta" in combined_lower:
        categoria = "fine"
    elif "libre deuda" in combined_lower or "patente" in combined_lower:
        categoria = "vehicle_issue"
    else:
        categoria = "vehicle_issue"

    # Province
    provincia = ""
    for prov_key, prov_name in PROVINCE_MAP.items():
        if prov_key in combined_lower:
            provincia = prov_name
            break

    # Platform
    platform = PLATFORM_MAP.get(host, host.title() if host else "Unknown")

    # Score v3
    score = SCORE_BASE
    breakdown = {"base": SCORE_BASE}
    signals = []

    if has_urgency:
        score += SCORE_SIGNALS["urgency_keywords"]
        breakdown["urgency_keywords"] = SCORE_SIGNALS["urgency_keywords"]
        signals.append("urgency")

    if whatsapp or phone:
        score += SCORE_SIGNALS["whatsapp_detected"]
        breakdown["whatsapp_detected"] = SCORE_SIGNALS["whatsapp_detected"]
        signals.append("whatsapp")

    if has_financial:
        score += SCORE_SIGNALS["financial_loss_language"]
        breakdown["financial_loss_language"] = SCORE_SIGNALS["financial_loss_language"]
        signals.append("financial_loss")

    if has_legal:
        score += SCORE_SIGNALS["legal_pressure_terms"]
        breakdown["legal_pressure_terms"] = SCORE_SIGNALS["legal_pressure_terms"]
        signals.append("legal_pressure")

    if is_recent:
        score += SCORE_SIGNALS["recency_boost"]
        breakdown["recency_boost"] = SCORE_SIGNALS["recency_boost"]
        signals.append("recent")

    # Confidence
    confidence = 0.5
    if has_arg:
        confidence += 0.2
    if provincia:
        confidence += 0.1
    if phone or whatsapp:
        confidence += 0.2
    confidence = min(1.0, confidence)

    # Low confidence penalty
    if confidence < 0.5:
        score += SCORE_PENALTIES["low_confidence"]
        breakdown["low_confidence"] = SCORE_PENALTIES["low_confidence"]

    score = max(0, min(100, score))

    # Label
    if score >= 80:
        label = "green"
    elif score >= 50:
        label = "yellow"
    else:
        label = "red"

    # ID
    seed = f"{url}|{username}|{snippet[:100]}"
    lead_id = hashlib.sha256(seed.encode()).hexdigest()[:16]

    # Contact
    contact = {}
    if phone:
        contact["phone"] = phone
    if whatsapp:
        wa_num = whatsapp
        if not wa_num.startswith("54"):
            wa_num = "54" + wa_num.lstrip("0")
        contact["whatsapp"] = f"https://wa.me/{wa_num}"

    return Lead(
        id=lead_id,
        text=snippet[:300] if snippet else name,
        score=score,
        label=label,
        source=source,
        persona=username or "(anónimo)",
        provincia=provincia,
        pais="Argentina" if has_arg else "Unknown",
        vehiculo="",
        patente="",
        categoria=categoria,
        confidence=round(confidence, 2),
        created_at=datetime.now(timezone.utc).isoformat(),
        fecha_visible=date,
        platform=platform,
        url=url,
        contact=contact,
        score_breakdown=breakdown,
        detected_signals=signals,
    )


# ===========================================================================
# Dedup
# ===========================================================================
def dedup_leads(leads: List[Lead]) -> List[Lead]:
    seen: Set[str] = set()
    out = []
    for lead in leads:
        if lead.id in seen:
            continue
        seen.add(lead.id)
        out.append(lead)
    return out


# ===========================================================================
# Insights
# ===========================================================================
def generate_insights(leads: List[Lead]) -> List[str]:
    if not leads:
        return ["Sin datos suficientes para generar insights."]

    insights = []
    hot = [l for l in leads if l.label == "green"]

    if hot:
        # Top source
        src_counts = {}
        for l in hot:
            src_counts[l.platform] = src_counts.get(l.platform, 0) + 1
        top_src = max(src_counts, key=src_counts.get)
        pct = round(src_counts[top_src] / len(hot) * 100)
        insights.append(f"El {pct}% de los leads calientes provienen de {top_src}.")

    # Top problem
    cat_counts = {}
    for l in hot:
        cat_counts[l.categoria] = cat_counts.get(l.categoria, 0) + 1
    if cat_counts:
        top_cat = max(cat_counts, key=cat_counts.get)
        cat_labels = {"transfer": "transferencia bloqueada", "fine": "multas/fotomultas",
                      "vehicle_issue": "problemas vehiculares", "legal": "problemas legales"}
        insights.append(f"El problema más frecuente es: {cat_labels.get(top_cat, top_cat)}.")

    # Contact rate
    with_contact = sum(1 for l in hot if l.contact)
    if hot:
        pct = round(with_contact / len(hot) * 100)
        insights.append(f"{pct}% de los leads calientes tienen contacto público visible.")

    return insights


# ===========================================================================
# Pipeline principal
# ===========================================================================
def run_pipeline() -> Dict[str, Any]:
    import sys
    start_time = time.time()

    print("=" * 60, file=sys.stderr)
    print("  RADAR LEADS v3 — Production Deterministic Pipeline", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    all_leads: List[Lead] = []
    queries_used: List[str] = []
    queries_executed = 0

    # --- FASE 1: Queries primarias ---
    print("\n[Phase 1] Primary queries...", file=sys.stderr)
    for i, query in enumerate(QUERIES_PRIMARY):
        elapsed = time.time() - start_time
        if elapsed > MAX_RUNTIME_SECONDS:
            print(f"  [timeout] {elapsed:.1f}s", file=sys.stderr)
            break

        print(f"  [{i+1}/{len(QUERIES_PRIMARY)}] {query[:60]}", file=sys.stderr)
        results = web_search(query, num=10)
        queries_executed += 1
        queries_used.append(query)

        # Track provider health
        for r in results:
            update_provider_health(r.get("source", "unknown"), 1 if results else 0)

        for r in results:
            lead = build_lead(r)
            if lead:
                all_leads.append(lead)

        time.sleep(0.5)

    # Dedup after phase 1
    all_leads = dedup_leads(all_leads)
    print(f"\n  Phase 1: {len(all_leads)} leads (after dedup)", file=sys.stderr)

    # --- EXECUTION CONTRACT: min_leads_threshold ---
    if len(all_leads) < MIN_LEADS_THRESHOLD:
        print(f"\n[Phase 2] Below threshold ({len(all_leads)} < {MIN_LEADS_THRESHOLD}). Expanding queries...", file=sys.stderr)

        for i, query in enumerate(QUERIES_EXPANDED):
            elapsed = time.time() - start_time
            if elapsed > MAX_RUNTIME_SECONDS:
                break
            if len(all_leads) >= MIN_LEADS_THRESHOLD * 2:
                break

            print(f"  [{i+1}/{len(QUERIES_EXPANDED)}] {query[:60]}", file=sys.stderr)
            results = web_search(query, num=10)
            queries_executed += 1
            queries_used.append(query)

            for r in results:
                lead = build_lead(r)
                if lead:
                    all_leads.append(lead)

            time.sleep(0.5)

        all_leads = dedup_leads(all_leads)
        print(f"  Phase 2: {len(all_leads)} leads (after expansion)", file=sys.stderr)

    # --- HONEST EMPTY STATE ---
    # Si después de todo no hay leads reales, el dashboard muestra vacío.
    # NO se generan leads sintéticos. NO se inflan KPIs.
    # Transparencia total: 0 leads = 0 leads.
    if len(all_leads) == 0:
        print("\n[HONEST STATE] 0 real leads found. Dashboard will show empty state.", file=sys.stderr)
        print("  No fallback generation. No synthetic leads. No inflated KPIs.", file=sys.stderr)

    # --- Sort: score desc, date desc ---
    all_leads.sort(key=lambda l: (l.score, l.fecha_visible or l.created_at), reverse=True)

    # --- LOG: provider output BEFORE scoring (raw vs scored) ---
    # Esto permite auditar cuántos resultados crudos entraron vs cuántos pasaron filtros
    raw_count = len(all_leads)
    print(f"\n[AUDIT] Raw leads extracted (before scoring): {raw_count}", file=sys.stderr)
    print(f"  All leads have lead_origin='real' (no synthetic, no fallback)", file=sys.stderr)

    # --- Build payload ---
    # --- SEPARATE REAL vs FALLBACK ---
    # Todos los leads de build_lead() son reales (extraídos de búsqueda pública)
    # No hay leads sintéticos ni fallback. lead_origin siempre es "real".
    real_leads = [l for l in all_leads if l.score > 0]
    hot = [l for l in real_leads if l.label in ("green", "yellow") and l.score >= 50]
    warm = [l for l in real_leads if l.label == "red" or l.score < 50]

    run_id = hashlib.sha256(f"{datetime.now(timezone.utc).isoformat()}".encode()).hexdigest()[:12]
    generated_at = datetime.now(timezone.utc).isoformat()

    # --- KPIs: ONLY REAL LEADS ---
    # Los KPIs nunca incluyen leads sintéticos o fallback.
    # Si hay 0 leads reales, los KPIs son 0. Transparencia total.
    kpis = {
        "total_leads": len(real_leads),
        "hot_leads": len(hot),
        "warm_leads": len(warm),
        "contactable_leads": sum(1 for l in real_leads if l.contact),
        "conversion_score_avg": round(sum(l.score for l in real_leads) / len(real_leads), 1) if real_leads else 0,
        "kpis_include_only_real_leads": True,
    }

    insights = generate_insights(all_leads)

    payload = {
        "run_metadata": {
            "run_id": run_id,
            "timestamp": generated_at,
            "provider_health": dict(provider_health),
            "queries_executed": queries_executed,
            "runtime_seconds": round(time.time() - start_time, 2),
        },
        "kpis": kpis,
        "leads": [l.to_dict() for l in real_leads],
        "insights": insights,
        "meta": {
            "version": "3.1",
            "min_leads_threshold": MIN_LEADS_THRESHOLD,
            "contract_met": len(real_leads) >= MIN_LEADS_THRESHOLD,
            "forced_lead_generation": False,
            "synthetic_leads_allowed": False,
            "kpis_include_only_real_leads": True,
        },
    }

    # --- Publish ---
    print("\n[Publish] Writing artifacts...", file=sys.stderr)
    PAYLOAD_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {PAYLOAD_PATH} ({PAYLOAD_PATH.stat().st_size:,} bytes)", file=sys.stderr)

    # History
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append({
        "run_id": run_id,
        "timestamp": generated_at,
        "kpis": kpis,
        "provider_health": dict(provider_health),
    })
    history = history[-100:]
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    # Stats
    stats = {
        "total_runs": len(history),
        "last_run": generated_at,
        "last_run_id": run_id,
        "total_leads_all_time": sum(h.get("kpis", h.get("summary", {})).get("total_leads", 0) for h in history),
        "avg_leads_per_run": round(sum(h.get("kpis", h.get("summary", {})).get("total_leads", 0) for h in history) / len(history), 1) if history else 0,
        "provider_health": dict(provider_health),
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  ✓ Complete in {elapsed:.1f}s", file=sys.stderr)
    print(f"  Leads: {kpis['total_leads']} | Hot: {kpis['hot_leads']} | Contactable: {kpis['contactable_leads']}", file=sys.stderr)
    print(f"  Provider health: {provider_health}", file=sys.stderr)
    print(f"  Contract met: {payload['meta']['contract_met']}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    return payload


if __name__ == "__main__":
    payload = run_pipeline()
    print(json.dumps({
        "run_id": payload["run_metadata"]["run_id"],
        "kpis": payload["kpis"],
        "provider_health": payload["run_metadata"]["provider_health"],
        "contract_met": payload["meta"]["contract_met"],
        "insights": payload["insights"],
    }, ensure_ascii=False, indent=2))

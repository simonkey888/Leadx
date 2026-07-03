#!/usr/bin/env python3
"""
radar_leads_v1.py — Radar de Leads Fotomultas v1.0.0

Cron-triggered batch pipeline con HTTP endpoint, scoring determinístico,
dashboard HTML single-file con embedded JSON.

Uso:
    # Modo pipeline directo (sin server)
    python radar_leads_v1.py --run

    # Modo HTTP server (espera POST /radar/run)
    python radar_leads_v1.py --serve --port 8080

    # El dashboard se sirve en GET /
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urlparse

# ===========================================================================
# Config
# ===========================================================================

VERSION = "1.0.0"
DATA_DIR = Path("/home/z/my-project/download/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEADS_LATEST = DATA_DIR / "leads_latest.json"
LEADS_HISTORY = DATA_DIR / "leads_history.json"
DASHBOARD_PAYLOAD = DATA_DIR / "dashboard_payload.json"
DASHBOARD_HTML = DATA_DIR / "dashboard.html"

# Performance
MAX_RUNTIME_SECONDS = 25
BATCH_SIZE = 10
RATE_LIMIT_MS = 2000
MAX_RESULTS_PER_QUERY = 10

# Auth
RADAR_SECRET_TOKEN = os.environ.get("RADAR_SECRET_TOKEN", "")

# Temporal filter
RECENCY_DAYS = 3
MIN_SCORE_THRESHOLD = 40

# ===========================================================================
# Queries (template-based expanded search)
# ===========================================================================

QUERIES = [
    "site:facebook.com 'no puedo transferir auto' Argentina",
    "site:facebook.com 'multa' 'no es mía' auto",
    "site:reddit.com 'car transfer problem fine'",
    "site:foros auto transferencia DNRPA problema",
    "site:mercadolibre.com.ar auto usado '08 firmado' transferencia",
    "site:facebook.com/groups auto vender urgente transferencia",
    "site:x.com auto multa transferencia problema",
    # Expansiones
    "site:reddit.com no puedo transferir auto argentina",
    "site:reddit.com me llegó multa argentina",
    "site:facebook.com libre deuda problema argentina",
    "site:facebook.com fotomulta reclamo argentina",
    "site:facebook.com 08 firmado problema",
    "no puedo transferir auto por multas argentina",
    "me llegó una multa y no es mi auto",
    "me dieron un libre deuda falso",
    "multas vencidas sin notificar argentina",
    "el vendedor no me entregó el 08",
    "quiero transferir auto radicado otra provincia",
    "patente bloqueada no puedo transferir",
    "tengo fotomultas de ruta argentina",
]

# ===========================================================================
# Content filtering rules
# ===========================================================================

MUST_INCLUDE_ONE = ["auto", "transferencia", "vehiculo", "multa", "patente"]

REJECT_IF_CONTAINS = [
    # News / institutional
    "publicado por", "leer más", "última actualización",
    "calculá tu", "calcula tu", "simulador", "arancel",
    "guía completa", "guia completa", "paso a paso",
    "trámite online", "turno web",
    # Wikipedia
    "wikipedia", "enciclopedia",
    # Banks
    "transferencia internacional", "transferir dinero",
    "enviar dinero", "criptomoneda",
]

# Blacklist domains (institutional sources → -20 penalty)
INSTITUTIONAL_DOMAINS = {
    "dnrpa.gov.ar", "argentina.gob.ar", "buenosaires.gob.ar",
    "gob.ar", "jus.gob.ar", "rentas.gob.ar", "arba.gov.ar",
    ".gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com",
    "es.wikipedia.org", "en.wikipedia.org",
    "youtube.com", "instagram.com", "tiktok.com",
}

# ===========================================================================
# Signal extraction patterns
# ===========================================================================

# Phone extractor (Argentina)
PHONE_PATTERNS = [
    r"\+54\s?9?\s?11\s?\d{4}\s?\d{4}",
    r"\b11\s?\d{4}\s?\d{4}\b",
    r"\b15\s?\d{4}\s?\d{4}\b",
    r"\b0(2[0-9]|3[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
    r"\b(34[0-9]|35[0-9]|26[0-9]|38[0-9])[\s\-]?\d{3}[\s\-]?\d{4}",
]

# WhatsApp detector
WHATSAPP_PATTERNS = [
    r"wa\.me/(\d{8,15})",
    r"whatsapp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"\bwp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
    r"WhatsApp\s*:?\s*(\+?\d[\d\s\-]{8,15})",
]

# Urgency detector
URGENCY_KEYWORDS = [
    "urgente", "mañana", "hoy", "ya", "no puedo",
    "vencimiento", "me retienen",
]
URGENCY_WEIGHT_MULTIPLIER = 1.4

# Problem classifier
PROBLEM_CATEGORIES = {
    "TRANSFER_PROBLEM": [
        "no puedo transferir", "transferencia", "transferir",
        "08 firmado", "registro automotor", "no me entregó",
        "no se puede transferir", "transferencia bloqueada",
    ],
    "FINE_DISPUTE": [
        "multa", "fotomulta", "multas", "fotomultas",
        "infracción", "infraccion", "apsv", "radares",
    ],
    "OWNERSHIP_ISSUE": [
        "no es mi auto", "no es mía", "no es mio",
        "vendí mi auto", "vendi mi auto",
        "titular", "a mi nombre",
    ],
    "DOCUMENTATION_ISSUE": [
        "libre deuda", "patente", "papeles",
        "verificación policial", "verificacion policial",
    ],
}

# Country detector
ARGENTINA_BOOST_KEYWORDS = [
    "DNRPA", "patente argentina", "Buenos Aires", "CABA",
    "Santa Fe", "Córdoba", "Mendoza", "Rosario", "La Plata",
    "ARBA", "Rentas", "ANSeS", "PBA", "GBA",
]

REJECT_COUNTRIES = {
    "méxico", "mexico", "colombia", "uruguay", "chile",
    "perú", "peru", "paraguay", "brasil", "brazil",
    "italia", "españa", "eeuu", "usa",
}

FOREIGN_INDICATORS = {
    "México": ["cdmx", "guadalajara", "monterrey", "+52"],
    "Colombia": ["bogotá", "bogota", "medellín", "+57"],
    "Uruguay": ["montevideo", "+598"],
    "Chile": ["santiago de chile", "+56"],
    "Brasil": ["são paulo", "sao paulo", "+55"],
    "Italia": ["pisa", "roma", "milano"],
    "España": ["madrid", "barcelona"],
    "EEUU": ["miami", "new york", "california"],
}

# Patents
PATENT_PATTERNS = [
    r"\b[A-Z]{2}\s?\d{3}\s?[A-Z]{2}\b",
    r"\b[A-Z]{3}\s?\d{3}\b",
]

# Vehicles
VEHICLE_KEYWORDS = [
    "auto", "moto", "camioneta", "camion", "utilitario",
    "ford", "chevrolet", "toyota", "honda", "volkswagen",
    "peugeot", "renault", "citroen", "fiat",
]


# ===========================================================================
# Dataclass
# ===========================================================================
@dataclass
class Lead:
    id: str = ""
    score: int = 0
    problem_category: str = ""
    problem_summary: str = ""
    person_name: str = ""
    username: str = ""
    profile_url: str = ""
    post_url: str = ""
    platform: str = ""
    date: str = ""
    discovery_timestamp: str = ""
    province: str = ""
    city: str = ""
    country: str = ""
    vehicle: str = ""
    patent: str = ""
    phone: str = ""
    whatsapp: str = ""
    whatsapp_link: str = ""
    snippet: str = ""
    has_phone: bool = False
    has_whatsapp: bool = False
    urgency_detected: bool = False
    urgency_keywords_found: List[str] = field(default_factory=list)
    recent_post: bool = False
    explicit_transfer_problem: bool = False
    multa_related: bool = False
    preventive_signal: bool = False
    institutional_source: bool = False
    unclear_country: bool = False
    review_state: str = "new"  # new / reviewed / contacted / ignored
    score_breakdown: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ===========================================================================
# z-ai web_search wrapper
# ===========================================================================
def web_search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    args = json.dumps({"query": query, "num": num}, ensure_ascii=False)
    tmp_file = f"/tmp/radar_leads_{hash(query) & 0xFFFFFFFF:x}.json"
    for attempt in range(3):
        try:
            result = subprocess.run(
                ["z-ai", "function", "-n", "web_search", "-a", args, "-o", tmp_file],
                capture_output=True, text=True, timeout=20,
            )
            if result.returncode != 0:
                stderr = result.stderr.lower()
                if "429" in stderr or "too many requests" in stderr:
                    wait = 5 * (attempt + 1)
                    print(f"  [rate-limit] {wait}s", file=sys.stderr)
                    time.sleep(wait)
                    continue
                return []
            with open(tmp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
    return []


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
# Step 1: Query generation (already in QUERIES)
# ===========================================================================

# ===========================================================================
# Step 2: Web retrieval (web_search function above)
# ===========================================================================

# ===========================================================================
# Step 3: Content filtering
# ===========================================================================
def passes_content_filter(text: str) -> bool:
    text_lower = text.lower()
    # must_include_one
    if not any(kw in text_lower for kw in MUST_INCLUDE_ONE):
        return False
    # reject_if_contains
    for reject in REJECT_IF_CONTAINS:
        if reject in text_lower:
            return False
    return True


# ===========================================================================
# Step 4: Signal extraction
# ===========================================================================
def extract_phone(text: str) -> str:
    for pattern in PHONE_PATTERNS:
        m = re.search(pattern, text)
        if m:
            digits = re.sub(r"\D", "", m.group(0))
            if 10 <= len(digits) <= 15:
                return digits
    return ""


def extract_whatsapp(text: str) -> str:
    for pattern in WHATSAPP_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            num = m.group(1) if m.groups() else m.group(0)
            digits = re.sub(r"\D", "", num)
            if 8 <= len(digits) <= 15:
                return digits
    return ""


def detect_urgency(text: str) -> Tuple[bool, List[str]]:
    text_lower = text.lower()
    found = [kw for kw in URGENCY_KEYWORDS if kw in text_lower]
    return len(found) > 0, found


def classify_problem(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for category, keywords in PROBLEM_CATEGORIES.items():
        scores[category] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def detect_country(text: str, url: str) -> str:
    text_lower = text.lower()

    # Check foreign indicators first
    for country, indicators in FOREIGN_INDICATORS.items():
        for ind in indicators:
            if ind in text_lower:
                return country

    # Check Argentina boost keywords
    for kw in ARGENTINA_BOOST_KEYWORDS:
        if kw.lower() in text_lower:
            return "Argentina"

    # Check phone patterns (Argentina)
    for pattern in PHONE_PATTERNS:
        if re.search(pattern, text):
            return "Argentina"

    # Check .ar domain
    host = get_host(url)
    if ".ar" in host:
        return "Argentina"

    return "Unknown"


def extract_location(text: str) -> Tuple[str, str]:
    text_lower = text.lower()
    cities = [
        ("la plata", "Buenos Aires"), ("rosario", "Santa Fe"),
        ("córdoba", "Córdoba"), ("cordoba", "Córdoba"),
        ("mendoza", "Mendoza"), ("paraná", "Entre Ríos"),
        ("parana", "Entre Ríos"), ("neuquén", "Neuquén"),
        ("neuquen", "Neuquén"), ("salta", "Salta"),
        ("lanús", "Buenos Aires"), ("lanus", "Buenos Aires"),
        ("avellaneda", "Buenos Aires"), ("quilmes", "Buenos Aires"),
        ("pilar", "Buenos Aires"), ("tigre", "Buenos Aires"),
    ]
    for city, prov in cities:
        if city in text_lower:
            return city.title(), prov
    for prov in ["buenos aires", "caba", "santa fe", "córdoba", "cordoba",
                 "mendoza", "entre ríos", "entre rios", "neuquén", "neuquen", "salta"]:
        if prov in text_lower:
            return "", prov.title()
    return "", ""


def extract_vehicle(text: str) -> str:
    text_lower = text.lower()
    for v in VEHICLE_KEYWORDS:
        if v in text_lower:
            return v
    return ""


def extract_patent(text: str) -> str:
    for pattern in PATENT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            return re.sub(r"\s+", "", m.group(0)).upper()
    return ""


def extract_username(result: Dict[str, Any]) -> str:
    text = f"{result.get('name', '')} {result.get('snippet', '')} {result.get('url', '')}"
    m = re.search(r"@(\w{3,20})", text)
    if m:
        return m.group(1)
    # Reddit user from URL
    m = re.search(r"/user/(\w+)", result.get("url", ""))
    if m:
        return m.group(1)
    return ""


def extract_person_name(result: Dict[str, Any]) -> str:
    text = f"{result.get('name', '')} {result.get('snippet', '')}"
    m = re.search(r"(?:hola\s+)?soy\s+([A-ZÁÉÍÓÚa-záéíóúñ]{3,20})", text, re.IGNORECASE)
    if m:
        return m.group(1).title()
    return ""


# ===========================================================================
# Step 5: Scoring engine
# ===========================================================================
def calculate_score(
    has_phone: bool,
    has_whatsapp: bool,
    urgency_detected: bool,
    recent_post: bool,
    explicit_transfer_problem: bool,
    multa_related: bool,
    preventive_signal: bool,
    institutional_source: bool,
    unclear_country: bool,
) -> Tuple[int, Dict[str, int]]:
    base = 20
    breakdown = {"base": base}

    if has_phone:
        breakdown["has_phone"] = 25
    if has_whatsapp:
        breakdown["has_whatsapp"] = 25
    if urgency_detected:
        breakdown["urgency_detected"] = 20
    if recent_post:
        breakdown["recent_post"] = 15
    if explicit_transfer_problem:
        breakdown["explicit_transfer_problem"] = 30
    if multa_related:
        breakdown["multa_related"] = 25
    if preventive_signal:
        breakdown["preventive_signal"] = 10

    # Penalties
    if institutional_source:
        breakdown["institutional_source"] = -20
    if unclear_country:
        breakdown["unclear_country"] = -15

    score = sum(breakdown.values())
    score = max(0, min(100, score))
    return score, breakdown


# ===========================================================================
# Step 6: Deduplication (composite hash)
# ===========================================================================
def dedup_composite_hash(leads: List[Lead]) -> List[Lead]:
    seen: Set[str] = set()
    out = []
    for lead in leads:
        components = [
            normalize_text(lead.snippet[:200]),
            lead.post_url,
            lead.username,
        ]
        composite = "|".join(components)
        h = hashlib.sha256(composite.encode("utf-8")).hexdigest()[:16]
        lead.id = h
        if h in seen:
            continue
        seen.add(h)
        out.append(lead)
    return out


# ===========================================================================
# Step 7: Temporal filter
# ===========================================================================
def temporal_filter(leads: List[Lead], window_days: int = 3) -> List[Lead]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    out = []
    for lead in leads:
        # Try post date first
        dt = parse_date(lead.date)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                lead.recent_post = True
                out.append(lead)
            continue
        # Fallback: use discovery timestamp
        dt_disc = parse_date(lead.discovery_timestamp)
        if dt_disc:
            if dt_disc.tzinfo is None:
                dt_disc = dt_disc.replace(tzinfo=timezone.utc)
            if dt_disc >= cutoff:
                out.append(lead)
            continue
        # If no date at all, keep (fallback_mode = use_discovery_timestamp)
        out.append(lead)
    return out


# ===========================================================================
# Build lead from search result
# ===========================================================================
def build_lead(result: Dict[str, Any], query: str) -> Optional[Lead]:
    name = result.get("name", "")
    snippet = result.get("snippet", "")
    url = result.get("url", "")
    date = result.get("date", "")
    host = get_host(url)
    combined = f"{name}. {snippet}"

    # Content filter
    if not passes_content_filter(combined):
        return None

    # Country filter
    country = detect_country(combined, url)
    if country.lower() in REJECT_COUNTRIES:
        return None

    # Signal extraction
    phone = extract_phone(combined)
    whatsapp = extract_whatsapp(combined)
    urgency, urgency_kws = detect_urgency(combined)
    problem_cat = classify_problem(combined)
    city, province = extract_location(combined)
    vehicle = extract_vehicle(combined)
    patent = extract_patent(combined)
    username = extract_username(result)
    person_name = extract_person_name(result)

    # Determine signal flags
    has_phone = bool(phone)
    has_whatsapp = bool(whatsapp)
    explicit_transfer = problem_cat == "TRANSFER_PROBLEM" or "transferencia" in combined.lower()
    multa_related = problem_cat == "FINE_DISPUTE" or "multa" in combined.lower()
    preventive = "vendo" in combined.lower() or "permuto" in combined.lower()
    institutional = any(d in host for d in INSTITUTIONAL_DOMAINS)
    unclear_country = country == "Unknown"

    # Temporal
    dt = parse_date(date)
    now = datetime.now(timezone.utc)
    recent = False
    if dt:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        recent = (now - dt) <= timedelta(days=RECENCY_DAYS)

    # Score
    score, breakdown = calculate_score(
        has_phone=has_phone,
        has_whatsapp=has_whatsapp,
        urgency_detected=urgency,
        recent_post=recent,
        explicit_transfer_problem=explicit_transfer,
        multa_related=multa_related,
        preventive_signal=preventive,
        institutional_source=institutional,
        unclear_country=unclear_country,
    )

    # Skip if below threshold
    if score < MIN_SCORE_THRESHOLD:
        return None

    # WhatsApp link
    wa_link = ""
    wa_num = whatsapp or phone
    if wa_num:
        if not wa_num.startswith("54") and len(wa_num) == 10:
            wa_num = "54" + wa_num
        wa_link = f"https://wa.me/{wa_num}"

    # Platform display
    platform_map = {
        "facebook.com": "Facebook", "reddit.com": "Reddit",
        "twitter.com": "X", "x.com": "X",
        "mercadolibre.com.ar": "MercadoLibre",
    }
    platform = platform_map.get(host, host.title() if host else "Unknown")

    # Problem summary
    summaries = {
        "TRANSFER_PROBLEM": "Problema de transferencia",
        "FINE_DISPUTE": "Disputa de multa/fotomulta",
        "OWNERSHIP_ISSUE": "Problema de titularidad",
        "DOCUMENTATION_ISSUE": "Problema documental",
    }
    summary = summaries.get(problem_cat, "Lead vehicular")

    return Lead(
        score=score,
        problem_category=problem_cat,
        problem_summary=summary,
        person_name=person_name or "(anónimo)",
        username=username,
        profile_url="",
        post_url=url,
        platform=platform,
        date=date,
        discovery_timestamp=now.isoformat(),
        province=province,
        city=city,
        country=country,
        vehicle=vehicle,
        patent=patent,
        phone=phone,
        whatsapp=whatsapp,
        whatsapp_link=wa_link,
        snippet=snippet[:300] if snippet else "",
        has_phone=has_phone,
        has_whatsapp=has_whatsapp,
        urgency_detected=urgency,
        urgency_keywords_found=urgency_kws,
        recent_post=recent,
        explicit_transfer_problem=explicit_transfer,
        multa_related=multa_related,
        preventive_signal=preventive,
        institutional_source=institutional,
        unclear_country=unclear_country,
        score_breakdown=breakdown,
    )


# ===========================================================================
# Pipeline runner
# ===========================================================================
def run_pipeline() -> Dict[str, Any]:
    start_time = time.time()
    execution_log = []
    all_leads: List[Lead] = []
    all_raw: List[Dict[str, Any]] = []
    queries_executed = 0

    execution_log.append({"step": "pipeline_start", "timestamp": datetime.now(timezone.utc).isoformat()})

    # Step 1+2: Query generation + Web retrieval
    for i, query in enumerate(QUERIES):
        elapsed = time.time() - start_time
        if elapsed > MAX_RUNTIME_SECONDS:
            execution_log.append({"step": "timeout", "elapsed_seconds": round(elapsed, 2)})
            break

        print(f"  [{i+1}/{len(QUERIES)}] {query[:60]}", file=sys.stderr)
        results = web_search(query, num=MAX_RESULTS_PER_QUERY)
        queries_executed += 1

        for r in results:
            r["_query"] = query
            all_raw.append(r)
            lead = build_lead(r, query)
            if lead:
                all_leads.append(lead)

        # Rate limit
        time.sleep(RATE_LIMIT_MS / 1000)

    execution_log.append({
        "step": "web_retrieval_complete",
        "queries_executed": queries_executed,
        "raw_results": len(all_raw),
        "leads_before_dedup": len(all_leads),
    })

    # Step 6: Deduplication
    all_leads = dedup_composite_hash(all_leads)
    execution_log.append({"step": "dedup_complete", "leads_after_dedup": len(all_leads)})

    # Step 7: Temporal filter
    all_leads = temporal_filter(all_leads, window_days=RECENCY_DAYS)
    execution_log.append({"step": "temporal_filter_complete", "leads_after_temporal": len(all_leads)})

    # Sort: score desc, then date desc
    all_leads.sort(key=lambda l: (l.score, l.date or l.discovery_timestamp), reverse=True)

    # Step 8: Storage
    leads_data = [l.to_dict() for l in all_leads]
    LEADS_LATEST.write_text(json.dumps(leads_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Append to history
    history = []
    if LEADS_HISTORY.exists():
        try:
            history = json.loads(LEADS_HISTORY.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "leads_count": len(leads_data),
        "leads": leads_data,
    })
    # Keep last 50 runs
    history = history[-50:]
    LEADS_HISTORY.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    # Dashboard payload
    metrics = {
        "total_leads": len(all_leads),
        "queries_executed": queries_executed,
        "runtime_seconds": round(time.time() - start_time, 2),
        "by_category": {},
        "by_platform": {},
        "with_contact": sum(1 for l in all_leads if l.has_phone or l.has_whatsapp),
        "avg_score": round(sum(l.score for l in all_leads) / len(all_leads), 1) if all_leads else 0,
    }
    for l in all_leads:
        metrics["by_category"][l.problem_category] = metrics["by_category"].get(l.problem_category, 0) + 1
        metrics["by_platform"][l.platform] = metrics["by_platform"].get(l.platform, 0) + 1

    DASHBOARD_PAYLOAD.write_text(json.dumps({"leads": leads_data, "metrics": metrics}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Step 9: Dashboard generator
    dashboard_html = generate_dashboard(leads_data, metrics)
    DASHBOARD_HTML.write_text(dashboard_html, encoding="utf-8")

    execution_log.append({"step": "pipeline_complete", "timestamp": datetime.now(timezone.utc).isoformat()})

    result = {
        "leads": leads_data,
        "metrics": metrics,
        "execution_log": execution_log,
    }

    print(f"\n  ✓ Pipeline complete: {len(all_leads)} leads in {metrics['runtime_seconds']}s", file=sys.stderr)
    print(f"  Dashboard: {DASHBOARD_HTML}", file=sys.stderr)
    return result


# ===========================================================================
# Dashboard generator (single-file static HTML with embedded JSON)
# ===========================================================================
def generate_dashboard(leads: List[Dict[str, Any]], metrics: Dict[str, Any]) -> str:
    embedded_json = json.dumps({"leads": leads, "metrics": metrics}, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Radar de Leads — Fotomultas</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
:root {{
  --bg: #f7f9fb; --card-bg: #fff; --border: #e0e5ee;
  --text: #1a1a2e; --text-muted: #6b7280;
  --primary: #0176d3; --primary-dark: #014486;
  --success: #2e844a; --warning: #ffb75d; --danger: #ba0517;
  --hot: #ff6b35;
}}
body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); }}

/* Header */
.header {{ background: var(--card-bg); border-bottom: 2px solid var(--border); padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }}
.header h1 {{ font-size: 18px; color: var(--primary-dark); }}
.header .stats {{ display: flex; gap: 20px; font-size: 13px; color: var(--text-muted); }}
.header .stats span b {{ color: var(--text); font-size: 16px; }}

/* Filters */
.filters {{ padding: 12px 24px; display: flex; gap: 12px; align-items: center; }}
.filter-btn {{ padding: 6px 16px; border: 1px solid var(--border); background: var(--card-bg); border-radius: 4px; cursor: pointer; font-size: 13px; color: var(--text-muted); }}
.filter-btn.active {{ background: var(--primary); color: white; border-color: var(--primary); }}

/* Lead cards */
.leads-container {{ padding: 0 24px 24px; max-width: 1400px; margin: 0 auto; }}
.lead-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 12px; display: flex; gap: 16px; transition: box-shadow 0.2s; }}
.lead-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
.lead-card.hot {{ border-left: 4px solid var(--hot); }}
.lead-card.reviewed {{ opacity: 0.6; }}
.lead-card.ignored {{ opacity: 0.4; }}

/* Score bar */
.score-section {{ min-width: 80px; text-align: center; }}
.score-value {{ font-size: 28px; font-weight: 700; line-height: 1; }}
.score-bar {{ height: 6px; background: var(--border); border-radius: 3px; margin-top: 6px; overflow: hidden; }}
.score-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
.score-label {{ font-size: 11px; color: var(--text-muted); margin-top: 4px; text-transform: uppercase; }}

/* Lead content */
.lead-content {{ flex: 1; min-width: 0; }}
.lead-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.problem-badge {{ padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
.badge-transfer {{ background: #e1f0ff; color: var(--primary); }}
.badge-fine {{ background: #ffe0e0; color: var(--danger); }}
.badge-ownership {{ background: #fff4e0; color: #b07000; }}
.badge-docs {{ background: #e8f5e9; color: var(--success); }}
.lead-platform {{ font-size: 12px; color: var(--text-muted); }}
.lead-snippet {{ font-size: 14px; color: var(--text); margin: 6px 0; line-height: 1.5; }}
.lead-meta {{ font-size: 12px; color: var(--text-muted); display: flex; gap: 12px; flex-wrap: wrap; }}

/* Actions */
.lead-actions {{ display: flex; flex-direction: column; gap: 6px; min-width: 120px; }}
.btn {{ padding: 6px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; text-decoration: none; text-align: center; }}
.btn-wa {{ background: #25d366; color: white; }}
.btn-wa:hover {{ background: #1da851; }}
.btn-link {{ background: var(--border); color: var(--text); }}
.btn-link:hover {{ background: #d1d5db; }}
.btn-state {{ background: transparent; border: 1px solid var(--border); color: var(--text-muted); font-size: 11px; }}
.btn-state.active {{ background: var(--primary); color: white; border-color: var(--primary); }}

/* Urgency indicator */
.urgency {{ display: inline-flex; align-items: center; gap: 2px; font-size: 11px; color: var(--hot); }}
.urgency::before {{ content: '🔥'; }}

/* Empty state */
.empty {{ text-align: center; padding: 60px; color: var(--text-muted); }}
</style>
</head>
<body>

<div class="header">
  <h1>🔍 Radar de Leads — Fotomultas</h1>
  <div class="stats">
    <span><b id="stat-total">0</b><br>leads</span>
    <span><b id="stat-contact">0</b><br>con contacto</span>
    <span><b id="stat-avg">0</b><br>score promedio</span>
  </div>
</div>

<div class="filters">
  <button class="filter-btn active" onclick="filterLeads('all_time')">Todo el tiempo</button>
  <button class="filter-btn" onclick="filterLeads('last_3_days')">Últimos 3 días</button>
  <input type="text" id="search-box" placeholder="Buscar..." style="padding:6px 12px; border:1px solid var(--border); border-radius:4px; width:200px;" oninput="renderLeads()">
</div>

<div class="leads-container" id="leads-container"></div>

<script>
const DATA = {embedded_json};
let currentFilter = 'all_time';
let reviewStates = JSON.parse(localStorage.getItem('radar_review_states') || '{{}}');

function getLeadState(id) {{
  return reviewStates[id] || 'new';
}}

function setLeadState(id, state) {{
  reviewStates[id] = state;
  localStorage.setItem('radar_review_states', JSON.stringify(reviewStates));
  renderLeads();
}}

function filterLeads(filter) {{
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  renderLeads();
}}

function isWithin3Days(lead) {{
  const dateStr = lead.date || lead.discovery_timestamp;
  if (!dateStr) return true;
  const d = new Date(dateStr);
  const diff = (Date.now() - d.getTime()) / (1000 * 60 * 60 * 24);
  return diff <= 3;
}}

function scoreColor(score) {{
  if (score >= 80) return '#2e844a';
  if (score >= 60) return '#0176d3';
  if (score >= 40) return #ffb75d;
  return #6b7280;
}}

function badgeClass(cat) {{
  return {{
    'TRANSFER_PROBLEM': 'badge-transfer',
    'FINE_DISPUTE': 'badge-fine',
    'OWNERSHIP_ISSUE': 'badge-ownership',
    'DOCUMENTATION_ISSUE': 'badge-docs'
  }}[cat] || 'badge-docs';
}}

function escapeHtml(t) {{
  const d = document.createElement('div');
  d.textContent = t || '';
  return d.innerHTML;
}}

function renderLeads() {{
  const search = document.getElementById('search-box').value.toLowerCase();
  let filtered = DATA.leads.filter(l => {{
    if (currentFilter === 'last_3_days' && !isWithin3Days(l)) return false;
    if (search && !(l.snippet + l.person_name + l.problem_summary + l.platform).toLowerCase().includes(search)) return false;
    return true;
  }});

  // Stats
  document.getElementById('stat-total').textContent = filtered.length;
  document.getElementById('stat-contact').textContent = filtered.filter(l => l.has_phone || l.has_whatsapp).length;
  const avg = filtered.length > 0 ? Math.round(filtered.reduce((a, l) => a + l.score, 0) / filtered.length) : 0;
  document.getElementById('stat-avg').textContent = avg;

  const container = document.getElementById('leads-container');
  if (filtered.length === 0) {{
    container.innerHTML = '<div class="empty">No hay leads que coincidan con el filtro.</div>';
    return;
  }}

  container.innerHTML = filtered.map(l => {{
    const state = getLeadState(l.id);
    const isHot = l.score >= 70;
    const urgencyStars = l.urgency_detected ? '<span class="urgency">urgente</span>' : '';
    const waBtn = l.whatsapp_link
      ? `<a class="btn btn-wa" href="${{l.whatsapp_link}}" target="_blank">WhatsApp</a>`
      : '<span style="font-size:11px;color:var(--text-muted);text-align:center;padding:6px;">Sin contacto</span>';
    const dateShort = l.date ? l.date.substring(0, 10) : (l.discovery_timestamp ? l.discovery_timestamp.substring(0, 10) : '—');

    return `
    <div class="lead-card ${{isHot ? 'hot' : ''}} ${{state !== 'new' ? state : ''}}">
      <div class="score-section">
        <div class="score-value" style="color:${{scoreColor(l.score)}}">${{l.score}}</div>
        <div class="score-bar"><div class="score-fill" style="width:${{l.score}}%;background:${{scoreColor(l.score)}}"></div></div>
        <div class="score-label">${{l.problem_category.replace('_',' ').substring(0,12)}}</div>
      </div>
      <div class="lead-content">
        <div class="lead-header">
          <span class="problem-badge ${{badgeClass(l.problem_category)}}">${{l.problem_summary}}</span>
          <span class="lead-platform">${{l.platform}}</span>
          ${{urgencyStars}}
        </div>
        <div class="lead-snippet">${{escapeHtml(l.snippet.substring(0, 200))}}</div>
        <div class="lead-meta">
          <span>👤 ${{escapeHtml(l.person_name)}}</span>
          ${{l.province ? `<span>📍 ${{l.province}}</span>` : ''}}
          ${{l.vehicle ? `<span>🚗 ${{l.vehicle}}</span>` : ''}}
          ${{l.patent ? `<span>🔢 ${{l.patent}}</span>` : ''}}
          <span>📅 ${{dateShort}}</span>
          ${{l.phone ? `<span>📞 ${{l.phone}}</span>` : ''}}
        </div>
      </div>
      <div class="lead-actions">
        ${{waBtn}}
        <a class="btn btn-link" href="${{l.post_url}}" target="_blank">Ver post</a>
        <div style="display:flex;gap:4px;margin-top:4px;">
          <button class="btn-state ${{state==='reviewed'?'active':''}}" onclick="setLeadState('${{l.id}}','reviewed')" title="Revisado">✓</button>
          <button class="btn-state ${{state==='contacted'?'active':''}}" onclick="setLeadState('${{l.id}}','contacted')" title="Contactado">📞</button>
          <button class="btn-state ${{state==='ignored'?'active':''}}" onclick="setLeadState('${{l.id}}','ignored')" title="Ignorar">✗</button>
        </div>
      </div>
    </div>`;
  }}).join('');
}}

renderLeads();
</script>
</body>
</html>"""


# ===========================================================================
# HTTP Server
# ===========================================================================
class RadarHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "/dashboard":
            self.serve_dashboard()
        elif self.path == "/data/leads_latest.json":
            self.serve_json(LEADS_LATEST)
        elif self.path == "/data/dashboard_payload.json":
            self.serve_json(DASHBOARD_PAYLOAD)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/radar/run":
            # Bearer auth
            auth = self.headers.get("Authorization", "")
            if RADAR_SECRET_TOKEN and auth != f"Bearer {RADAR_SECRET_TOKEN}":
                self.send_error(401, "Unauthorized")
                return
            # Run pipeline
            result = run_pipeline()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_error(404)

    def serve_dashboard(self):
        if DASHBOARD_HTML.exists():
            content = DASHBOARD_HTML.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "Dashboard not generated yet")

    def serve_json(self, path: Path):
        if path.exists():
            content = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}", file=sys.stderr)


# ===========================================================================
# Main
# ===========================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Radar de Leads Fotomultas v1.0.0")
    parser.add_argument("--run", action="store_true", help="Run pipeline directly")
    parser.add_argument("--serve", action="store_true", help="Start HTTP server")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    args = parser.parse_args()

    if args.run:
        result = run_pipeline()
        print(json.dumps({"metrics": result["metrics"], "execution_log": result["execution_log"]}, ensure_ascii=False, indent=2))
        return

    if args.serve:
        print(f"Starting server on :{args.port}", file=sys.stderr)
        print(f"  Dashboard: http://localhost:{args.port}/", file=sys.stderr)
        print(f"  API:       POST http://localhost:{args.port}/radar/run", file=sys.stderr)
        if RADAR_SECRET_TOKEN:
            print(f"  Auth: Bearer token required", file=sys.stderr)
        else:
            print(f"  Auth: NONE (set RADAR_SECRET_TOKEN env var)", file=sys.stderr)
        server = HTTPServer(("0.0.0.0", args.port), RadarHandler)
        server.serve_forever()

    # Default: run pipeline
    result = run_pipeline()
    print(f"\n✓ {len(result['leads'])} leads guardados en {LEADS_LATEST}")
    print(f"✓ Dashboard: {DASHBOARD_HTML}")


if __name__ == "__main__":
    main()

"""
source_registry.py — Source Registry v10.2 (Lite)

Descubre, puntúa y mantiene un registro de fuentes públicas argentinas
para el pipeline de leads.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Any
import sys

from search_providers import search as provider_search

REGISTRY_PATH = os.environ.get("SOURCE_REGISTRY_PATH", "data/source_registry.json")

SEED_SUBREDDITS = [
    "ArAutos", "argentina", "Cordoba", "BuenosAires",
    "DerechoGenial", "AskArgentina", "PreguntasReddit",
    "Mendoza", "Rosario", "Salta",
]

DISCOVERY_QUERIES = [
    'site:com.ar "transferencia" "auto" "multa"',
    'site:com.ar "fotomulta" "Argentina"',
    'site:com.ar "juez de faltas" auto',
    'site:com.ar "08 firmado" auto',
    'site:com.ar foro multas automotor',
    'site:reddit.com/r/ArAutos multa transferencia',
    'site:reddit.com/r/DerechoGenial fotomulta',
    'site:reddit.com/r/argentina libre deuda auto',
]

BLACKLIST_DOMAINS = {
    "gob.ar", "gov.ar", "jus.gov.ar", "dnrpa.jus.gov.ar",
    "clarin.com", "lanacion.com.ar", "infobae.com", "perfil.com",
    "tn.com.ar", "cronista.com", "ambito.com", "pagina12.com.ar",
    "iprofesional.com", "wikipedia.org", "youtube.com",
    "multabot.com.ar", "segurarse.com.ar", "iusnoticias.com.ar",
    "parrillacero5.com.ar", "autocosmos.com.ar",
    "facebook.com", "instagram.com", "tiktok.com",
}

VEHICLE_KEYWORDS = {"multa", "multas", "fotomulta", "transferencia", "08",
                     "libre deuda", "auto", "vehiculo", "patente", "registro",
                     "automotor", "juez de faltas", "veraz", "cedula"}

ARGENTINA_KEYWORDS = {"argentina", "caba", "buenos aires", "cordoba",
                       "rosario", "mendoza", "salta", ".ar"}


@dataclass
class Source:
    id: str = ""
    name: str = ""
    canonical_url: str = ""
    domain: str = ""
    platform: str = "other"
    status: str = "candidate"
    trust_score: int = 50
    noise_score: int = 0
    final_score: int = 50
    discovered_at: str = ""
    discovery_origin: str = "web_search"
    topics: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "runs": 0, "successful": 0, "failed": 0,
        "consecutive_failures": 0, "total_leads": 0,
        "last_success": "", "last_failure": "",
    })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_domain(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/")
        return f"{parsed.scheme}://{host}{path}"
    except Exception:
        return url


def make_source_id(url: str) -> str:
    import hashlib
    return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()[:12]


def score_source(source: Source) -> int:
    score = 50
    text = f"{source.name} {source.canonical_url} {' '.join(source.topics)}".lower()
    domain = source.domain.lower()

    if any(kw in text for kw in VEHICLE_KEYWORDS):
        score += 20
    if source.platform == "reddit" and "reddit.com/r/" in source.canonical_url:
        score += 15
    if any(kw in text or kw in domain for kw in ARGENTINA_KEYWORDS):
        score += 10
    if source.stats.get("total_leads", 0) > 0:
        score += 10

    if any(bl in domain for bl in BLACKLIST_DOMAINS):
        score -= 50
    if source.stats.get("consecutive_failures", 0) >= 3:
        score -= 30

    return max(0, min(100, score))


def discover_sources() -> List[Source]:
    print("[SourceHunter] Descubriendo fuentes nuevas...", file=sys.stderr)
    discovered = []
    seen_domains = set()

    for query in DISCOVERY_QUERIES:
        try:
            results = provider_search(query, num=10)
            print(f"  [{query[:50]}] -> {len(results)} resultados", file=sys.stderr)
            for r in results:
                url = r.get("url", "")
                if not url:
                    continue
                domain = get_domain(url)
                if not domain or domain in seen_domains:
                    continue
                if any(bl in domain for bl in BLACKLIST_DOMAINS):
                    continue

                platform = "other"
                if "reddit.com" in domain:
                    platform = "reddit"
                elif "mercadolibre" in domain or "mercadolivre" in domain:
                    platform = "marketplace"
                elif "t.me" in domain or "telegram" in domain:
                    platform = "telegram"
                elif any(kw in (r.get("title","") + r.get("snippet","")).lower()
                         for kw in ["foro", "forum", "comunidad"]):
                    platform = "forum"
                else:
                    platform = "blog"

                source = Source(
                    id=make_source_id(url),
                    name=r.get("title", "")[:100],
                    canonical_url=canonicalize_url(url),
                    domain=domain,
                    platform=platform,
                    status="candidate",
                    discovered_at=datetime.now(timezone.utc).isoformat(),
                    discovery_origin="web_search",
                    topics=["multas", "transferencia", "auto"],
                )
                source.final_score = score_source(source)
                if source.final_score >= 70:
                    source.status = "approved"
                elif source.final_score < 40:
                    source.status = "rejected"
                discovered.append(source)
                seen_domains.add(domain)
            time.sleep(2)
        except Exception as e:
            print(f"  [SourceHunter] error en query: {e}", file=sys.stderr)
            continue

    print(f"[SourceHunter] Descubiertas {len(discovered)} fuentes nuevas", file=sys.stderr)
    return discovered


def load_registry() -> Dict[str, Any]:
    if not os.path.exists(REGISTRY_PATH):
        return {
            "metadata": {
                "version": "10.2",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "sources": [],
        }
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"metadata": {}, "sources": []}


def save_registry(registry: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(REGISTRY_PATH) or ".", exist_ok=True)
    registry["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)


def merge_sources(existing: List, new: List[Source]) -> List:
    by_url = {}
    for s in existing:
        if isinstance(s, Source):
            by_url[s.canonical_url] = s
        elif isinstance(s, dict):
            by_url[s.get("canonical_url","")] = s
    for s in new:
        if s.canonical_url in by_url:
            continue
        by_url[s.canonical_url] = s
    return list(by_url.values())


def update_source_stats(source: Source, success: bool, leads_found: int) -> None:
    s = source.stats
    s["runs"] += 1
    if success:
        s["successful"] += 1
        s["consecutive_failures"] = 0
        s["last_success"] = datetime.now(timezone.utc).isoformat()
        s["total_leads"] += leads_found
    else:
        s["failed"] += 1
        s["consecutive_failures"] += 1
        s["last_failure"] = datetime.now(timezone.utc).isoformat()
        if s["consecutive_failures"] >= 3:
            source.status = "paused"


def seed_subreddits() -> List[Source]:
    sources = []
    for sub in SEED_SUBREDDITS:
        url = f"https://www.reddit.com/r/{sub}/"
        s = Source(
            id=make_source_id(url),
            name=f"r/{sub}",
            canonical_url=url,
            domain="reddit.com",
            platform="reddit",
            status="approved",
            discovered_at=datetime.now(timezone.utc).isoformat(),
            discovery_origin="seed",
            topics=["autos", "argentina", "multas", "transferencia"],
        )
        s.final_score = 80
        sources.append(s)
    return sources


def run_discovery_and_update() -> Dict[str, Any]:
    registry = load_registry()
    existing_sources = []
    for s in registry.get("sources", []):
        if isinstance(s, dict):
            try:
                existing_sources.append(Source(**{k: v for k, v in s.items()
                                                  if k in Source.__dataclass_fields__}))
            except Exception:
                pass
        elif isinstance(s, Source):
            existing_sources.append(s)

    if not existing_sources:
        existing_sources = seed_subreddits()
        print(f"[SourceHunter] Sembrados {len(existing_sources)} subreddits AR", file=sys.stderr)

    new_sources = discover_sources()
    all_sources = merge_sources(existing_sources, new_sources)

    registry["sources"] = [s.to_dict() if isinstance(s, Source) else s for s in all_sources]
    save_registry(registry)

    approved = [s for s in all_sources if (s.status if isinstance(s, Source) else s.get("status")) == "approved"]
    print(f"[SourceHunter] Registry: {len(all_sources)} total, {len(approved)} approved",
          file=sys.stderr)

    return registry


def get_approved_sources() -> List[Source]:
    """Devuelve las fuentes approved para que el pipeline las use."""
    registry = load_registry()
    out = []
    for s in registry.get("sources", []):
        if s.get("status") == "approved":
            try:
                out.append(Source(**{k: v for k, v in s.items()
                                     if k in Source.__dataclass_fields__}))
            except Exception:
                pass
    return out


if __name__ == "__main__":
    reg = run_discovery_and_update()
    print(f"\nOK Registry guardado en {REGISTRY_PATH}")
    print(f"  Sources: {len(reg['sources'])}")
    print(f"  Approved: {len([s for s in reg['sources'] if s['status']=='approved'])}")

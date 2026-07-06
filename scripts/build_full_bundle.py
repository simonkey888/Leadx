#!/usr/bin/env python3
"""
build_full_bundle.py — Empaqueta TODOS los archivos del proyecto LeadX en un único .md descargable.
Genera /home/z/my-project/download/LEADX_CODIGO_COMPLETO.md
"""
from pathlib import Path
from datetime import datetime, timezone
import html

OUT = Path("/home/z/my-project/download/LEADX_CODIGO_COMPLETO.md")
REPO = Path("/tmp/leadx_repo")

FILES = [
    ("worker.js", "javascript", "Cloudflare Worker v3 — HTML embebido + 20+ endpoints API + CRM dashboard + cron edge"),
    ("generate_payload.py", "python", "Pipeline Python (GH Actions cada 1h) — scraping Reddit RSS + VentaFe + scoring + OSINT + mining"),
    ("search_providers.py", "python", "Providers: Reddit /search.rss, Facebook via DDG, ForoArgentina, MercadoLibre Q&A"),
    ("source_registry.py", "python", "Registro de fuentes y rotación de queries"),
    ("pending_queries_kv.py", "python", "Helper para persistir queries pendientes en KV"),
    ("generate_payload_old_zai.py", "python", "Versión legacy del pipeline usando z-ai web_search (backup)"),
    ("wrangler.toml", "toml", "Config Cloudflare Worker — KV binding + cron trigger cada 1h"),
    (".github/workflows/radar-cron.yml", "yaml", "GitHub Actions — cron cada 1h, ejecuta generate_payload.py + commit JSONs"),
    ("README.md", "markdown", "Documentación del proyecto"),
    ("dashboard_payload.schema.json", "json", "Schema del payload que consume el dashboard"),
    ("crm_dashboard.html", "html", "HTML estático del CRM (referencia, el worker.js tiene el embebido)"),
]

def get_repo_file(rel_path: str) -> str:
    p = REPO / rel_path
    if not p.exists():
        return f"[ARCHIVO NO ENCONTRADO: {rel_path}]"
    return p.read_text(encoding="utf-8", errors="replace")

def build():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = []
    lines.append("# 📦 LeadX — Código Completo (Bundle Único)")
    lines.append("")
    lines.append(f"**Generado:** {now}  ")
    lines.append(f"**Repo:** https://github.com/simonkey888/Leadx  ")
    lines.append(f"**Deploy:** https://leadx.simondalmasso44.workers.dev  ")
    lines.append(f"**Stack:** Cloudflare Worker (edge) + Python GH Actions (scoring) + KV storage")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📋 Índice de Archivos")
    lines.append("")
    lines.append("| # | Archivo | Líneas | Descripción |")
    lines.append("|---|---------|--------|-------------|")
    for i, (rel, _, desc) in enumerate(FILES, 1):
        content = get_repo_file(rel)
        n = content.count("\n") + 1
        lines.append(f"| {i} | `{rel}` | {n:,} | {desc} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🏗️ Arquitectura")
    lines.append("")
    lines.append("```")
    lines.append("┌─────────────────────────────────────────────────────────────┐")
    lines.append("│  GITHUB ACTIONS (cron cada 1h)                              │")
    lines.append("│  ┌─────────────────────────────────────────────────────┐   │")
    lines.append("│  │ generate_payload.py                                 │   │")
    lines.append("│  │  1. scrape_ventafe_leads()  → VentaFe (HTML + tel)  │   │")
    lines.append("│  │  2. search_reddit()         → /search.rss (Atom)    │   │")
    lines.append("│  │  3. extract_entities()      → phone/patent/persona  │   │")
    lines.append("│  │  4. classify_and_score()    → heat 0-100            │   │")
    lines.append("│  │  5. dedup by ID                                     │   │")
    lines.append("│  │  6. POST /api/ingest → Worker (deep merge por ID)   │   │")
    lines.append("│  └─────────────────────────────────────────────────────┘   │")
    lines.append("└──────────────────────────────┬──────────────────────────────┘")
    lines.append("                               │")
    lines.append("                               ▼")
    lines.append("┌─────────────────────────────────────────────────────────────┐")
    lines.append("│  CLOUDFLARE WORKER (edge IP, cron cada 1h)                  │")
    lines.append("│  ┌─────────────────────────────────────────────────────┐   │")
    lines.append("│  │ worker.js                                           │   │")
    lines.append("│  │  • CRM HTML embebido (single file)                  │   │")
    lines.append("│  │  • /api/leads         GET  → lista paginada          │   │")
    lines.append("│  │  • /api/ingest        POST → deep merge por ID       │   │")
    lines.append("│  │  • /api/cron-run      GET  → scraping Reddit+VentaFe │   │")
    lines.append("│  │  • /api/enrich-all    GET  → clasific.ar + OSINT     │   │")
    lines.append("│  │  • /api/shadow-osint  GET  → Linktree Hunter         │   │")
    lines.append("│  │  • /api/ventafe-debug GET  → debug HTML VentaFe      │   │")
    lines.append("│  │  • normalizePhoneAR() → 27 códigos de área AR        │   │")
    lines.append("│  │  • Pinned leads (13 curados primeros)                │   │")
    lines.append("│  └─────────────────────────────────────────────────────┘   │")
    lines.append("│           │                                                 │")
    lines.append("│           ▼                                                 │")
    lines.append("│  ┌─────────────────────────────────────────────────────┐   │")
    lines.append("│  │ KV: LEADX_KV (leads + history + pinned)             │   │")
    lines.append("│  └─────────────────────────────────────────────────────┘   │")
    lines.append("└─────────────────────────────────────────────────────────────┘")
    lines.append("                               │")
    lines.append("                               ▼")
    lines.append("  Frontend read-only: leadx.simondalmasso44.workers.dev")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, (rel, lang, desc) in enumerate(FILES, 1):
        content = get_repo_file(rel)
        lines.append(f"## {i}. `{rel}`")
        lines.append("")
        lines.append(f"**Descripción:** {desc}  ")
        lines.append("")
        lines.append(f"```{lang}")
        lines.append(content.rstrip())
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Footer
    lines.append("## 🔑 Secrets / Variables Necesarias")
    lines.append("")
    lines.append("| Lugar | Variable | Uso |")
    lines.append("|-------|----------|-----|")
    lines.append("| Cloudflare KV secret | `INGEST_SECRET` | Auth X-Webhook-Secret en /api/ingest |")
    lines.append("| Cloudflare KV secret | `LEGACY_SECRET_REMOVED` | Token API interno |")
    lines.append("| GitHub Actions secret | `ZAI_API_KEY` | z-ai web_search SDK |")
    lines.append("| GitHub Actions secret | `WEBHOOK_URL` | URL del Worker /api/ingest |")
    lines.append("| GitHub Actions secret | `WEBHOOK_SECRET` | debe matchear INGEST_SECRET |")
    lines.append("| Apify (opcional) | `APIFY_TOKEN` | Facebook scraper con cookies |")
    lines.append("| Apify (opcional) | `WA_VALIDATOR_TOKEN` | WhatsApp validator (fire & forget) |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**Bundle generado automáticamente el {now}**")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK → {OUT}")
    print(f"Tamaño: {OUT.stat().st_size:,} bytes ({OUT.stat().st_size/1024:.1f} KB)")
    print(f"Líneas totales: {len(lines):,}")

if __name__ == "__main__":
    build()

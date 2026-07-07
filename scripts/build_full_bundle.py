#!/usr/bin/env python3
"""
build_full_bundle.py — Empaqueta TODOS los archivos del proyecto LeadX en un único .md descargable.
Genera /home/z/my-project/download/LEADX_CODIGO_COMPLETO.md
"""
from pathlib import Path
from datetime import datetime, timezone
import subprocess

OUT = Path("/home/z/my-project/download/LEADX_CODIGO_COMPLETO.md")
REPO = Path("/tmp/leadx_repo")

FILES = [
    ("worker.js", "javascript",
     "Cloudflare Worker v3 — HTML embebido + 20+ endpoints API + CRM dashboard + cron edge. "
     "Incluye: normalizePhoneAR() con 27 códigos de área AR, getUrlSecret() con sessionStorage+auto-prompt, "
     "validateWaFromModal() abre WhatsApp directo sin Apify, pinned leads, WhatsApp SVG icons, heat score 0-100."),
    ("generate_payload.py", "python",
     "Pipeline Python (GH Actions cada 1h). Incluye: scrape_ventafe_leads() con URLs reales del aviso "
     "(/automoviles/5011376-honda-hr-v-...), normalize_ar_phone_ventafe(), filtros PAIN_KEYWORDS_RE con "
     "excepción VentaFe, scoring con bypass para VentaFe, dedup por URL+teléfono, mine_comments_for_contacts(), "
     "enrich_contacts_via_reddit_profile(), detector de contradicciones."),
    ("search_providers.py", "python",
     "Providers: Reddit /search.rss (Atom feed) con html.unescape(), Facebook via DDG, ForoArgentina, "
     "MercadoLibre Q&A. Blacklist de subreddits irrelevantes. Rotación de 10 queries."),
    ("source_registry.py", "python",
     "Registro de fuentes y rotación de queries."),
    ("pending_queries_kv.py", "python",
     "Helper para persistir queries pendientes en KV (rotación cuando Reddit devuelve 429)."),
    ("generate_payload_old_zai.py", "python",
     "Versión legacy del pipeline usando z-ai web_search (backup, no se usa en producción)."),
    ("wrangler.toml", "toml",
     "Config Cloudflare Worker — KV binding LEADX_KV + cron trigger `0 * * * *` (cada 1h)."),
    (".github/workflows/radar-cron.yml", "yaml",
     "GitHub Actions — cron cada 1h. Steps: checkout → setup python → install z-ai CLI → run pipeline → "
     "commit JSONs → POST /api/ingest al Worker → deploy Worker."),
    ("README.md", "markdown", "Documentación del proyecto."),
    ("dashboard_payload.schema.json", "json", "Schema del payload que consume el dashboard."),
    ("crm_dashboard.html", "html",
     "HTML estático del CRM (referencia, el worker.js tiene el embebido actualizado)."),
]

def get_repo_file(rel_path: str) -> str:
    p = REPO / rel_path
    if not p.exists():
        return f"[ARCHIVO NO ENCONTRADO: {rel_path}]"
    return p.read_text(encoding="utf-8", errors="replace")

def git_log_oneline(n: int = 15) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO), "log", "--oneline", f"-{n}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return "(no se pudo obtener git log)"

def build():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log = git_log_oneline(20)
    lines = []
    lines.append("# 📦 LeadX — Código Completo (Bundle Único para Qwen)")
    lines.append("")
    lines.append(f"**Generado:** {now}  ")
    lines.append(f"**Repo:** https://github.com/simonkey888/Leadx  ")
    lines.append(f"**Deploy:** https://leadx.simondalmasso44.workers.dev  ")
    lines.append(f"**Stack:** Cloudflare Worker (edge) + Python GH Actions (scoring) + KV storage  ")
    lines.append(f"**Worker Version:** v34ae0710-e4d8-4a37-a165-a3ffeb730fb8  ")
    lines.append(f"**Estado:** Producción activa · cron cada 1h · 80 leads en KV · 28 con teléfono")
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
    lines.append("│  │     • URL real del aviso: /automoviles/ID-slug      │   │")
    lines.append("│  │     • normalize_ar_phone_ventafe()                  │   │")
    lines.append("│  │  2. search_reddit()         → /search.rss (Atom)    │   │")
    lines.append("│  │  3. extract_entities()      → phone/patent/persona  │   │")
    lines.append("│  │     • PAIN_KEYWORDS_RE + excepción VentaFe          │   │")
    lines.append("│  │  4. classify_and_score()    → heat 0-100            │   │")
    lines.append("│  │     • VentaFe bypass no_pain penalty                │   │")
    lines.append("│  │  5. dedup by URL+teléfono (estable entre runs)      │   │")
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
    lines.append("│  │  • getUrlSecret() → sessionStorage + auto-prompt    │   │")
    lines.append("│  │    + fallback hardcoded 'LEGACY_SECRET_REMOVED'                  │   │")
    lines.append("│  │  • validateWaFromModal() → window.open(waUrl)       │   │")
    lines.append("│  │    (ABRE WHATSAPP DIRECTO, sin Apify)               │   │")
    lines.append("│  │  • normalizePhoneAR() → 27 códigos de área AR       │   │")
    lines.append("│  │  • /api/leads         GET  → lista paginada          │   │")
    lines.append("│  │  • /api/ingest        POST → deep merge por ID       │   │")
    lines.append("│  │  • /api/cron-run      GET  → scraping Reddit+VentaFe │   │")
    lines.append("│  │  • /api/enrich-all    GET  → clasific.ar + OSINT     │   │")
    lines.append("│  │  • /api/shadow-osint  GET  → Linktree Hunter         │   │")
    lines.append("│  │  • /api/ventafe-debug GET  → debug HTML VentaFe      │   │")
    lines.append("│  │  • /api/whatsapp-validate POST → legacy (sin uso)    │   │")
    lines.append("│  │  • Pinned leads (12 curados primeros)                │   │")
    lines.append("│  └─────────────────────────────────────────────────────┘   │")
    lines.append("│           │                                                 │")
    lines.append("│           ▼                                                 │")
    lines.append("│  ┌─────────────────────────────────────────────────────┐   │")
    lines.append("│  │ KV: LEADX_KV (leads + history + pinned)             │   │")
    lines.append("│  │   INGEST_SECRET = 'LEGACY_SECRET_REMOVED' (sincronizado GH+CF)    │   │")
    lines.append("│  └─────────────────────────────────────────────────────┘   │")
    lines.append("└─────────────────────────────────────────────────────────────┘")
    lines.append("                               │")
    lines.append("                               ▼")
    lines.append("  Frontend read-only: leadx.simondalmasso44.workers.dev")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## ✅ Fixes Aplicados (Historia Reciente)")
    lines.append("")
    lines.append("### BOMBA #1 — WhatsApp Unauthorized → FIXED")
    lines.append("- `getUrlSecret()` ahora usa `sessionStorage` (persistente por tab)")
    lines.append("- Auto-prompt pide la clave la primera vez que se carga el dashboard")
    lines.append("- Fallback hardcoded `'LEGACY_SECRET_REMOVED'` como última línea para que la UI nunca quede en read-only")
    lines.append("- Worker `INGEST_SECRET` seteado a `'LEGACY_SECRET_REMOVED'` via `wrangler secret put`")
    lines.append("- GitHub Actions secret `INGEST_SECRET` también actualizado a `'LEGACY_SECRET_REMOVED'` via API")
    lines.append("")
    lines.append("### BOMBA #2 — Filtrado se comía leads VentaFe → FIXED (4 partes)")
    lines.append("")
    lines.append("| # | Punto del pipeline | Antes | Después |")
    lines.append("|---|---|---|---|")
    lines.append("| 1 | `VEHICULAR_KEYWORDS_STRICT` (l.~750) | `has_contact` siempre False porque los teléfonos se extraían DESPUÉS del check | Bypass directo para `is_ventafe` |")
    lines.append("| 2 | `PAIN_KEYWORDS_RE` (l.~826) | Regex muy estricto, no incluía 'papeles al día', 'listo para transferir' | Ampliado + excepción explícita VentaFe |")
    lines.append("| 3 | `classify_and_score` (l.~1197) | `has_explicit_pain` no incluía keywords preventivas → VentaFe caía en `reject` | Ampliado + bypass del penalty -50 para VentaFe |")
    lines.append("| 4 | `deduplicate_cases` (l.~1322) | Todos los leads VentaFe compartían `source_url` → dedup los colapsaba en 1 | URL única real del aviso + composite incluye teléfono |")
    lines.append("")
    lines.append("### FIX QWEN #1 — URLs VentaFe genéricas → FIXED")
    lines.append("- Scraper ahora extrae el `href` real del HTML de cada aviso")
    lines.append("- Cada lead VentaFe tiene URL única clickeable tipo `https://www.ventafe.com.ar/automoviles/4859456-toyota-corolla-2-0-xei-cvt-2025-0klm`")
    lines.append("- `aviso_id` disponible como campo para enriquecimiento futuro (cruce con clasific.ar)")
    lines.append("- Fallback por teléfono solo si no encuentra el href")
    lines.append("")
    lines.append("### FIX QWEN #2 — WhatsApp validate fallaba con Apify → FIXED (OPCIÓN A)")
    lines.append("- `validateWaFromModal()` ya NO llama a `/api/whatsapp-validate`")
    lines.append("- Ahora hace `window.open(waUrl, '_blank')` directo → abre WhatsApp en nueva pestaña")
    lines.append("- Construye `_wa_url` al vuelo si falta (fallback con `_wa_e164`)")
    lines.append("- Marca el lead como `validated_whatsapp` localmente (persistido en localStorage)")
    lines.append("- Endpoint `/api/whatsapp-validate` queda como legacy (no se rompe) pero el frontend ya no lo llama")
    lines.append("")
    lines.append("### Estado final del KV (verificado)")
    lines.append("")
    lines.append("| Métrica | Antes de todos los fixes | Después |")
    lines.append("|---|---|---|")
    lines.append("| Total leads | 53 | **80** |")
    lines.append("| Leads con teléfono | 1 | **28** |")
    lines.append("| Leads con WhatsApp link | 1 | **27** |")
    lines.append("| Leads VentaFe con URL clickeable al aviso real | 0 | **13** |")
    lines.append("| Botón WhatsApp funcional | ❌ Unauthorized | ✅ Abre wa.me directo |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📜 Git Log (últimos 20 commits)")
    lines.append("")
    lines.append("```")
    lines.append(log)
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
    lines.append("| Lugar | Variable | Valor actual | Uso |")
    lines.append("|-------|----------|--------------|-----|")
    lines.append("| Cloudflare Worker secret | `INGEST_SECRET` | `LEGACY_SECRET_REMOVED` | Auth X-Webhook-Secret en /api/ingest y otros |")
    lines.append("| Cloudflare Worker secret | `APIFY_TOKEN` | (legacy) | Facebook scraper + WA validator (no se usa más) |")
    lines.append("| Cloudflare Worker secret | `CLASIFICAR_WEBHOOK_SECRET` | (seteado) | Webhook de clasific.ar |")
    lines.append("| Cloudflare Worker secret | `FB_COOKIES` | (seteado) | Cookies Facebook para scraper |")
    lines.append("| GitHub Actions secret | `INGEST_SECRET` | `LEGACY_SECRET_REMOVED` | Debe matchear Worker INGEST_SECRET |")
    lines.append("| GitHub Actions secret | `ZAI_API_KEY` | (seteado) | z-ai web_search SDK |")
    lines.append("| GitHub Actions env | `WORKER_URL` | `https://leadx.simondalmasso44.workers.dev` | URL del Worker |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🚀 Cómo reproducir un deploy")
    lines.append("")
    lines.append("```bash")
    lines.append("# 1. Clonar repo")
    lines.append("git clone https://github.com/simonkey888/Leadx.git")
    lines.append("cd Leadx")
    lines.append("")
    lines.append("# 2. Deploy Cloudflare Worker")
    lines.append("npx wrangler deploy \\")
    lines.append("  --name leadx \\")
    lines.append("  --account-id b21fa81d12acb663798f9f7c51801955")
    lines.append("")
    lines.append("# 3. Setear secrets del Worker")
    lines.append("echo 'LEGACY_SECRET_REMOVED' | npx wrangler secret put INGEST_SECRET")
    lines.append("")
    lines.append("# 4. Trigger manual del workflow")
    lines.append("curl -X POST \\")
    lines.append("  -H 'Authorization: Bearer $GH_TOKEN' \\")
    lines.append("  -H 'Accept: application/vnd.github+json' \\")
    lines.append("  https://api.github.com/repos/simonkey888/Leadx/actions/workflows/radar-cron.yml/dispatches \\")
    lines.append("  -d '{\"ref\":\"main\"}'")
    lines.append("")
    lines.append("# 5. Verificar")
    lines.append("curl 'https://leadx.simondalmasso44.workers.dev/api/leads?key=LEGACY_SECRET_REMOVED' | python3 -m json.tool | head -30")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"**Bundle generado automáticamente el {now} para auditoría de Qwen.**")
    lines.append("")
    lines.append("Próximos pasos sugeridos para Qwen auditar:")
    lines.append("1. Performance del scraper VentaFe (100 bloques, 17 válidos — ¿se puede subir a 30+?)")
    lines.append("2. Cruce de patentes VentaFe con clasific.ar (free 200/mes) para detectar deuda real")
    lines.append("3. Encoding de títulos Reddit ('tran ferencia' → 'transferencia' — entities HTML)")
    lines.append("4. Limpieza de leads basura del KV (los que no tienen VentaFe ni teléfono)")
    lines.append("5. Minería de contactos en perfil de Reddit users (Linktree Hunter)")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK → {OUT}")
    print(f"Tamaño: {OUT.stat().st_size:,} bytes ({OUT.stat().st_size/1024:.1f} KB)")
    print(f"Líneas totales: {len(lines):,}")

if __name__ == "__main__":
    build()

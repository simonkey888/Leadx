#!/usr/bin/env python3
"""
extract_patentes_vlm.py — Extrae patentes de imágenes de leads de Facebook
usando z-ai vision (VLM). Más preciso que Tesseract para capturas de actas.

Uso:
    python scripts/extract_patentes_vlm.py

Flujo:
    1. Descarga leads del Worker (/api/leads)
    2. Filtra leads de FB con imágenes y sin patente
    3. Descarga cada imagen
    4. Pasa por z-ai vision preguntando "¿hay patente visible?"
    5. Si encuentra → POST /api/enrich-patente al Worker
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

WORKER_URL = os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
SECRET = os.environ.get("INGEST_SECRET", "LEGACY_SECRET_REMOVED")
MAX_LEADS = 20
PATENTE_RE = re.compile(r'\b([A-Z]{2}\s?\d{3}\s?[A-Z]{2}|[A-Z]{3}\s?\d{3})\b', re.IGNORECASE)
BLACKLIST = {"CEL", "CON", "DIR", "TEL", "WSP", "WPP", "CBU", "DNI", "URL", "WEB", "IMG", "JPG", "PNG", "PDF", "CP", "ID", "PIN", "NRO"}


def validate_patente(text):
    """Valida y normaliza patente AR. Retorna None si es falso positivo."""
    if not text:
        return None
    clean = re.sub(r'[^A-Z0-9]', '', text.upper())
    # Mercosur: AB123CD (7 chars)
    if len(clean) == 7:
        m = re.match(r'^([A-Z]{2})(\d{3})([A-Z]{2})$', clean)
        if m:
            return f"{m.group(1)} {m.group(2)} {m.group(3)}"
    # Tradicional: ABC123 (6 chars)
    if len(clean) == 6:
        m = re.match(r'^([A-Z]{3})(\d{3})$', clean)
        if m and m.group(1) not in BLACKLIST:
            return f"{m.group(1)} {m.group(2)}"
    return None


def download_image(url, filepath):
    """Descarga imagen de FB CDN."""
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            with open(filepath, 'wb') as f:
                f.write(data)
        return True
    except Exception as e:
        print(f"  [VLM] Error descargando imagen: {e}", file=sys.stderr)
        return False


def vlm_extract_patente(image_path):
    """Usa z-ai vision CLI para extraer patente de la imagen."""
    try:
        result = subprocess.run(
            ['z-ai', 'vision',
             '-p', 'Mirá esta imagen con atención. ¿Se ve una patente de vehículo argentino? Si sí, respondé SOLO el código de la patente (ej: AB 123 CD o ABC 123). Si no hay patente visible, respondé SOLO la palabra NINGUNA.',
             '-i', image_path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return None
        # Parsear respuesta del VLM
        output = result.stdout
        try:
            data = json.loads(output)
            text = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        except Exception:
            text = output.strip()

        if not text or 'NINGUNA' in text.upper():
            return None

        # Validar que sea una patente real
        patente = validate_patente(text)
        return patente
    except Exception as e:
        print(f"  [VLM] Error: {e}", file=sys.stderr)
        return None


def main():
    print("=" * 60, file=sys.stderr)
    print("  LeadX — Extractor de Patentes VLM", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 1. Descargar leads del Worker
    print("[1/4] Descargando leads del Worker...", file=sys.stderr)
    try:
        req = urllib.request.Request(
            f"{WORKER_URL}/api/leads?key={SECRET}",
            headers={'Accept': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"Error descargando leads: {e}", file=sys.stderr)
        return

    leads = data.get('leads_all', data.get('leads', []))
    print(f"  Total leads en KV: {len(leads)}", file=sys.stderr)

    # 2. Filtrar leads de FB con imágenes y sin patente
    candidates = []
    for lead in leads:
        if lead.get('patente'):
            continue  # Ya tiene patente
        if 'facebook' not in (lead.get('platform', '') + lead.get('source', '')).lower():
            continue  # No es de FB
        # Buscar imágenes en el lead
        images = lead.get('images', []) or lead.get('imageUrl', '') or lead.get('image_url', '')
        if isinstance(images, str):
            images = [images] if images else []
        if not images:
            continue
        candidates.append({**lead, '_images': images[:3]})  # Máx 3 imágenes por lead

    print(f"  Leads candidatos (FB + imágenes + sin patente): {len(candidates)}", file=sys.stderr)

    if not candidates:
        print("  No hay candidatos. Saliendo.", file=sys.stderr)
        return

    # 3. Procesar cada lead
    print(f"[2/4] Procesando {min(len(candidates), MAX_LEADS)} leads...", file=sys.stderr)
    enriched = 0

    for lead in candidates[:MAX_LEADS]:
        lead_id = lead.get('id', '')
        persona = lead.get('persona', '?')[:25]
        print(f"\n  Procesando: {persona} (id={lead_id})", file=sys.stderr)

        for img_url in lead['_images']:
            # Descargar imagen
            img_path = f"/tmp/lead_{lead_id}.jpg"
            if not download_image(img_url, img_path):
                continue

            # VLM extract
            print(f"    Analizando imagen con VLM...", file=sys.stderr)
            patente = vlm_extract_patente(img_path)

            # Limpiar
            try:
                os.remove(img_path)
            except:
                pass

            if patente:
                print(f"    ✅ PATENTE ENCONTRADA: {patente}", file=sys.stderr)
                # 4. Enviar al Worker
                payload = json.dumps({
                    "lead_id": lead_id,
                    "patentes": [{"patente": patente, "tipo": "mercosur" if len(patente.replace(" ", "")) == 7 else "tradicional", "confianza": 0.85}],
                    "score_boost": 15,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }).encode('utf-8')

                try:
                    req = urllib.request.Request(
                        f"{WORKER_URL}/api/enrich-patente",
                        data=payload,
                        headers={
                            'X-Webhook-Secret': SECRET,
                            'Content-Type': 'application/json'
                        },
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        result = json.loads(resp.read().decode('utf-8'))
                    if result.get('ok'):
                        print(f"    ✓ Lead enriquecido en KV. Score: {result.get('new_score')}", file=sys.stderr)
                        enriched += 1
                    else:
                        print(f"    ✕ Error: {result}", file=sys.stderr)
                except Exception as e:
                    print(f"    ✕ Error enviando: {e}", file=sys.stderr)

                break  # Pasar al siguiente lead
            else:
                print(f"    — No se detectó patente en esta imagen", file=sys.stderr)

            time.sleep(1)  # Rate limit VLM

    # Resumen
    print(f"\n[4/4] Resumen:", file=sys.stderr)
    print(f"  Leads procesados: {min(len(candidates), MAX_LEADS)}", file=sys.stderr)
    print(f"  Patentes encontradas: {enriched}", file=sys.stderr)
    print(f"  Sin patente: {min(len(candidates), MAX_LEADS) - enriched}", file=sys.stderr)


if __name__ == "__main__":
    main()

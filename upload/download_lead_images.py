#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LeadX Image Downloader
Descarga imágenes de leads desde Cloudflare Worker para procesamiento OCR.

Uso:
    python scripts/download_lead_images.py \
        --worker-url https://leadx.simondalmasso44.workers.dev \
        --secret LEGACY_SECRET_REMOVED \
        --output-dir ./data/lead_images \
        --max-leads 50
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict

import requests


def fetch_leads_without_patente(worker_url: str, secret: str, max_leads: int) -> List[Dict]:
    """
    Obtiene leads que no tienen patente extraída aún.

    Returns:
        Lista de leads con campos: id, source_label, image_urls, fb_post_url
    """
    try:
        response = requests.get(
            f"{worker_url}/api/leads",
            headers={
                'X-Ingest-Secret': secret,
                'Content-Type': 'application/json'
            },
            params={
                'filter': 'no_patente',
                'limit': max_leads,
                'sources': 'facebook,reddit,ventafe'
            },
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        leads = data.get('leads', [])

        # Filtrar solo leads con imágenes potenciales
        leads_with_images = [
            lead for lead in leads
            if lead.get('image_urls') or lead.get('fb_post_url')
        ]

        print(f"📥 {len(leads_with_images)} leads con imágenes potenciales")
        return leads_with_images

    except Exception as e:
        print(f"❌ Error fetching leads: {e}")
        return []


def download_image(url: str, output_path: Path) -> bool:
    """Descarga una imagen desde URL y la guarda localmente."""
    try:
        response = requests.get(url, timeout=30, stream=True)
        response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return True

    except Exception as e:
        print(f"❌ Error descargando {url}: {e}")
        return False


def extract_image_urls_from_post(post_data: Dict) -> List[str]:
    """
    Extrae URLs de imágenes del payload de un post de Facebook.
    Maneja múltiples formatos de imagen que puede devolver Apify.
    """
    urls = []

    # Formato 1: imageUrls array (Apify Facebook Groups Scraper)
    if 'imageUrls' in post_data and isinstance(post_data['imageUrls'], list):
        urls.extend(post_data['imageUrls'])

    # Formato 2: media array
    if 'media' in post_data and isinstance(post_data['media'], list):
        for media in post_data['media']:
            if isinstance(media, dict):
                if 'url' in media:
                    urls.append(media['url'])
                elif 'thumbnail' in media:
                    urls.append(media['thumbnail'])

    # Formato 3: attachments
    if 'attachments' in post_data and isinstance(post_data['attachments'], list):
        for att in post_data['attachments']:
            if isinstance(att, dict) and 'url' in att:
                urls.append(att['url'])

    # Formato 4: topComments con imágenes
    if 'topComments' in post_data and isinstance(post_data['topComments'], list):
        for comment in post_data['topComments']:
            if isinstance(comment, dict) and 'media' in comment:
                for media in comment.get('media', []):
                    if isinstance(media, dict) and 'url' in media:
                        urls.append(media['url'])

    # Filtrar duplicados y None
    return list(dict.fromkeys([u for u in urls if u]))


def main():
    parser = argparse.ArgumentParser(description='Download lead images for OCR processing')
    parser.add_argument('--worker-url', required=True, help='LeadX Worker URL')
    parser.add_argument('--secret', required=True, help='INGEST_SECRET')
    parser.add_argument('--output-dir', default='./data/lead_images', help='Output directory')
    parser.add_argument('--max-leads', type=int, default=50, help='Max leads to process')
    parser.add_argument('--batch-id', default='', help='Optional batch ID filter')

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  LeadX Image Downloader")
    print("=" * 60)
    print(f"  Worker: {args.worker_url}")
    print(f"  Output: {output_dir}")
    print(f"  Max leads: {args.max_leads}")
    print("=" * 60)
    print()

    # Obtener leads
    leads = fetch_leads_without_patente(args.worker_url, args.secret, args.max_leads)

    if not leads:
        print("⚠️ No hay leads para procesar")
        return 0

    # Descargar imágenes
    total_downloaded = 0
    total_failed = 0

    for lead in leads:
        lead_id = lead.get('id', f"unknown_{hash(str(lead))}")
        lead_dir = output_dir / lead_id

        # Extraer URLs de imágenes
        image_urls = extract_image_urls_from_post(lead)

        if not image_urls:
            print(f"📭 Lead {lead_id}: sin imágenes")
            continue

        print(f"📸 Lead {lead_id}: {len(image_urls)} imágenes")

        for i, url in enumerate(image_urls):
            # Determinar extensión
            ext = '.jpg'
            if '.png' in url.lower():
                ext = '.png'
            elif '.webp' in url.lower():
                ext = '.webp'

            output_path = lead_dir / f"img_{i:02d}{ext}"

            if download_image(url, output_path):
                total_downloaded += 1
                print(f"  ✅ {output_path.name}")
            else:
                total_failed += 1
                print(f"  ❌ img_{i:02d}{ext}")

    # Guardar metadata
    metadata = {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'total_leads': len(leads),
        'total_downloaded': total_downloaded,
        'total_failed': total_failed,
        'leads': [{ 'id': l.get('id'), 'source': l.get('source_label') } for l in leads]
    }

    metadata_path = output_dir / '_download_metadata.json'
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  Leads procesados: {len(leads)}")
    print(f"  Imágenes descargadas: {total_downloaded}")
    print(f"  Fallos: {total_failed}")
    print(f"  Metadata: {metadata_path}")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    exit(main())

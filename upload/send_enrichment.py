#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LeadX Enrichment Sender
Envía resultados de extracción de patentes al Cloudflare Worker.

Uso:
    python scripts/send_enrichment.py \
        --worker-url https://leadx.simondalmasso44.workers.dev \
        --secret LEGACY_SECRET_REMOVED \
        --results-dir ./data/patentes_extracted
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict

import requests


def load_results(results_dir: Path) -> List[Dict]:
    """Carga todos los archivos JSON de resultados."""
    results = []

    for json_file in sorted(results_dir.glob('*.json')):
        if json_file.name.startswith('_'):
            continue  # Skip metadata files

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # El archivo puede ser un array de enriquecimientos o un objeto con results
            if 'results' in data:
                results.extend(data['results'])
            elif isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)

        except Exception as e:
            print(f"⚠️ Error leyendo {json_file}: {e}")

    return results


def send_enrichment(payload: Dict, worker_url: str, secret: str) -> bool:
    """Envía un payload de enriquecimiento al Worker."""
    try:
        response = requests.post(
            f"{worker_url}/api/enrich-patente",
            json=payload,
            headers={
                'Content-Type': 'application/json',
                'X-Ingest-Secret': secret
            },
            timeout=15
        )
        response.raise_for_status()

        result = response.json()
        print(f"  ✅ Lead {payload['lead_id']}: {result.get('patentes_enriched', 0)} patentes enriquecidas")
        return True

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  ⚠️ Lead {payload['lead_id']}: no encontrado en KV")
        elif e.response.status_code == 401:
            print(f"  ❌ Error de autenticación - verificar INGEST_SECRET")
            return False
        else:
            print(f"  ❌ HTTP {e.response.status_code} para lead {payload['lead_id']}")
        return False

    except Exception as e:
        print(f"  ❌ Error enviando lead {payload['lead_id']}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Send enrichment results to LeadX Worker')
    parser.add_argument('--worker-url', required=True, help='LeadX Worker URL')
    parser.add_argument('--secret', required=True, help='INGEST_SECRET')
    parser.add_argument('--results-dir', default='./data/patentes_extracted', help='Results directory')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for sending')

    args = parser.parse_args()

    results_dir = Path(args.results_dir)

    if not results_dir.exists():
        print(f"❌ Directorio no existe: {results_dir}")
        return 1

    print("=" * 60)
    print("  LeadX Enrichment Sender")
    print("=" * 60)
    print(f"  Worker: {args.worker_url}")
    print(f"  Results: {results_dir}")
    print("=" * 60)
    print()

    # Cargar resultados
    results = load_results(results_dir)

    if not results:
        print("⚠️ No hay resultados para enviar")
        return 0

    print(f"📦 {len(results)} enriquecimientos para enviar")
    print()

    # Enviar en batches
    sent = 0
    failed = 0

    for i, enrichment in enumerate(results):
        # Construir payload compatible con Worker
        payload = {
            'lead_id': enrichment.get('lead_id'),
            'patentes': [
                {
                    'patente': p.get('patente_normalizada', p.get('patente')),
                    'tipo': p.get('tipo', 'desconocido'),
                    'confianza': p.get('confianza', 0.5),
                    'dnrpa_consultable': p.get('dnrpa_consultable', False)
                }
                for p in enrichment.get('patentes', [])
            ],
            'score_boost': enrichment.get('score_boost', 0),
            'dnrpa_links': [
                f"https://www.dnrpa.gov.ar/consulta_patente.php?patente={p.get('patente_normalizada', '').replace(' ', '')}"
                for p in enrichment.get('patentes', [])
                if p.get('dnrpa_consultable', False)
            ],
            'timestamp': __import__('datetime').datetime.now().isoformat()
        }

        if send_enrichment(payload, args.worker_url, args.secret):
            sent += 1
        else:
            failed += 1

        # Rate limiting entre requests
        if (i + 1) % args.batch_size == 0:
            print(f"  ⏳ Pausa de 1s entre batches...")
            __import__('time').sleep(1)

    # Guardar stats
    stats = {
        'timestamp': __import__('datetime').datetime.now().isoformat(),
        'total': len(results),
        'sent': sent,
        'failed': failed,
        'success_rate': round(sent / len(results) * 100, 1) if results else 0
    }

    stats_path = results_dir / 'last_run_stats.json'
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print()
    print("=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print(f"  Total: {len(results)}")
    print(f"  Enviados: {sent}")
    print(f"  Fallidos: {failed}")
    print(f"  Tasa de éxito: {stats['success_rate']}%")
    print(f"  Stats: {stats_path}")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    exit(main())

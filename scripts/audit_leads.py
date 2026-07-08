#!/usr/bin/env python3
"""Audit real leads state in KV — Simon's request at 7:45 AM."""
import json

with open('/tmp/leads_now.json') as f:
    data = json.load(f)
leads = data.get('leads_all', [])

norm = []
for l in leads:
    norm.append({
        'id': l.get('id', '')[:12],
        'persona': l.get('persona') or l.get('fb_username') or l.get('nombre') or 'sin_nombre',
        'source': l.get('source') or l.get('platform') or '?',
        'tel': l.get('telefono') or l.get('phone') or '',
        'fb_id': l.get('fb_author_id') or l.get('fb_username') or '',
        'patente': l.get('patente') or '',
        'score': l.get('score', 0),
        'label': l.get('label', ''),
        'category': l.get('problem_category', ''),
        'summary': (l.get('problem_summary') or '')[:100],
        'quoted': (l.get('quoted_text') or '')[:300].replace('\n', ' '),
        'url': l.get('source_url', '')[:100],
        'fecha': l.get('fecha_visible', '')[:10],
        'provincia': l.get('provincia', ''),
        'vehiculo': l.get('vehiculo', ''),
    })

from collections import Counter
print('=' * 80)
print('LEADX KV AUDIT — ' + data.get('meta', {}).get('generated_at', '?'))
print('=' * 80)
print()
print(f"TOTAL LEADS EN KV: {len(leads)}")
print()
print('--- SOURCES ---')
for k, v in Counter(l['source'] for l in norm).items():
    print(f'  {k}: {v}')

print()
print('--- SCORE DISTRIBUTION ---')
for bucket, lo, hi in [('HOT (>=80)', 80, 999), ('WARM (50-79)', 50, 79), ('PREVENTIVO (40-49)', 40, 49), ('LOW (<40)', 0, 39)]:
    n = sum(1 for l in norm if lo <= l['score'] < hi)
    print(f'  {bucket}: {n}')

print()
print('--- CONTACTABILIDAD ---')
con_tel = [l for l in norm if l['tel']]
con_fb = [l for l in norm if l['fb_id']]
con_patente = [l for l in norm if l['patente']]
print(f'  Con telefono/WhatsApp directo: {len(con_tel)}')
print(f'  Con FB/Messenger: {len(con_fb)}')
print(f'  Con patente: {len(con_patente)}')
print(f'  Total contactables (tel O fb): {len([l for l in norm if l["tel"] or l["fb_id"]])}')

print()
print('=' * 80)
print('--- HOT LEADS (score>=70) ---')
print('=' * 80)
hots = sorted([l for l in norm if l['score'] >= 70], key=lambda x: -x['score'])
for i, l in enumerate(hots, 1):
    print(f"  {i:2d}. [sc={l['score']:3d}] {l['persona'][:35]:35s} | {l['source'][:12]:12s} | tel={l['tel'] or '-':15s} | fb={l['fb_id'][:22] or '-':22s}")
    print(f"      cat={l['category'][:30]:30s} | {l['summary'][:80]}")
    print(f"      quoted: {l['quoted'][:200]}")
    print()

print()
print('=' * 80)
print('--- LEADS CON FB/MESSENGER (boton azul) ---')
print('=' * 80)
for i, l in enumerate([x for x in norm if x['fb_id']], 1):
    print(f"  {i:2d}. [sc={l['score']:3d}] fb={l['fb_id'][:30]:30s} | {l['source'][:12]:12s} | cat={l['category'][:25]}")
    print(f"      quoted: {l['quoted'][:250]}")
    print()

print()
print('=' * 80)
print('--- LEADS VENTAFE (preventivos capados) ---')
print('=' * 80)
vf = [l for l in norm if l['source'] == 'VentaFe']
print(f'  Total: {len(vf)} | Con tel: {sum(1 for l in vf if l["tel"])} | Con patente: {sum(1 for l in vf if l["patente"])}')
for i, l in enumerate(vf[:5], 1):
    print(f"  {i:2d}. [sc={l['score']:3d}] {l['persona'][:30]:30s} | {l['vehiculo'][:25]:25s} | url={l['url'][:60]}")

print()
print('=' * 80)
print('--- REDDIT LEADS (sospecha de basura) ---')
print('=' * 80)
rd = [l for l in norm if l['source'] == 'reddit_rss']
print(f'  Total: {len(rd)}')
for i, l in enumerate(rd, 1):
    print(f"  {i:2d}. [sc={l['score']:3d}] {l['persona'][:25]:25s} | {l['summary'][:70]}")

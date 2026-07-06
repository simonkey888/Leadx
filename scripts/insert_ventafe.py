#!/usr/bin/env python3
"""Script para insertar VentaFe scraper en generate_payload.py"""
import re

path = "/tmp/leadx_deploy/generate_payload.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Insertar la funcion scrape_ventafe_leads() antes de collect_public_sources
ventafe_func = '''
#===========================================================================
# Step 1.5: VentaFe Scraper — Portal de clasificados del interior (ORO)
#===========================================================================
def scrape_ventafe_leads() -> List[Dict[str, Any]]:
    """
    Scrapea VentaFe.com.ar (clasificados de autos del interior).
    Extrae: titulo, descripcion, precio, telefono, patente.
    """
    import urllib.request as _urq
    import urllib.error
    
    print("[Step 1.5] Scraping VentaFe.com.ar...", file=sys.stderr)
    
    BASE_URL = "https://www.ventafe.com.ar/automoviles"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'es-AR,es;q=0.9,en;q=0.8',
    }
    
    PHONE_REGEX = re.compile(
        r'(?:\\+?54\\s?9?\\s?)?'
        r'(?:\\(?(?:0?342|342|0?341|341|0?351|351|0?343|343|0?261|261|0?221|221|0?381|381|0?299|299)\\)?[\\s\\-]?)?'
        r'(?:15\\s?)?'
        r'\\d{4}[\\s\\-]?\\d{4}',
        re.IGNORECASE
    )
    PATENTE_REGEX = re.compile(r'\\b([A-Z]{2,3}\\s?\\d{3}\\s?[A-Z]{2}|[A-Z]{3}\\s?\\d{3})\\b')
    
    PROBLEMA_KEYWORDS = {
        'TRANSFERENCIA_BLOQUEADA': r'no\\s+puedo\\s+transferir|transferencia\\s+bloqueada|no\\s+me\\s+dejan\\s+transferir',
        'MULTA': r'multa|fotomulta|infraccion|infraccion',
        'DEUDA': r'deuda|adeuda|debo|debe',
        'LIBRE_DEUDA': r'libre\\s+de\\s+deuda|libre\\s+deuda|sin\\s+deuda',
        'PAPELES_AL_DIA': r'papeles\\s+al\\s+d[ií]a|documentaci[oó]n\\s+al\\s+d[ií]a|listo\\s+para\\s+transferir',
    }
    
    all_leads = []
    total_pages = 8
    
    for page in range(1, total_pages + 1):
        url = f"{BASE_URL}?page={page}" if page > 1 else BASE_URL
        print(f"  [VentaFe] Scraping page {page}/{total_pages}...", file=sys.stderr)
        
        try:
            req = _urq.Request(url, headers=HEADERS)
            with _urq.urlopen(req, timeout=20) as resp:
                html = resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f"  [VentaFe] Error page {page}: {e}", file=sys.stderr)
            continue
        
        aviso_blocks = re.split(r'#\\d{6,8}', html)
        
        for block in aviso_blocks[1:]:
            text = re.sub(r'<[^>]+>', ' ', block)
            text = re.sub(r'&[a-z]+;', ' ', text)
            text = re.sub(r'\\s+', ' ', text).strip()
            
            if len(text) < 100:
                continue
            
            phone_matches = PHONE_REGEX.findall(text)
            phones = []
            for p in phone_matches:
                digits = re.sub(r'\\D', '', p)
                if 10 <= len(digits) <= 15:
                    if len(digits) == 10 and not digits.startswith('54'):
                        digits = '54' + digits
                    phones.append(digits)
            phones = list(set(phones))
            
            patente_matches = PATENTE_REGEX.findall(text)
            patentes = list(set([p.replace(' ', '').upper() for p in patente_matches]))
            
            problemas = []
            for prob_name, prob_regex in PROBLEMA_KEYWORDS.items():
                if re.search(prob_regex, text, re.IGNORECASE):
                    problemas.append(prob_name)
            
            if not phones and not patentes:
                continue
            
            lead_id = 'ventafe_' + hashlib.sha256(text[:200].encode()).hexdigest()[:12]
            lead = {
                'id': lead_id,
                'name': text[:80],
                'url': 'https://www.ventafe.com.ar/automoviles',
                'snippet': text[:500],
                'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'host_name': 'ventafe.com.ar',
                'username': '',
                'author': 'Vendedor VentaFe',
                'source': 'ventafe',
                '_query': 'ventafe_automoviles',
                'telefonos': phones,
                'patentes': patentes,
                'problemas': problemas,
                'zona': 'Santa Fe',
            }
            all_leads.append(lead)
        
        time.sleep(2)
    
    hot_leads = [l for l in all_leads if l['problemas'] or l['patentes']]
    print(f"  [VentaFe] Total scrapeados: {len(all_leads)} | Calientes: {len(hot_leads)}", file=sys.stderr)
    
    return hot_leads


'''

old_collect = "def collect_public_sources() -> List[Dict[str, Any]]:"
new_collect = ventafe_func + old_collect

if old_collect in content:
    content = content.replace(old_collect, new_collect, 1)
    print("✅ scrape_ventafe_leads() agregada")

# 2. Llamar a scrape_ventafe_leads dentro de collect_public_sources
old_fb_block = '''    except Exception as e:
        print(f"  Facebook (Apify) ERROR: {e}", file=sys.stderr)

    return all_results'''

new_fb_block = '''    except Exception as e:
        print(f"  Facebook (Apify) ERROR: {e}", file=sys.stderr)

    # VentaFe Scraper (portal de clasificados del interior - SANTA FE ORO)
    try:
        ventafe_results = scrape_ventafe_leads()
        if ventafe_results:
            all_results.extend(ventafe_results)
            print(f"  VentaFe: +{len(ventafe_results)} leads agregados", file=sys.stderr)
    except Exception as e:
        print(f"  VentaFe ERROR: {e}", file=sys.stderr)

    return all_results'''

if old_fb_block in content:
    content = content.replace(old_fb_block, new_fb_block)
    print("✅ Llamada a VentaFe en collect_public_sources()")

# 3. Adaptar extract_entities para VentaFe
old_extract_start = '''    # Extract phone
    # (ya inicializado arriba)
    for pattern in ARG_PHONE_PATTERNS:'''

new_extract_start = '''    # VentaFe: campos personalizados
    telefonos_ventafe = result.get('telefonos', [])
    patentes_ventafe = result.get('patentes', [])
    problemas_ventafe = result.get('problemas', [])
    zona_ventafe = result.get('zona', '')
    
    if telefonos_ventafe:
        phone = telefonos_ventafe[0]
        whatsapp = telefonos_ventafe[0]
        contacto_publico = True
    
    if patentes_ventafe:
        patent = patentes_ventafe[0]
    
    if problemas_ventafe:
        combined += ' ' + ' '.join(problemas_ventafe)
        combined_lower = combined.lower()
    
    if zona_ventafe:
        provincia = zona_ventafe

    # Extract phone (si no vino de VentaFe)
    # (ya inicializado arriba)
    for pattern in ARG_PHONE_PATTERNS:'''

if old_extract_start in content:
    content = content.replace(old_extract_start, new_extract_start)
    print("✅ extract_entities adaptada para VentaFe")

# 4. Scoring para VentaFe en classify_and_score
old_ml_boost = '''    # multa_or_fotomulta: +60'''

new_ventafe_boost = '''    # VentaFe: scoring especifico para clasificados
    source_str = (record.get("source", "") or "").lower()
    if 'ventafe' in source_str:
        score += 20
        breakdown['ventafe_base'] = 20
        signals.append('VENTAFE_LISTING')
        
        if record.get('patentes'):
            score += 15
            breakdown['ventafe_patente'] = 15
            signals.append('VENTAFE_PATENTE')
        
        problemas = record.get('problemas', [])
        if 'TRANSFERENCIA_BLOQUEADA' in problemas:
            score += 30
            breakdown['ventafe_transferencia'] = 30
            signals.append('VENTAFE_TRANSFERENCIA')
        if 'MULTA' in problemas:
            score += 25
            breakdown['ventafe_multa'] = 25
            signals.append('VENTAFE_MULTA')
        if 'DEUDA' in problemas:
            score += 25
            breakdown['ventafe_deuda'] = 25
            signals.append('VENTAFE_DEUDA')

    # multa_or_fotomulta: +60'''

if old_ml_boost in content:
    content = content.replace(old_ml_boost, new_ventafe_boost)
    print("✅ Scoring VentaFe agregado en classify_and_score()")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("✅ Archivo guardado")

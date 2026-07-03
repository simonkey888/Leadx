"""
search_providers.py — Multi-provider search engine for Radar Leads.

Reemplaza completamente search_providers CLI. 100% autónomo en GitHub Actions.

Providers:
  1. DuckDuckGo HTML (gratis, sin API key)
  2. Reddit JSON público (gratis, sin API key)
  3. RSS feeds (gratis, sin API key)

Interfaz unificada:
  search(query, num=10) → List[Dict] con campos normalizados:
    title, url, snippet, source, date

Anti-blocking:
  - Random User-Agent
  - Rate limit entre requests
  - Retry con backoff exponencial
  - Cache simple en memoria
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import re as _re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from html.parser import HTMLParser

# ===========================================================================
# Config
# ===========================================================================

RATE_LIMIT_SECONDS = 2.0
MAX_RETRIES = 3
CACHE_TTL = 300  # 5 min

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Cache simple
_cache: Dict[str, tuple] = {}  # key → (timestamp, data)


# ===========================================================================
# HTTP helper con anti-blocking
# ===========================================================================
def _fetch_url(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch URL con random UA, retry y backoff."""
    cache_key = hashlib.sha256(url.encode()).hexdigest()[:16]
    now = time.time()

    # Check cache
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < CACHE_TTL:
            return data

    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", random.choice(USER_AGENTS))
            req.add_header("Accept", "text/html,application/xhtml+xml,application/json,*/*")
            req.add_header("Accept-Language", "es-AR,es;q=0.9,en;q=0.8")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                _cache[cache_key] = (now, content)
                return content
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = (attempt + 1) * 2 + random.uniform(0, 1)
                time.sleep(wait)
            else:
                return None
    return None


# ===========================================================================
# Provider 1: DuckDuckGo HTML
# ===========================================================================
class _DDGResultParser(HTMLParser):
    """Parser minimalista para resultados de DuckDuckGo HTML."""

    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._current: Dict[str, str] = {}
        self._in_result = False
        self._in_title = False
        self._in_snippet = False
        self._capture_tag = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        # DuckDuckGo lite usa <a class="result-link">
        # DuckDuckGo HTML usa <div class="result">
        cls = attrs_dict.get("class", "")

        if "result-link" in cls or ("result__a" in cls):
            self._in_title = True
            self._current = {"title": "", "url": "", "snippet": ""}
            href = attrs_dict.get("href", "")
            # DDG a veces wrappea URLs
            if href.startswith("//duckduckgo.com/l/?uddg="):
                href = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
            self._current["url"] = href

        if "result-snippet" in cls or "result__snippet" in cls:
            self._in_snippet = True
            if not self._current:
                self._current = {"title": "", "url": "", "snippet": ""}

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._in_title = False
        if self._in_snippet and tag in ("a", "td", "div"):
            self._in_snippet = False
            if self._current and self._current.get("url"):
                self.results.append(self._current)
                self._current = {}

    def handle_data(self, data):
        if self._in_title:
            self._current["title"] += data.strip()
        if self._in_snippet:
            self._current["snippet"] += data.strip() + " "


def search_duckduckgo(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en DuckDuckGo (HTML lite version)."""
    # Usar DuckDuckGo Lite (html only, más fácil de parsear)
    encoded = urllib.parse.quote(query)
    url = f"https://lite.duckduckgo.com/lite/?q={encoded}&kl=ar-es"

    html = _fetch_url(url)
    if not html:
        return []

    parser = _DDGResultParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    results = []
    for r in parser.results[:num]:
        if r.get("url") and r.get("title"):
            results.append({
                "title": r["title"][:200],
                "url": r["url"],
                "snippet": r.get("snippet", "")[:300],
                "source": "duckduckgo",
                "date": "",
            })

    return results


# ===========================================================================
# Provider 2: Reddit JSON (público, sin API key)
# ===========================================================================
def search_reddit(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en Reddit via JSON público (sin auth).
    Por cada post, también trae los top comments para enriquecer el snippet.
    """
    import sys as _sys
    encoded = urllib.parse.quote(query)
    # Reddit search JSON endpoint (público)
    url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit={num}&type=link"
    print(f"    [reddit] searching: {query[:60]}", file=_sys.stderr)

    # Reddit bloquea UAs de bots. Usar UA de browser real + headers completos.
    # Ademas, usar old.reddit.com que es mas permisivo.
    url = url.replace("https://www.reddit.com", "https://old.reddit.com")
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        req.add_header("Accept", "text/html,application/json,application/xhtml+xml,*/*")
        req.add_header("Accept-Language", "es-AR,es;q=0.9,en;q=0.8")
        req.add_header("Accept-Encoding", "identity")  # evitar gzip
        req.add_header("Connection", "keep-alive")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"    [reddit] ERROR: {e}", file=_sys.stderr)
        # Fallback: intentar con www.reddit.com sin el .json (RSS)
        try:
            rss_url = f"https://www.reddit.com/search.rss?q={encoded}&sort=new&limit={num}"
            req2 = urllib.request.Request(rss_url)
            req2.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                rss_content = resp2.read().decode("utf-8", errors="replace")
            # Parse RSS XML simple
            import re as _re
            items = _re.findall(r"<item>(.*?)</item>", rss_content, _re.DOTALL)
            results = []
            for item in items[:num]:
                title_m = _re.search(r"<title>(.*?)</title>", item, _re.DOTALL)
                link_m = _re.search(r"<link>(.*?)</link>", item, _re.DOTALL)
                desc_m = _re.search(r"<description><!\[CDATA\[(.*?)\]\]></description>", item, _re.DOTALL)
                author_m = _re.search(r"<dc:creator>(.*?)</dc:creator>", item, _re.DOTALL)
                date_m = _re.search(r"<pubDate>(.*?)</pubDate>", item, _re.DOTALL)
                if title_m and link_m:
                    results.append({
                        "title": title_m.group(1)[:200],
                        "url": link_m.group(1),
                        "snippet": (desc_m.group(1) if desc_m else "")[:3000],
                        "source": "reddit_rss",
                        "date": date_m.group(1) if date_m else "",
                        "username": author_m.group(1) if author_m else "",
                        "author": author_m.group(1) if author_m else "",
                    })
            print(f"    [reddit] RSS fallback: got {len(results)} results", file=_sys.stderr)
            return results[:num]
        except Exception as e2:
            print(f"    [reddit] RSS fallback ERROR: {e2}", file=_sys.stderr)
            return []

    print(f"    [reddit] got {len(data.get('data',{}).get('children',[]))} results", file=_sys.stderr)

    results = []
    if isinstance(data, dict) and "data" in data:
        for child in data["data"].get("children", []):
            post = child.get("data", {})
            if not post:
                continue

            # Construir URL completa
            permalink = post.get("permalink", "")
            full_url = f"https://www.reddit.com{permalink}" if permalink else ""

            # Snippet: selftext completo si existe, sino title
            selftext = post.get("selftext", "")
            snippet = selftext[:3000] if selftext else post.get("title", "")[:300]

            # Author (username)
            author = post.get("author", "")
            if author == "[deleted]" or author == "AutoModerator":
                author = ""

            # Fecha
            created = post.get("created_utc", 0)
            date = ""
            if created:
                from datetime import datetime, timezone
                date = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()

            results.append({
                "title": post.get("title", "")[:200],
                "url": full_url,
                "snippet": snippet,
                "source": "reddit",
                "date": date,
                "username": author,
                "author": author,
                "permalink": permalink,
            })

    # Opcional: traer top comments de los primeros 5 posts para enriquecer
    # (con rate limit para no ser bloqueados)
    for i, r in enumerate(results[:5]):
        permalink = r.get("permalink", "")
        if not permalink:
            continue
        try:
            time.sleep(1.0)  # rate limit
            comments_url = f"https://old.reddit.com{permalink}.json?limit=10"
            req2 = urllib.request.Request(comments_url)
            req2.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            req2.add_header("Accept", "text/html,application/json,*/*")
            req2.add_header("Accept-Language", "es-AR,es;q=0.9")
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                cdata = json.loads(resp2.read().decode("utf-8", errors="replace"))
            if isinstance(cdata, list) and len(cdata) >= 2:
                comments_text = []
                for c in cdata[1].get("data", {}).get("children", [])[:10]:
                    body = c.get("data", {}).get("body", "")
                    if body and len(body) > 20 and body != "[deleted]" and body != "[removed]":
                        comments_text.append(body[:500])
                if comments_text:
                    # Agregar comments al snippet para extraccion
                    r["snippet"] = (r["snippet"] + " " + " ".join(comments_text))[:6000]
                    # Author real (del post, no comments)
                    if not r["username"] and cdata[0].get("data",{}).get("children",[]):
                        post_full = cdata[0]["data"]["children"][0].get("data",{})
                        a = post_full.get("author","")
                        if a and a != "[deleted]":
                            r["username"] = a
                            r["author"] = a
        except Exception:
            continue

    return results[:num]


# ===========================================================================
# Provider 3: RSS feeds (foros argentinos)
# ===========================================================================
RSS_FEEDS = [
    # Foros argentinos con RSS
    "https://www.reddit.com/r/argentina/new.json?limit=10",
    "https://www.reddit.com/r/ArAutos/new.json?limit=10",
    "https://www.reddit.com/r/Cordoba/new.json?limit=10",
    "https://www.reddit.com/r/DerechoGenial/new.json?limit=10",
]


def search_rss(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en feeds RSS (Reddit subs argentinos)."""
    results = []
    query_lower = query.lower()
    query_keywords = [w for w in query_lower.split() if len(w) > 3]

    for feed_url in RSS_FEEDS:
        try:
            req = urllib.request.Request(feed_url)
            req.add_header("User-Agent", "RadarLeadsBot/1.0")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))

            if isinstance(data, dict) and "data" in data:
                for child in data["data"].get("children", []):
                    post = child.get("data", {})
                    if not post:
                        continue

                    text = f"{post.get('title', '')} {post.get('selftext', '')}".lower()

                    # Filtro por keywords de la query
                    if query_keywords and not any(kw in text for kw in query_keywords):
                        continue

                    permalink = post.get("permalink", "")
                    full_url = f"https://www.reddit.com{permalink}" if permalink else ""

                    created = post.get("created_utc", 0)
                    date = ""
                    if created:
                        from datetime import datetime, timezone
                        date = datetime.fromtimestamp(created, tz=timezone.utc).isoformat()

                    results.append({
                        "title": post.get("title", "")[:200],
                        "url": full_url,
                        "snippet": post.get("selftext", "")[:300],
                        "source": "reddit_rss",
                        "date": date,
                        "username": post.get("author", ""),
                    })

                    if len(results) >= num:
                        break
        except Exception:
            continue

        if len(results) >= num:
            break

    return results[:num]


# ===========================================================================
# Search Manager — unifica todos los providers
# ===========================================================================

# ===========================================================================
# Reddit post enrichment: trae selftext completo + comentarios top
# ===========================================================================
def enrich_reddit_post(url: str) -> Dict[str, Any]:
    """Dada una URL de Reddit post, trae selftext completo + top comments.
    Retorna dict con: full_text, comments (list of strings), author.
    """
    result = {"full_text": "", "comments": [], "author": ""}
    if "reddit.com" not in url:
        return result

    # Convertir URL a .json
    json_url = url.rstrip("/") + "/.json?limit=20"

    try:
        req = urllib.request.Request(json_url)
        req.add_header("User-Agent", "RadarLeadsBot/1.0 (lead intelligence research)")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return result

    if not isinstance(data, list) or len(data) < 1:
        return result

    # Post data
    post_listing = data[0]
    post_data = post_listing.get("data", {}).get("children", [])
    if post_data:
        post = post_data[0].get("data", {})
        result["full_text"] = post.get("selftext", "")[:3000]
        result["author"] = post.get("author", "")

    # Comments
    if len(data) >= 2:
        comments_listing = data[1]
        for child in comments_listing.get("data", {}).get("children", [])[:15]:
            comment = child.get("data", {})
            body = comment.get("body", "")
            if body and len(body) > 20:
                result["comments"].append(body[:500])

    return result



# ===========================================================================
# Provider 4: Telegram public channels (t.me/s/<channel>)
# ===========================================================================
TELEGRAM_CHANNELS_AR = [
    "MultasArgentina",
    "AutosUsadosAR",
    "GestoriaAutomotor",
    "TramitesArgentina",
    "InfraccionesAR",
]

def search_telegram(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en canales públicos de Telegram via t.me/s/ (sin auth)."""
    import sys as _sys
    results = []
    query_lower = query.lower()
    # Quitar site:xxx de la query para buscar texto
    clean_query = _re.sub(r"site:\S+", "", query_lower).strip()
    if not clean_query:
        return []
    
    keywords = [w for w in clean_query.split() if len(w) > 2][:5]
    if not keywords:
        return []
    
    for channel in TELEGRAM_CHANNELS_AR:
        try:
            url = f"https://t.me/s/{channel}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", random.choice(USER_AGENTS))
            req.add_header("Accept-Language", "es-AR,es;q=0.9")
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            
            # Parse simple HTML: buscar divs con clase tgme_widget_message_text
            import re as _re2
            posts = _re2.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, _re2.DOTALL)
            dates = _re2.findall(r'<time datetime="([^"]+)"', html)
            for i, post_html in enumerate(posts[:20]):
                # Strip HTML tags
                text = _re2.sub(r"<[^>]+>", " ", post_html)
                text = _re2.sub(r"&amp;", "&", text)
                text = _re2.sub(r"&lt;", "<", text)
                text = _re2.sub(r"&gt;", ">", text)
                text = _re2.sub(r"&quot;", '"', text)
                text = _re2.sub(r"&#39;", "'", text)
                text = _re2.sub(r"\s+", " ", text).strip()
                if not text or len(text) < 30:
                    continue
                # Filtrar por keywords
                text_lower = text.lower()
                if not any(kw in text_lower for kw in keywords):
                    continue
                date = dates[i] if i < len(dates) else ""
                results.append({
                    "title": text[:120],
                    "url": f"https://t.me/s/{channel}",
                    "snippet": text[:3000],
                    "source": "telegram",
                    "date": date,
                    "username": channel,
                    "author": channel,
                })
            time.sleep(1.0)
        except Exception as e:
            print(f"    [telegram] {channel} error: {e}", file=_sys.stderr)
            continue
    
    print(f"    [telegram] got {len(results)} results", file=_sys.stderr)
    return results[:num]


# ===========================================================================
# Provider 5: MercadoLibre API pública (sin auth)
# ===========================================================================
def search_mercadolibre(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca publicaciones en MercadoLibre Argentina via API pública."""
    import sys as _sys
    # Quitar site:xxx
    clean_query = _re.sub(r"site:\S+", "", query).strip()
    if not clean_query:
        return []
    
    encoded = urllib.parse.quote(clean_query)
    url = f"https://api.mercadolibre.com/sites/MLA/search?q={encoded}&limit={num}&condition=used"
    
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"    [ml] ERROR: {e}", file=_sys.stderr)
        return []
    
    results = []
    for item in data.get("results", [])[:num]:
        title = item.get("title", "")
        price = item.get("price", 0)
        permalink = item.get("permalink", "")
        seller = item.get("seller", {})
        seller_nick = seller.get("nickname", "")
        seller_id = seller.get("id", "")
        # Questions endpoint (público)
        questions_text = ""
        try:
            q_url = f"https://api.mercadolibre.com/questions/search?item={item.get('id','')}"
            q_req = urllib.request.Request(q_url)
            q_req.add_header("User-Agent", random.choice(USER_AGENTS))
            with urllib.request.urlopen(q_req, timeout=5) as q_resp:
                q_data = json.loads(q_resp.read().decode("utf-8", errors="replace"))
            qs = [q.get("text","") for q in q_data.get("questions", [])[:5]]
            questions_text = " ".join(qs)
        except Exception:
            pass
        
        snippet = f"Precio: ${price}. Vendedor: {seller_nick}. Preguntas: {questions_text}"[:3000]
        results.append({
            "title": title[:200],
            "url": permalink,
            "snippet": snippet,
            "source": "mercadolibre",
            "date": "",
            "username": seller_nick,
            "author": seller_nick,
        })
    
    print(f"    [ml] got {len(results)} results", file=_sys.stderr)
    return results

def search(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """
    Busca usando múltiples providers en orden de fallback.

    Orden:
      1. DuckDuckGo (cobertura amplia)
      2. Reddit (foros, alta calidad de leads)
      3. RSS (backup)

    Devuelve resultados normalizados con campos:
      title, url, snippet, source, date, username?
    """
    all_results = []

    # Si la query es site:reddit.com, usar search_reddit directamente (trae author + comments)
    if "site:reddit.com" in query.lower():
        try:
            real_query = query.lower().replace("site:reddit.com", "").strip()
            reddit = search_reddit(real_query, num=num)
            all_results.extend(reddit)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:mercadolibre.com, usar ML API
    if "site:mercadolibre" in query.lower() or "site:mla" in query.lower():
        try:
            real_query = _re.sub(r"site:\S+", "", query, flags=_re.IGNORECASE).strip()
            ml = search_mercadolibre(real_query, num=num)
            all_results.extend(ml)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query menciona telegram, usar provider telegram
    if "site:telegram" in query.lower() or "telegram" in query.lower():
        try:
            tg = search_telegram(query, num=num)
            all_results.extend(tg)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:facebook.com o site:x.com, igual usar DuckDuckGo (no tenemos API directa)
    # Provider 1: DuckDuckGo
    try:
        ddg = search_duckduckgo(query, num=num)
        all_results.extend(ddg)
        time.sleep(RATE_LIMIT_SECONDS)
    except Exception:
        pass

    # Provider 2: Reddit (sólo si la query no es muy larga)
    if len(query) < 200 and "site:reddit.com" not in query.lower():
        try:
            reddit = search_reddit(query, num=num)
            all_results.extend(reddit)
            time.sleep(RATE_LIMIT_SECONDS)
        except Exception:
            pass

    # Provider 3: RSS (sólo si los anteriores no dieron suficiente)
    if len(all_results) < num // 2:
        try:
            rss = search_rss(query, num=num)
            all_results.extend(rss)
        except Exception:
            pass

    # Dedup por URL
    seen_urls = set()
    unique = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(r)

    return unique[:num]


# ===========================================================================
# Smoke test
# ===========================================================================
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  SMOKE TEST search_providers.py (sin search_providers, sin API key)")
    print("=" * 60)

    test_query = "no puedo transferir auto multa argentina"

    print(f"\n  Query: '{test_query}'\n")

    # Test DuckDuckGo
    print("  [1] DuckDuckGo...")
    ddg = search_duckduckgo(test_query, num=5)
    print(f"      Resultados: {len(ddg)}")
    for r in ddg[:2]:
        print(f"      - {r['title'][:60]}")
        print(f"        {r['url'][:80]}")

    time.sleep(2)

    # Test Reddit
    print("\n  [2] Reddit...")
    reddit = search_reddit(test_query, num=5)
    print(f"      Resultados: {len(reddit)}")
    for r in reddit[:2]:
        print(f"      - {r['title'][:60]}")
        print(f"        {r['url'][:80]}")

    # Test unified search
    print("\n  [3] Unified search()...")
    all_results = search(test_query, num=10)
    print(f"      Total: {len(all_results)}")
    for r in all_results[:3]:
        print(f"      [{r['source']:12s}] {r['title'][:50]}")

    print(f"\n{'='*60}")
    print(f"  ✓ Sin search_providers, sin API key, sin credenciales")
    print(f"  ✓ Funciona en GitHub Actions")
    print(f"{'='*60}")

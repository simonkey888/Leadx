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
_rss_cache: Dict[str, tuple] = {}  # Reddit RSS: query_hash → (timestamp, results)


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
    """Busca en Reddit via /search.rss (Atom feed). Cache 1h en memoria."""
    import sys as _sys
    import hashlib as _hl
    import time as _tm

    # Cache check: si la misma query se pidio hace <1h, devolver cache
    cache_key = _hl.sha256(query.encode()).hexdigest()[:12]
    if cache_key in _rss_cache:
        ts, cached = _rss_cache[cache_key]
        if _tm.time() - ts < 3600:
            print(f"    [reddit] cache hit ({len(cached)} items): {query[:50]}", file=_sys.stderr)
            return cached[:num]

    print(f"    [reddit] searching (via RSS): {query[:60]}", file=_sys.stderr)
    
    # Paso 1: DuckDuckGo para encontrar URLs de Reddit
    ddg_query = f"site:reddit.com {query}"
    ddg_results = search_duckduckgo(ddg_query, num=num * 2)
    reddit_urls = [r for r in ddg_results if "reddit.com" in r.get("url", "").lower() and "/comments/" in r.get("url", "")]
    
    print(f"    [reddit] DDG found {len(reddit_urls)} reddit post URLs", file=_sys.stderr)
    
    if not reddit_urls:
        # Fallback al endpoint directo (puede que funcione a veces)
        encoded = urllib.parse.quote(query)
        url = f"https://www.reddit.com/search.json?q={encoded}&sort=new&limit={num}&type=link"

    # Reddit bloquea /search.json y /comments/.json con 403.
    # Pero /search.rss (Atom feed) SI funciona y trae el author como <name>/u/xxx</name>.
    # Estrategia: usar search.rss en vez de DDG + scrape.
    encoded = urllib.parse.quote(query)
    rss_url = f"https://www.reddit.com/search.rss?q={encoded}&sort=new&limit={num}"
    try:
        req = urllib.request.Request(rss_url)
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        req.add_header("Accept", "application/atom+xml, application/xml, text/xml, */*")
        req.add_header("Accept-Language", "es-AR,es;q=0.9")
        with urllib.request.urlopen(req, timeout=15) as resp:
            rss_content = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [reddit] RSS search fail: {e}", file=_sys.stderr)
        # Ultimo fallback: usar los resultados de DDG (sin author)
        results = []
        for r in reddit_urls[:num]:
            results.append({
                "title": r.get("title","")[:200],
                "url": r.get("url",""),
                "snippet": r.get("snippet","")[:3000],
                "source": "reddit_ddg",
                "date": r.get("date",""),
                "username": "",
                "author": "",
            })
        return results
    
    # Parse Atom feed
    import re as _re2
    entries = _re2.findall(r"<entry>(.*?)</entry>", rss_content, _re2.DOTALL)
    print(f"    [reddit] RSS entries: {len(entries)}", file=_sys.stderr)
    
    results = []
    for entry in entries[:num]:
        title_m = _re2.search(r"<title[^>]*>([^<]+)</title>", entry)
        link_m = _re2.search(r'<link[^>]*href="([^"]+)"', entry)
        author_m = _re2.search(r"<name[^>]*>([^<]+)</name>", entry)
        content_m = _re2.search(r"<content[^>]*>(.*?)</content>", entry, _re2.DOTALL)
        updated_m = _re2.search(r"<updated[^>]*>([^<]+)</updated>", entry)
        
        title = title_m.group(1) if title_m else ""
        url = link_m.group(1) if link_m else ""
        author = ""
        if author_m:
            author_raw = author_m.group(1).strip()
            # Formato Reddit: /u/username
            u_match = _re2.search(r"/u/([A-Za-z0-9_\-\:]{3,20})", author_raw)
            if u_match:
                author = u_match.group(1)
            else:
                author = author_raw
        
        # Content tiene HTML, limpiar tags
        snippet = ""
        if content_m:
            raw = content_m.group(1)
            # Buscar u/username adicional en el content
            u2 = _re2.search(r"/u/([A-Za-z0-9_\-\:]{3,20})", raw)
            if u2 and not author:
                author = u2.group(1)
            # Strip HTML
            snippet = _re2.sub(r"<[^>]+>", " ", raw)
            snippet = _re2.sub(r"<!--.*?-->", "", snippet, flags=_re2.DOTALL)
            snippet = snippet.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
            snippet = _re2.sub(r"\s+", " ", snippet).strip()
        
        # Solo incluir si es un post (tiene /comments/ en la URL) y no un subreddit
        if "/comments/" not in url:
            continue
        
        results.append({
            "title": title[:200],
            "url": url,
            "snippet": snippet[:3000],
            "source": "reddit",
            "date": updated_m.group(1) if updated_m else "",
            "username": author,
            "author": author,
        })
    
    print(f"    [reddit] got {len(results)} posts with author", file=_sys.stderr)
    # Guardar en cache 1h
    if results:
        _rss_cache[cache_key] = (_tm.time(), results)
    return results[:num]


def c_data_iter(comment_listing):
    """Itera sobre los bodies de comments de un listing de Reddit."""
    try:
        for c in comment_listing.get("data",{}).get("children",[])[:10]:
            yield c.get("data",{}).get("body","")
    except Exception:
        return

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



# ===========================================================================
# Provider 6: ForoArgentina.net (foro AR, sin rate limit agresivo)
# ===========================================================================
def search_foroargentina(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca en foroargentina.net via su buscador interno."""
    import sys as _sys
    print(f"    [foro] searching: {query[:60]}", file=_sys.stderr)
    
    # Limpiar query: quitar site:xxx
    clean_query = _re.sub(r"site:\S+", "", query).strip()
    if not clean_query:
        return []
    
    encoded = urllib.parse.quote(clean_query)
    search_url = f"https://www.foroargentina.net/buscar?buscar={encoded}&ordenar=fecha"
    
    try:
        req = urllib.request.Request(search_url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept-Language", "es-AR,es;q=0.9")
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [foro] ERROR: {e}", file=_sys.stderr)
        return []
    
    # Parse simple: buscar links a /viewtopic.php?t=XXX
    results = []
    # Patron: <a href="./viewtopic.php?f=X&t=Y" class="topictitle">TITLE</a>
    import re as _re2
    matches = _re2.findall(r'<a[^>]*href="[^"]*viewtopic\.php[^"]*t=(\d+)[^"]*"[^>]*class="[^"]*topictitle[^"]*"[^>]*>([^<]+)</a>', html)
    if not matches:
        # Fallback: buscar cualquier link a viewtopic con texto
        matches = _re2.findall(r'<a[^>]*href="((?:\./)?viewtopic\.php\?[^"]*t=\d+[^"]*)"[^>]*>([^<]{15,150})</a>', html)
    
    for tid, title in matches[:num]:
        title = _re2.sub(r"<[^>]+>", "", title).strip()
        if not title:
            continue
        # URL completa
        if isinstance(tid, str) and tid.isdigit():
            post_url = f"https://www.foroargentina.net/viewtopic.php?t={tid}"
        else:
            href = tid  # fallback caso 2
            post_url = href if href.startswith("http") else f"https://www.foroargentina.net/{href.lstrip('./')}"
        
        results.append({
            "title": title[:200],
            "url": post_url,
            "snippet": "",  # el search no da snippet, habria que scrapear el post
            "source": "foroargentina",
            "date": "",
            "username": "",
            "author": "",
        })
    
    # Para cada resultado, scrapear el post para conseguir author + body
    for r in results[:5]:  # solo top 5 para no abusar
        try:
            time.sleep(1.5)
            req2 = urllib.request.Request(r["url"])
            req2.add_header("User-Agent", random.choice(USER_AGENTS))
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                post_html = resp2.read().decode("utf-8", errors="replace")
            
            # Author: <a class="username" ...>NAME</a> o <span class="postauthor">NAME</span>
            author_m = _re2.search(r'class="username[^"]*"[^>]*>([^<]{3,30})<', post_html)
            if not author_m:
                author_m = _re2.search(r'class="postauthor"[^>]*>([^<]{3,30})<', post_html)
            if author_m:
                r["username"] = author_m.group(1).strip()
                r["author"] = author_m.group(1).strip()
            
            # Body: <div class="content">...</div>
            body_m = _re2.search(r'<div class="content"[^>]*>(.*?)</div>', post_html, _re2.DOTALL)
            if body_m:
                body = _re2.sub(r"<[^>]+>", " ", body_m.group(1))
                body = body.replace("&amp;","&").replace("&lt;","<").replace("&gt;",">").replace("&quot;",'"').replace("&#39;","'")
                r["snippet"] = _re2.sub(r"\s+", " ", body).strip()[:2000]
            
            # Date: <time datetime="2024-01-15...">
            date_m = _re2.search(r'<time[^>]*datetime="([^"]+)"', post_html)
            if date_m:
                r["date"] = date_m.group(1)[:10]
        except Exception:
            continue
    
    print(f"    [foro] got {len(results)} results", file=_sys.stderr)
    return results[:num]



# ===========================================================================
# Provider 7: Facebook groups via DuckDuckGo (sin auth, sin cookies)
# ===========================================================================
def search_facebook_via_ddg(query: str, num: int = 10) -> List[Dict[str, Any]]:
    """Busca posts de grupos publicos de Facebook via DuckDuckGo.
    No requiere cuenta FB ni API key.
    Devuelve leads con texto y link pero SIN author (limitacion de DDG snippets).
    """
    import sys as _sys
    print(f"    [facebook] searching: {query[:60]}", file=_sys.stderr)
    
    # Si la query no tiene site:facebook.com, agregarlo
    if "site:facebook.com" not in query.lower():
        search_query = f"site:facebook.com/groups {query}"
    else:
        search_query = query
    
    # Usar search_duckduckgo existente
    ddg_results = search_duckduckgo(search_query, num=num * 2)
    
    results = []
    for r in ddg_results:
        url = r.get("url", "")
        if "facebook.com/groups" not in url:
            continue
        
        # Extraer group_name de la URL
        # facebook.com/groups/multasargentina/posts/123456
        # o facebook.com/groups/276074287942602/permalink/...
        import re as _re2
        group_match = _re2.search(r"/groups/([^/?#]+)", url)
        group_id_raw = ""
        if group_match:
            group_id_raw = group_match.group(1)
        
        # Si group_id es solo numeros (ID interno FB), usar el title del result
        # Title suele ser "Nombre del Grupo - Facebook"
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        
        if group_id_raw.isdigit():
            # Extraer nombre del grupo del title
            # "Defensas contra las Multas de Transito (Argentina) - Facebook"
            group_name = title.replace(" | Facebook", "").replace(" - Facebook", "").strip()
        else:
            group_name = group_id_raw.replace("-", " ").replace("_", " ").title()
        
        if not snippet and not title:
            continue
        if len(snippet) < 20 and len(title) < 10:
            continue
        
        results.append({
            "title": (title or snippet)[:200],
            "url": url,
            "snippet": snippet[:3000],
            "source": "facebook_groups",
            "date": r.get("date", ""),
            "username": group_name,
            "author": group_name,
            "group_name": group_name,
        })
    
    print(f"    [facebook] got {len(results)} posts from FB groups", file=_sys.stderr)
    return results[:num]



# ===========================================================================
# Provider 8: MercadoLibre Questions Radar (sin auth, API publica)
# ===========================================================================
# Estrategia (Sakana+Claude corregido):
# 1. Pre-filtrar items por titulo con keywords de problema
# 2. Para cada item, pedir /questions/search?item=XXX
# 3. Filtrar questions localmente por keywords de multa
# 4. Author real = seller.nickname

ML_BASE = "https://api.mercadolibre.com"
ML_SITE_ID = "MLA"  # Argentina
ML_CATEGORY_AUTOS = "MLA1744"  # Autos y Camionetas

# Keywords para pre-filtrar TITULOS de items (Claude fix)
ML_TITLE_QUERIES = [
    "transferir urgente",
    "no puedo transferir",
    "con multa",
    "deuda patente",
    "libre deuda",
    "transferencia pendiente",
]

# Keywords para filtrar preguntas de compradores
ML_MULTA_KEYWORDS = [
    "multa", "multas", "infraccion", "libre deuda", "deuda",
    "fotomulta", "puede transferir", "transferencia", "patente",
    "08", "cedula", "transferir",
]

# Max items por query (limitar para no quemar rate limit ML)
ML_MAX_ITEMS_PER_QUERY = 3
ML_MAX_TOTAL_ITEMS = 10


def _ml_get(url: str) -> Optional[dict]:
    """GET a ML API con timeout y manejo de errores."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        import sys as _sys
        print(f"    [ml] ERROR {url[:80]}: {e}", file=_sys.stderr)
        return None


def _ml_normalize_provincia(raw: str) -> str:
    """Normaliza nombres de provincia de ML."""
    if not raw:
        return ""
    MAP = {
        "Santa Fe": "Santa Fe",
        "Buenos Aires": "Buenos Aires",
        "Ciudad Autonoma de Buenos Aires": "CABA",
        "Capital Federal": "CABA",
        "Cordoba": "Cordoba",
        "Entre Rios": "Entre Rios",
        "Misiones": "Misiones",
        "La Pampa": "La Pampa",
        "Mendoza": "Mendoza",
        "Tucuman": "Tucuman",
        "Salta": "Salta",
        "Chaco": "Chaco",
        "Corrientes": "Corrientes",
    }
    # Quitar acentos para matching
    raw_clean = raw.replace("ó","o").replace("á","a").replace("é","e").replace("í","i").replace("ú","u")
    return MAP.get(raw_clean, raw)




def fetch_ml_seller_contact(seller_id: str) -> dict:
    """Endpoint publico: /users/{seller_id}
    Vendedores profesionales suelen tener email y telefono visibles.
    Sin auth.
    """
    if not seller_id:
        return {}
    url = f"https://api.mercadolibre.com/users/{seller_id}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", random.choice(USER_AGENTS))
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {}
    
    contact = {}
    
    # Email - disponible si el vendedor lo hizo publico
    email = data.get("email", "")
    if email and "@" in email and "mercadolibre" not in email.lower():
        contact["email"] = email.lower().strip()
        contact["contact_source"] = "ml_seller_profile"
    
    # Telefono - cuentas profesionales
    phone = data.get("phone", {})
    if isinstance(phone, dict):
        number = phone.get("number", "")
        area = phone.get("area_code", "")
        if number:
            digits = re.sub(r"\D", "", f"{area}{number}")
            if len(digits) >= 8:
                contact["phone"] = f"+{digits}" if not digits.startswith("+") else digits
                if "contact_source" not in contact:
                    contact["contact_source"] = "ml_seller_profile"
    
    # Tags utiles para scoring
    tags = data.get("tags", [])
    contact["seller_tags"] = tags
    contact["is_professional"] = any(t in tags for t in
        ["real_estate_agency", "car_dealer", "meli_choice", "large_seller"])
    
    # Nickname real si estaba vacio
    if not contact.get("nickname"):
        nick = data.get("nickname", "")
        if nick:
            contact["seller_nickname"] = nick
    
    return contact

def search_mercadolibre_questions(num: int = 15) -> List[Dict[str, Any]]:
    """Llama al endpoint /api/ml-questions del Worker que hace fetch a ML API
    desde IP de Cloudflare edge (evita 403 de GH Actions).
    """
    import os as _os
    import sys as _sys
    worker_url = _os.environ.get("WORKER_URL", "https://leadx.simondalmasso44.workers.dev")
    secret = _os.environ.get("INGEST_SECRET", "")
    
    if not secret:
        print(f"    [ml] SKIP: INGEST_SECRET no configurado", file=_sys.stderr)
        return []
    
    print(f"    [ml] calling Worker /api/ml-questions (Cloudflare edge)", file=_sys.stderr)
    
    url = f"{worker_url}/api/ml-questions"
    try:
        req = urllib.request.Request(url)
        req.add_header("X-Webhook-Secret", secret)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "LeadX-Pipeline/2.0")
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        
        if not data.get("ok"):
            print(f"    [ml] Worker error: {data.get('error','?')}", file=_sys.stderr)
            return []
        
        leads = data.get("leads", [])
        contactables = data.get("contactables", 0)
        items_processed = data.get("items_processed", 0)
        print(f"    [ml] Worker OK: {len(leads)} leads, {contactables} contactables, {items_processed} items",
              file=_sys.stderr)
        return leads[:num]
    except Exception as e:
        print(f"    [ml] Worker call failed: {e}", file=_sys.stderr)
        return []

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

    # Si la query menciona foroargentina, usar provider foroargentina
    if "site:foroargentina" in query.lower() or "foroargentina" in query.lower():
        try:
            fa = search_foroargentina(query, num=num)
            all_results.extend(fa)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:facebook.com, usar provider dedicado
    if "site:facebook.com" in query.lower():
        try:
            fb = search_facebook_via_ddg(query, num=num)
            all_results.extend(fb)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:mercadolibre, usar ML Questions Radar
    if "site:mercadolibre" in query.lower() or "site:mla" in query.lower():
        try:
            ml = search_mercadolibre_questions(num=num)
            all_results.extend(ml)
            return all_results[:num * 2]
        except Exception:
            pass

    # Si la query es site:x.com o sin site:, usar DuckDuckGo
    # Provider 1: DuckDuckGo
    try:
        ddg = search_duckduckgo(query, num=num)
        all_results.extend(ddg)
        time.sleep(RATE_LIMIT_SECONDS)
    except Exception:
        pass

    # Provider 2: Reddit — SOLO para queries que no tengan site: ya especifico
    # (no llamar a search_reddit para site:com.ar o site:facebook.com, quema rate limit)
    # El ruteo explicito de site:reddit.com ya esta arriba.

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

# ===========================================================================
# Wrapper para PendingQueryManager: devuelve (leads, got_429)
# ===========================================================================
def search_reddit_with_status(query: str, num: int = 10):
    """Wrapper de search_reddit que devuelve (leads, got_429).
    
    got_429=True si Reddit devolvió HTTP 429.
    got_429=False si fue exitoso o falló por otra razón.
    """
    import sys as _sys
    # Parchar temporalmente el print de error para detectar 429
    _orig_stderr = _sys.stderr
    _captured_err = []
    class _StderrCapture:
        def write(self, s):
            _captured_err.append(s)
            _orig_stderr.write(s)  # también imprimir normal
        def flush(self):
            _orig_stderr.flush()
    _sys.stderr = _StderrCapture()
    
    try:
        leads = search_reddit(query, num=num)
        # Si hubo 429 en los logs, devolver True
        err_text = "".join(_captured_err)
        got_429 = "429" in err_text and "RSS search fail" in err_text
        return leads, got_429
    finally:
        _sys.stderr = _orig_stderr


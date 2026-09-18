#!/usr/bin/env python3
"""
crawl.py - Collect raw SEO signals from a website into a single JSON file.

No API keys required. If PAGESPEED_API_KEY is set, Core Web Vitals field data
from Google's PageSpeed Insights API is added for the homepage.

Usage:
    python crawl.py https://example.com --max-pages 25 --out .seo-audit/site.json

The output JSON is the *only* input the specialist agents read, so everything
an agent might need to make a judgement should be captured here, verbatim
where practical (titles, metas, JSON-LD blocks, headings, etc.).
"""

import argparse
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (compatible; seo-audit-skill/1.0; "
    "+https://github.com/amantalwar/seo-audit-skill)"
)
TIMEOUT = 15
CRAWL_DELAY = 0.5  # seconds between requests - be polite

# Files that matter for AI/LLM crawlers and classic SEO
SITE_FILES = ["robots.txt", "sitemap.xml", "sitemap_index.xml", "llms.txt", "llms-full.txt", "ads.txt"]

# AI crawler user-agents to check for in robots.txt
AI_BOTS = [
    "GPTBot", "ChatGPT-User", "OAI-SearchBot", "Google-Extended", "ClaudeBot",
    "anthropic-ai", "PerplexityBot", "Bytespider", "CCBot", "Applebot-Extended",
    "Amazonbot", "cohere-ai", "Meta-ExternalAgent",
]


def log(msg):
    print(f"[crawl] {msg}", file=sys.stderr, flush=True)


def normalize(url):
    """Strip fragments and trailing slashes for dedupe (keep root slash)."""
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return parsed._replace(path=path, query=parsed.query).geturl()


def same_site(url, root_netloc):
    n = urlparse(url).netloc.lower()
    r = root_netloc.lower()
    return n == r or n == f"www.{r}" or r == f"www.{n}"


def fetch(session, url, allow_redirects=True):
    start = time.time()
    try:
        r = session.get(url, timeout=TIMEOUT, allow_redirects=allow_redirects)
        elapsed = round((time.time() - start) * 1000)
        return r, elapsed, None
    except requests.RequestException as e:
        return None, round((time.time() - start) * 1000), str(e)


def text_of(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


def _walk_types(block):
    """Yield every @type found anywhere inside a JSON-LD block."""
    if isinstance(block, dict):
        t = block.get("@type")
        yield from ([t] if isinstance(t, str) else (t or []))
        for v in block.values():
            yield from _walk_types(v)
    elif isinstance(block, list):
        for b in block:
            yield from _walk_types(b)


def parse_page(url, resp, elapsed_ms, root_netloc):
    """Extract every on-page signal an SEO specialist would want to see."""
    ctype = resp.headers.get("Content-Type", "")
    page = {
        "url": url,
        "final_url": resp.url,
        "status": resp.status_code,
        "redirect_chain": [h.url for h in resp.history],
        "content_type": ctype,
        "response_ms": elapsed_ms,
        "bytes": len(resp.content),
        "headers": {
            k: v for k, v in resp.headers.items()
            if k.lower() in (
                "content-type", "cache-control", "x-robots-tag", "content-encoding",
                "strict-transport-security", "content-security-policy", "x-frame-options",
                "x-content-type-options", "referrer-policy", "link", "vary", "server",
                "last-modified", "etag", "content-language",
            )
        },
    }
    if "html" not in ctype.lower():
        return page

    soup = BeautifulSoup(resp.text, "lxml")
    html_tag = soup.find("html")

    # --- Head signals -----------------------------------------------------
    title = soup.find("title")
    page["title"] = text_of(title)
    page["title_length"] = len(page["title"])
    page["lang"] = html_tag.get("lang") if html_tag else None

    metas = {}
    for m in soup.find_all("meta"):
        name = (m.get("name") or m.get("property") or m.get("http-equiv") or "").lower()
        if name:
            metas[name] = m.get("content", "")
    page["meta"] = metas
    page["meta_description"] = metas.get("description", "")
    page["meta_description_length"] = len(page["meta_description"])
    page["meta_robots"] = metas.get("robots", "")
    page["meta_googlebot"] = metas.get("googlebot", "")  # Google also honours a Googlebot-specific meta tag
    page["viewport"] = metas.get("viewport", "")

    # Directives that control snippets/previews in Search *and* AI features (AI Overviews, AI Mode) -
    # per developers.google.com/search/docs/appearance/ai-features, robots.txt/Googlebot access plus
    # these tags are the site owner's controls for AI inclusion. Pull from both meta sources + header.
    robots_directives = f"{page['meta_robots']} {page['meta_googlebot']} {page['headers'].get('X-Robots-Tag', '')}".lower()
    page["snippet_controls"] = {
        "nosnippet": "nosnippet" in robots_directives,
        "max_snippet": next((d.strip() for d in robots_directives.split(",") if "max-snippet" in d), None),
        "max_image_preview": next((d.strip() for d in robots_directives.split(",") if "max-image-preview" in d), None),
        "data_nosnippet_elements": len(soup.find_all(attrs={"data-nosnippet": True})),
    }
    page["og"] = {k: v for k, v in metas.items() if k.startswith("og:")}
    page["twitter"] = {k: v for k, v in metas.items() if k.startswith("twitter:")}

    canon = soup.find("link", rel=lambda v: v and "canonical" in v)
    page["canonical"] = canon.get("href") if canon else None

    page["hreflang"] = [
        {"lang": l.get("hreflang"), "href": l.get("href")}
        for l in soup.find_all("link", rel=lambda v: v and "alternate" in v)
        if l.get("hreflang")
    ]
    page["amp"] = bool(soup.find("link", rel=lambda v: v and "amphtml" in v))

    # --- Headings & content ----------------------------------------------
    page["headings"] = {
        f"h{i}": [text_of(h) for h in soup.find_all(f"h{i}")] for i in range(1, 7)
    }
    page["h1_count"] = len(page["headings"]["h1"])

    # Strip nav/footer/script for a rough "main content" word count
    body = soup.find("body")
    if body:
        for tag in body.find_all(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
            tag.decompose()
        body_text = text_of(body)
    else:
        body_text = ""
    words = body_text.split()
    page["word_count"] = len(words)
    page["text_sample"] = " ".join(words[:400])  # enough for E-E-A-T judgement

    # --- Images ----------------------------------------------------------
    imgs = soup.find_all("img")
    page["images"] = {
        "total": len(imgs),
        "missing_alt": [i.get("src", "")[:200] for i in imgs if not i.get("alt")][:25],
        "lazy_loaded": sum(1 for i in imgs if i.get("loading") == "lazy"),
        "without_dimensions": sum(1 for i in imgs if not (i.get("width") and i.get("height"))),
        # Samples so agents can judge whether alt text is *descriptive* (Starter Guide), not just present
        "alt_samples": [{"src": i.get("src", "")[-80:], "alt": i.get("alt", "")[:120]} for i in imgs if i.get("alt")][:10],
    }
    # Videos: the guide wants them on a standalone page near relevant text
    page["videos"] = {
        "video_tags": len(soup.find_all("video")),
        "embeds": sum(1 for f in soup.find_all("iframe", src=True) if re.search(r"youtube|youtu\.be|vimeo|wistia|loom", f["src"], re.I)),
    }
    page["meta_keywords_present"] = bool(metas.get("keywords"))

    # --- Links -----------------------------------------------------------
    internal, external, nofollow = [], [], 0
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        abs_url = urljoin(resp.url, href)
        if not abs_url.startswith(("http://", "https://")):
            continue
        rel = a.get("rel") or []
        if "nofollow" in rel:
            nofollow += 1
        entry = {"href": normalize(abs_url), "text": text_of(a)[:80]}
        (internal if same_site(abs_url, root_netloc) else external).append(entry)
    page["links"] = {
        "internal_count": len(internal),
        "external_count": len(external),
        "nofollow_count": nofollow,
        "internal": internal,
        "external": external[:50],
        "generic_anchor_count": sum(
            1 for l in internal if l["text"].lower() in ("click here", "read more", "here", "learn more", "more")
        ),
    }

    # --- Structured data --------------------------------------------------
    jsonld = []
    for s in soup.find_all("script", type="application/ld+json"):
        raw = s.string or s.get_text()
        try:
            jsonld.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            jsonld.append({"_parse_error": True, "_raw": (raw or "")[:500]})
    page["jsonld"] = jsonld
    page["microdata_itemtypes"] = list({t.get("itemtype") for t in soup.find_all(itemtype=True)})

    # --- Tech / performance hints ----------------------------------------
    scripts = soup.find_all("script", src=True)
    styles = soup.find_all("link", rel=lambda v: v and "stylesheet" in v)
    page["resource_urls"] = [urljoin(resp.url, x.get("src") or x.get("href")) for x in (scripts[:15] + styles[:10]) if (x.get("src") or x.get("href"))]
    page["resources"] = {
        "scripts": len(scripts),
        "render_blocking_scripts": sum(1 for s in scripts if not (s.get("async") or s.get("defer") or s.get("type") == "module")),
        "stylesheets": len(styles),
        "inline_style_blocks": len(soup.find_all("style")),
        "iframes": len(soup.find_all("iframe")),
        "preload_hints": len(soup.find_all("link", rel=lambda v: v and ("preload" in v or "preconnect" in v))),
    }
    page["forms"] = len(soup.find_all("form"))
    page["has_search_box"] = bool(soup.find("input", attrs={"type": "search"})) or bool(
        soup.find("input", attrs={"name": re.compile(r"^(q|s|search|query)$", re.I)})
    )

    # --- Site-type signals (used by orchestrator to decide which agents run)
    lower_html = resp.text.lower()
    jsonld_types = {str(t) for b in jsonld for t in _walk_types(b)}
    ecom_hits = sum(k in lower_html for k in ("add to cart", "add-to-cart", "checkout", "shopping cart", "woocommerce", "shopify", "cart-count", "/cart"))
    local_hits = sum(k in lower_html for k in ("opening hours", "openinghours", "get directions", "our location", "visit us", "hours of operation", "store hours"))
    phone = bool(re.search(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b", body_text))
    address = bool(soup.find("address")) or bool(re.search(r"\b\d{1,5}\s+\w+(?:\s\w+)?\s+(street|st|avenue|ave|road|rd|blvd|boulevard|drive|dr|lane|ln|way|suite)\b", body_text, re.I))
    page["signals"] = {
        # Require corroboration so a single word like "checkout" or "directions" doesn't misclassify a site
        "ecommerce": ecom_hits >= 2 or bool(jsonld_types & {"Product", "Offer", "AggregateOffer"}),
        "local": (local_hits >= 1 and (phone or address)) or (phone and address)
                 or bool(jsonld_types & {"LocalBusiness", "PostalAddress"}) or any(t.endswith("Business") for t in jsonld_types),
        "phone_present": phone,
        "address_present": address,
        "international": len(page["hreflang"]) > 0 or bool(re.search(r"/(en|fr|de|es|it|pt|ja|zh|ko|nl|ar|hi)(-[a-z]{2})?/", resp.url, re.I)),
        "author_byline": bool(soup.find(attrs={"rel": "author"})) or bool(soup.find(class_=re.compile("author|byline", re.I))),
        "dates_present": bool(soup.find("time")) or "datepublished" in lower_html,
    }

    return page, [l["href"] for l in internal]


def fetch_site_files(session, root):
    out = {}
    for name in SITE_FILES:
        url = urljoin(root, "/" + name)
        r, ms, err = fetch(session, url)
        entry = {"url": url, "status": r.status_code if r is not None else None, "error": err}
        if r is not None and r.status_code == 200:
            body = r.text
            entry["size"] = len(body)
            entry["content"] = body[:20000]
            if name == "robots.txt":
                entry["sitemaps"] = re.findall(r"(?im)^sitemap:\s*(\S+)", body)
                entry["ai_bot_rules"] = {
                    bot: bool(re.search(rf"(?im)^user-agent:\s*{re.escape(bot)}\s*$", body)) for bot in AI_BOTS
                }
                entry["disallow_all_for_star"] = bool(
                    re.search(r"(?is)user-agent:\s*\*\s*(?:\r?\n(?!user-agent).*)*?disallow:\s*/\s*$", body, re.M)
                )
            if name.startswith("sitemap"):
                entry["url_count"] = len(re.findall(r"<loc>", body))
                entry["is_index"] = "<sitemapindex" in body
                entry["has_lastmod"] = "<lastmod>" in body
        out[name] = entry
        time.sleep(0.2)
    return out


def sitemap_urls(session, root, site_files, root_netloc, limit=500):
    """Return page URLs listed in the site's sitemaps, following sitemap-index files one level.
    Used to seed the crawl so pages that aren't linked from the homepage are still audited."""
    candidates = list(site_files.get("robots.txt", {}).get("sitemaps") or [])
    for name in ("sitemap.xml", "sitemap_index.xml"):
        if site_files.get(name, {}).get("status") == 200:
            candidates.append(site_files[name]["url"])
    seen_maps, pages = set(), []
    queue = deque(candidates)
    depth = {c: 0 for c in candidates}
    while queue and len(pages) < limit:
        sm = queue.popleft()
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        body = site_files.get("sitemap.xml", {}).get("content") if sm == site_files.get("sitemap.xml", {}).get("url") else None
        if body is None:
            r, _, _ = fetch(session, sm)
            if r is None or r.status_code != 200:
                continue
            body = r.text
            time.sleep(0.2)
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.I | re.S)
        if "<sitemapindex" in body.lower():
            if depth.get(sm, 0) < 1:
                for child in locs[:20]:
                    depth[child] = depth.get(sm, 0) + 1
                    queue.append(child)
        else:
            pages.extend(l for l in locs if same_site(l, root_netloc))
    return {"sitemaps_read": sorted(seen_maps), "urls": pages[:limit]}


def check_https_and_redirects(session, root):
    """Check http->https and www/non-www consolidation."""
    parsed = urlparse(root)
    host = parsed.netloc
    alt_host = host[4:] if host.startswith("www.") else f"www.{host}"
    variants = [f"http://{host}/", f"https://{host}/", f"http://{alt_host}/", f"https://{alt_host}/"]
    results = []
    for v in variants:
        r, ms, err = fetch(session, v)
        results.append({
            "url": v,
            "final_url": r.url if r is not None else None,
            "status": r.status_code if r is not None else None,
            "hops": len(r.history) if r is not None else None,
            "error": err,
        })
        time.sleep(0.2)
    return results


def pagespeed(url):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from keys import apply_to_environ  # env var → ~/.talwar-seo-audit/.env → ./.env
        apply_to_environ()
    except ImportError:
        pass
    key = os.environ.get("PAGESPEED_API_KEY")
    if not key:
        return {"skipped": "PAGESPEED_API_KEY not set - run `python scripts/keys.py status` for how to add it"}
    out = {}
    for strategy in ("mobile", "desktop"):
        try:
            r = requests.get(
                "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                params={"url": url, "strategy": strategy, "key": key, "category": ["performance", "seo", "accessibility"]},
                timeout=90,
            )
            data = r.json()
            if "error" in data or r.status_code != 200:
                msg = (data.get("error") or {}).get("message") or f"HTTP {r.status_code}"
                out[strategy] = {"error": f"PageSpeed API rejected the request: {msg}. "
                                          "Run `python scripts/keys.py verify PAGESPEED_API_KEY`."}
                continue
            lh = data.get("lighthouseResult", {})
            cats = lh.get("categories", {})
            audits = lh.get("audits", {})
            field = data.get("loadingExperience", {}).get("metrics", {})
            out[strategy] = {
                "performance_score": cats.get("performance", {}).get("score"),
                "seo_score": cats.get("seo", {}).get("score"),
                "accessibility_score": cats.get("accessibility", {}).get("score"),
                "lab": {
                    k: audits.get(k, {}).get("displayValue")
                    for k in ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time", "first-contentful-paint", "speed-index", "interactive")
                },
                "field": {
                    k: {"p75": v.get("percentile"), "category": v.get("category")}
                    for k, v in field.items()
                },
            }
        except Exception as e:  # noqa: BLE001 - we want the audit to continue
            out[strategy] = {"error": str(e)}
    return out


def diagnose_zero_pages(pages, skipped_by_robots, host_variants, site_files, urls_discovered):
    """Explain why nothing was crawled, in a form the report can show a client."""
    html_ok = [p for p in pages if p.get("status") == 200 and "html" in (p.get("content_type") or "").lower()]
    if html_ok:
        return None
    statuses = [h.get("status") for h in host_variants]
    errors = [h.get("error") for h in host_variants if h.get("error")]
    robots = site_files.get("robots.txt", {})
    robots_note = chr(10).join(l for l in (robots.get("content") or "").splitlines() if l.startswith("#"))[:600]
    if all(s is None for s in statuses) and errors:
        return {"reason": "unreachable",
                "title": "The site could not be reached",
                "detail": "Every host variant failed at the network level (DNS, TLS, or connection timeout).",
                "evidence": errors[:4]}
    if skipped_by_robots and not pages:
        return {"reason": "robots",
                "title": "robots.txt disallows automated crawling",
                "detail": ("The site's robots.txt denies access to crawlers that are not explicitly whitelisted. "
                           f"{len(skipped_by_robots)} discovered URL(s) were skipped in compliance with those rules."),
                "evidence": [robots_note] if robots_note else [],
                "also_http": [s for s in statuses if s and s >= 400],
                "whitelisted_agents": re.findall(r"(?im)^user-agent:\s*(\S.*?)\s*$", robots.get("content") or "")[:40]}
    if statuses and all((s or 0) >= 400 for s in statuses):
        return {"reason": "http_forbidden",
                "title": f"The server refused the crawler (HTTP {statuses[0]})",
                "detail": "Every host variant returned an error status. The site is likely behind a bot-protection layer "
                          "(e.g. a CDN/WAF challenge) or blocks unrecognised user agents.",
                "evidence": [f"{h['url']} -> HTTP {h.get('status')}" for h in host_variants]}
    if pages:
        return {"reason": "no_html",
                "title": "Pages were fetched but none were indexable HTML",
                "detail": "Responses were non-HTML or non-200 for every URL tried.",
                "evidence": [f"{p.get('url')} -> {p.get('status')} {p.get('content_type', '')}" for p in pages[:6]]}
    return {"reason": "unknown", "title": "No pages could be crawled",
            "detail": f"{urls_discovered} URL(s) were discovered but none produced an HTML page.", "evidence": []}


def crawl(start_url, max_pages, respect_robots=True):
    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url
    root_netloc = urlparse(start_url).netloc
    root = f"{urlparse(start_url).scheme}://{root_netloc}/"

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en"})

    log(f"Fetching site-level files for {root}")
    site_files = fetch_site_files(session, root)

    # Parse robots.txt from the body we fetched with *our* user-agent. Using
    # RobotFileParser.read() would refetch with urllib's default UA, which
    # many CDNs block with 403 - and robotparser treats 403 as "disallow all".
    rp = None
    robots_entry = site_files.get("robots.txt", {})
    if respect_robots and robots_entry.get("status") == 200:
        rp = robotparser.RobotFileParser()
        rp.parse(robots_entry.get("content", "").splitlines())
    log("Checking protocol / host variants")
    host_variants = check_https_and_redirects(session, root)

    queue = deque([normalize(start_url)])
    seen = {normalize(start_url)}
    log("Reading sitemaps to seed the crawl")
    sm = sitemap_urls(session, root, site_files, root_netloc)
    for u in sm["urls"]:
        n = normalize(u)
        if n not in seen:
            seen.add(n)
            queue.append(n)
    log(f"Sitemaps read: {len(sm['sitemaps_read'])}, URLs seeded: {len(sm['urls'])}")
    pages, broken_links, skipped_by_robots = [], [], []
    inbound = {}  # url -> count of internal links pointing to it

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        # normalize() strips trailing slashes, but robots rules like "Disallow: /wp-admin/"
        # only match the slashed form - so test both spellings.
        if rp and not (rp.can_fetch(USER_AGENT, url) and rp.can_fetch(USER_AGENT, url + "/")):
            skipped_by_robots.append(url)
            continue
        log(f"[{len(pages)+1}/{max_pages}] {url}")
        r, ms, err = fetch(session, url)
        if r is None:
            pages.append({"url": url, "status": None, "error": err, "response_ms": ms})
            continue
        result = parse_page(url, r, ms, root_netloc)
        if isinstance(result, tuple):
            page, links = result
            for l in links:
                inbound[l] = inbound.get(l, 0) + 1
                if l not in seen and same_site(l, root_netloc):
                    seen.add(l)
                    queue.append(l)
        else:
            page = result
        pages.append(page)
        time.sleep(CRAWL_DELAY)

    # Light-touch check of discovered-but-uncrawled internal links for 4xx/5xx
    remaining = [u for u in list(queue)[:40]]
    for u in remaining:
        r, ms, err = fetch(session, u)
        if r is None or r.status_code >= 400:
            broken_links.append({"url": u, "status": r.status_code if r is not None else None, "error": err})
        time.sleep(0.2)
    for p in pages:
        if p.get("status") and p["status"] >= 400:
            broken_links.append({"url": p["url"], "status": p["status"]})

    for p in pages:
        p["inbound_internal_links"] = inbound.get(normalize(p["url"]), 0)

    # Starter Guide: Google must be able to fetch the same CSS/JS as a browser.
    # Test each first-party resource URL against robots.txt as Googlebot.
    blocked_resources = []
    if rp:
        seen_res = set()
        for p in pages:
            for u in p.get("resource_urls", []):
                if u in seen_res or not same_site(u, root_netloc):
                    continue
                seen_res.add(u)
                if not rp.can_fetch("Googlebot", u):
                    blocked_resources.append({"resource": u, "used_by": p["url"]})
    for p in pages:
        p.pop("resource_urls", None)

    home = next((p for p in pages if p.get("status") == 200 and "html" in p.get("content_type", "")), None)

    return {
        "meta": {
            "tool": "seo-audit-skill",
            "version": "1.0.7",
            "start_url": start_url,
            "root": root,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
            "max_pages": max_pages,
            "pages_crawled": len(pages),
            "urls_discovered": len(seen),
            "skipped_by_robots": skipped_by_robots,
            "sitemaps_read": sm["sitemaps_read"],
            "sitemap_urls_found": len(sm["urls"]),
            "crawl_blocked": diagnose_zero_pages(pages, skipped_by_robots, host_variants, site_files, len(seen)),
        },
        "site_files": site_files,
        "host_variants": host_variants,
        "pagespeed": pagespeed(home["final_url"]) if home else {"skipped": "no homepage"},
        "broken_links": broken_links,
        "blocked_resources": blocked_resources[:50],
        "site_signals": {
            "ecommerce": sum(1 for p in pages if p.get("signals", {}).get("ecommerce")),
            "local": sum(1 for p in pages if p.get("signals", {}).get("local")),
            "international": sum(1 for p in pages if p.get("signals", {}).get("international")),
            "pages_with_jsonld": sum(1 for p in pages if p.get("jsonld")),
            # Walks nested blocks (e.g. Yoast/RankMath "@graph") so LocalBusiness/Product inside a graph count
            "jsonld_types": sorted({
                str(t) for p in pages for b in p.get("jsonld", []) for t in _walk_types(b)
            }),
        },
        "pages": pages,
    }


def main():
    ap = argparse.ArgumentParser(description="Crawl a site and dump SEO signals to JSON.")
    ap.add_argument("url")
    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("--out", default=".seo-audit/site.json")
    ap.add_argument("--ignore-robots", action="store_true", help="Crawl even if robots.txt disallows (only for sites you own)")
    args = ap.parse_args()

    data = crawl(args.url, args.max_pages, respect_robots=not args.ignore_robots)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Wrote {args.out} ({data['meta']['pages_crawled']} pages)")
    print(json.dumps({
        "out": args.out,
        "pages_crawled": data["meta"]["pages_crawled"],
        "site_signals": data["site_signals"],
        "broken_links": len(data["broken_links"]),
        "crawl_blocked": data["meta"].get("crawl_blocked"),
    }, indent=2))


if __name__ == "__main__":
    main()

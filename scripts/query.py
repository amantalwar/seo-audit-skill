#!/usr/bin/env python3
"""
query.py - Compact views of site.json so specialist agents can inspect crawl
data without loading the whole file into context.

Usage:
    python query.py SITE_JSON overview          # crawl meta, site files, host variants, signals
    python query.py SITE_JSON pages             # one line per page: status, title/meta lengths, h1, words, canonical
    python query.py SITE_JSON page URL          # everything captured for one page (minus link lists)
    python query.py SITE_JSON heads             # titles + meta descriptions + h1s for every page (duplicate detection)
    python query.py SITE_JSON jsonld            # every JSON-LD block, grouped by page
    python query.py SITE_JSON links             # internal link graph summary, orphan-ish pages, broken links
    python query.py SITE_JSON hreflang          # hreflang + lang attributes per page
    python query.py SITE_JSON robots            # robots.txt content + AI bot rules + sitemap details
    python query.py SITE_JSON content           # word counts, text samples, author/date signals (for E-E-A-T)
    python query.py SITE_JSON images            # image alt/dimension stats per page
    python query.py SITE_JSON perf              # response times, bytes, resource counts, PageSpeed data
    python query.py SITE_JSON ecommerce         # product/offer schema, cart signals
    python query.py SITE_JSON local             # LocalBusiness schema, NAP signals
"""

import json
import sys
from collections import Counter


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def html_pages(d):
    return [p for p in d["pages"] if "html" in (p.get("content_type") or "").lower() and p.get("status") == 200]


def dump(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def overview(d):
    dump({
        "meta": d["meta"],
        "site_files": {k: {kk: vv for kk, vv in v.items() if kk != "content"} for k, v in d["site_files"].items()},
        "host_variants": d["host_variants"],
        "site_signals": d["site_signals"],
        "broken_links": d["broken_links"],
        "blocked_css_js_for_googlebot": d.get("blocked_resources", []),
        "pagespeed": d.get("pagespeed"),
        "status_counts": dict(Counter(str(p.get("status")) for p in d["pages"])),
    })


def pages(d):
    for p in d["pages"]:
        print(f"{p.get('status')}\t{p.get('response_ms')}ms\t"
              f"T{p.get('title_length', '-')}\tD{p.get('meta_description_length', '-')}\t"
              f"H1x{p.get('h1_count', '-')}\tW{p.get('word_count', '-')}\t"
              f"in{p.get('inbound_internal_links', 0)}\t"
              f"robots={p.get('meta_robots') or '-'}\tcanon={'self' if p.get('canonical') in (p.get('url'), p.get('final_url')) else (p.get('canonical') or 'NONE')}\t"
              f"{p.get('url')}")


def page(d, url):
    for p in d["pages"]:
        if p.get("url") == url or p.get("final_url") == url:
            q = dict(p)
            q["links"] = {k: v for k, v in p.get("links", {}).items() if k not in ("internal", "external")}
            dump(q)
            return
    print(f"no page matching {url}", file=sys.stderr)
    sys.exit(1)


def heads(d):
    titles, descs = Counter(), Counter()
    for p in html_pages(d):
        titles[p.get("title", "")] += 1
        descs[p.get("meta_description", "")] += 1
    for p in html_pages(d):
        print(f"URL:   {p['url']}")
        print(f"TITLE: ({p.get('title_length')}) {p.get('title')}{'  [DUPLICATE]' if titles[p.get('title', '')] > 1 else ''}")
        print(f"DESC:  ({p.get('meta_description_length')}) {p.get('meta_description')}{'  [DUPLICATE]' if p.get('meta_description') and descs[p.get('meta_description')] > 1 else ''}")
        print(f"H1:    {p.get('headings', {}).get('h1')}")
        print(f"H2:    {p.get('headings', {}).get('h2', [])[:8]}")
        print(f"OG:    {p.get('og')}")
        print()


def jsonld(d):
    for p in html_pages(d):
        if p.get("jsonld") or p.get("microdata_itemtypes"):
            print(f"=== {p['url']}")
            dump({"jsonld": p.get("jsonld"), "microdata_itemtypes": p.get("microdata_itemtypes")})
    print("SITE JSON-LD TYPES:", d["site_signals"]["jsonld_types"])


def links(d):
    inbound = Counter()
    for p in html_pages(d):
        for l in p.get("links", {}).get("internal", []):
            inbound[l["href"]] += 1
    dump({
        "per_page": [{
            "url": p["url"], "internal": p["links"]["internal_count"], "external": p["links"]["external_count"],
            "nofollow": p["links"]["nofollow_count"], "generic_anchors": p["links"]["generic_anchor_count"],
            "inbound": p.get("inbound_internal_links", 0),
        } for p in html_pages(d)],
        "low_inbound_crawled_pages": [p["url"] for p in html_pages(d) if p.get("inbound_internal_links", 0) <= 1 and p["url"] != d["meta"]["root"]],
        "most_linked_internal": inbound.most_common(15),
        "broken_links": d["broken_links"],
        "redirect_chains": [{"url": p["url"], "chain": p["redirect_chain"]} for p in d["pages"] if len(p.get("redirect_chain", [])) > 1],
    })


def hreflang(d):
    for p in html_pages(d):
        print(f"{p['url']}\n  lang={p.get('lang')} content-language={p.get('headers', {}).get('Content-Language')} hreflang={p.get('hreflang')}")


def robots(d):
    r = d["site_files"].get("robots.txt", {})
    print("--- robots.txt", r.get("status"))
    print(r.get("content", "")[:6000])
    print("\n--- AI bot rules present:", {k: v for k, v in r.get("ai_bot_rules", {}).items()})
    print("--- sitemaps declared:", r.get("sitemaps"))
    for name in ("sitemap.xml", "sitemap_index.xml", "llms.txt", "llms-full.txt"):
        s = d["site_files"].get(name, {})
        print(f"\n--- {name}: status={s.get('status')} size={s.get('size')} url_count={s.get('url_count')} is_index={s.get('is_index')} has_lastmod={s.get('has_lastmod')}")
        if name.startswith("llms") and s.get("content"):
            print(s["content"][:2000])
    print("\n--- per-page meta robots / x-robots-tag:")
    for p in html_pages(d):
        xr = p.get("headers", {}).get("X-Robots-Tag")
        if p.get("meta_robots") or xr:
            print(f"  {p['url']}: meta={p.get('meta_robots')!r} header={xr!r}")
    print("--- skipped by robots:", d["meta"].get("skipped_by_robots"))


def content(d):
    for p in html_pages(d):
        print(f"=== {p['url']}  words={p.get('word_count')} author_byline={p['signals'].get('author_byline')} dates={p['signals'].get('dates_present')} h1={p.get('headings', {}).get('h1')}")
        print(p.get("text_sample", "")[:1200])
        print()


def images(d):
    for p in html_pages(d):
        im = p.get("images", {})
        print(f"{p['url']}: total={im.get('total')} missing_alt={len(im.get('missing_alt', []))} lazy={im.get('lazy_loaded')} no_dims={im.get('without_dimensions')}")
        for src in im.get("missing_alt", [])[:5]:
            print(f"    missing alt: {src}")
        for a in im.get("alt_samples", [])[:5]:
            print(f"    alt sample: {a['alt']!r}  ({a['src']})")
        v = p.get("videos", {})
        if v.get("video_tags") or v.get("embeds"):
            print(f"    videos: <video>={v.get('video_tags')} embeds={v.get('embeds')} words_on_page={p.get('word_count')}")


def perf(d):
    for p in html_pages(d):
        r = p.get("resources", {})
        print(f"{p['url']}: {p.get('response_ms')}ms {p.get('bytes')}B scripts={r.get('scripts')} blocking={r.get('render_blocking_scripts')} css={r.get('stylesheets')} iframes={r.get('iframes')} preload={r.get('preload_hints')} viewport={p.get('viewport')!r} cache={p.get('headers', {}).get('Cache-Control')!r} enc={p.get('headers', {}).get('Content-Encoding')!r}")
    print("\nPageSpeed:")
    dump(d.get("pagespeed"))


def _types(block):
    if isinstance(block, dict):
        t = block.get("@type")
        yield from ([t] if isinstance(t, str) else (t or []))
        for v in block.values():
            yield from _types(v)
    elif isinstance(block, list):
        for b in block:
            yield from _types(b)


def ecommerce(d):
    for p in html_pages(d):
        types = set(_types(p.get("jsonld", [])))
        hit = p["signals"].get("ecommerce") or types & {"Product", "Offer", "AggregateOffer", "ItemList", "BreadcrumbList"}
        if hit:
            print(f"=== {p['url']} signals.ecommerce={p['signals'].get('ecommerce')} types={sorted(types)}")
            for b in p.get("jsonld", []):
                if "Product" in set(_types(b)):
                    dump(b)


def local(d):
    for p in html_pages(d):
        types = set(_types(p.get("jsonld", [])))
        s = p["signals"]
        if s.get("local") or s.get("address_present") or types & {"LocalBusiness", "Organization", "PostalAddress"} or any(t.endswith("Business") or t in ("Store", "Restaurant", "Dentist", "Attorney") for t in types):
            print(f"=== {p['url']} local={s.get('local')} phone={s.get('phone_present')} address={s.get('address_present')} types={sorted(types)}")
            for b in p.get("jsonld", []):
                if set(_types(b)) & {"LocalBusiness", "Organization", "PostalAddress"} or any(t.endswith("Business") for t in _types(b)):
                    dump(b)


COMMANDS = {
    "overview": overview, "pages": pages, "heads": heads, "jsonld": jsonld, "links": links,
    "hreflang": hreflang, "robots": robots, "content": content, "images": images, "perf": perf,
    "ecommerce": ecommerce, "local": local,
}


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in COMMANDS and sys.argv[2] != "page":
        print(__doc__)
        sys.exit(1)
    d = load(sys.argv[1])
    if sys.argv[2] == "page":
        page(d, sys.argv[3])
    else:
        COMMANDS[sys.argv[2]](d)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

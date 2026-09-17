#!/usr/bin/env python3
"""
render_pdf.py - Merge specialist-agent findings into a prioritized SEO audit PDF.

Usage:
    python render_pdf.py --site .seo-audit/site.json \
                         --findings-dir .seo-audit/findings \
                         --out .seo-audit/seo-audit-example-com.pdf

Each file in --findings-dir is JSON written by one specialist agent:

{
  "agent": "seo-technical",
  "category": "Technical SEO",
  "score": 72,                       # 0-100, agent's judgement of this area
  "summary": "One short paragraph.",
  "findings": [
    {
      "id": "TECH-001",
      "title": "Homepage returns 200 on both http and https",
      "severity": "high",            # critical | high | medium | low | info
      "effort": "low",               # low | medium | high
      "affected_urls": ["https://example.com/"],
      "evidence": "host_variants shows http://example.com/ -> 200 with 0 hops.",
      "recommendation": "301-redirect all http:// requests to https://.",
      "how_to_test": "curl -I http://example.com/ should return 301 with Location: https://...",
      "source": {"title": "Google: HTTPS as a ranking signal", "url": "https://..."}
    }
  ]
}

Pure-Python (ReportLab) so it installs anywhere with pip - no system deps.
Also writes an .html twin of the report next to the PDF.
"""

import argparse
import glob
import html
import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlparse

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_WEIGHT = {"critical": 10, "high": 6, "medium": 3, "low": 1, "info": 0}
EFFORT_WEIGHT = {"low": 1.0, "medium": 0.7, "high": 0.45}
SEVERITY_COLOR = {
    "critical": colors.HexColor("#B42318"),
    "high": colors.HexColor("#C4320A"),
    "medium": colors.HexColor("#B54708"),
    "low": colors.HexColor("#175CD3"),
    "info": colors.HexColor("#475467"),
}
INK = colors.HexColor("#101828")
MUTED = colors.HexColor("#475467")
RULE = colors.HexColor("#D0D5DD")
BAND = colors.HexColor("#F2F4F7")
ACCENT = colors.HexColor("#1D4ED8")

REPO_URL = "https://github.com/amantalwar/seo-audit-skill"
REPO_NAME = "Talwar SEO Audit Skill"

# Category display order (agents not listed go last, alphabetically)
CATEGORY_ORDER = [
    "Technical SEO", "Content Quality (E-E-A-T)", "Structured Data (Schema.org)",
    "AI Search (GEO)", "Local SEO", "E-commerce SEO", "International SEO",
]


# ----------------------------------------------------------------------------
# Data loading / prioritisation
# ----------------------------------------------------------------------------

def load_findings(findings_dir):
    reports = []
    for path in sorted(glob.glob(os.path.join(findings_dir, "*.json"))):
        with open(path, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[render] skipping {path}: {e}", file=sys.stderr)
                continue
        data.setdefault("agent", os.path.splitext(os.path.basename(path))[0])
        data.setdefault("category", data["agent"])
        data.setdefault("findings", [])
        data.setdefault("summary", "")
        for i, fnd in enumerate(data["findings"], 1):
            fnd.setdefault("id", f"{data['agent'].upper()}-{i:03d}")
            fnd["severity"] = str(fnd.get("severity", "medium")).lower()
            fnd["effort"] = str(fnd.get("effort", "medium")).lower()
            fnd["category"] = data["category"]
            fnd.setdefault("affected_urls", [])
            fnd.setdefault("evidence", "")
            fnd.setdefault("recommendation", "")
            fnd.setdefault("how_to_test", "")
            fnd.setdefault("source", {})
            fnd["priority"] = round(
                SEVERITY_WEIGHT.get(fnd["severity"], 3) * EFFORT_WEIGHT.get(fnd["effort"], 0.7), 2
            )
        reports.append(data)
    reports.sort(key=lambda r: (CATEGORY_ORDER.index(r["category"]) if r["category"] in CATEGORY_ORDER else 99, r["category"]))
    merged = dedupe_findings(reports)
    if merged:
        print(f"[render] merged {merged} duplicate finding(s) reported by more than one agent", file=sys.stderr)
    return reports


# ----------------------------------------------------------------------------
# Cross-agent de-duplication
# ----------------------------------------------------------------------------

_STOP = {"the", "a", "an", "and", "or", "of", "to", "on", "in", "is", "are", "not", "no", "for",
         "with", "at", "by", "from", "its", "it", "this", "that", "page", "pages", "site"}


def _tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in _STOP and len(w) > 2}


def dedupe_findings(reports, threshold=0.6):
    """Merge findings from different agents that describe the same issue.

    Two findings are duplicates when their title token sets overlap by >= threshold
    (overlap coefficient: |A∩B| / min(|A|,|B|), which tolerates one title being much
    longer than the other) and they share at least one affected URL (or both have none). The
    higher-severity finding survives; it gains the other's affected URLs and a
    'also_flagged_by' note, and the duplicate is dropped from its report.
    """
    survivors = []  # (finding, report)
    dropped = 0
    for r in reports:
        kept = []
        for f in r["findings"]:
            ft = _tokens(f["title"])
            match = None
            for g, gr in survivors:
                if gr is r:
                    continue
                gt = _tokens(g["title"])
                if not ft or not gt:
                    continue
                overlap = len(ft & gt) / min(len(ft), len(gt))
                fu = {u.rstrip("/") for u in f["affected_urls"]}
                gu = {u.rstrip("/") for u in g["affected_urls"]}
                if overlap >= threshold and (fu & gu or (not fu and not gu)):
                    match = g
                    break
            if match is None:
                survivors.append((f, r))
                kept.append(f)
            else:
                # Keep the more severe one; if equal keep the earlier (already in survivors)
                if SEVERITY_ORDER.get(f["severity"], 9) < SEVERITY_ORDER.get(match["severity"], 9):
                    # Promote f: swap contents into the survivor slot so ids/categories stay stable
                    match.update({k: f[k] for k in ("title", "severity", "effort", "evidence", "recommendation", "how_to_test", "source", "priority")})
                match["affected_urls"] = sorted(set(match["affected_urls"]) | set(f["affected_urls"]))
                match.setdefault("also_flagged_by", []).append(f"{r['category']} ({f['id']})")
                dropped += 1
        r["findings"] = kept
    return dropped


def overall_score(reports):
    scored = [r["score"] for r in reports if isinstance(r.get("score"), (int, float))]
    return round(sum(scored) / len(scored)) if scored else None


def severity_counts(reports):
    counts = {k: 0 for k in SEVERITY_ORDER}
    for r in reports:
        for f in r["findings"]:
            counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return counts


# ----------------------------------------------------------------------------
# PDF helpers
# ----------------------------------------------------------------------------

def esc(text):
    """Escape for ReportLab Paragraph (a mini-HTML dialect)."""
    return html.escape(str(text or ""), quote=False)


def styles():
    ss = getSampleStyleSheet()
    base = "Helvetica"
    s = {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=26, leading=32, textColor=INK, alignment=0, spaceAfter=6),
        "subtitle": ParagraphStyle("st", parent=ss["Normal"], fontName=base, fontSize=12, leading=16, textColor=MUTED),
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=INK, spaceBefore=6, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=INK, spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontName=base, fontSize=9.5, leading=13.5, textColor=INK),
        "small": ParagraphStyle("s", parent=ss["Normal"], fontName=base, fontSize=8, leading=11, textColor=MUTED),
        "label": ParagraphStyle("l", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MUTED),
        "mono": ParagraphStyle("m", parent=ss["Normal"], fontName="Courier", fontSize=8, leading=11, textColor=INK),
        "cell": ParagraphStyle("c", parent=ss["Normal"], fontName=base, fontSize=8.5, leading=11.5, textColor=INK),
        "cellb": ParagraphStyle("cb", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11.5, textColor=INK),
        "score_big": ParagraphStyle("sb", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=40, leading=44, textColor=INK, alignment=TA_CENTER),
        "score_cap": ParagraphStyle("sc", parent=ss["Normal"], fontName=base, fontSize=8, leading=10, textColor=MUTED, alignment=TA_CENTER),
    }
    return s


def sev_chip(sev, st):
    color = SEVERITY_COLOR.get(sev, MUTED)
    return Paragraph(f'<font color="{color.hexval()}"><b>{esc(sev.upper())}</b></font>', st["cellb"])


def score_color(score):
    if score is None:
        return MUTED
    if score >= 80:
        return colors.HexColor("#067647")
    if score >= 60:
        return colors.HexColor("#B54708")
    return colors.HexColor("#B42318")


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 12 * mm, doc.report_domain + " - SEO audit")
    canvas.drawRightString(A4[0] - doc.rightMargin, 12 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(RULE)
    canvas.line(doc.leftMargin, 16 * mm, A4[0] - doc.rightMargin, 16 * mm)
    canvas.restoreState()


def table(data, col_widths, st, header=True, zebra=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), BAND),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, MUTED),
        ]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FAFAFA")))
    t.setStyle(TableStyle(style))
    return t


# ----------------------------------------------------------------------------
# Report sections
# ----------------------------------------------------------------------------

def cover(site, reports, st, generated):
    meta = site.get("meta", {})
    domain = urlparse(meta.get("root", "")).netloc or meta.get("start_url", "")
    score = overall_score(reports)
    counts = severity_counts(reports)
    flow = [
        Spacer(1, 50 * mm),
        Paragraph("SEO Audit Report", st["title"]),
        Paragraph(esc(domain), ParagraphStyle("d", parent=st["subtitle"], fontSize=16, leading=20, textColor=ACCENT)),
        Spacer(1, 6 * mm),
        Paragraph(f"Generated {esc(generated)} &nbsp;|&nbsp; {meta.get('pages_crawled', 0)} pages crawled "
                  f"&nbsp;|&nbsp; {len(reports)} specialist reviews", st["subtitle"]),
        Spacer(1, 14 * mm),
    ]
    # Score + severity strip
    score_cell = [
        Paragraph(f'<font color="{score_color(score).hexval()}">{score if score is not None else "-"}</font>', st["score_big"]),
        Paragraph("OVERALL SCORE / 100", st["score_cap"]),
    ]
    sev_cells = []
    for sev in ("critical", "high", "medium", "low"):
        sev_cells.append([
            Paragraph(f'<font color="{SEVERITY_COLOR[sev].hexval()}">{counts.get(sev, 0)}</font>',
                      ParagraphStyle("x", parent=st["score_big"], fontSize=24, leading=28)),
            Paragraph(sev.upper(), st["score_cap"]),
        ])
    strip = Table([[score_cell] + sev_cells], colWidths=[50 * mm] + [30 * mm] * 4)
    strip.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (0, 0), 0.8, RULE),
        ("BACKGROUND", (0, 0), (0, 0), BAND),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    flow += [strip, Spacer(1, 20 * mm)]
    flow.append(Paragraph(
        f'This report was produced by the open-source <link href="{REPO_URL}" color="{ACCENT.hexval()}">'
        f'<b>{REPO_NAME}</b></link> for Claude Code. '
        "Findings are grounded in Google Search Central documentation; every recommendation "
        "includes a way to verify the fix. Scores are heuristic and intended for prioritisation, "
        "not as a ranking prediction.", st["small"]))
    flow.append(PageBreak())
    return flow


def executive_summary(site, reports, st):
    flow = [Paragraph("Executive summary", st["h1"])]
    rows = [[Paragraph("Area", st["cellb"]), Paragraph("Score", st["cellb"]),
             Paragraph("Crit", st["cellb"]), Paragraph("High", st["cellb"]),
             Paragraph("Med", st["cellb"]), Paragraph("Low", st["cellb"]),
             Paragraph("Summary", st["cellb"])]]
    for r in reports:
        c = {k: 0 for k in SEVERITY_ORDER}
        for f in r["findings"]:
            c[f["severity"]] = c.get(f["severity"], 0) + 1
        sc = r.get("score")
        rows.append([
            Paragraph(esc(r["category"]), st["cellb"]),
            Paragraph(f'<font color="{score_color(sc).hexval()}"><b>{sc if sc is not None else "-"}</b></font>', st["cell"]),
            Paragraph(str(c["critical"]), st["cell"]), Paragraph(str(c["high"]), st["cell"]),
            Paragraph(str(c["medium"]), st["cell"]), Paragraph(str(c["low"]), st["cell"]),
            Paragraph(esc(r.get("summary", "")), st["cell"]),
        ])
    flow.append(table(rows, [36 * mm, 13 * mm, 10 * mm, 10 * mm, 10 * mm, 10 * mm, 81 * mm], st))
    flow.append(Spacer(1, 6 * mm))

    # Crawl facts
    meta = site.get("meta", {})
    sf = site.get("site_files", {})
    facts = [
        ("Start URL", meta.get("start_url", "")),
        ("Pages crawled", f"{meta.get('pages_crawled', 0)} of {meta.get('urls_discovered', 0)} discovered (limit {meta.get('max_pages')})"),
        ("robots.txt", f"HTTP {sf.get('robots.txt', {}).get('status')}"),
        ("sitemap.xml", f"HTTP {sf.get('sitemap.xml', {}).get('status')}" + (f", {sf['sitemap.xml'].get('url_count', 0)} URLs" if sf.get('sitemap.xml', {}).get('status') == 200 else "")),
        ("llms.txt", f"HTTP {sf.get('llms.txt', {}).get('status')}"),
        ("Broken links found", str(len(site.get("broken_links", [])))),
        ("Structured data types", ", ".join(site.get("site_signals", {}).get("jsonld_types", [])) or "none detected"),
    ]
    ps = site.get("pagespeed", {})
    if isinstance(ps, dict) and "mobile" in ps and "performance_score" in ps.get("mobile", {}):
        m = ps["mobile"]
        facts.append(("PageSpeed (mobile)", f"Performance {round((m.get('performance_score') or 0) * 100)}/100, LCP {m['lab'].get('largest-contentful-paint')}, CLS {m['lab'].get('cumulative-layout-shift')}"))
    flow.append(Paragraph("Crawl facts", st["h2"]))
    flow.append(table([[Paragraph(esc(k), st["cellb"]), Paragraph(esc(v), st["cell"])] for k, v in facts],
                      [40 * mm, 130 * mm], st, header=False, zebra=False))
    flow.append(PageBreak())
    return flow


def action_plan(reports, st, limit=15):
    all_f = [f for r in reports for f in r["findings"] if f["severity"] != "info"]
    all_f.sort(key=lambda f: (-f["priority"], SEVERITY_ORDER.get(f["severity"], 9), f["id"]))
    top = all_f[:limit]
    flow = [Paragraph("Prioritized action plan", st["h1"]),
            Paragraph("Ordered by impact (severity) weighted against implementation effort. "
                      "Start at the top; each item links to a detailed finding with evidence, "
                      "recommendation, and a test to confirm the fix.", st["body"]),
            Spacer(1, 3 * mm)]
    rows = [[Paragraph("#", st["cellb"]), Paragraph("Finding", st["cellb"]), Paragraph("Area", st["cellb"]),
             Paragraph("Severity", st["cellb"]), Paragraph("Effort", st["cellb"]), Paragraph("Ref", st["cellb"])]]
    for i, f in enumerate(top, 1):
        rows.append([
            Paragraph(str(i), st["cell"]),
            Paragraph(esc(f["title"]), st["cell"]),
            Paragraph(esc(f["category"]), st["cell"]),
            sev_chip(f["severity"], st),
            Paragraph(esc(f["effort"].title()), st["cell"]),
            Paragraph(esc(f["id"]), st["mono"]),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No actionable findings.", st["cell"]), "", "", "", "", ""])
    flow.append(table(rows, [8 * mm, 72 * mm, 34 * mm, 20 * mm, 16 * mm, 20 * mm], st))
    flow.append(PageBreak())
    return flow


def finding_block(f, st):
    parts = [
        Paragraph(f'<font color="{SEVERITY_COLOR.get(f["severity"], MUTED).hexval()}">[{esc(f["severity"].upper())}]</font> '
                  f'{esc(f["title"])} <font color="{MUTED.hexval()}" size="8">({esc(f["id"])}, effort: {esc(f["effort"])})</font>', st["h3"]),
    ]
    rows = []
    if f["affected_urls"]:
        urls = f["affected_urls"][:8]
        more = f" (+{len(f['affected_urls']) - 8} more)" if len(f["affected_urls"]) > 8 else ""
        rows.append([Paragraph("Affected", st["label"]), Paragraph("<br/>".join(esc(u) for u in urls) + esc(more), st["mono"])])
    if f["evidence"]:
        rows.append([Paragraph("Evidence", st["label"]), Paragraph(esc(f["evidence"]), st["cell"])])
    if f["recommendation"]:
        rows.append([Paragraph("Fix", st["label"]), Paragraph(esc(f["recommendation"]), st["cell"])])
    if f["how_to_test"]:
        rows.append([Paragraph("Test", st["label"]), Paragraph(esc(f["how_to_test"]), st["cell"])])
    if f.get("also_flagged_by"):
        rows.append([Paragraph("Also by", st["label"]), Paragraph(esc("; ".join(f["also_flagged_by"])), st["small"])])
    src = f.get("source") or {}
    if src.get("url"):
        rows.append([Paragraph("Source", st["label"]),
                     Paragraph(f'<link href="{esc(src["url"])}" color="{ACCENT.hexval()}">{esc(src.get("title") or src["url"])}</link>', st["small"])])
    if rows:
        t = Table(rows, colWidths=[20 * mm, 150 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("LINEBELOW", (0, -1), (-1, -1), 0.25, RULE),
        ]))
        parts.append(t)
    parts.append(Spacer(1, 3 * mm))
    return KeepTogether(parts)


def detailed_findings(reports, st):
    flow = [Paragraph("Detailed findings", st["h1"])]
    for r in reports:
        sc = r.get("score")
        flow.append(Paragraph(
            f'{esc(r["category"])} <font color="{score_color(sc).hexval()}">{sc if sc is not None else ""}</font>', st["h2"]))
        if r.get("summary"):
            flow.append(Paragraph(esc(r["summary"]), st["body"]))
            flow.append(Spacer(1, 2 * mm))
        if not r["findings"]:
            flow.append(Paragraph("No issues found in this area.", st["small"]))
        for f in sorted(r["findings"], key=lambda x: (SEVERITY_ORDER.get(x["severity"], 9), -x["priority"])):
            flow.append(finding_block(f, st))
        flow.append(Spacer(1, 4 * mm))
    return flow


def appendix(site, st):
    flow = [PageBreak(), Paragraph("Appendix: crawled pages", st["h1"])]
    rows = [[Paragraph(h, st["cellb"]) for h in ("URL", "Status", "Title (len)", "Meta desc (len)", "H1", "Words", "ms")]]
    for p in site.get("pages", []):
        rows.append([
            Paragraph(esc(p.get("url", "")), st["mono"]),
            Paragraph(str(p.get("status", "")), st["cell"]),
            Paragraph(f'{esc((p.get("title") or "")[:60])} ({p.get("title_length", 0)})', st["cell"]),
            Paragraph(str(p.get("meta_description_length", 0)), st["cell"]),
            Paragraph(str(p.get("h1_count", "")), st["cell"]),
            Paragraph(str(p.get("word_count", "")), st["cell"]),
            Paragraph(str(p.get("response_ms", "")), st["cell"]),
        ])
    flow.append(table(rows, [62 * mm, 13 * mm, 52 * mm, 16 * mm, 9 * mm, 12 * mm, 10 * mm], st))
    return flow


def build_pdf(site, reports, out_path):
    st = styles()
    generated = datetime.now().strftime("%d %b %Y, %H:%M")
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title=f"SEO Audit - {site.get('meta', {}).get('root', '')}", author="seo-audit-skill")
    doc.report_domain = urlparse(site.get("meta", {}).get("root", "")).netloc
    story = []
    story += cover(site, reports, st, generated)
    story += executive_summary(site, reports, st)
    story += action_plan(reports, st)
    story += detailed_findings(reports, st)
    story += appendix(site, st)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


# ----------------------------------------------------------------------------
# HTML twin (simple, self-contained)
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# "Crawl blocked" report - produced when zero pages could be audited
# ----------------------------------------------------------------------------

NEXT_STEPS = {
    "robots": [
        "If you own this site: allow the auditor in robots.txt (add a 'User-agent: seo-audit-skill' block with 'Allow: /'), "
        "or run the audit from a machine/agent the site already whitelists, then re-run.",
        "If you don't own it: request written permission from the publisher, or use a tool the site explicitly "
        "whitelists (see the list above). The auditor will not bypass robots.txt.",
        "Google Search Console remains available to verified owners and is unaffected by these rules.",
    ],
    "http_forbidden": [
        "The site is likely behind a bot-protection layer (CDN / WAF). If you own it, add an allow rule for the "
        "user agent 'seo-audit-skill' or for your own IP address, then re-run.",
        "Confirm the site loads normally in a browser - if it also fails there, the issue is not bot protection.",
        "If you don't own the site, audit it through Google Search Console or a whitelisted tool instead.",
    ],
    "unreachable": [
        "Check the domain spelling and that the site resolves in a browser.",
        "If it works in a browser but not here, a firewall or DNS filter on this network may be blocking it.",
        "Re-run once the site is reachable.",
    ],
    "no_html": [
        "The URLs fetched did not return HTML (or returned error statuses). Try the exact URL of the homepage.",
        "If the site is a single-page app that renders only in the browser, its HTML shell may still be auditable - "
        "check that the server returns HTML for a plain GET request.",
    ],
    "unknown": ["Re-run with a specific page URL, or inspect site.json in the output folder for details."],
}


def build_blocked_pdf(site, blocked, out_path):
    st = styles()
    meta = site.get("meta", {})
    domain = urlparse(meta.get("root", "")).netloc
    generated = datetime.now().strftime("%d %b %Y, %H:%M")
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title=f"SEO Audit - {meta.get('root', '')} (crawl blocked)", author="seo-audit-skill")
    doc.report_domain = domain
    warn = colors.HexColor("#B54708")
    flow = [
        Spacer(1, 40 * mm),
        Paragraph("SEO Audit Report", st["title"]),
        Paragraph(esc(domain), ParagraphStyle("d", parent=st["subtitle"], fontSize=16, leading=20, textColor=ACCENT)),
        Spacer(1, 4 * mm),
        Paragraph(f"Generated {esc(generated)} &nbsp;|&nbsp; 0 pages crawled", st["subtitle"]),
        Spacer(1, 12 * mm),
        Paragraph(f'<font color="{warn.hexval()}"><b>Audit could not be completed: {esc(blocked.get("title", ""))}</b></font>',
                  ParagraphStyle("w", parent=st["h2"], fontSize=14, leading=18)),
        Paragraph(esc(blocked.get("detail", "")), st["body"]),
        Spacer(1, 6 * mm),
        Paragraph("What was attempted", st["h2"]),
    ]
    attempts = [
        ("Start URL", meta.get("start_url", "")),
        ("robots.txt", f"HTTP {site.get('site_files', {}).get('robots.txt', {}).get('status')}"),
        ("Sitemaps read", str(len(meta.get("sitemaps_read", [])))),
        ("URLs discovered", str(meta.get("urls_discovered", 0))),
        ("URLs skipped for robots.txt", str(len(meta.get("skipped_by_robots", [])))),
        ("Pages fetched", str(meta.get("pages_crawled", 0))),
    ]
    flow.append(table([[Paragraph(esc(k), st["cellb"]), Paragraph(esc(v), st["cell"])] for k, v in attempts],
                      [50 * mm, 120 * mm], st, header=False, zebra=False))
    hv = site.get("host_variants", [])
    if hv:
        flow.append(Spacer(1, 3 * mm))
        rows = [[Paragraph("Host variant", st["cellb"]), Paragraph("Response", st["cellb"])]]
        for h in hv:
            rows.append([Paragraph(esc(h.get("url", "")), st["mono"]),
                         Paragraph(esc(f"HTTP {h.get('status')}" if h.get("status") else (h.get("error") or "no response")[:90]), st["cell"])])
        flow.append(table(rows, [70 * mm, 100 * mm], st))

    flow.append(Paragraph("Evidence", st["h2"]))
    for ev in (blocked.get("evidence") or [])[:6]:
        for line in str(ev).splitlines()[:12]:
            if line.strip() and not re.fullmatch(r"[#=\-\s]+", line):  # skip decorative separator lines
                flow.append(Paragraph(esc(line.strip()), st["mono"]))
        flow.append(Spacer(1, 2 * mm))
    if blocked.get("whitelisted_agents"):
        flow.append(Paragraph("Crawlers this site explicitly allows (from robots.txt)", st["h3"]))
        flow.append(Paragraph(esc(", ".join(blocked["whitelisted_agents"][:30])), st["small"]))

    flow.append(Paragraph("What you can do", st["h2"]))
    for step in NEXT_STEPS.get(blocked.get("reason"), NEXT_STEPS["unknown"]):
        flow.append(Paragraph("&bull; " + esc(step), st["body"]))
    flow.append(Spacer(1, 8 * mm))
    flow.append(Paragraph(
        f'This report was produced by the open-source <link href="{REPO_URL}" color="{ACCENT.hexval()}">'
        f'<b>{REPO_NAME}</b></link> for Claude Code. The auditor respects robots.txt and does not attempt to '
        "bypass access controls; no site content was collected.", st["small"]))
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)


def build_blocked_html(site, blocked, out_path):
    meta = site.get("meta", {})
    domain = urlparse(meta.get("root", "")).netloc
    h = html.escape
    steps = "".join(f"<li>{h(s)}</li>" for s in NEXT_STEPS.get(blocked.get("reason"), NEXT_STEPS["unknown"]))
    evidence = "".join(f"<pre style='background:#F2F4F7;padding:10px;border-radius:6px;white-space:pre-wrap;font-size:12px'>{h(str(e))}</pre>"
                       for e in (blocked.get("evidence") or [])[:6])
    hv = "".join(f"<tr><td><code>{h(x.get('url', ''))}</code></td><td>{h('HTTP ' + str(x.get('status')) if x.get('status') else (x.get('error') or 'no response')[:90])}</td></tr>"
                 for x in site.get("host_variants", []))
    wl = ", ".join(blocked.get("whitelisted_agents", [])[:30])
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SEO Audit - {h(domain)} (crawl blocked)</title>
<style>body{{font:15px/1.5 system-ui,Segoe UI,Helvetica,Arial,sans-serif;color:#101828;max-width:860px;margin:40px auto;padding:0 20px}}
h1{{font-size:28px;margin:0 0 4px}} h2{{font-size:20px;margin:32px 0 10px;border-bottom:1px solid #D0D5DD;padding-bottom:6px}}
.muted{{color:#475467}} .warn{{color:#B54708;font-size:18px;font-weight:700;margin-top:24px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} td{{padding:6px 8px;border-bottom:1px solid #EAECF0;vertical-align:top}}
code{{font-size:12px;background:#F2F4F7;padding:1px 4px;border-radius:3px}}</style></head><body>
<h1>SEO Audit Report</h1><div class="muted">{h(domain)} &middot; {h(datetime.now().strftime('%d %b %Y'))} &middot; 0 pages crawled</div>
<p class="warn">Audit could not be completed: {h(blocked.get('title', ''))}</p><p>{h(blocked.get('detail', ''))}</p>
<h2>What was attempted</h2><table>
<tr><td><b>Start URL</b></td><td>{h(meta.get('start_url', ''))}</td></tr>
<tr><td><b>Sitemaps read</b></td><td>{len(meta.get('sitemaps_read', []))}</td></tr>
<tr><td><b>URLs discovered</b></td><td>{meta.get('urls_discovered', 0)}</td></tr>
<tr><td><b>URLs skipped for robots.txt</b></td><td>{len(meta.get('skipped_by_robots', []))}</td></tr>
{hv}</table>
<h2>Evidence</h2>{evidence}{('<p class="muted"><b>Crawlers this site explicitly allows:</b> ' + h(wl) + '</p>') if wl else ''}
<h2>What you can do</h2><ul>{steps}</ul>
<p class="muted" style="margin-top:40px;font-size:13px">This report was produced by the open-source <a href="{h(REPO_URL)}"><b>{h(REPO_NAME)}</b></a>
for Claude Code. The auditor respects robots.txt and does not attempt to bypass access controls; no site content was collected.</p>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)


def build_html(site, reports, out_path):
    meta = site.get("meta", {})
    domain = urlparse(meta.get("root", "")).netloc
    score = overall_score(reports)
    counts = severity_counts(reports)
    all_f = [f for r in reports for f in r["findings"] if f["severity"] != "info"]
    all_f.sort(key=lambda f: (-f["priority"], SEVERITY_ORDER.get(f["severity"], 9)))
    h = html.escape

    def sev(s):
        return f'<span class="sev sev-{s}">{h(s.upper())}</span>'

    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>SEO Audit - {h(domain)}</title>
<style>
body{{font:15px/1.5 system-ui,Segoe UI,Helvetica,Arial,sans-serif;color:#101828;max-width:960px;margin:40px auto;padding:0 20px}}
h1{{font-size:28px;margin:0 0 4px}} h2{{font-size:20px;margin:36px 0 10px;border-bottom:1px solid #D0D5DD;padding-bottom:6px}}
h3{{font-size:15px;margin:22px 0 6px}} .muted{{color:#475467}} table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid #EAECF0}} th{{background:#F2F4F7}}
.sev{{font-weight:700;font-size:11px;letter-spacing:.04em}} .sev-critical{{color:#B42318}} .sev-high{{color:#C4320A}}
.sev-medium{{color:#B54708}} .sev-low{{color:#175CD3}} .sev-info{{color:#475467}}
.strip{{display:flex;gap:16px;margin:20px 0}} .stat{{padding:14px 18px;background:#F2F4F7;border-radius:8px;min-width:90px;text-align:center}}
.stat b{{display:block;font-size:30px}} .stat small{{color:#475467;font-size:11px}}
dl{{display:grid;grid-template-columns:90px 1fr;gap:4px 12px;font-size:14px;margin:6px 0 0}} dt{{color:#475467;font-weight:600}} dd{{margin:0}}
code{{font-size:12px;background:#F2F4F7;padding:1px 4px;border-radius:3px}}
</style></head><body>
<h1>SEO Audit Report</h1><div class="muted">{h(domain)} &middot; {h(datetime.now().strftime('%d %b %Y'))} &middot; {meta.get('pages_crawled', 0)} pages crawled</div>
<div class="strip"><div class="stat"><b>{score if score is not None else '-'}</b><small>OVERALL / 100</small></div>"""]
    for s in ("critical", "high", "medium", "low"):
        parts.append(f'<div class="stat"><b class="sev-{s}">{counts.get(s, 0)}</b><small>{s.upper()}</small></div>')
    parts.append("</div><h2>Executive summary</h2><table><tr><th>Area</th><th>Score</th><th>Summary</th></tr>")
    for r in reports:
        parts.append(f"<tr><td><b>{h(r['category'])}</b></td><td>{r.get('score', '-')}</td><td>{h(r.get('summary', ''))}</td></tr>")
    parts.append("</table><h2>Prioritized action plan</h2><table><tr><th>#</th><th>Finding</th><th>Area</th><th>Severity</th><th>Effort</th><th>Ref</th></tr>")
    for i, f in enumerate(all_f[:15], 1):
        parts.append(f"<tr><td>{i}</td><td><a href='#{h(f['id'])}'>{h(f['title'])}</a></td><td>{h(f['category'])}</td><td>{sev(f['severity'])}</td><td>{h(f['effort'])}</td><td><code>{h(f['id'])}</code></td></tr>")
    parts.append("</table><h2>Detailed findings</h2>")
    for r in reports:
        parts.append(f"<h2>{h(r['category'])} <span class='muted'>{r.get('score', '')}</span></h2><p>{h(r.get('summary', ''))}</p>")
        for f in sorted(r["findings"], key=lambda x: SEVERITY_ORDER.get(x["severity"], 9)):
            src = f.get("source") or {}
            parts.append(f"<h3 id='{h(f['id'])}'>{sev(f['severity'])} {h(f['title'])} <span class='muted'>({h(f['id'])}, effort: {h(f['effort'])})</span></h3><dl>")
            if f["affected_urls"]:
                parts.append("<dt>Affected</dt><dd>" + "<br>".join(f"<code>{h(u)}</code>" for u in f["affected_urls"][:8]) + "</dd>")
            for k, label in (("evidence", "Evidence"), ("recommendation", "Fix"), ("how_to_test", "Test")):
                if f.get(k):
                    parts.append(f"<dt>{label}</dt><dd>{h(f[k])}</dd>")
            if f.get("also_flagged_by"):
                parts.append(f"<dt>Also by</dt><dd>{h('; '.join(f['also_flagged_by']))}</dd>")
            if src.get("url"):
                parts.append(f"<dt>Source</dt><dd><a href='{h(src['url'])}'>{h(src.get('title') or src['url'])}</a></dd>")
            parts.append("</dl>")
    parts.append(f"<p class='muted' style='margin-top:40px;font-size:13px'>This report was produced by the open-source "
                 f"<a href='{h(REPO_URL)}'><b>{h(REPO_NAME)}</b></a> for Claude Code. Findings are grounded in Google Search Central "
                 f"documentation; every recommendation includes a way to verify the fix. Scores are heuristic and intended for "
                 f"prioritisation, not as a ranking prediction.</p>")
    parts.append("</body></html>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


# ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Render SEO audit findings to PDF (+HTML).")
    ap.add_argument("--site", default=".seo-audit/site.json")
    ap.add_argument("--findings-dir", default=".seo-audit/findings")
    ap.add_argument("--out", help="Output PDF path (default: .seo-audit/seo-audit-<domain>-<date>.pdf)")
    args = ap.parse_args()

    with open(args.site, encoding="utf-8") as f:
        site = json.load(f)

    domain = urlparse(site.get("meta", {}).get("root", "")).netloc.replace("www.", "")
    out = args.out or os.path.join(
        os.path.dirname(args.site) or ".",
        f"seo-audit-{re.sub(r'[^a-z0-9]+', '-', domain.lower())}-{datetime.now().strftime('%Y-%m-%d')}.pdf",
    )
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    # Nothing crawled: produce a short report explaining why, so the user still gets a deliverable.
    blocked = site.get("meta", {}).get("crawl_blocked")
    if blocked or site.get("meta", {}).get("pages_crawled", 0) == 0:
        blocked = blocked or {"reason": "unknown", "title": "No pages could be crawled", "detail": "", "evidence": []}
        build_blocked_pdf(site, blocked, out)
        html_out = os.path.splitext(out)[0] + ".html"
        build_blocked_html(site, blocked, html_out)
        print(json.dumps({"pdf": os.path.abspath(out), "html": os.path.abspath(html_out),
                          "crawl_blocked": blocked["reason"], "blocked_title": blocked["title"],
                          "overall_score": None, "severity_counts": {}, "total_findings": 0}, indent=2))
        return

    reports = load_findings(args.findings_dir)
    if not reports:
        print(f"[render] no findings JSON in {args.findings_dir}", file=sys.stderr)
        sys.exit(1)
    build_pdf(site, reports, out)
    html_out = os.path.splitext(out)[0] + ".html"
    build_html(site, reports, html_out)

    print(json.dumps({
        "pdf": os.path.abspath(out),
        "html": os.path.abspath(html_out),
        "overall_score": overall_score(reports),
        "severity_counts": severity_counts(reports),
        "total_findings": sum(len(r["findings"]) for r in reports),
    }, indent=2))


if __name__ == "__main__":
    main()

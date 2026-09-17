---
name: seo-audit
description: Run a full SEO audit of a website and produce a prioritized PDF report. Crawls the site (no API keys needed), runs specialist agents in parallel (technical SEO, content quality/E-E-A-T, Schema.org, AI search/GEO, and - when relevant - local, e-commerce, international), and renders a PDF with an action plan where every recommendation is testable and cites Google's own documentation. Use when the user asks for an SEO audit, site audit, SEO report, or "how is my site doing in search".
argument-hint: <url> [--max-pages N] [--out DIR] [--all] [--skip agent,agent] [--only agent,agent] [--allow-live]
---

# /seo-audit - website SEO audit → PDF

You are the **orchestrator**. You crawl, delegate analysis to specialist subagents running in
parallel, merge their findings, and render the PDF. You do not do the SEO analysis yourself.

## 1. Parse arguments

`$ARGUMENTS` contains: `<url>` (required) plus optional flags.

| Flag | Default | Meaning |
|---|---|---|
| `--max-pages N` | 25 | Crawl limit. The user may set any number; warn above 200 that it will be slow. |
| `--out DIR` | `./seo-audit-output/<domain>-<YYYY-MM-DD>` | Where site.json, findings/, and the PDF go. |
| `--all` | off | Run all seven agents regardless of detected site type. |
| `--only a,b` | - | Run only these agents (names below). |
| `--skip a,b` | - | Never run these agents. |
| `--allow-live` | off | Let agents fetch the live site for spot checks. Default is crawl-data only (faster, reproducible). |
| `--ignore-robots` | off | Pass through to the crawler. Only for sites the user owns. |

Agent names: `seo-technical`, `seo-content`, `seo-schema`, `seo-geo`, `seo-local`,
`seo-ecommerce`, `seo-international`.

If no URL is given, ask for one. If the URL has no scheme, use `https://`.

## 2. Preflight (Python + dependencies)

Pick the interpreter: try `python3 --version`, then `python --version`, then `py --version`.
Call it `$PY` below. Then check deps:

```bash
$PY -c "import requests, bs4, lxml, reportlab" 2>&1
```

If that fails, install them (tell the user you're doing it):

```bash
$PY -m pip install -r "${CLAUDE_PLUGIN_ROOT}/scripts/requirements.txt"
```

If `PAGESPEED_API_KEY` is set in the environment, Core Web Vitals field data will be
included automatically; mention this in the final summary either way.

## 3. Crawl

```bash
mkdir -p "<OUT>/findings"
$PY "${CLAUDE_PLUGIN_ROOT}/scripts/crawl.py" "<url>" --max-pages <N> --out "<OUT>/site.json" [--ignore-robots]
```

The script prints progress to stderr and a JSON summary to stdout:
`pages_crawled`, `site_signals` (`ecommerce`, `local`, `international` page counts,
`jsonld_types`), `broken_links`. If `pages_crawled` is 0, stop and tell the user why
(look at `site_files.robots.txt` and `host_variants` in site.json - usually the site
blocks bots or the host is wrong).

## 4. Choose which specialists run

Always: `seo-technical`, `seo-content`, `seo-schema`, `seo-geo`.

Conditionally (unless `--all`, `--only`, or `--skip` override):

| Agent | Run when |
|---|---|
| `seo-local` | `site_signals.local >= 1` **or** `jsonld_types` includes `LocalBusiness`/a `*Business` subtype/`PostalAddress` |
| `seo-ecommerce` | `site_signals.ecommerce >= 2` **or** `jsonld_types` includes `Product`/`Offer` |
| `seo-international` | `site_signals.international >= 1` |

Tell the user which agents will run and why in one line before spawning.

## 5. Spawn the specialists **in parallel**

Issue **all Agent tool calls in a single message** so they run concurrently. For each
selected agent use `subagent_type: "seo-audit:<agent-name>"` and this prompt (fill the
placeholders with absolute paths):

```
Audit this crawl for your specialty and write your findings file.

SITE_JSON  = <OUT>/site.json
OUT_JSON   = <OUT>/findings/<agent-name>.json
REFERENCES = ${CLAUDE_PLUGIN_ROOT}/references/google-guidance.md
QUERY      = <$PY> "${CLAUDE_PLUGIN_ROOT}/scripts/query.py"
PYTHON     = <$PY>
LIVE_FETCH = <allowed|not allowed>

Start with `QUERY SITE_JSON overview`, then the views your instructions list.
Follow your output contract exactly and write valid JSON to OUT_JSON with the Write tool.
Reply with only a two-line summary.
```

While they run, do nothing else. Do not summarise their findings yourself.

## 6. Validate

For each agent that ran, confirm `<OUT>/findings/<agent>.json` exists and parses:

```bash
$PY -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); print(d['agent'], d.get('score'), len(d['findings']))" "<OUT>/findings/<agent>.json"
```

If a file is missing or invalid, re-run that one agent once with the same prompt plus
"Your previous attempt did not produce valid JSON at OUT_JSON. Write it now." If it fails
again, continue without it and say so in the summary.

## 7. Render the PDF

```bash
$PY "${CLAUDE_PLUGIN_ROOT}/scripts/render_pdf.py" --site "<OUT>/site.json" --findings-dir "<OUT>/findings"
```

Stdout is JSON with `pdf`, `html`, `overall_score`, `severity_counts`, `total_findings`.

## 8. Report back

Reply with:

1. The PDF path (as a clickable link) and the HTML twin.
2. Overall score and severity counts.
3. The **top 5** items from the action plan (title + severity + effort), read from the
   findings files (highest `severity`, then lowest `effort`).
4. Which agents ran, pages crawled, and whether PageSpeed data was included.
5. One line: "Re-run with `--max-pages`, `--all`, or `--only` to change scope."

Then offer to open the PDF. Keep the whole reply under ~25 lines - the detail lives in the PDF.

## Notes for the orchestrator
- Never edit the findings files by hand; if something looks wrong, re-run the agent.
- The crawler respects robots.txt and waits 0.5 s between requests. Do not parallelise crawls.
- Output directories are safe to delete; nothing is written outside `<OUT>`.
- Scores are heuristic prioritisation aids, not ranking predictions - say so if asked.

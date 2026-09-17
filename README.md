# seo-audit-skill

A [Claude Code](https://claude.com/claude-code) plugin that audits any website and produces a
**prioritized SEO report as a PDF**.

```
/talwar-seo-audit https://example.com
```

- **No API keys required.** The crawler collects everything from the site itself. Set
  `PAGESPEED_API_KEY` (free from Google) and you also get Core Web Vitals field data.
- **Specialist agents run in parallel**: technical SEO, content quality (E-E-A-T),
  Schema.org structured data, AI search (GEO), plus local, e-commerce, and international
  SEO when the site needs them.
- **Every recommendation is testable and sourced.** Each finding has evidence from the crawl,
  a concrete fix, a way to verify the fix, and a link to Google's own documentation
  (or the relevant vendor doc for AI crawlers).
- **PDF + HTML output**, pure-Python rendering (ReportLab) - `pip install` and go, no
  system dependencies.

## Install

Requires Claude Code and Python 3.10+.

```bash
claude plugin marketplace add amantalwar/seo-audit-skill
claude plugin install talwar-seo-audit@talwar-seo-audit-marketplace
```

Python dependencies are installed automatically on first run, or install them yourself:

```bash
pip install -r scripts/requirements.txt
```

### Try it without installing

```bash
git clone https://github.com/amantalwar/seo-audit-skill
claude --plugin-dir ./seo-audit-skill
```

## Usage

```
/talwar-seo-audit <url> [--max-pages N] [--out DIR] [--all] [--only a,b] [--skip a,b] [--allow-live]
```

| Flag | Default | What it does |
|---|---|---|
| `--max-pages N` | 25 | How many pages to crawl (homepage first, then internal links breadth-first). |
| `--out DIR` | `./seo-audit-output/<domain>-<date>` | Output folder for `site.json`, `findings/`, the PDF and HTML. |
| `--all` | off | Run all seven specialists even if the site doesn't look local / e-commerce / international. |
| `--only` / `--skip` | - | Choose specialists explicitly. |
| `--allow-live` | off | Let specialists fetch the live site for spot checks (default: crawl data only). |
| `--no-keys` | off | Skip the prompt about missing optional API keys. |

Examples:

```
/talwar-seo-audit https://example.com
/talwar-seo-audit example.com --max-pages 100 --all
/talwar-seo-audit https://shop.example.com --only seo-ecommerce,seo-schema
```

### Optional API keys

The audit needs no keys. Adding them unlocks extra data, and the skill tells you when one
is missing and how to add it:

| Key | Unlocks | Cost |
|---|---|---|
| `PAGESPEED_API_KEY` | Real-user Core Web Vitals (LCP / INP / CLS) and Lighthouse scores from Google PageSpeed Insights | Free - [get a key](https://developers.google.com/speed/docs/insights/v5/get-started) |

Store a key from your own terminal (input is hidden, saved to `~/.talwar-seo-audit/.env`):

```bash
python scripts/keys.py set PAGESPEED_API_KEY
```

`python scripts/keys.py status` shows what's configured. An environment variable of the
same name also works and takes precedence. Never paste keys into the chat.

## What the report contains

1. **Cover** - overall score, counts of critical / high / medium / low findings.
2. **Executive summary** - one row per specialist with score and a plain-English summary, plus crawl facts.
3. **Prioritized action plan** - top 15 findings ranked by severity weighted against effort.
4. **Detailed findings** - per area: affected URLs, evidence, fix, how to test, source.
5. **Appendix** - every crawled page with status, title/meta lengths, H1 count, word count, response time.

Scores are heuristic prioritisation aids, not ranking predictions.

## How it works

```
/talwar-seo-audit URL
   │
   ├─ scripts/crawl.py ──────────► site.json      (titles, metas, headings, links, JSON-LD,
   │                                               robots.txt, sitemap, llms.txt, hreflang,
   │                                               images, resources, host/https variants…)
   │
   ├─ detects site type ─────────► picks agents   (local? e-commerce? international?)
   │
   ├─ spawns agents in parallel ─► findings/*.json
   │     seo-technical   seo-content   seo-schema   seo-geo
   │     seo-local       seo-ecommerce seo-international
   │
   └─ scripts/render_pdf.py ─────► seo-audit-<domain>-<date>.pdf (+ .html)
```

Agents never read the raw `site.json` into context; they use `scripts/query.py` for compact
views (`overview`, `pages`, `heads`, `jsonld`, `links`, `robots`, `content`, …). Every agent
writes the same findings schema, documented at the top of `scripts/render_pdf.py`.

## Repository layout

```
.claude-plugin/plugin.json      plugin manifest
.claude-plugin/marketplace.json lets people install straight from this repo
skills/talwar-seo-audit/SKILL.md  the /talwar-seo-audit orchestrator
agents/*.md                     the seven specialists (generated from scripts/dev/build_agents.py)
scripts/crawl.py                crawler → site.json
scripts/query.py                compact views of site.json for agents
scripts/render_pdf.py           findings → PDF + HTML
scripts/keys.py                 optional API key manager (status / set / unset)
references/google-guidance.md   the only sources agents may cite (all URLs verified)
```

## Customising your fork

- **Change what's crawled**: edit `parse_page()` in `scripts/crawl.py`. Add a field there,
  expose it in `scripts/query.py`, and agents can use it.
- **Change an agent's checklist**: edit `scripts/dev/build_agents.py` and run it. Editing
  `agents/*.md` directly also works, but the build script keeps the shared contract in sync.
- **Add a specialist**: add an entry to `AGENTS` in `build_agents.py`, run it, and add a
  row to the "Choose which specialists run" table in `skills/talwar-seo-audit/SKILL.md`.
- **Restyle the PDF**: colours, fonts, and section order live in `scripts/render_pdf.py`.
- **Add sources**: append to `references/google-guidance.md`. Keep to primary sources.

## Running the scripts standalone

The Python scripts work without Claude, useful for CI or for building your own front-end:

```bash
python scripts/crawl.py https://example.com --max-pages 25 --out out/site.json
python scripts/query.py out/site.json pages
# ...write out/findings/*.json in the documented schema...
python scripts/render_pdf.py --site out/site.json --findings-dir out/findings
```

## Good citizenship

The crawler identifies itself as `seo-audit-skill`, respects `robots.txt`, and waits 0.5 s
between requests. Only audit sites you own or have permission to audit. `--ignore-robots`
exists for auditing your own staging sites and nothing else.

## Releasing a change

Claude Code's plugin manager only pulls a new version when the version number changes.
After merging changes, bump `version` in **both** `.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json`, then push. Users update with:

```bash
claude plugin marketplace update talwar-seo-audit-marketplace
claude plugin update talwar-seo-audit@talwar-seo-audit-marketplace
```

## Contributing

Issues and pull requests are welcome. Keep findings evidence-based and sourced - a PR that
adds a check should also add the primary source it relies on to `references/google-guidance.md`.

## License

[MIT](LICENSE)

Built by [Aman Talwar](https://amantalwar.com).

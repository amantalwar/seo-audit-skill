# Primary-source SEO guidance

Every finding in an audit **must** cite one of these sources (or another page under the
same official domains). Agents may not cite blogs, SEO tools' marketing pages, or
"industry consensus". If no primary source supports a recommendation, downgrade it to
`info` severity and say so in the evidence.

Official domains: `developers.google.com/search`, `support.google.com`, `web.dev`,
`schema.org`, `bing.com/webmasters`, `developers.openai.com`, `support.claude.com`,
`llmstxt.org`.

## Foundations
| Topic | Source |
|---|---|
| SEO Starter Guide | https://developers.google.com/search/docs/fundamentals/seo-starter-guide |
| Search Essentials (technical requirements, spam policies, key best practices) | https://developers.google.com/search/docs/essentials |
| Spam policies | https://developers.google.com/search/docs/essentials/spam-policies |
| How Search works | https://developers.google.com/search/docs/fundamentals/how-search-works |
| Creating helpful, reliable, people-first content | https://developers.google.com/search/docs/fundamentals/creating-helpful-content |
| E-E-A-T explained (Google blog) | https://developers.google.com/search/blog/2022/12/google-raters-guidelines-e-e-a-t |
| Search Quality Rater Guidelines (PDF) | https://static.googleusercontent.com/media/guidelines.raterhub.com/en//searchqualityevaluatorguidelines.pdf |

## Crawling & indexing (Technical SEO)
| Topic | Source |
|---|---|
| Overview of Google crawlers and user agents | https://developers.google.com/crawling/docs/crawlers-fetchers/overview-google-crawlers |
| robots.txt introduction | https://developers.google.com/search/docs/crawling-indexing/robots/intro |
| How Google interprets robots.txt | https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec |
| robots meta tag and X-Robots-Tag | https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag |
| Sitemaps overview | https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview |
| Build and submit a sitemap | https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap |
| Canonicalization / consolidate duplicate URLs | https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls |
| Redirects and Google Search | https://developers.google.com/search/docs/crawling-indexing/301-redirects |
| HTTP status codes and network errors | https://developers.google.com/crawling/docs/troubleshooting/http-status-codes |
| URL structure best practices | https://developers.google.com/search/docs/crawling-indexing/url-structure |
| Make links crawlable | https://developers.google.com/search/docs/crawling-indexing/links-crawlable |
| Qualify outbound links (rel=nofollow / sponsored / ugc) | https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links |
| JavaScript SEO basics | https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics |
| Mobile-first indexing best practices | https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites-mobile-first-indexing |
| HTTPS as a ranking signal (blog, 2014) | https://developers.google.com/search/blog/2014/08/https-as-ranking-signal |
| Large-site crawl budget management | https://developers.google.com/crawling/docs/crawl-budget |
| Block indexing with noindex | https://developers.google.com/search/docs/crawling-indexing/block-indexing |

## Appearance in results (titles, snippets, images, page experience)
| Topic | Source |
|---|---|
| Title links (title tag) | https://developers.google.com/search/docs/appearance/title-link |
| Snippets & meta descriptions | https://developers.google.com/search/docs/appearance/snippet |
| Site names | https://developers.google.com/search/docs/appearance/site-names |
| Favicons | https://developers.google.com/search/docs/appearance/favicon-in-search |
| Google Images SEO best practices | https://developers.google.com/search/docs/appearance/google-images |
| Page experience in Google Search | https://developers.google.com/search/docs/appearance/page-experience |
| Core Web Vitals and Search results | https://developers.google.com/search/docs/appearance/core-web-vitals |
| Web Vitals (thresholds: LCP 2.5s, INP 200ms, CLS 0.1) | https://web.dev/articles/vitals |
| Optimize LCP | https://web.dev/articles/optimize-lcp |
| Optimize CLS | https://web.dev/articles/optimize-cls |
| Optimize INP | https://web.dev/articles/optimize-inp |
| AI features and your website (AI Overviews / AI Mode) | https://developers.google.com/search/docs/appearance/ai-features |

## Structured data (Schema.org)
| Topic | Source |
|---|---|
| Structured data introduction | https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data |
| General structured data guidelines & policies | https://developers.google.com/search/docs/appearance/structured-data/sd-policies |
| Structured data feature gallery (all supported types) | https://developers.google.com/search/docs/appearance/structured-data/search-gallery |
| Organization | https://developers.google.com/search/docs/appearance/structured-data/organization |
| Article | https://developers.google.com/search/docs/appearance/structured-data/article |
| Breadcrumb | https://developers.google.com/search/docs/appearance/structured-data/breadcrumb |
| FAQ rich results - RETIRED for most sites (Aug 2023); do not recommend FAQPage for rich results | https://developers.google.com/search/updates#removing-faq-rich-result |
| Product | https://developers.google.com/search/docs/appearance/structured-data/product |
| Merchant listing / Product snippets | https://developers.google.com/search/docs/appearance/structured-data/merchant-listing |
| Review snippet | https://developers.google.com/search/docs/appearance/structured-data/review-snippet |
| Local business | https://developers.google.com/search/docs/appearance/structured-data/local-business |
| Video | https://developers.google.com/search/docs/appearance/structured-data/video |
| Retired features list (check before recommending any rich result) | https://developers.google.com/search/updates |
| Rich Results Test (tool) | https://search.google.com/test/rich-results |
| Schema.org validator (tool) | https://validator.schema.org/ |
| Schema.org vocabulary | https://schema.org/docs/schemas.html |

## International SEO
| Topic | Source |
|---|---|
| Localized versions / hreflang | https://developers.google.com/search/docs/specialty/international/localized-versions |
| Managing multi-regional and multilingual sites | https://developers.google.com/search/docs/specialty/international/managing-multi-regional-sites |
| Locale-adaptive pages | https://developers.google.com/search/docs/specialty/international/locale-adaptive-pages |

## E-commerce SEO
| Topic | Source |
|---|---|
| E-commerce SEO overview | https://developers.google.com/search/docs/specialty/ecommerce |
| Share product data with Google | https://developers.google.com/search/docs/specialty/ecommerce/share-your-product-data-with-google |
| Design a URL structure for e-commerce sites | https://developers.google.com/search/docs/specialty/ecommerce/designing-a-url-structure-for-ecommerce-sites |
| Help Google understand your e-commerce site structure | https://developers.google.com/search/docs/specialty/ecommerce/help-google-understand-your-ecommerce-site-structure |
| Pagination, incremental page loading | https://developers.google.com/search/docs/specialty/ecommerce/pagination-and-incremental-page-loading |

## Local SEO
| Topic | Source |
|---|---|
| Google Business Profile guidelines | https://support.google.com/business/answer/3038177 |
| How to improve your local ranking on Google | https://support.google.com/business/answer/7091 |
| Local business structured data | https://developers.google.com/search/docs/appearance/structured-data/local-business |
| Get reviews on Google | https://support.google.com/business/answer/3474122 |

## AI search / GEO (generative engine optimization)
| Topic | Source |
|---|---|
| AI features and your website (Google) | https://developers.google.com/search/docs/appearance/ai-features |
| Google-Extended and other Google crawlers | https://developers.google.com/crawling/docs/crawlers-fetchers/overview-google-crawlers |
| OpenAI crawlers (GPTBot, OAI-SearchBot, ChatGPT-User) | https://developers.openai.com/api/docs/bots |
| Anthropic crawler (ClaudeBot) | https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler |
| llms.txt proposal | https://llmstxt.org/ |
| Bing Webmaster Guidelines (Copilot draws on Bing's index) | https://www.bing.com/webmasters/help/webmaster-guidelines-30fba23a |

## Citing rules for agents
1. Prefer the most specific document (e.g. *Title links* over *SEO Starter Guide*).
2. Put the exact URL in `source.url` and a short human title in `source.title`.
3. Never invent a URL. If unsure, use the section-level overview page listed above.
4. Vendor guidance (llms.txt, OpenAI, Anthropic) is acceptable **only** for the AI search category and must be labelled as vendor guidance in the evidence text.

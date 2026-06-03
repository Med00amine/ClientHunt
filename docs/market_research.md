# Market research: where to find freelance / contract work

Checked: **2026-10-26**. Method: web search plus direct fetch of official pages. Where an official page could
not be fetched (HTTP 403/404, or only third-party summaries were found) the item is marked **UNVERIFIED**.
Nothing below is invented; unverified items must be re-checked on the live site before you rely on them.

## 0. Project status

New standalone project (ClientHunt). `~/Desktop/rag-project` is scaffold only (empty Dockerfile/compose, 3 commits), and no repository for
the churn API or Vocality.ai/Soni2 was found on this machine, so those portfolio entries are marked **unverified** and are never cited in
drafts until you confirm them.

### Hiring-email finding (checked 2026-10-26)
In the current Hacker News "Ask HN: Who is hiring? (October 2026)" thread, 22 of 63 top-level posts matching "python" contained an email
address the company published for applications (for example "To apply, email …"). Remotive, Remote OK and Himalayas listings expose apply
links, not emails. The "Freelancer? Seeking freelancer?" thread (posted monthly by a different account than the main thread) held 21 posts
that month, all "SEEKING WORK", i.e. people looking for work, so it is not a lead source and personal data of freelancers is not collected.

## 1. Source-by-source findings

### Upwork
- Official API: key requested through Upwork (help article *How to request an API key*:
  https://support.upwork.com/hc/en-us/articles/115015857647-How-to-request-an-API-key-from-Upwork).
  Per that article (as surfaced by search, two versions of the criteria were seen): eligibility may require
  **$25,000 lifetime earnings/spend and ≥90% Job Success Score**; the API is stated to be **not available for
  commercial use**; 40,000 requests/day cap; reply within about two weeks. Third-party guides conflict on timing.
- Automation policy: https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly
  (could not be fetched, HTTP 403). The search summary of it says scraping public/private data and spamming proposals
  is off limits even with a key. Treat as **prohibited**.
- Unverified: whether an approved key exposes job *discovery* (search) for your use case. Third-party vendors
  claim the newer API/MCP terms forbid continuously monitoring the job corpus; not confirmed from Upwork's own text.
- **Decision:** no Upwork scraper, no unofficial scraping API. Supported path = Upwork's own **saved searches +
  email notifications**; you paste or upload the alert emails into the **Alert import** screen (links preserved, parsed
  locally). Applications are submitted by you in Upwork. An Upwork adapter is present but reports
  "not configured / not eligible" rather than faking a connection.
- Cost: $0 for alerts. (Upwork charges "Connects" per proposal; price not verified here.)

### Fiverr
- Search found no Fiverr public API for buyer requests or project opportunities, and could not retrieve Fiverr's own
  API terms (https://www.fiverr.com/legal-portal/api-terms-of-use returned 403). **UNVERIFIED.** Fiverr's own blog
  recommends official APIs over scraping (https://block.fiverr.com/resources/guides/programming-tech/ethical-web-scraping).
- Fiverr is primarily a seller-gig marketplace; buyer requests are an in-app feature. No supported programmatic access found.
- **Decision:** no Fiverr scraping, no seller/buyer data collection. Use Fiverr manually for a gig profile; the app can track
  such leads you add by hand (Manual add).

### Freelancer.com
- Official developer portal exists (URL `developers.freelancer.com/docs` returned 404 for me; endpoints below come from
  third-party guides): `GET /api/projects/0.1/projects/active` style endpoints with OAuth / developer client id.
  **UNVERIFIED** (rate limits, terms, whether bidding is restricted).
- **Decision:** adapter slot present, disabled until you supply a token and confirm the docs; not claimed as working.

### PeoplePerHour, Guru, Contra, Wellfound
- Search did not surface their terms or any public job API. **UNVERIFIED.** Assume automated access is not permitted
  (typical for these platforms) and use their native email alerts/saved searches via **Alert import** or manual add.

### Remote job boards with documented public APIs (used)
| Source | Access | Limits / terms (from primary docs) | Notes |
|---|---|---|---|
| **Remotive** https://github.com/remotive-com/remote-jobs-api | `GET https://remotive.com/api/remote-jobs?search=&category=&limit=` no key | Max ~4 fetches/day, >2 req/min blocked; **24-hour delay**; must link back and name Remotive; do not republish to other job boards; do not use to collect emails; paid private API available | Fields: id, url, title, company_name, category, job_type, publication_date, candidate_required_location, salary (optional), description (HTML). Software-dev category is relevant. |
| **Remote OK** https://remoteok.com/api | `GET https://remoteok.com/api` no key | First element is a ToS notice: link back with followed link and credit Remote OK; logo is trademarked (not used) | Fields: id, slug, date, company, position, tags, description, location, salary_min/max, apply_url, url. No search params; filtering done locally. Size/history limits reported by third parties only. |
| **Himalayas** https://himalayas.app/api | `GET /jobs/api/search?q=…` no key; free key gives 60 req/min, 10,000/day | Use `applicationLink` unchanged, visible link to Himalayas, display only in your own app, drop expired jobs, daily data refresh | Has `employmentType`, `locationRestrictions`, `timezoneRestrictions`, salary fields, `expiryDate`; open-check endpoint for re-verifying a job. |
| **Hacker News "Who is hiring?"** (Algolia HN Search API https://hn.algolia.com/api) | `GET https://hn.algolia.com/api/v1/search_by_date?tags=comment,story_<id>` no key | Rate limit is per-hour (exact figure not published in what I fetched, **UNVERIFIED**) | Monthly thread; many comments are companies hiring contractors, often with contact instructions. Free-text comments → treated as untrusted. |
| We Work Remotely RSS | public RSS | Terms not found, **UNVERIFIED** | Not implemented; Alert/manual path only. |

### Procurement
- **TED (EU)**: Search API needs no authentication for published notices
  (https://docs.ted.europa.eu/api/latest/search.html). Software-development tenders are usually large, require
  EU-registered bidders and bureaucracy: poor fit for a solo Tunisia-based engineer in a first-client phase. Not implemented; listed as a later option.

### Direct B2B discovery
- Lawful, low-cost approach: use companies that **already advertise** a need (listings from above) and research their
  *official website* (robots.txt respected, SSRF-safe fetch). The app stores evidence excerpt + URL + timestamp.
- Public search provider: **Brave Search API** — sources disagree: current reports say the free tier was replaced by a
  credit model of $5 per 1,000 requests with about $5 monthly credit and a required card; its docs page still showed an older
  free plan (2,000/month). **UNVERIFIED — check https://api-docs.search.brave.software/pricing.** Disabled by default.
- Agencies that subcontract: found via manual research / their own "partners" or "careers" pages; added through
  **Manual add** with the page URL as source. No automated harvesting of emails.
- Contact data policy: an email on a web page does not authorise cold marketing. Contacts without a source stay `unknown`;
  the app marks `eligible` only for an address the company itself published to receive applications (hiring-post invitation, or a
  careers/jobs mailbox on its own site), everything else is `review_required`, and you can change it. Contacts live in their own table and are never used to
  generate platform proposals. EU/UK/Swiss/other rules differ by country and by recipient type (individual vs. corporate
  subscriber); this app is not legal advice.

### LLM cost (for drafts/research summaries)
- Anthropic pricing page snippet fetched only showed older models; secondary sources list Haiku 4.5 $1/$5, Sonnet 4.6
  $3/$15 per million input/output tokens and an unconfirmed Haiku 5.5 claim ($0.10/$0.50). **UNVERIFIED for the current
  lineup.** The app keeps per-model prices in `.env` (`LLM_PRICE_IN_PER_MTOK`, `LLM_PRICE_OUT_PER_MTOK`), defaults to
  **no LLM** (template drafts, $0), and enforces per-run and monthly caps.
  A typical draft (≈3k in / 600 out tokens) at $3/$15 per MTok ≈ $0.012; at $1/$5 ≈ $0.006. 100 drafts ≈ $0.6–$1.2.

## 2. Recommended source ranking

1. **Upwork saved-search email alerts** (best relevance and volume for your skills; free; compliant; manual apply).
2. **Remotive + Himalayas + Remote OK APIs** (free, documented, automatable; contract/freelance share is small, so filter hard).
3. **HN "Who is hiring"** monthly (free; high-signal startups; contractors sometimes accepted).
4. **Freelancer.com API** (needs token; unverified).
5. **Manual B2B list**: AI/AWS consultancies and agencies you find yourself, researched in-app from their official site.
6. Others (Contra, PeoplePerHour, Guru, Wellfound, Fiverr): native alerts only.

## 3. Monthly cost estimate (your $50–$200 budget)

| Item | Cost |
|---|---|
| Job APIs and alerts above | $0 |
| Hosting locally / Docker | $0 (small VPS, if wanted: roughly $5–$10/month, **price not verified**) |
| LLM drafts (optional) | about $1–$5 at the caps in `.env`; hard cap default $10/month |
| Search provider (optional) | ≈$0–$5 (see Brave caveat) |
| Upwork Connects / platform fees | Not verified; budget separately |
| **Total software** | **$0–$20/month**, leaving most of your budget for platform proposal credits |

## 4. Trade-offs and honest limitations

- Free APIs return few *contract* listings (mostly full-time jobs). Expect low volume; no number of leads or clients is promised.
- The biggest freelance marketplaces do not offer permitted discovery APIs for your situation, so the highest-value flow
  (Upwork) is semi-manual via alerts.
- Remotive's 24-hour delay and its "max 4 fetches/day" rule are enforced in the adapter (cached response reused).
- All attribution requirements (link back, source name) are met by storing and displaying the original URL.

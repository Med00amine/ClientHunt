# ClientHunt

A private workspace for finding companies that need a Python / AI / LLM / RAG / FastAPI / AWS engineer **and
published an email to apply**, ranking them transparently, researching the client from public sources with
evidence, drafting messages you review, and downloading everything as CSV. **It never sends or submits anything for you.**

Research report with sources and costs: [docs/market_research.md](docs/market_research.md) ·
How to use it: [docs/USER_GUIDE.md](docs/USER_GUIDE.md) · Setup, backup, compliance, troubleshooting:
[docs/OPERATIONS.md](docs/OPERATIONS.md)

## Quick start (local, no Docker)

```bash
python3 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
cp .env.example .env            # set APP_PASSWORD and SESSION_SECRET (or run ./scripts/setup.sh)
cd backend && .venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8765        # open http://127.0.0.1:8765
```

## Quick start (Docker, PostgreSQL)

```bash
./scripts/setup.sh              # writes .env with generated secrets and prints the login password
docker compose up -d --build    # http://127.0.0.1:8080  (bound to localhost only)
```

## What it does

| Area | Behaviour |
|---|---|
| **Download everything** | **Runs & exports → ⬇ Download ALL CSVs (ZIP)** gives every opportunities/emails CSV in one file (with a `manifest.csv`); also per run and on the Leads tab. A file changed after export is left out and flagged. |
| **Leads + emails** | The **Leads** tab lists companies hiring now with the email *they* published (in their hiring post, or a careers/contact mailbox on their own website), plus where and when it was found. **⬇ Download all emails (CSV)** is one click; every run also writes its own `emails_*.csv`. Emails are never guessed, never taken from Upwork/Fiverr, and each one is marked `eligible` (company invited applications there) or `review_required`. |
| Easy to reach | A 0–100 heuristic from visible signals: email to apply (+30), contract/freelance wording (+20), open to any location (+15), posted this week (+10), wants someone soon (+10), small team (+5), several openings (+5); minus for "no contractors/agencies" or location/work-authorisation limits. It shows *why*. It is not a hiring prediction. |
| Sources | Remotive, Remote OK, Himalayas, Hacker News "Who is hiring?" via their public APIs; **alert-email import** (Upwork, Contra, PeoplePerHour, Guru, Wellfound…); manual add. Upwork/Freelancer.com API adapters report "not available" instead of faking a connection. |
| Ranking | 0–100 heuristic: skills 35, portfolio relevance 25, budget 15, information quality 10, remote/location 10, freshness 5. Unknown data scores 0 and is listed. Location-restricted listings are capped at 50. Only portfolio items you mark *verified* earn points or get cited. You can override a score or exclude an opportunity. |
| Company intelligence | Fetches the company's own site (SSRF-safe, robots.txt respected). Facts are verbatim excerpts verified against the page, with URL and timestamp; inferences are stored separately as hypotheses and never used in drafts. You approve each fact before it can appear in a proposal. |
| Drafts | Free template drafts (grounded in the listing + verified portfolio + approved facts) or optional LLM drafts with per-run/monthly cost caps. An unsupported-claim checker flags invented years, results, certifications, URLs, compliments and off-platform contact details. Edit → approval resets. Approve ≠ submitted. |
| CSV | Created automatically for every completed/partial run (also with zero rows), timestamped, never overwritten, UTF-8 (BOM for Excel), formula-injection neutralised, SHA-256 recorded and checked on download. Failed runs produce no CSV; failed exports can be retried. |
| Jobs | Runs are DB rows executed by a worker thread: pending/running/completed/partial/failed/cancelled, progress, retries, cancel, restart recovery. |
| Contacts | Separate tables from opportunities. Provenance (source URL, date, snippet), eligibility checks, suppression list and a `forget` command. "Eligible" can only be set with a source and a recorded basis. |

## Tests (actual results, 2026-10-26)

```bash
cd backend && .venv/bin/python -m pytest -q          # 86 passed
cd frontend && npx vitest run                        # 15 passed (loading/error/empty states, CSV panel, Leads)
cd frontend && npx playwright test                   # 1 passed (login → import → leads → emails CSV download → draft → approve → record)
```

Tests use synthetic data and mocked HTTP; no real emails or applications are ever sent.
The live app was also run against the real public APIs; see "Verified" below.

## Verified in the running application

- A real run against Remotive, Remote OK, Himalayas and HN (about 20 s): 47–100 stored opportunities, company research on the
  public websites of top-ranked companies, 3 template drafts, a CSV whose rows, URLs and SHA-256 match the database exactly.
- Docker Compose with PostgreSQL 16: migrations applied, authentication enforced (401 without login), manual add → CSV written.
- Live data exposed 5 defects that were fixed and covered by regression tests: Himalayas time-zone shape, escaped HN URLs,
  country allow-lists scored as worldwide, PLN salary scored as USD, and max-results truncating by arrival order instead of score.

## Limitations (honest list)

- **Emails** are only those a company published itself. In the current Hacker News "Who is hiring?" thread about 1 in 3 matching posts carries one; Remotive, Remote OK and Himalayas listings use apply links, not emails. Website discovery (careers/contact mailboxes) only runs when the company website is known (Hacker News posts, or one you add). An email is checked for *format* only; the app cannot tell you it is deliverable or that the person will answer.
- **Easy to reach** comes from keywords in the post. A post can say "ASAP" and still be slow. Always read the original listing first.
- The Hacker News freelancer thread ("Seeking freelancer?") is not used: this month it only contains people seeking work.
- Free job APIs return few contract/freelance roles; volume is modest and no number of clients is promised.
- Upwork, Fiverr, Freelancer.com, PeoplePerHour, Guru, Contra, Wellfound have **no verified permitted discovery API** for this use
  case; Upwork works through alert emails you paste/upload. There is no IMAP polling yet.
- HN posts are free text; company/location parsing is heuristic. Always open the original link.
- Skill detection is keyword based; fit scores are a reading-order heuristic, not a prediction of winning.
- LLM drafting is implemented and tested with a mocked API only; it has not been run against the live Anthropic API and the
  price defaults in `.env.example` are unverified.
- `RAG project`, `churn API` and `Vocality/Soni2` are marked **unverified** in the portfolio because no working code was found on
  this machine; they earn no points and are never cited until you confirm them (Sources & settings).
- The SSRF guard resolves DNS before fetching; a hostile DNS rebind between check and connect is not fully excluded.
- Single-user, single-worker design. The legal rules for cold email differ by country; the app records provenance and eligibility
  but is not legal advice and does not send email at all.

## Next improvements

IMAP read-only alert polling; Freelancer.com adapter once its docs/terms are verified; Brave/other search provider for
finding official company sites (after verifying current pricing); per-source quotas dashboard; scheduled runs; contact discovery
from official "team/contact" pages with provenance; TED/procurement adapter.

# Operations

## Setup

See README quick starts. Configuration is in `.env` (see `.env.example`). Important values:
`APP_PASSWORD`, `SESSION_SECRET`, `COOKIE_SECURE=true` behind HTTPS, budget limits, optional `ANTHROPIC_API_KEY` with
`LLM_ENABLED=true`. Keys live only in `.env` (git-ignored, mode 600); the UI never shows them and logs contain none.
With no `APP_PASSWORD` the app is open (acceptable only on a single-user machine); Docker Compose refuses to start without it.
Before exposing it on a network put a TLS reverse proxy (Caddy/nginx) in front; Compose binds to 127.0.0.1 only.

## Backups

- SQLite: `./scripts/backup.sh` or `python -m app.cli backup` (online backup into `backups/`), also the *Back up database now* button.
  A backup is made automatically before every contacts import.
- PostgreSQL: `./scripts/backup.sh docker` (pg_dump, gzipped). Restore: `gunzip -c backups/pg_X.sql.gz | docker compose exec -T db psql -U clienthunt clienthunt`.
- Exports are tarred by the same script.

## Data retention and deletion

Contacts are personal data. Keep only what you need. `python -m app.cli forget someone@example.com` deletes the contact row and keeps
a suppression entry so the address cannot become eligible again. Delete old CSVs from `exports/` manually if desired (history rows keep
working; downloads of removed files return 404).

## Compliance notes (not legal advice)

- Emails are collected only from text the company itself published (its hiring post or its own website, robots.txt respected), with the source URL, date and surrounding snippet stored. On company websites only role mailboxes (jobs@, careers@, contact@, info@ …) on the company's own domain are kept, not named staff. Addresses are never guessed or labelled verified.
- `eligible` is a narrow judgement: the company invited applications at that address. Use it only for that purpose. A named person's address in a hiring post is personal data; keep it only as long as you need it (`python -m app.cli forget someone@example.com`).

- Platform proposals stay inside the platform; drafts warn on external contact details/links.
- A public email address is not consent for marketing. Rules differ (e.g. EU/UK distinguish individuals from corporate subscribers;
  other countries differ). Contacts default to `unknown`; "eligible" needs a recorded source and basis.
- Source terms recorded in `docs/market_research.md`; Remotive/Remote OK/Himalayas attribution (link back, name the source) is satisfied
  by storing and showing the original URL and source name. Do not republish their listings elsewhere.
- Retrieved pages, job descriptions and imported files are treated as untrusted data; instructions inside them are never followed
  (the LLM prompt wraps them as untrusted data and drafts are re-checked).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `address already in use` | Another service uses the port (neurogrid uses 8000). Use `--port 8765` or change Compose's `8080`. |
| Page shows "Cannot reach the server" | Backend not running or wrong port; check `uvicorn` terminal / `docker compose logs app`. |
| Source shows `failed` in a run | Read its error on the run card; transient errors are retried 3× with backoff, then reported. Use *Retry run*. |
| Remotive returns the same results | Intentional: cached 6 h to respect its "max 4 fetches/day" rule. |
| `unavailable` source | Needs authorisation or has no permitted API (see Sources & settings). Use Alert import. |
| Run "partial" | At least one source failed/unavailable, or paid drafting hit its budget; details are on the run card. |
| Export failed | Check free disk space/permissions of `exports/`, then *Retry export* (creates a new file). |
| After restart a run says "re-queued" | Expected: interrupted runs are safely re-executed (read-only fetches, idempotent upserts). |
| 401 everywhere | Sign in again (sessions last 12 h) or check `APP_PASSWORD`. |

## Cost estimate (verified vs. unverified)

Free sources and alerts: $0 (verified from their docs, see research report). Template drafts: $0. LLM drafts: roughly $0.006–$0.012
per draft at the commonly reported Haiku/Sonnet-class prices (**unverified**; set real prices in `.env`). Default hard cap $10/month and
$1/run; paid drafting stops and the run reports what remains. Platform costs (e.g. Upwork Connects) were not verified.

## Tests

`cd backend && .venv/bin/python -m pytest -q` · `cd frontend && npx vitest run && npx playwright test`.
The Playwright test starts its own server with a temporary database on port 8791 (needs the Playwright Chromium browser installed).

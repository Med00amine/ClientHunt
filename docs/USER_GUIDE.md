# User guide

## Fastest path: get the emails

1. **Research** tab → saved search **“Easy to reach: hiring now, apply by email”** → **Run Research** (about 10 seconds).
2. **Leads (emails)** tab → click **⬇ Download all emails (CSV)**. Open it in Excel or Google Sheets.
   (Each run card on the Research tab also has its own `emails_…csv` link.)
3. Sort/filter: the list is ordered by *fit for you + easy to reach*; untick “hide US only” to see restricted ones.
4. For each lead read the original listing (“Open ↗”), then write your own message. Click **Details / draft** to get a draft grounded in the listing and your verified portfolio. The app never sends anything.

**All CSVs at once:** *Runs & exports* → **⬇ Download ALL CSVs (ZIP)** (choose “Only emails” or “Only opportunities” if you want). Each run card also has a ZIP of its own two files.

**Email columns:** `business_email, email_type, contact_purpose, outreach_eligibility, eligibility_basis, email_source_url, email_found_at, email_context, listing_title, listing_url, apply_method, hiring_ease_score, hiring_signals, fit_score, company_name, company_website, …`.
`eligible` = the company published that address to receive applications, so use it only to apply or ask about that role. `review_required` = a general mailbox or free-mail address: check before writing. Do not email anyone who has asked not to be contacted (Contacts → Suppress).

## Daily workflow (≈30 minutes)

1. **Open** the app (http://127.0.0.1:8765 locally, http://127.0.0.1:8080 with Docker) and sign in.
2. **Research** tab → choose a saved search (five presets: AI/LLM & RAG, Python & FastAPI, AWS & cloud, workflow automation &
   API integration, agency subcontracting & remote B2B) or "Custom search…" → **Run Research**.
3. **Monitor**: the run card shows status, the source being queried, counters, errors per source and cost. You can Cancel.
4. **Download the CSV**: when the run finishes, its card shows the filename, row count and a download link. The same file is in
   `exports/`. Past files are under **Runs & exports**.
5. **Opportunities** tab → sort by Best fit → click a row. Open **the original listing** first and confirm it is real, open and fits.
   Use *Re-check listing*, *Shortlist*, *Exclude*, or correct the score.
6. **Company intelligence** (if the company is named): add/confirm the official website → *Research company*. Tick *approve* only on
   facts you have confirmed. Hypotheses (orange) are never used in drafts.
7. **Generate proposal draft** → read the rationale and any warnings → edit the text → *Save edit* → *Approve* (tick the warnings box
   if there are any). Remove placeholders such as `[Your name]` and add a concrete, true example of your own work.
8. **Submit it yourself** in the platform (Upwork, etc.), then click *I submitted this on the platform*.
9. **Pipeline** tab: set replied / interview / won / lost and log messages.

## Using Upwork (and other platforms without an API)

On the platform create saved searches with email alerts (e.g. "Python FastAPI RAG", "LLM integration"). Paste the alert email text
(or upload the `.eml`) into **Sources & settings → Alert import**. The links are preserved; each import also produces a CSV. Do not
use scrapers or browser bots on Upwork or Fiverr: it breaches their rules and can get your account banned.

## Portfolio honesty

Sources & settings → *Portfolio evidence*. Only items marked **verified** earn score points and appear in drafts. Check each item,
add its real URL, then click *I confirm this is accurate* and *Rescore all*. Never claim experience, clients, results or certificates
you cannot prove.

## Reading the score

Hover-free explanation is on every opportunity: component bars (skills 35, portfolio 25, budget 15, information 10, remote/location 10,
freshness 5), listed unknowns (scored 0), missing requirements and a cap of 50 for location restrictions. It tells you what to read
first, not whether you will win.

## Contacts

Every contact the app stores has a source link and date. You can add one yourself (Contacts tab) with its source URL. Mark a contact
eligible only after you checked the rules for the recipient's country and type (individual vs. company address). Suppress anyone who
opts out. The app does not send email. “All emails” CSV: Leads tab or Runs & exports.

## CSV columns

`run_id, discovered_at, source_platform, source_type, opportunity_id, title, company_name, company_website, original_url, posted_at,
deadline, engagement_type, remote_status, location_requirements, budget_min, budget_max, currency, rate_type, description,
required_skills, matched_skills, portfolio_evidence, fit_score, fit_explanation, missing_requirements, company_research_summary,
research_sources, contact_name, contact_role, business_email, contact_source_url, contact_verified_status, outreach_eligibility,
recommended_action, proposal_status, application_status, last_verified_at, hiring_ease_score, hiring_signals, apply_method`. Blank means unknown. Text beginning with `= + - @` is
prefixed with `'` so spreadsheets never run it as a formula. Open in Excel or Google Sheets (UTF-8).

"""The written part of the strategy: channels, networks, message shape, follow-up rhythm, spend plan and rules.
Everything that can be counted from the user's own data lives in strategy.py. This file holds the reasoning, and every
fact about an outside organisation carries the page it was read on and the date. Nothing here predicts results."""
from __future__ import annotations

CHECKED = "2026-10-27"     # the day the outside pages below were read; they change, so each entry links to its source

# Follow-up rhythm, in days after the first message. The app uses the same numbers to build the "due today" list.
FOLLOW_UP = {
    "first_after_days": 4, "last_after_days": 10, "close_after_days": 21,
    "text": [
        "Day 4: one short follow-up on the same thread. Add one new useful sentence, not just 'any update?'.",
        "Day 10: one last follow-up that makes it easy to say no ('if this is not a priority, tell me and I will close it').",
        "After that, stop. Mark it lost in Pipeline and move your time to a new lead.",
    ],
}

TIME_PLAN = {
    "label": "A starting split for about 2.5 hours; change it once your own numbers show what pays",
    "steps": [
        {"minutes": 20, "task": "Open Today, pick at most 3 targets. Skip anything restricted to other countries."},
        {"minutes": 75, "task": "Write the 3 messages: read the post or site, approve one fact, edit the draft, send it yourself."},
        {"minutes": 25, "task": "Prospects: research 2 new sites and pitch 1 that is ready."},
        {"minutes": 20, "task": "Follow-ups that are due (a few lines each), then log replies in Pipeline."},
        {"minutes": 10, "task": "Write down what you would change tomorrow."},
    ],
}

WEEK = [
    {"when": "Monday", "task": "Run the Best matches search, read what is new, choose the week's targets."},
    {"when": "Tuesday to Thursday", "task": "Three tailored messages a day, plus the follow-ups that are due."},
    {"when": "Wednesday", "task": "Add five companies or agencies you picked yourself to Prospects, research them, pitch the best one."},
    {"when": "Friday", "task": "Count: messages sent, replies, calls, proposals, wins. Change one thing for next week."},
    {"when": "First weekday of the month",
     "task": "Hacker News posts a new 'Ask HN: Who is hiring?' thread (the October 2026 one is dated 2026-10-01). Run the Hacker News source that day."},
]

MESSAGE = {
    "max_words": 120,
    "parts": [
        {"part": "Subject", "text": "Specific and short: what you can do for them, not who you are."},
        {"part": "First line", "text": "Proof that you read it: quote one line from their post or site that you approved in the app."},
        {"part": "Middle", "text": "What you would do first, concretely, with one link to work you have verified."},
        {"part": "Ask", "text": "One easy question or offer: a one-page outline, or a 20-minute call."},
        {"part": "Close", "text": "Your real name and location. For an unsolicited message add one sentence on how to stop hearing from you."},
    ],
    "never": [
        "Years of experience, results, clients or certifications you cannot prove.",
        "Compliments you do not mean, or familiarity you do not have.",
        "The same text sent to many companies: the draft is built from what you approved for that company.",
        "Guarantees.",
    ],
}

CHANNELS = [
    {"key": "email_leads", "name": "Hiring posts that publish an email", "tab": "Leads", "share": 30,
     "what": "Companies that wrote their own address in a hiring or project post (Hacker News and job boards).",
     "why": "They invited a message and there is no marketplace in between. Each takes about 20 minutes done well.",
     "honest": "Few of these are contract or freelance and open to Tunisia. The numbers in 'What clients ask for' show how many your own data holds.",
     "how": ["Open the listing, read the post, approve one fact from the company's page, edit the draft and send it yourself.",
             "Newest posts first: Find work shows the post date."]},
    {"key": "marketplace", "name": "Small paid projects on marketplaces", "tab": "Live projects", "share": 25,
     "what": "Projects posted on Freelancer.com (Find work → Live projects, never stored) and Upwork (alert emails you import).",
     "why": "The shortest road to a first paid project and a first review.",
     "honest": "Crowded: Live projects shows how many bids a project already has. Choose projects with few bids and a clear scope, and answer their exact question first.",
     "how": ["Filter by minimum budget and maximum bids, open the project, propose a concrete first step.",
             "Keep talking and getting paid inside the platform until a contract exists: Upwork's help center calls moving a client off-platform before a contract circumvention."]},
    {"key": "agencies", "name": "Agencies that may subcontract", "tab": "Prospects", "share": 20,
     "what": "Agencies and consultancies that sell Python, AI or AWS delivery and sometimes need extra hands.",
     "why": "One agency relationship can bring repeat work, and you never have to find the end client.",
     "honest": "Replies are slow and many agencies prefer local partners. A mailbox published on a site is for business enquiries, so the app marks it 'review' unless the site itself invites freelancers.",
     "how": ["Add the agency under Prospects (category Agency), let the app read its site, approve one fact, send the pitch yourself.",
             "Offer extra capacity and one small paid trial task, not a long engagement."]},
    {"key": "networks", "name": "Vetted talent networks", "tab": "Strategy", "share": 10,
     "what": "Networks that screen you once and then match you with clients (list below).",
     "why": "One application can bring several matches, and they handle sales and contracts.",
     "honest": "Selective and slow. A.Team says under 2% of applicants are accepted, Lemon.io lists 1.2%, and Lemon.io asks for 20 hours or more a week, which does not fit 2 to 3 hours a day. Apply to two or three, once, with your strongest verified project.",
     "how": ["Pick the ones whose page states no location limit and whose hours you can meet.",
             "Track each application in Prospects (category Network) so nothing is applied for twice."]},
    {"key": "direct", "name": "Direct pitches to companies with a visible need", "tab": "Prospects", "share": 10,
     "what": "Companies you choose because their own site shows AI, automation, documents or cloud work.",
     "why": "No competing bids: you shape the project and the price.",
     "honest": "The lowest reply rate per message and the strictest rules, because the message is unsolicited. Pitch one small pilot with a defined result.",
     "how": ["Use a specific offer from 'What to offer', quote only what you approved from their site, and include the opt-out line.",
             "Check the rules for the recipient's country before you send."]},
    {"key": "proof", "name": "Public proof", "tab": "Settings", "share": 5,
     "what": "Verified portfolio items, a clear README and a short live demo of your best work.",
     "why": "Every other channel works better when the person you write to can check something in a minute.",
     "honest": "Slow to pay off. The app only cites portfolio items you marked verified, so unverified items weaken every draft.",
     "how": ["Verify only what is true, under Data → Portfolio.", "Keep one demo link in every message."]},
]

# Facts read from each organisation's own page on CHECKED. "quote" is a sentence that appears on that page.
NETWORKS = [
    {"key": "ld_talent", "name": "LD Talent", "category": "network", "url": "https://www.ldtalentwork.com/",
     "how_to_apply": "Email your résumé (PDF or DOC only) to the address their site gives.",
     "email": "info@ldtalentwork.com",
     "quote": "To join LD Talent, please send your resumé (PDF or DOC only) to info@ldtalentwork.com.",
     "location": "The page states no limit on where applicants live.",
     "hours": "Contract talent track half-hour Slack-based work sessions.",
     "bar": "Vetting and training come before you are listed."},
    {"key": "scalable_path", "name": "Scalable Path", "category": "network", "url": "https://www.scalablepath.com/for-freelancers",
     "how_to_apply": "'Apply as a Freelancer': create a profile (about 10 minutes), then a screening interview and a technical interview with live coding.",
     "email": "",
     "quote": "Generally, the vetting process takes between 3-5 days.",
     "location": "The page states no country limit. Roles are matched on your skills and your time zone; you need strong written and spoken English.",
     "hours": "Not stated on the page; clients set the schedule.",
     "bar": "Two interviews, one with a live coding exercise."},
    {"key": "braintrust", "name": "Braintrust", "category": "network", "url": "https://www.usebraintrust.com/for-talent",
     "how_to_apply": "Join the Network: profile (about 20 minutes), AI skills interview, certification with ID verification, then role matching.",
     "email": "",
     "quote": "We never charge talent — no fees, no markups, no surprises.",
     "location": "Roles are described as remote ('Work from anywhere'); the page lists no excluded countries.",
     "hours": "Not stated on the page.",
     "bar": "ID verification and a skills interview are part of onboarding."},
    {"key": "turing", "name": "Turing", "category": "network", "url": "https://www.turing.com/jobs",
     "how_to_apply": "Create a profile at developers.turing.com/signup, then complete skill assessments and live interviews.",
     "email": "",
     "quote": "Complete our skill assessments and live interviews matched to your experience.",
     "location": "'Work from anywhere'; the page lists no countries. Contractors handle their own taxes.",
     "hours": "Not stated on the page.",
     "bar": "Assessments and live interviews; the page gives no pass rate."},
    {"key": "arc", "name": "Arc", "category": "network", "url": "https://arc.dev/talent",
     "how_to_apply": "Create a profile. Freelance vetting is a communication test, then a domain expertise interview.",
     "email": "",
     "quote": "Experts with 5+ years of industry experience and excellent English communication do best in Arc’s vetting.",
     "location": "The page states no limit on where applicants live.",
     "hours": "Not stated on the page.",
     "bar": "Their own page says 5+ years of experience do best."},
    {"key": "a_team", "name": "A.Team", "category": "network", "url": "https://www.a.team/join",
     "how_to_apply": "'Apply to Join': share LinkedIn, portfolio or GitHub, then a short call.",
     "email": "",
     "quote": "Under 2% of applicants are accepted.",
     "location": "No limit on applicants stated; some missions carry location requirements for data security, compliance or tax reasons.",
     "hours": "Not stated on the page.",
     "bar": "Built for experienced builders: lead with your strongest verified project."},
    {"key": "toptal", "name": "Toptal", "category": "network", "url": "https://www.toptal.com/talent/apply",
     "how_to_apply": "Apply on their site (LinkedIn sign-up or a form) and pick the Developer category.",
     "email": "",
     "quote": "an exclusive network of the world's top talent in business, design, marketing, and technology",
     "location": "The page states no location limit, no screening steps and no acceptance rate.",
     "hours": "Not stated on the page.",
     "bar": "Described as exclusive; the page gives no figures."},
]

# Seen on the organisation's own page, and not a fit for the stated time. Shown so you do not spend an hour finding out.
NOT_NOW = [
    {"name": "Lemon.io", "url": "https://lemon.io/for-developers/",
     "reason": "Its page asks for developers who 'can commit 20 hours or more a week'; you have about 10 to 15. It lists a 1.2% acceptance rate."},
]

SPEND_PLAN = {
    "budget": "Your startup budget is $50 to $200. Nothing below needs all of it.",
    "items": [
        {"item": "This app", "cost": "$0",
         "note": "Sources are free and template drafts cost nothing. AI drafting is off unless you switch it on and set a monthly cap."},
        {"item": "A domain and a mailbox on it", "cost": "small, mostly a yearly domain fee (check current prices)",
         "note": "Writing from you@yourname.com looks more professional than a free-mail address and keeps work apart from personal mail."},
        {"item": "A live demo of your best verified project", "cost": "keep it to a few dollars a month",
         "note": "A clickable demo lets a prospect check your work in a minute. Set a cost alert on the cloud account before you deploy."},
        {"item": "Paid bids, contact lists, bulk-email tools", "cost": "$0 for now",
         "note": "Do not buy contact lists or bulk-mail tools: they break the rules this app is built around. Try paid bids only after the free routes have had a few weeks."},
        {"item": "Reserve", "cost": "at least half the budget unspent for the first 4 to 6 weeks",
         "note": "Spend when a result shows where money helps."},
    ],
}

RULES = [
    "Only addresses that a company published itself, with the page and date they came from. Never guessed, never called verified.",
    "You read and send every message. The app never sends, submits or applies for you.",
    "An unsolicited message names who you are, why you write and how to stop. Check the rules of the recipient's country first. Put anyone who opts out on the suppression list.",
    "No scraping of Upwork, Fiverr or LinkedIn, and no way around logins, CAPTCHAs or rate limits.",
    "Cite only portfolio items you verified. No invented clients, results or testimonials.",
    "Keep a marketplace conversation on the marketplace until a contract exists.",
    "Everything fetched from the web is untrusted text: it is shown to you, never obeyed.",
]

WHY_NOT_UPWORK = {
    "asked": "Scrape company names from Upwork and then search for their emails.",
    "answer": "This is not built, on purpose. The legitimate version of the same idea is built instead.",
    "reasons": [
        "Upwork's help center says automated tools that act faster than a person can lead to warnings or bans, and that approved API access is the permitted route.",
        "Upwork's help center treats contact outside Upwork before a contract starts as circumvention of its terms, which risks the account you would use for your best channel.",
        "An address found by searching for a company name was not published as an invitation to be contacted about a project. That is what the app's email rules refuse to treat as one.",
        "Your own brief said not to scrape Upwork or Fiverr profiles or emails and not to bypass logins or rate limits.",
    ],
    "instead": [
        "Import the Upwork alert emails you already receive (Data → Sources), so Upwork projects enter the app through its own notifications.",
        "Find work → Live projects shows Freelancer.com projects through its API without storing them.",
        "Prospects: you name the companies and agencies; the app reads their own public sites and lists the mailboxes they published.",
        "Find work: hiring posts whose company published its own address to receive applications.",
    ],
    "sources": [
        {"title": "Upwork help: use bots and other automation properly",
         "url": "https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly"},
        {"title": "Upwork help: why can't I get paid directly (circumvention)",
         "url": "https://support.upwork.com/hc/en-us/articles/360048105134-Why-Can-t-I-Get-Paid-Directly"},
    ],
    "note": "Upwork blocks automated fetching of these pages, so this summary comes from search results about them. Read the current text yourself before relying on it.",
}

INCOME = {
    "hours_per_day": 2.5, "days_per_month": 20, "billable_share": 0.6,
    "targets": [1000, 3000], "prices": [100, 250, 500, 1000, 2000],
    "note": "Arithmetic on assumptions you can change, not a forecast. At the start, finding clients takes a large part of your hours, so only a share is billable.",
}

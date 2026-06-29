import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import Prospects from "./pages/Prospects";
import Strategy from "./pages/Strategy";
import Pipeline from "./pages/Pipeline";
import OneFile from "./pages/OneFile";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
afterEach(() => vi.restoreAllMocks());
const COUNTS = { runs: 3, opportunities: 12, leads: 5, emails: 9, prospects: 2 };
const META = {
  offers: { rag_assistant: { label: "Question-answering assistant over your own documents (RAG)", audience: "a", deliverable: "A working pilot", first_step: "A 30-minute call" },
            subcontract_capacity: { label: "Extra delivery capacity for an agency or consultancy", audience: "a", deliverable: "Well-scoped tasks", first_step: "One small paid task" } },
  categories: { company: { label: "Company that may need something built", offer: "rag_assistant" }, agency: { label: "Agency or firm that may subcontract", offer: "subcontract_capacity" },
                network: { label: "Network or marketplace to join", offer: "network_application" } },
};

/** Routes by URL substring and optional method; the first matching key wins, so list the specific ones first. */
function serve(table: Record<string, unknown>, fallback: unknown = []) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(((u: any, init?: any) => {
    const url = String(u), method = init?.method ?? "GET";
    const key = Object.keys(table).find((k) => { const [m, frag] = k.includes(" ") ? k.split(" ") : ["GET", k]; return m === method && url.includes(frag); });
    const v = key ? table[key] : fallback;
    return typeof v === "function" ? (v as any)(url, init) : json(v);
  }) as any);
}
const sent = (spy: any, method: string, frag: string) => spy.mock.calls.filter((c: any) => (c[1]?.method ?? "GET") === method && String(c[0]).includes(frag));
const body = (call: any) => JSON.parse(call[1].body);

const mailbox = { id: 1, email: "partners@northwind.example", eligibility: "eligible", purpose: "partner_invited", basis: "The site invites freelancers", source_url: "https://northwind.example/contact", found_at: "2026-10-27T10:00:00Z" };
const general = { id: 2, email: "hello@northwind.example", eligibility: "review_required", purpose: "b2b_mailbox", basis: "Unsolicited: identify yourself", source_url: "https://northwind.example/contact", found_at: "2026-10-27T10:00:00Z" };
const prospect = (over: object = {}) => ({ id: 21, name: "Northwind Docs", website: "https://northwind.example", category: "company", offer: "rag_assistant", offer_label: META.offers.rag_assistant.label,
  evidence_url: "https://directory.example/nw", evidence_quote: "Offers staff augmentation", research_status: "done", need_score: 65, signals: ["Public site mentions AI / machine learning (+20)", "Publishes a role mailbox (+10)"],
  relevance: 40, recommended_action: "Review the evidence, approve one fact, then draft a pitch to the published mailbox", last_verified_at: null, added_at: null, summary: [], contacts: [mailbox, general],
  draft_status: "none", application_status: "none", review_status: "new", ...over });

// ---------------------------------------------------------------- Prospects page
test("prospects: honest empty state, the form and the one-file panel", async () => {
  serve({ "/prospects/meta": META, "/export/all/counts": COUNTS, "/prospects?": { total: 0, items: [] } });
  render(<Prospects openId={null} setOpenId={() => {}} />);
  expect(await screen.findByText(/No prospects yet/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing here is sample data/)).toBeInTheDocument();
  expect(screen.getByLabelText("Websites, one per line")).toBeInTheDocument();
  expect(screen.getByText(/It never sends anything/)).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toBeInTheDocument();
  expect(screen.getByText(/Excel sheets: Summary, Leads, Opportunities, Prospects, Emails, Runs/)).toBeInTheDocument();
});

test("prospects: a row shows signs, mailboxes with where they were found, status, and refuses an unsafe website link", async () => {
  serve({ "/prospects/meta": META, "/export/all/counts": COUNTS, "/prospects?": { total: 2, items: [prospect({ application_status: "submitted" }),
    prospect({ id: 22, name: "Evil Co", website: "javascript:alert(1)", research_status: "failed", contacts: [], need_score: 0, signals: [], offer_label: "" })] } });
  render(<Prospects openId={null} setOpenId={() => {}} />);
  expect(await screen.findByText("Northwind Docs")).toBeInTheDocument();
  expect(screen.getByText("partners@northwind.example")).toBeInTheDocument();
  expect(screen.getByText("hello@northwind.example")).toBeInTheDocument();
  expect(screen.getByText("eligible")).toBeInTheDocument();
  expect(screen.getByText("review required")).toBeInTheDocument();                       // a pitch to a general mailbox stays "review"
  const found = screen.getAllByRole("link", { name: "found here" });
  expect(found[0]).toHaveAttribute("href", "https://northwind.example/contact");
  expect(screen.getByText("contacted")).toBeInTheDocument();
  expect(screen.getByText("could not read it")).toBeInTheDocument();
  expect(screen.getByText("none found")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /alert\(1\)/ })).not.toBeInTheDocument();     // javascript: is plain text, never a link
  expect(screen.getByText(/alert\(1\)/)).toBeInTheDocument();
});

test("prospects: a network shows no 'signs of need' score and its drawer says why", async () => {
  const net = prospect({ id: 41, name: "LD Talent", website: "https://www.ldtalentwork.com", category: "network", offer: "network_application", offer_label: "", need_score: 0, signals: [],
    contacts: [{ ...mailbox, id: 9, email: "info@ldtalentwork.com", source_url: "https://www.ldtalentwork.com/" }] });
  serve({ "/opportunities/41": detail({ id: 41, title: "LD Talent" }), "/prospects/meta": META, "/export/all/counts": COUNTS, "/prospects": { total: 1, items: [net] } });
  render(<Prospects openId={41} setOpenId={() => {}} />);
  const dlg = await screen.findByRole("dialog", { name: "Prospect detail" });
  expect(await within(dlg).findByText(/A network is not scored: it does not need work done/)).toBeInTheDocument();
  expect(within(dlg).queryByText(/Public signs they may need this/)).not.toBeInTheDocument();
  const row = screen.getAllByRole("row").find((r) => r.textContent?.includes("LD Talent"))!;
  expect(within(row).getAllByRole("cell")[0]).toHaveTextContent("—");                      // no number in the "signs of need" column
});

test("prospects: adding sends the lines with the chosen kind, reports what was refused and keeps only those lines", async () => {
  const spy = serve({ "/prospects/meta": META, "/export/all/counts": COUNTS, "POST /prospects": { created: [prospect()], errors: [{ website: "http://localhost", error: "Private or local addresses are not allowed" }] },
    "/prospects?": { total: 0, items: [] } });
  render(<Prospects openId={null} setOpenId={() => {}} />);
  await screen.findByText(/No prospects yet/);
  fireEvent.change(screen.getByLabelText("Websites, one per line"), { target: { value: "northwind.example\n\nhttp://localhost\n" } });
  fireEvent.change(screen.getByLabelText("What are they?"), { target: { value: "agency" } });
  fireEvent.change(screen.getByLabelText(/Where did you see/), { target: { value: "https://directory.example/nw" } });
  fireEvent.change(screen.getByLabelText(/What it said/), { target: { value: "Offers staff augmentation" } });
  fireEvent.click(screen.getByRole("button", { name: "Add prospects" }));
  expect(await screen.findByText(/Added or updated 1\./)).toBeInTheDocument();
  expect(screen.getByText(/Not added: http:\/\/localhost: Private or local addresses are not allowed/)).toBeInTheDocument();
  const b = body(sent(spy, "POST", "/prospects")[0]);
  expect(b.research).toBe(true);
  expect(b.items).toEqual([
    { website: "northwind.example", category: "agency", offer: "", evidence_url: "https://directory.example/nw", evidence_quote: "Offers staff augmentation" },
    { website: "http://localhost", category: "agency", offer: "", evidence_url: "https://directory.example/nw", evidence_quote: "Offers staff augmentation" }]);
  expect((screen.getByLabelText("Websites, one per line") as HTMLTextAreaElement).value).toBe("http://localhost");   // only the refused line is left to fix
});

test("prospects: an empty submission is refused without calling the server", async () => {
  const spy = serve({ "/prospects/meta": META, "/export/all/counts": COUNTS, "/prospects?": { total: 0, items: [] } });
  render(<Prospects openId={null} setOpenId={() => {}} />);
  await screen.findByText(/No prospects yet/);
  fireEvent.click(screen.getByRole("button", { name: "Add prospects" }));
  expect(await screen.findByText(/Paste at least one website/)).toBeInTheDocument();
  expect(sent(spy, "POST", "/prospects")).toHaveLength(0);
});

test("prospects: filters are sent to the server", async () => {
  const spy = serve({ "/prospects/meta": META, "/export/all/counts": COUNTS, "/prospects?": { total: 0, items: [] } });
  render(<Prospects openId={null} setOpenId={() => {}} />);
  await screen.findByText(/No prospects yet/);
  fireEvent.change(screen.getByLabelText("category filter"), { target: { value: "agency" } });
  fireEvent.click(screen.getByLabelText(/only with a published mailbox/));
  await waitFor(() => expect(spy.mock.calls.some((c) => String(c[0]).includes("category=agency&only_with_mailbox=true"))).toBe(true));
});

const detail = (over: object = {}) => ({ id: 21, title: "Northwind Docs", url: "https://northwind.example", source: "prospect", company: { id: 1, name: "Northwind Docs", website: "https://northwind.example", description: "We automate invoices.", research_status: "done", last_error: "" },
  evidence: [{ id: 51, kind: "fact", claim: "Page title: Northwind", excerpt: "Northwind Docs – paperwork automation", source_url: "https://northwind.example/", retrieved_at: "2026-10-27T10:00:00Z", confidence: "high", approved: false },
             { id: 52, kind: "hypothesis", claim: "Hypothesis (unverified inference): maybe", excerpt: "", source_url: "https://northwind.example/", retrieved_at: "2026-10-27T10:00:00Z", confidence: "low", approved: false }],
  drafts: [], application: null, contacts: [], history: [], ...over });
const draft = (over: object = {}) => ({ id: 31, version: 1, body: "Hello,\n\nI build things.", status: "draft", generator: "template", est_cost_usd: 0, rationale: "Built from the offer", warnings: ["Replace the placeholders"], portfolio_ids: ["neurogrid"], evidence_ids: [], ...over });

test("prospect drawer: why it is on the list, signs, mailboxes with their basis, evidence approval and a pitch that says 'I sent this myself'", async () => {
  const spy = serve({ "POST /evidence/51": { ok: true }, "POST /opportunities/21/drafts": draft(), "POST /opportunities/21/applications": { id: 1 },
    "/opportunities/21": detail({ drafts: [draft({ status: "approved", warnings: [] })] }), "/prospects/meta": META, "/export/all/counts": COUNTS,
    "/prospects": { total: 1, items: [prospect()] } });
  render(<Prospects openId={21} setOpenId={() => {}} />);
  const dlg = await screen.findByRole("dialog", { name: "Prospect detail" });
  expect(await within(dlg).findByText(/“Offers staff augmentation”/)).toBeInTheDocument();
  expect(within(dlg).getByText(/Public signs they may need this: 65 \/ 100/)).toBeInTheDocument();
  expect(within(dlg).getByText(/Public site mentions AI/)).toBeInTheDocument();
  expect(within(dlg).getByText("The site invites freelancers")).toBeInTheDocument();
  expect(within(dlg).getByText("Unsolicited: identify yourself")).toBeInTheDocument();
  expect(within(dlg).getByText(/Hypothesis \(not a fact, never used in drafts\)/)).toBeInTheDocument();
  fireEvent.click(within(dlg).getByLabelText(/approve for use in proposals/));
  await waitFor(() => expect(sent(spy, "POST", "/evidence/51")).toHaveLength(1));
  expect(body(sent(spy, "POST", "/evidence/51")[0])).toEqual({ approved: true });
  fireEvent.click(within(dlg).getByRole("button", { name: "I sent this myself" }));
  await waitFor(() => expect(sent(spy, "POST", "/opportunities/21/applications")).toHaveLength(1));
  expect(body(sent(spy, "POST", "/opportunities/21/applications")[0])).toEqual({ draft_id: 31 });
  expect(within(dlg).queryByText(/on the platform/)).not.toBeInTheDocument();             // prospect wording, not marketplace wording
});

test("prospect drawer: changing the offer patches it; read-again and a refused removal keep the drawer open", async () => {
  const closes: any[] = [];
  const spy = serve({ "PATCH /prospects/21": prospect(), "POST /prospects/21/research": prospect({ research_status: "researching" }),
    "DELETE /prospects/21": () => json({ detail: "An application is recorded for this prospect; it cannot be removed" }, 409),
    "/opportunities/21": detail(), "/prospects/meta": META, "/export/all/counts": COUNTS, "/prospects": { total: 1, items: [prospect()] } });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<Prospects openId={21} setOpenId={(v) => closes.push(v)} />);
  const dlg = await screen.findByRole("dialog", { name: "Prospect detail" });
  await within(dlg).findByText(/Public signs/);
  fireEvent.change(within(dlg).getByLabelText("offer"), { target: { value: "subcontract_capacity" } });
  await waitFor(() => expect(sent(spy, "PATCH", "/prospects/21")).toHaveLength(1));
  expect(body(sent(spy, "PATCH", "/prospects/21")[0])).toEqual({ offer: "subcontract_capacity" });
  fireEvent.click(within(dlg).getByRole("button", { name: "Read the site again" }));
  await waitFor(() => expect(sent(spy, "POST", "/prospects/21/research")).toHaveLength(1));
  fireEvent.click(within(dlg).getByRole("button", { name: "Remove" }));
  expect(await within(dlg).findByText(/cannot be removed/)).toBeInTheDocument();
  expect(closes).toEqual([]);                                                             // a refused removal must not close the drawer
});

// ---------------------------------------------------------------- Strategy page
const leadItem = (over: object = {}) => ({ id: 5, title: "Contract Python engineer", company: "Acme", source: "hn_hiring", url: "https://news.ycombinator.com/item?id=5", fit: 72, ease: 55,
  engagement: "contract", location_check: "worldwide", posted_at: "2026-10-26T10:00:00Z", has_draft: true, proposal_status: "draft",
  emails: [{ email: "jobs@acme.example", eligibility: "eligible", source_url: "https://news.ycombinator.com/item?id=5" }], ...over });
const STRATEGY = (over: any = {}) => ({
  generated_at: "2026-10-27T12:00:00Z", checked: "2026-10-27",
  today: {
    apply_by_email: { total: 7, items: [leadItem()] },
    apply_by_link: { total: 1, items: [leadItem({ id: 6, title: "Freelance FastAPI developer", company: "Beta", source: "himalayas", emails: [], has_draft: false })] },
    follow_ups: { total: 2, waiting: 3, items: [
      { application_id: 9, opportunity_id: 5, title: "Contract Python engineer", company: "Acme", days: 5, stage: "first", kind: "application" },
      { application_id: 10, opportunity_id: 21, title: "Northwind Docs", company: "Northwind Docs", days: 25, stage: "close", kind: "pitch" }] },
    prospects: { total: 2, contacted: 0, to_research: { total: 1, items: [{ id: 30, name: "New Agency", website: "https://new.example", category: "agency", offer: "x", need_score: 0, mailboxes: 0, status: "not_started", next: "" }] },
      ready: { total: 1, items: [{ id: 21, name: "Northwind Docs", website: "https://northwind.example", category: "company", offer: "x", need_score: 65, mailboxes: 2, status: "done", next: "" }] } },
    portfolio: { verified: 1, unverified: [{ id: "rag-project", title: "RAG project", note: "Confirm what actually works before enabling." }] },
    time_plan: { label: "A starting split for about 2.5 hours", steps: [{ minutes: 20, task: "Open Today, pick at most 3 targets." }, { minutes: 75, task: "Write the 3 messages." }] },
  },
  market: { fitting_listings: 148, engagement: { unknown: 127, contract: 21 },
    skills: [{ skill: "python", count: 101, share_percent: 68, verified_evidence: true }, { skill: "aws", count: 60, share_percent: 41, verified_evidence: false }, { skill: "machine learning", count: 60, share_percent: 41, verified_evidence: false }],
    sources: [{ source: "hn_hiring", fitting: 40, contract_or_freelance: 4, with_email: 5 }],
    hourly: { n: 6, median_usd: null, min_usd: null, max_usd: null, note: "Only 6 stored listings state an hourly rate in USD. That is too few to say what the market pays, so no figure is shown." } },
  funnel: { messages_sent: 0, pitches: 0, replies: 0, won: 0, reply_rate_percent: null, win_rate_percent: null, note: "Rates are shown once you have logged at least 10 messages; with fewer, a percentage would only look precise." },
  offers: [{ key: "document_extraction", label: "Document processing: turn PDFs and forms into structured data", audience: "Companies that re-type invoices", deliverable: "A pipeline for one document type", first_step: "Send me 20 sample documents", core_skill: "document processing", ready: true, backed_by: ["Client Acquisition Studio (neurogrid)"] },
           { key: "rag_assistant", label: "Question-answering assistant over your own documents (RAG)", audience: "Teams with PDFs", deliverable: "A working pilot", first_step: "A 30-minute call", core_skill: "rag", ready: false, backed_by: [] }],
  income: { assumptions: { hours_per_day: 2.5, days_per_month: 20, billable_share: 0.6 }, hours_per_month: 50, billable_hours: 30, note: "Arithmetic on assumptions you can change, not a forecast.",
    rows: [{ target: 1000, hourly_needed: 33, projects: [{ price: 100, count: 10 }, { price: 500, count: 2 }] }, { target: 3000, hourly_needed: 100, projects: [{ price: 100, count: 30 }, { price: 500, count: 6 }] }] },
  channels: [{ key: "email_leads", name: "Hiring posts that publish an email", tab: "Leads", share: 30, what: "Companies that wrote their own address.", why: "They invited a message.", honest: "Few are contract.", how: ["Open the lead."] }],
  networks: [{ key: "ld_talent", name: "LD Talent", category: "network", url: "https://www.ldtalentwork.com/", how_to_apply: "Email your résumé.", email: "info@ldtalentwork.com",
    quote: "To join LD Talent, please send your resumé (PDF or DOC only) to info@ldtalentwork.com.", location: "No limit stated.", hours: "Slack-based sessions.", bar: "Vetting comes first." },
    { key: "turing", name: "Turing", category: "network", url: "https://www.turing.com/jobs", how_to_apply: "Create a profile.", email: "", quote: "Complete our skill assessments and live interviews matched to your experience.", location: "Work from anywhere.", hours: "Not stated.", bar: "Assessments." }],
  not_now: [{ name: "Lemon.io", url: "https://lemon.io/for-developers/", reason: "Asks for 20 hours or more a week." }],
  message: { max_words: 120, parts: [{ part: "Subject", text: "Specific and short." }], never: ["Guarantees."] },
  follow_up: { first_after_days: 4, last_after_days: 10, close_after_days: 21, text: ["Day 4: one short follow-up."] },
  week: [{ when: "Friday", task: "Count what happened." }],
  spend_plan: { budget: "Your startup budget is $50 to $200. Nothing below needs all of it.", items: [{ item: "This app", cost: "$0", note: "Sources are free." }] },
  rules: ["You read and send every message."],
  why_not_upwork: { asked: "Scrape company names from Upwork and then search for their emails.", answer: "This is not built, on purpose.", reasons: ["Upwork's help center says automated tools can lead to bans."], instead: ["Import the Upwork alert emails you receive."],
    sources: [{ title: "Upwork help: use bots and other automation properly", url: "https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly" }], note: "Read the current text yourself." },
  ...over });

function strategyServer(extra: Record<string, unknown> = {}, strategy: any = STRATEGY()) {
  return serve({ "/strategy": strategy, "/prospects": { total: 0, items: [] }, ...extra });
}

test("strategy: today lists the leads with their published email and source, flags drafts and counts the rest", async () => {
  strategyServer();
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText("jobs@acme.example")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "where it was published" })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(screen.getByText("draft ready")).toBeInTheDocument();
  expect(screen.getByText("6 more in the Leads tab.")).toBeInTheDocument();
  expect(screen.getByText("Freelance FastAPI developer", { exact: false })).toBeInTheDocument();
  expect(screen.getByText(/Counts come from your own database/)).toBeInTheDocument();
  expect(screen.getByText(/each links to its page/)).toBeInTheDocument();
});

test("strategy: opening a lead or a prospect goes to the right tab with its id", async () => {
  strategyServer();
  const go = vi.fn();
  render(<Strategy go={go} />);
  fireEvent.click((await screen.findAllByRole("button", { name: "Details / draft" }))[0]);
  expect(go).toHaveBeenCalledWith("Opportunities", 5);
  const ready = screen.getByText("Ready to pitch (1)").closest(".panel") as HTMLElement;
  fireEvent.click(within(ready).getByRole("button", { name: "Open" }));
  expect(go).toHaveBeenCalledWith("Prospects", 21);
});

test("strategy: follow-ups log your own message or close the thread, and say when to stop", async () => {
  const spy = strategyServer({ "POST /applications/9/conversations": { id: 9 }, "PATCH /applications/10": { id: 10 } });
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText("Day 4 or later: send one short follow-up.")).toBeInTheDocument();
  expect(screen.getByText(/No answer after two follow-ups, or 21 days: close it and move on\./)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "I sent the follow-up" }));
  await waitFor(() => expect(sent(spy, "POST", "/applications/9/conversations")).toHaveLength(1));
  expect(body(sent(spy, "POST", "/applications/9/conversations")[0])).toEqual({ direction: "out", summary: "Follow-up sent" });
  expect(screen.getAllByRole("button", { name: "I sent the follow-up" })).toHaveLength(1);        // a thread to close has no 'I followed up' button
  fireEvent.click(screen.getAllByRole("button", { name: "Close it (no reply)" })[1]);
  await waitFor(() => expect(sent(spy, "PATCH", "/applications/10")).toHaveLength(1));
  expect(body(sent(spy, "PATCH", "/applications/10")[0])).toEqual({ status: "lost" });
});

test("strategy: market shows gaps without verified evidence and refuses to invent an hourly rate", async () => {
  strategyServer();
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText(/Most asked for with no verified example of yours:/)).toHaveTextContent("aws (41%), machine learning (41%)");
  expect(screen.getAllByText("no verified work shows it")).toHaveLength(2);
  expect(screen.getByText("your verified work shows it")).toBeInTheDocument();
  expect(screen.getByText(/That is too few to say what the market pays/)).toBeInTheDocument();
  expect(screen.queryByText(/Median \$/)).not.toBeInTheDocument();
  expect(screen.getByText(/127 do not say whether it is contract or employment, 21 contract/)).toBeInTheDocument();
});

test("strategy: an hourly median appears only when the server sends one", async () => {
  strategyServer({}, STRATEGY({ market: { ...STRATEGY().market, hourly: { n: 12, median_usd: 42.5, min_usd: 20, max_usd: 90, note: "Median of the midpoints of 12 listings." } } }));
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText(/Median \$42.5\/hour \(range \$20 to \$90\)/)).toBeInTheDocument();
});

test("strategy: offers are 'ready' only with verified work behind them", async () => {
  strategyServer();
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText("ready: Client Acquisition Studio (neurogrid)")).toBeInTheDocument();
  expect(screen.getByText("add a verified rag example first")).toBeInTheDocument();
});

test("strategy: networks quote their own page, link to it, and can be tracked as prospects with that quote", async () => {
  const spy = strategyServer({ "POST /prospects": { created: [{ id: 99 }], errors: [] } });
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText(/“To join LD Talent, please send your resumé/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /LD Talent ↗/ })).toHaveAttribute("href", "https://www.ldtalentwork.com/");
  expect(screen.getByText("info@ldtalentwork.com", { selector: "b" })).toBeInTheDocument();
  expect(screen.getByText(/Not a fit right now:/)).toHaveTextContent("Lemon.io");
  fireEvent.click(screen.getAllByRole("button", { name: "Track in Prospects" })[0]);
  expect(await screen.findByText(/LD Talent is in Prospects/)).toBeInTheDocument();
  expect(body(sent(spy, "POST", "/prospects")[0])).toEqual({ research: true, items: [{ website: "https://www.ldtalentwork.com/", name: "LD Talent", category: "network",
    evidence_url: "https://www.ldtalentwork.com/", evidence_quote: "To join LD Talent, please send your resumé (PDF or DOC only) to info@ldtalentwork.com." }] });
});

test("strategy: a network already in Prospects shows 'Tracked' and opens it", async () => {
  const go = vi.fn();
  strategyServer({ "/prospects": { total: 1, items: [prospect({ id: 77, name: "LD Talent", website: "https://ldtalentwork.com", category: "network" })] } });
  render(<Strategy go={go} />);
  const tracked = await screen.findByRole("button", { name: "Tracked" });
  fireEvent.click(tracked);
  expect(go).toHaveBeenCalledWith("Prospects", 77);
  expect(screen.getAllByRole("button", { name: "Track in Prospects" })).toHaveLength(1);            // only the other network can still be added
});

test("strategy: says why there is no Upwork scraper and links the sources", async () => {
  strategyServer();
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText("Why there is no Upwork scraper")).toBeInTheDocument();
  expect(screen.getByText(/This is not built, on purpose\./)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Upwork help: use bots and other automation properly/ })).toHaveAttribute("href", expect.stringContaining("support.upwork.com"));
  expect(screen.getByText("Import the Upwork alert emails you receive.")).toBeInTheDocument();
});

test("strategy: the income calculator recomputes from the assumptions you type", async () => {
  strategyServer();
  render(<Strategy go={() => {}} />);
  await screen.findByText("Income arithmetic");
  expect(screen.getByText("$33/h")).toBeInTheDocument();                                           // 2.5 h x 20 days x 0.6 = 30 billable hours
  fireEvent.change(screen.getByLabelText("billable share"), { target: { value: "0.5" } });         // 25 billable hours
  expect(screen.getByText("$40/h")).toBeInTheDocument();
  expect(screen.getByText("$120/h")).toBeInTheDocument();
  expect(screen.getByText(/not a forecast/)).toBeInTheDocument();
});

test("strategy: with nothing stored it says so instead of showing sample data", async () => {
  const empty = STRATEGY({
    today: { ...STRATEGY().today, apply_by_email: { total: 0, items: [] }, apply_by_link: { total: 0, items: [] }, follow_ups: { total: 0, waiting: 0, items: [] },
      prospects: { total: 0, contacted: 0, to_research: { total: 0, items: [] }, ready: { total: 0, items: [] } }, portfolio: { verified: 1, unverified: [] } },
    market: { fitting_listings: 0, engagement: {}, skills: [], sources: [], hourly: STRATEGY().market.hourly } });
  strategyServer({}, empty);
  render(<Strategy go={() => {}} />);
  expect(await screen.findByText(/No open lead with a published email fits you right now/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing is due\. Log what you send in the Pipeline tab/)).toBeInTheDocument();
  expect(screen.getByText(/No stored listing fits you yet/)).toBeInTheDocument();
  expect(screen.getByText("Every portfolio item is verified.")).toBeInTheDocument();
  expect(screen.queryByText("jobs@acme.example")).not.toBeInTheDocument();
});

test("strategy: a server error is shown with a retry", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ detail: "boom" }, 500));
  render(<Strategy go={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

// ---------------------------------------------------------------- Pipeline: your own follow-ups
test("pipeline: you can log your own follow-up as well as their reply, and a pitch opens as a prospect", async () => {
  const app = { id: 4, opportunity_id: 21, draft_id: 31, status: "submitted", submitted_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-20T10:00:00Z", notes: "", title: "Northwind Docs",
    company_name: "Northwind GmbH", url: "https://northwind.example", source: "prospect", conversations: [{ id: 1, direction: "out", at: "2026-10-24T10:00:00Z", summary: "Follow-up sent" }, { id: 2, direction: "in", at: "2026-10-25T10:00:00Z", summary: "Thanks, tell me more" }] };
  const spy = serve({ "POST /applications/4/conversations": app, "/applications": [app] });
  const open = vi.fn();
  render(<Pipeline openOpp={open} />);
  expect(await screen.findByText("Northwind Docs")).toBeInTheDocument();
  expect(screen.getByText(/I wrote: Follow-up sent/)).toBeInTheDocument();
  expect(screen.getByText(/they wrote: Thanks, tell me more/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "their website" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("note type"), { target: { value: "out" } });
  fireEvent.change(screen.getByPlaceholderText("Log what was said"), { target: { value: "Second follow-up" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(sent(spy, "POST", "/applications/4/conversations")).toHaveLength(1));
  expect(body(sent(spy, "POST", "/applications/4/conversations")[0])).toEqual({ direction: "out", summary: "Second follow-up" });
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
  expect(open).toHaveBeenCalledWith(21, true);
});

test("one-file panel: prospects alone enable the Excel download, but not the flat CSV of opportunities", async () => {
  serve({ "/export/all/counts": { runs: 0, opportunities: 0, leads: 0, emails: 0, prospects: 3 } });
  render(<OneFile />);
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toHaveAttribute("href", "/api/export/all?format=xlsx");
  expect(screen.queryByRole("link", { name: /or as one CSV/ })).not.toBeInTheDocument();
  expect(screen.getByText(/3 prospects/)).toBeInTheDocument();
});

test("one-file panel: with nothing at all it says what to do", async () => {
  serve({ "/export/all/counts": { runs: 0, opportunities: 0, leads: 0, emails: 0, prospects: 0 } });
  render(<OneFile />);
  expect(await screen.findByText(/Nothing to download yet\. Run a research or add a prospect first\./)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Download ALL runs in ONE file/ })).toBeDisabled();
});

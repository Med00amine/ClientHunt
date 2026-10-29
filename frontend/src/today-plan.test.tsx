import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import App from "./App";
import Today from "./pages/Today";
import Plan from "./pages/Plan";
import Find from "./pages/Find";
import { COUNTS, body, json, renderApp, sent, serve } from "./testing";

afterEach(() => vi.restoreAllMocks());

const overview = (over: object = {}) => ({ opportunities_total: 10, prospects: 1, applications_submitted: 0, replies: 0, won: 0, auth_enabled: true, ...over });
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
const EMPTY_TODAY = () => STRATEGY({
  today: { ...STRATEGY().today, apply_by_email: { total: 0, items: [] }, apply_by_link: { total: 0, items: [] }, follow_ups: { total: 0, waiting: 0, items: [] },
    prospects: { total: 0, contacted: 0, to_research: { total: 0, items: [] }, ready: { total: 0, items: [] } }, portfolio: { verified: 1, unverified: [] } },
  market: { fitting_listings: 0, engagement: {}, skills: [], sources: [], hourly: STRATEGY().market.hourly } });
const todayServer = (extra: Record<string, unknown> = {}, strategy: any = STRATEGY(), ov: any = overview()) => serve({ "/overview": ov, "/strategy": strategy, ...extra });

// ---------------------------------------------------------------- Today
test("today: loading, then an honest empty state without sample data", async () => {
  todayServer({}, EMPTY_TODAY(), overview({ opportunities_total: 0, prospects: 0 }));
  renderApp(<Today />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText(/No opportunities yet/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing here is sample data/)).toBeInTheDocument();
  expect(screen.getByText(/None fit you right now/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing is due\. Log what you send in Pipeline/)).toBeInTheDocument();
  expect(screen.queryByText("jobs@acme.example")).not.toBeInTheDocument();
  expect(screen.queryByText(/not verified/)).not.toBeInTheDocument();
});

test("today: a few numbers only — what waits for you and what came of it", async () => {
  todayServer({}, STRATEGY(), overview({ applications_submitted: 11, replies: 4, won: 2 }));
  renderApp(<Today />);
  const stat = async (label: string) => (await screen.findByText(label)).previousElementSibling!.textContent;
  expect(await stat("to write (email published)")).toBe("7");
  expect(await stat("follow-ups due")).toBe("2");
  expect(await stat("prospects to read")).toBe("1");
  expect(await stat("sent")).toBe("11");
  expect(await stat("replies")).toBe("4");
  expect(await stat("won")).toBe("2");
});

test("today: no password set is flagged", async () => {
  todayServer({}, STRATEGY(), overview({ auth_enabled: false }));
  renderApp(<Today />);
  expect(await screen.findByText(/No APP_PASSWORD is set/)).toBeInTheDocument();
});

test("today: a server error is shown with a retry that asks again", async () => {
  let n = 0;
  const spy = serve({ "/overview": overview(), "/strategy": () => (n++ === 0 ? json({ detail: "boom" }, 500) : json(STRATEGY())) });
  renderApp(<Today />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(spy.mock.calls.filter((c) => String(c[0]).includes("/strategy"))).toHaveLength(2);
});

test("today: backend unreachable is explained", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fail"));
  renderApp(<Today />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the server/);
});

test("today: leads show their published email and source, flag drafts and count the rest", async () => {
  todayServer();
  renderApp(<Today />);
  expect(await screen.findByText("jobs@acme.example")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "found here" })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(screen.getByText("draft ready")).toBeInTheDocument();
  expect(screen.getByText("6 more in Find work")).toBeInTheDocument();
  expect(screen.getByText(/Freelance FastAPI developer/)).toBeInTheDocument();
  expect(screen.getByText("A starting split for about 2.5 hours").closest("details")).not.toHaveAttribute("open");   // the plan is one click away
});

test("today: a lead or a prospect opens over this page, with its id", async () => {
  todayServer();
  const { ctx } = renderApp(<Today />);
  const lead = (await screen.findByText("jobs@acme.example")).closest(".item") as HTMLElement;
  fireEvent.click(within(lead).getByRole("button", { name: "Open" }));
  expect(ctx.open).toHaveBeenCalledWith("opp", 5);
  const ready = screen.getByText("Ready to pitch (1)").parentElement as HTMLElement;
  fireEvent.click(within(ready).getByRole("button", { name: "Open" }));
  expect(ctx.open).toHaveBeenCalledWith("prospect", 21);
  const toRead = screen.getByText("To read (1)").parentElement as HTMLElement;
  fireEvent.click(within(toRead).getByRole("button", { name: "Open" }));
  expect(ctx.open).toHaveBeenCalledWith("prospect", 30);
  fireEvent.click(screen.getByText("6 more in Find work"));
  expect(ctx.go).toHaveBeenCalledWith("find");
});

test("today: follow-ups log your own message or close the thread, and say when to stop", async () => {
  const spy = todayServer({ "POST /applications/9/conversations": { id: 9 }, "PATCH /applications/10": { id: 10 } });
  const { ctx } = renderApp(<Today />);
  expect(await screen.findByText("Day 4 or later: one short follow-up.")).toBeInTheDocument();
  expect(screen.getByText(/No answer after two follow-ups, or 21 days: close it\./)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "I sent the follow-up" }));
  await waitFor(() => expect(sent(spy, "POST", "/applications/9/conversations")).toHaveLength(1));
  expect(body(sent(spy, "POST", "/applications/9/conversations")[0])).toEqual({ direction: "out", summary: "Follow-up sent" });
  expect(screen.getAllByRole("button", { name: "I sent the follow-up" })).toHaveLength(1);        // a thread to close has no 'I followed up' button
  fireEvent.click(screen.getAllByRole("button", { name: "Close it (no reply)" })[1]);
  await waitFor(() => expect(sent(spy, "PATCH", "/applications/10")).toHaveLength(1));
  expect(body(sent(spy, "PATCH", "/applications/10")[0])).toEqual({ status: "lost" });
  const pitch = screen.getByText("Northwind Docs", { selector: "b" }).closest(".item") as HTMLElement;
  fireEvent.click(within(pitch).getByRole("button", { name: "Open" }));
  expect(ctx.open).toHaveBeenCalledWith("prospect", 21);                                          // a pitch opens as a prospect, an application as a listing
});

test("today: unverified portfolio items are flagged once, with a way to fix them", async () => {
  todayServer();
  const { ctx } = renderApp(<Today />);
  expect(await screen.findByText(/1 portfolio item is not verified/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Verify" }));
  expect(ctx.go).toHaveBeenCalledWith("data", "portfolio");
});

// ---------------------------------------------------------------- Plan
const planServer = (extra: Record<string, unknown> = {}, strategy: any = STRATEGY()) => serve({ "/strategy": strategy, "/prospects": { total: 0, items: [] }, ...extra });

test("plan: every section is a closed heading until you open it", async () => {
  planServer();
  renderApp(<Plan />);
  await screen.findByText(/each links to its page/);
  const titles = ["What clients ask for", "What to offer", "Where clients come from", "Networks you can apply to", "How to write, and when to follow up", "Spending your $50–200", "Rules that protect your income", "Your numbers"];
  for (const t of titles) expect(screen.getByText(t).closest("details")).not.toHaveAttribute("open");
});

test("plan: market shows gaps without verified evidence and refuses to invent an hourly rate", async () => {
  planServer();
  renderApp(<Plan />);
  expect(await screen.findByText(/Most asked for with no verified example of yours:/)).toHaveTextContent("aws (41%), machine learning (41%)");
  expect(screen.getAllByText("no verified work shows it")).toHaveLength(2);
  expect(screen.getByText("your verified work shows it")).toBeInTheDocument();
  expect(screen.getByText(/That is too few to say what the market pays/)).toBeInTheDocument();
  expect(screen.queryByText(/Median \$/)).not.toBeInTheDocument();
  expect(screen.getByText(/127 do not say whether it is contract or employment, 21 contract/)).toBeInTheDocument();
});

test("plan: an hourly median appears only when the server sends one", async () => {
  planServer({}, STRATEGY({ market: { ...STRATEGY().market, hourly: { n: 12, median_usd: 42.5, min_usd: 20, max_usd: 90, note: "Median of the midpoints of 12 listings." } } }));
  renderApp(<Plan />);
  expect(await screen.findByText(/Median \$42.5\/hour \(range \$20 to \$90\)/)).toBeInTheDocument();
});

test("plan: offers are 'ready' only with verified work behind them", async () => {
  planServer();
  renderApp(<Plan />);
  expect(await screen.findByText("ready: Client Acquisition Studio (neurogrid)")).toBeInTheDocument();
  expect(screen.getByText("add a verified rag example first")).toBeInTheDocument();
});

test("plan: a channel jumps to the tab it is about", async () => {
  planServer();
  const { ctx } = renderApp(<Plan />);
  fireEvent.click(await screen.findByRole("button", { name: "Open Find work" }));
  expect(ctx.go).toHaveBeenCalledWith("find", "");
  expect(screen.getByText(/Few are contract/)).toBeInTheDocument();
});

test("plan: networks quote their own page, link to it, and can be tracked as prospects with that quote", async () => {
  const spy = planServer({ "POST /prospects": { created: [{ id: 99 }], errors: [] } });
  renderApp(<Plan />);
  expect(await screen.findByText(/“To join LD Talent, please send your resumé/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /LD Talent ↗/ })).toHaveAttribute("href", "https://www.ldtalentwork.com/");
  expect(screen.getByText("info@ldtalentwork.com", { selector: "b" })).toBeInTheDocument();
  expect(screen.getByText(/Not a fit right now:/)).toHaveTextContent("Lemon.io");
  fireEvent.click(screen.getAllByRole("button", { name: "Track in Prospects" })[0]);
  expect(await screen.findByText(/LD Talent is in Prospects/)).toBeInTheDocument();
  expect(body(sent(spy, "POST", "/prospects")[0])).toEqual({ research: true, items: [{ website: "https://www.ldtalentwork.com/", name: "LD Talent", category: "network",
    evidence_url: "https://www.ldtalentwork.com/", evidence_quote: "To join LD Talent, please send your resumé (PDF or DOC only) to info@ldtalentwork.com." }] });
});

test("plan: a network already in Prospects shows 'Tracked' and opens it", async () => {
  planServer({ "/prospects": { total: 1, items: [{ id: 77, name: "LD Talent", website: "https://ldtalentwork.com", category: "network" }] } });
  const { ctx } = renderApp(<Plan />);
  fireEvent.click(await screen.findByRole("button", { name: "Tracked" }));
  expect(ctx.open).toHaveBeenCalledWith("prospect", 77);
  expect(screen.getAllByRole("button", { name: "Track in Prospects" })).toHaveLength(1);            // only the other network can still be added
});

test("plan: says why there is no Upwork scraper and links the sources", async () => {
  planServer();
  renderApp(<Plan />);
  expect(await screen.findByText("Why there is no Upwork scraper")).toBeInTheDocument();
  expect(screen.getByText(/This is not built, on purpose\./)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Upwork help: use bots and other automation properly/ })).toHaveAttribute("href", expect.stringContaining("support.upwork.com"));
  expect(screen.getByText("Import the Upwork alert emails you receive.")).toBeInTheDocument();
});

test("plan: the income calculator recomputes from the assumptions you type", async () => {
  planServer();
  renderApp(<Plan />);
  await screen.findByText("Income arithmetic");
  expect(screen.getByText("$33/h")).toBeInTheDocument();                                           // 2.5 h x 20 days x 0.6 = 30 billable hours
  fireEvent.change(screen.getByLabelText("billable share"), { target: { value: "0.5" } });         // 25 billable hours
  expect(screen.getByText("$40/h")).toBeInTheDocument();
  expect(screen.getByText("$120/h")).toBeInTheDocument();
  expect(screen.getByText(/not a forecast/)).toBeInTheDocument();
});

test("plan: with nothing stored it says so instead of showing sample data", async () => {
  planServer({}, EMPTY_TODAY());
  renderApp(<Plan />);
  expect(await screen.findByText(/No stored listing fits you yet/)).toBeInTheDocument();
});

test("plan: a server error is shown with a retry", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ detail: "boom" }, 500));
  renderApp(<Plan />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

// ---------------------------------------------------------------- Find: two views of one job
test("find: Listings and Live projects switch through the shell, not through the page", async () => {
  serve({ "/live/projects": { queries: [], sources: {}, errors: [], total_matches: 0, items: [], emails: [], cached_for_minutes: 15, notice: "x" }, "/leads": { total: 0, emails: [], items: [] }, "/profiles": [], "/sources": [], "/runs": [] });
  const { ctx, unmount } = renderApp(<Find sub="" />);
  expect(await screen.findByRole("button", { name: "Run search" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Listings" })).toHaveAttribute("aria-current", "page");
  fireEvent.click(screen.getByRole("button", { name: "Live projects" }));
  expect(ctx.go).toHaveBeenCalledWith("find", "live");
  unmount();
  renderApp(<Find sub="live" />);
  expect(await screen.findByText(/Nothing is stored/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Run search" })).not.toBeInTheDocument();
});

// ---------------------------------------------------------------- the shell
const OPP = { id: 5, title: "Contract Python engineer", url: "https://news.ycombinator.com/item?id=5", source: "hn_hiring", engagement_type: "contract", remote_status: "remote", listing_status: "open",
  review_status: "new", fit_score: 72, score_override: null, score_components: null, fit_explanation: "", company_name: "Acme", budget_min: null, budget_max: null, currency: "", rate_type: "",
  posted_at: null, deadline: null, location_requirements: "", recommended_action: "", ease_score: 0, ease_signals: [], contacts: [], drafts: [], application: null, required_skills: [],
  matched_skills: [], missing_requirements: [], portfolio_evidence: [], description: "", company: null, evidence: [], history: [] };
const shellServer = () => serve({ "/auth/me": { authenticated: true }, "/overview": overview(), "/strategy": STRATEGY(), "/export/all/counts": COUNTS, "/opportunities/5": OPP,
  "/live/projects": { queries: [], sources: {}, errors: [], total_matches: 0, items: [], emails: [], cached_for_minutes: 15, notice: "x" }, "/leads": { total: 0, emails: [], items: [] }, "/sources": [], "/applications": [], "/prospects": { total: 0, items: [] } });
beforeEach(() => { location.hash = ""; });

test("shell: six tabs in the order you work, Today first and marked as the current page", async () => {
  shellServer();
  render(<App />);
  const nav = await screen.findByRole("navigation", { name: "Main" });
  expect(within(nav).getAllByRole("button").map((b) => b.textContent)).toEqual(["Today", "Find work", "Prospects", "Pipeline", "Plan", "Data"]);
  expect(within(nav).getByRole("button", { name: "Today" })).toHaveAttribute("aria-current", "page");
  expect(await screen.findByRole("link", { name: /Download all/ })).toBeInTheDocument();           // the one download is always one click away
});

test("shell: where you are is in the address, so a reload or the Back button keeps it", async () => {
  shellServer();
  render(<App />);
  const nav = await screen.findByRole("navigation", { name: "Main" });
  fireEvent.click(within(nav).getByRole("button", { name: "Find work" }));
  await waitFor(() => expect(location.hash).toBe("#/find"));
  fireEvent.click(await screen.findByRole("button", { name: "Live projects" }));
  await waitFor(() => expect(location.hash).toBe("#/find/live"));
  expect(await screen.findByText(/Nothing is stored/)).toBeInTheDocument();
  expect(within(nav).getByRole("button", { name: "Find work" })).toHaveAttribute("aria-current", "page");
  location.hash = "#/data/sources";                                                                // what Back, a bookmark or a reload does
  expect(await screen.findByText("Import an alert email")).toBeInTheDocument();
  location.hash = "#/nonsense";
  await waitFor(() => expect(within(nav).getByRole("button", { name: "Today" })).toHaveAttribute("aria-current", "page"));
});

test("shell: a record opens over the page you are on, Escape brings you back to the same place", async () => {
  shellServer();
  render(<App />);
  const lead = (await screen.findByText("jobs@acme.example")).closest(".item") as HTMLElement;
  fireEvent.click(within(lead).getByRole("button", { name: "Open" }));
  const dlg = await screen.findByRole("dialog", { name: "Opportunity detail" });
  expect(within(dlg).getByText("Contract Python engineer")).toBeInTheDocument();
  expect(location.hash === "" || location.hash === "#/today").toBe(true);                         // still on Today: no tab switch
  expect(screen.getByText("jobs@acme.example")).toBeInTheDocument();                              // and Today is still there behind the drawer
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(screen.getByText("jobs@acme.example")).toBeInTheDocument();
});

test("shell: changing tab closes a drawer that belonged to the page you left", async () => {
  shellServer();
  render(<App />);
  fireEvent.click(within((await screen.findByText("jobs@acme.example")).closest(".item") as HTMLElement).getByRole("button", { name: "Open" }));
  await screen.findByRole("dialog");
  fireEvent.click(within(screen.getByRole("navigation", { name: "Main" })).getByRole("button", { name: "Pipeline" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("shell: asking for a password shows the sign-in form instead of the app", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ authenticated: false })) as any);
  render(<App />);
  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
});

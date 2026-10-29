import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import Listings from "./pages/Listings";
import RunSummary from "./pages/RunSummary";
import RunRow from "./pages/RunRow";
import RunPanel from "./pages/RunPanel";
import Files from "./pages/Files";
import OneFile, { DownloadButton } from "./pages/OneFile";
import LiveProjects from "./pages/LiveProjects";
import Sources from "./pages/Sources";
import { ago, fmtBudget, safeUrl } from "./format";
import { COUNTS, NO_COUNTS, body, json, renderApp, sent, serve } from "./testing";

afterEach(() => vi.restoreAllMocks());

const run = (over: object = {}) => ({ id: 3, status: "completed", profile_name: "p", retry_count: 0, sources_queried: ["a"], discovered: 5, stored: 2, new_count: 2,
  rejected_irrelevant: 3, rejected_duplicate: 0, selected_for_review: 1, companies_researched: 0, drafts_generated: 0, cost_usd: 0, duration_s: 4, started_at: null,
  source_results: { a: { status: "ok", fetched: 5 } }, errors: [], incomplete_notes: [], export_status: "ok", exports: [], info_notes: [], ...over });
const file = (kind: string, name: string, n: number, url: string) => ({ kind, status: "ok", filename: name, row_count: n, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: url });

// ---------------------------------------------------------------- runs
test("completed run shows CSV filename, rows and download link", () => {
  render(<RunSummary run={run({ exports: [file("opportunities", "opportunities_2026-10-26_10-00-00.csv", 2, "/api/exports/9/download")] })} />);
  expect(screen.getByRole("link", { name: /opportunities_2026-10-26_10-00-00\.csv/ })).toHaveAttribute("href", "/api/exports/9/download");
  expect(screen.getByText(/2 rows/)).toBeInTheDocument();
});

test("failed export shows retry; failed run says no CSV", () => {
  const { unmount } = render(<RunSummary run={run({ export_status: "failed" })} />);
  expect(screen.getByText("Retry export")).toBeInTheDocument();
  unmount();
  render(<RunSummary run={run({ status: "failed", export_status: "none", errors: ["x: down"] })} />);
  expect(screen.getByText(/No CSV is produced for a failed run/)).toBeInTheDocument();
  expect(screen.getByText("x: down")).toBeInTheDocument();
});

test("a failed action on a run is shown on the run, not in a browser alert", async () => {
  const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
  serve({ "POST /runs/3/retry": () => json({ detail: "Already running" }, 409) });
  render(<RunSummary run={run({ status: "failed", export_status: "none" })} />);
  fireEvent.click(screen.getByRole("button", { name: "Retry run" }));
  expect(await screen.findByText("Already running")).toBeInTheDocument();
  expect(alertSpy).not.toHaveBeenCalled();
});

test("budget formatting never invents values", () => {
  expect(fmtBudget({ budget_min: null, budget_max: null, currency: "", rate_type: "" })).toBe("not published");
  expect(fmtBudget({ budget_min: 40, budget_max: 60, currency: "USD", rate_type: "hourly" })).toBe("40–60 USD / hourly");
});

test("run card shows the emails CSV and count, and a ZIP of that run's two CSVs", () => {
  render(<RunSummary run={run({ id: 8, emails_found: 4, exports: [file("opportunities", "opportunities_x.csv", 9, "/x/1"), file("emails", "emails_x.csv", 4, "/api/exports/2/download")] })} />);
  expect(screen.getByRole("link", { name: /emails_x\.csv/ })).toHaveAttribute("href", "/api/exports/2/download");
  expect(screen.getByTestId("emails-export")).toHaveTextContent("4 emails");
  expect(screen.getByRole("link", { name: /Download both CSVs of this run/ })).toHaveAttribute("href", "/api/exports/download-all?run_id=8");
});

test("run row: running run opens by itself, finished run stays closed", () => {
  const { unmount } = render(<RunRow run={run({ status: "running", current_source: "jobicy" })} />);
  expect(screen.getByText(/Now querying/)).toBeInTheDocument();
  unmount();
  render(<RunRow run={run({ status: "completed" })} />);
  expect(screen.queryByText("Sources queried")).not.toBeInTheDocument();
});

// ---------------------------------------------------------------- listings (one list: with and without an email)
const lead = { id: 5, title: "Python engineer", company_name: "Acme", source: "hn_hiring", url: "https://news.ycombinator.com/item?id=5", fit_score: 70, score_override: null, ease_score: 85,
  review_status: "new", location_requirements: "Worldwide", engagement_type: "contract",
  contacts: [{ id: 1, email: "jobs@acme.example", type: "role / generic mailbox", purpose: "application_invited", eligibility: "eligible", basis: "published for applications",
    source_url: "https://news.ycombinator.com/item?id=5", found_at: "2026-10-26T10:00:00Z", context: "To apply, email jobs@acme.example" }] };
const LEADS = { total: 1, emails: ["jobs@acme.example"], items: [lead] };

test("listings: empty state says what to do and the email buttons wait for emails", async () => {
  serve({ "/leads": { total: 0, emails: [], items: [] }, "/sources": [] });
  renderApp(<Listings />);
  expect(await screen.findByText(/No listings match/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy 0 emails" })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Emails \(CSV\)/ })).toBeInTheDocument();
});

test("listings: a row shows the email with its source link and eligibility, and opens the listing over the page", async () => {
  serve({ "/leads": LEADS, "/sources": [] });
  const { ctx } = renderApp(<Listings />);
  expect(await screen.findByText("jobs@acme.example")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "found here" })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(screen.getByText("eligible")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Listing/ })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  fireEvent.click(screen.getByText("Python engineer"));
  expect(ctx.open).toHaveBeenCalledWith("opp", 5);
  fireEvent.click(screen.getByRole("link", { name: "found here" }));                          // a link inside the row must not also open the drawer
  expect(ctx.open).toHaveBeenCalledTimes(1);
});

test("listings: a listing without an email still shows, and the filters are sent to the server", async () => {
  const spy = serve({ "/leads": { total: 1, emails: [], items: [{ ...lead, contacts: [] }] }, "/sources": [{ key: "jobicy" }] });
  renderApp(<Listings />);
  expect(await screen.findByText("Python engineer")).toBeInTheDocument();
  expect(screen.getByText("no email published")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/only with an email/));
  fireEvent.change(screen.getByLabelText("sort"), { target: { value: "ease" } });
  fireEvent.change(screen.getByLabelText("source filter"), { target: { value: "jobicy" } });
  fireEvent.click(screen.getByLabelText(/show excluded/));
  await waitFor(() => expect(spy.mock.calls.some((c) => /has_email=false.*sort=ease.*source=jobicy.*show_excluded=true/.test(String(c[0])))).toBe(true));
});

test("listings: emails-only button creates the CSV and reports the file", async () => {
  const spy = serve({ "POST /exports/emails": { status: "ok", filename: "emails_all_2026.csv", row_count: 1, download_url: "/api/exports/7/download" }, "/leads": LEADS, "/sources": [] });
  const original = Object.getOwnPropertyDescriptor(window, "location")!;
  const loc = { href: "" } as any;
  Object.defineProperty(window, "location", { value: loc, writable: true, configurable: true });
  try {
    renderApp(<Listings />);
    await screen.findByText("jobs@acme.example");
    fireEvent.click(screen.getByRole("button", { name: /Emails \(CSV\)/ }));
    expect(await screen.findByText(/emails_all_2026\.csv created with 1 emails/)).toBeInTheDocument();
    expect(loc.href).toBe("/api/exports/7/download");
    expect(sent(spy, "POST", "/exports/emails")).toHaveLength(1);
  } finally { Object.defineProperty(window, "location", original); }
});

// ---------------------------------------------------------------- run a search
const PROFILES = [
  { id: 1, name: "AI/LLM and RAG projects", params: { keywords: ["llm"], required_skills: [], sources: ["remotive"] }, is_preset: true },
  { id: 7, name: "AI / ML projects: contract & freelance only", params: { keywords: ["machine learning"], required_skills: [], sources: ["jobicy", "wwr"], strict_engagement: true }, is_preset: true },
];
const SOURCES = [{ key: "jobicy", name: "Jobicy (public API)", kind: "api", enabled: true, verified: true, docs_url: "https://jobicy.com", terms_url: "", notes: "", checked_at: "2026-10-27" },
  { key: "reddit_live", name: "Reddit: [Hiring] posts (live, not stored)", kind: "live", enabled: true, verified: true, docs_url: "javascript:alert(1)", terms_url: "https://redditinc.com/policies/data-api-terms", notes: "no storing", checked_at: "2026-10-27" }];

test("run panel: preselects the AI/ML saved search and shows only the newest run, compact until opened", async () => {
  const runs = [3, 2, 1].map((i) => run({ id: i, exports: [file("opportunities", `o${i}.csv`, 2, `/x/${i}`)] }));
  serve({ "/profiles": PROFILES, "/sources": SOURCES, "/runs": runs });
  render(<RunPanel />);
  const select = (await screen.findByLabelText("Saved search")) as HTMLSelectElement;
  await waitFor(() => expect(select.value).toBe("7"));
  expect(screen.getByText(/only listings that say contract, freelance or part-time/)).toBeInTheDocument();
  expect(await screen.findAllByTestId("run-row")).toHaveLength(1);
  expect(screen.queryByRole("link", { name: /o3\.csv/ })).not.toBeInTheDocument();           // no CSV link until the run is opened
  fireEvent.click(screen.getByRole("button", { name: "Run 3 details" }));
  expect(screen.getByRole("link", { name: /o3\.csv/ })).toBeInTheDocument();
  expect(screen.getByTestId("run-files").tagName).toBe("DETAILS");
});

test("run panel: Run search starts the chosen saved search", async () => {
  const spy = serve({ "POST /runs": { id: 9 }, "/profiles": PROFILES, "/sources": SOURCES, "/runs": [] });
  render(<RunPanel />);
  const select = (await screen.findByLabelText("Saved search")) as HTMLSelectElement;
  await waitFor(() => expect(select.value).toBe("7"));
  fireEvent.click(screen.getByRole("button", { name: "Run search" }));
  expect(await screen.findByText("Run #9 started.")).toBeInTheDocument();
  expect(body(sent(spy, "POST", "/runs")[0])).toEqual({ profile_id: 7 });
});

test("run panel: a custom search offers the strict contract/freelance option and the enabled sources", async () => {
  serve({ "/profiles": PROFILES, "/sources": SOURCES, "/runs": [] });
  render(<RunPanel />);
  fireEvent.change(await screen.findByLabelText("Saved search"), { target: { value: "custom" } });
  expect(await screen.findByLabelText(/Only listings that say contract \/ freelance \/ part-time/)).toBeInTheDocument();
  expect(screen.getByLabelText(/Jobicy \(public API\)/)).toBeInTheDocument();
  expect(screen.queryByLabelText(/Reddit: [Hiring] posts/)).not.toBeInTheDocument();   // the live view is not a stored source
});

// ---------------------------------------------------------------- downloads
test("header download: a link to the one Excel file, disabled while there is nothing to download", async () => {
  serve({ "/export/all/counts": COUNTS });
  const { unmount } = render(<DownloadButton />);
  expect(await screen.findByRole("link", { name: /Download all/ })).toHaveAttribute("href", "/api/export/all?format=xlsx");
  unmount();
  vi.restoreAllMocks();
  serve({ "/export/all/counts": NO_COUNTS });
  render(<DownloadButton />);
  expect(await screen.findByRole("button", { name: /Download all/ })).toBeDisabled();
});

test("one-file panel: counts, Excel and CSV links; disabled when empty", async () => {
  serve({ "/export/all/counts": COUNTS });
  const { unmount } = render(<OneFile />);
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toHaveAttribute("href", "/api/export/all?format=xlsx");
  expect(screen.getByRole("link", { name: /or as one CSV/ })).toHaveAttribute("href", "/api/export/all?format=csv");
  expect(screen.getByText(/12 opportunities · 5 leads you can act on \(email, good fit, open to Tunisia\) · 9 emails in total · 0 prospects · 3 runs/)).toBeInTheDocument();
  expect(screen.getByText(/Summary, Leads, Opportunities, Prospects, Emails, Runs/)).toBeInTheDocument();
  unmount();
  vi.restoreAllMocks();
  serve({ "/export/all/counts": NO_COUNTS });
  render(<OneFile />);
  expect(await screen.findByRole("button", { name: /Download ALL runs in ONE file/ })).toBeDisabled();
  expect(screen.getByText(/Nothing to download yet/)).toBeInTheDocument();
});

const exp = (over: object) => ({ id: 1, run_id: 1, kind: "opportunities", status: "ok", filename: "a.csv", row_count: 1, created_at: "2026-10-26T10:00:00Z",
  run_status: "completed", download_url: "/api/exports/1/download", error: "", ...over });
const USAGE = { events: [], month_spend_usd: 0, monthly_budget_usd: 10, llm_price_note: "" };

test("files: one-file download on top, ZIP of individual files tucked in the archive", async () => {
  serve({ "/export/all/counts": COUNTS, "/exports": [exp({}), exp({ id: 2, kind: "emails", filename: "e.csv" })], "/runs": [], "/usage": USAGE });
  render(<Files />);
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toHaveAttribute("href", "/api/export/all?format=xlsx");
  const archive = screen.getByTestId("archive");
  expect(archive.tagName).toBe("DETAILS");
  expect(archive).not.toHaveAttribute("open");                                    // individual files are hidden by default
  expect(await screen.findByRole("link", { name: /Download all of them \(ZIP\)/ })).toHaveAttribute("href", "/api/exports/download-all");
  fireEvent.change(screen.getByLabelText("which CSVs"), { target: { value: "emails" } });
  expect(screen.getByRole("link", { name: /Download all of them/ })).toHaveAttribute("href", "/api/exports/download-all?kind=emails");
  expect(screen.getByText(/1 file\(s\) in one ZIP/)).toBeInTheDocument();
  expect(screen.getByText(/No paid usage recorded/)).toBeInTheDocument();
});

test("files: nothing exported yet disables both downloads; runs list as compact rows", async () => {
  serve({ "/export/all/counts": NO_COUNTS, "/exports": [], "/runs": [run({ id: 4 }), run({ id: 5 })], "/usage": USAGE });
  render(<Files />);
  expect(await screen.findByRole("button", { name: /Download ALL runs in ONE file/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Download all of them/ })).toBeDisabled();
  expect(await screen.findAllByTestId("run-row")).toHaveLength(2);
});

test("files: a failed backup is reported on the page", async () => {
  serve({ "POST /admin/backup": () => json({ detail: "disk full" }, 500), "/export/all/counts": NO_COUNTS, "/exports": [], "/runs": [], "/usage": USAGE });
  render(<Files />);
  fireEvent.click(await screen.findByRole("button", { name: "Back up database now" }));
  expect(await screen.findByText("disk full")).toBeInTheDocument();
});

// ---------------------------------------------------------------- live projects
const MAIL = { name: "Jane Doe", email: "jane@acme.example", company: "Acme", name_from: "text", company_from: "post", invited: true,
  post_title: "SEEKING FREELANCER | Acme | LLM agent", post_url: "https://news.ycombinator.com/item?id=11", source_name: "HN: Seeking freelancer" };
const POST = { id: "hn:11", source: "hn_freelance", source_name: "HN: Seeking freelancer", title: "Acme | LLM agent for support", url: "https://news.ycombinator.com/item?id=11",
  company: "Acme", poster: "", engagement: "freelance", remote: "remote", age_minutes: 25, excerpt: "Build an agent", matched: ["LLM"], emails: [MAIL], fit: 71, worth: 78, matched_skills: ["python"] };
const NONE = { queries: [], sources: {}, errors: [], total_matches: 0, items: [], emails: [], reddit_configured: false, cached_for_minutes: 15, notice: "x" };

test("live projects: posts from HN and Reddit with the client email table, safe links and the no-storage notice", async () => {
  serve({ "/live/projects": { ...NONE, total_matches: 2, items: [POST, { ...POST, id: "hn:12", title: "Evil", url: "javascript:alert(1)", emails: [] }], emails: [MAIL] } });
  render(<LiveProjects />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(screen.getByText(/Nothing is stored/)).toBeInTheDocument();
  const link = await screen.findByRole("link", { name: /LLM agent for support/ });
  expect(link).toHaveAttribute("href", "https://news.ycombinator.com/item?id=11");
  expect(screen.getByText("Client emails (1)")).toBeInTheDocument();
  expect(screen.getByText("Jane Doe")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "jane@acme.example" })[0]).toHaveAttribute("href", "mailto:jane@acme.example");
  expect(screen.queryByText(/freelancer\.com/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Evil/ })).not.toBeInTheDocument();         // javascript: is plain text, never a link
  expect(screen.getByText(/Evil/)).toBeInTheDocument();
});

test("live projects: a busy source is one quiet line, never a banner; and the empty state", async () => {
  serve({ "/live/projects": { ...NONE, total_matches: 1, items: [POST], emails: [MAIL], errors: ["Reddit: Reddit is busy right now"],
    sources: { hn_freelance: { ok: true, posts: 3, matching: 1, name: "HN: Seeking freelancer" }, reddit: { ok: false, posts: 0, name: "Reddit", error: "Reddit is busy right now" } } } });
  const { unmount } = render(<LiveProjects />);
  const line = await screen.findByTestId("source-line");
  expect(line).toHaveTextContent("HN: Seeking freelancer: 1 matching · Reddit: unavailable right now");
  expect(screen.queryByText(/Reddit is busy right now/)).not.toBeInTheDocument();
  expect(screen.queryByText(/REDDIT_CLIENT_ID|API app/)).not.toBeInTheDocument();
  unmount();
  vi.restoreAllMocks();
  serve({ "/live/projects": NONE });
  render(<LiveProjects />);
  expect(await screen.findByText(/No client posts match/)).toBeInTheDocument();
});

test("live projects: Search sends the chosen sources and filters", async () => {
  const spy = serve({ "/live/projects": NONE });
  render(<LiveProjects />);
  await screen.findByText(/No client posts match/);
  expect(screen.queryByLabelText(/Reddit \[Hiring\] posts/)).not.toBeInTheDocument();   // no Reddit keys: not offered at all
  fireEvent.click(screen.getByLabelText(/Mastodon #hiring/));
  fireEvent.click(screen.getByLabelText(/only posts with an email/));
  fireEvent.change(screen.getByLabelText("sort"), { target: { value: "newest" } });
  fireEvent.change(screen.getByLabelText("posted within"), { target: { value: "7" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(spy.mock.calls.some((c) => { const u = decodeURIComponent(String(c[0]).replace(/\+/g, " "));
    return /sources=marketplaces,hn_freelance,hn_hiring,bluesky,bounties,boards,reddit&/.test(u) && /only_email=true/.test(u)
      && /sort=newest/.test(u) && /max_days=7/.test(u) && /intelligence artificielle/.test(u) && /ذكاء اصطناعي/.test(u); })).toBe(true));
});

test("live projects: client projects show their budget, and the direct-only filter hides job ads", async () => {
  const project = { ...POST, id: "marketplaces:Codeur.com:1", source: "marketplaces", source_name: "Codeur.com · FR", title: "Agent IA WhatsApp",
    url: "https://www.codeur.com/projects/1-agent-ia", emails: [], direct: true, budget: "500 € à 1 000 €" };
  const ad = { ...POST, id: "mastodon:x", source: "mastodon", source_name: "Mastodon #AIjobs", title: "Open Role | ML Engineer", emails: [], direct: false, budget: "" };
  serve({ "/live/projects": { ...NONE, total_matches: 2, items: [project, ad] } });
  render(<LiveProjects />);
  expect(await screen.findByRole("link", { name: /Agent IA WhatsApp/ })).toHaveAttribute("href", "https://www.codeur.com/projects/1-agent-ia");
  expect(screen.getByText("500 € à 1 000 €")).toBeInTheDocument();
  expect(screen.getByText("client project")).toBeInTheDocument();
  expect(screen.getByText(/Open Role \| ML Engineer/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText(/only direct client projects/));
  expect(screen.queryByText(/Open Role \| ML Engineer/)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Agent IA WhatsApp/ })).toBeInTheDocument();
});

test("live projects: pasted text becomes a Name / Email / Company table", async () => {
  const spy = serve({ "/live/projects": NONE, "POST /tools/extract-emails": () => json({ rows: [{ ...MAIL, name: "Ali Ben", email: "ali@shop.example", company: "Shop", company_from: "domain" }] }) });
  render(<LiveProjects />);
  await screen.findByText(/No client posts match/);
  fireEvent.change(screen.getByLabelText("text to search for emails"), { target: { value: "Ali Ben <ali@shop.example>" } });
  fireEvent.click(screen.getByRole("button", { name: "Find emails" }));
  expect(await screen.findByText("Ali Ben")).toBeInTheDocument();
  expect(screen.getByText("Shop")).toBeInTheDocument();
  expect(spy.mock.calls.some((c) => String(c[0]).endsWith("/tools/extract-emails"))).toBe(true);
});

// ---------------------------------------------------------------- sources
test("sources: live source is labelled, unsafe docs link is dropped, the resources list names what the app never reads", async () => {
  serve({ "/sources": SOURCES });
  render(<Sources />);
  expect(await screen.findByText("live view only (not stored)")).toBeInTheDocument();
  const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
  expect(hrefs.some((h) => (h ?? "").startsWith("javascript:"))).toBe(false);
  const res = screen.getByTestId("resources");
  expect(res.tagName).toBe("DETAILS");
  expect(res).not.toHaveAttribute("open");
  expect(res).toHaveTextContent("Upwork");
  expect(res).toHaveTextContent("Reddit r/forhire");
  expect(res).toHaveTextContent("never reads it");
});

test("sources: an alert email is sent for parsing and the outcome is shown", async () => {
  const spy = serve({ "POST /alerts/import": { parsed: 2, run: { exports: [{ filename: "opportunities_alert.csv" }] } }, "/sources": SOURCES });
  render(<Sources />);
  await screen.findByText("live view only (not stored)");
  const importBtn = screen.getByRole("button", { name: "Import" });
  expect(importBtn).toBeDisabled();                                                        // nothing to parse yet
  fireEvent.change(screen.getByLabelText("alert email text"), { target: { value: "New job: LLM engineer https://www.upwork.com/jobs/~01" } });
  fireEvent.click(importBtn);
  expect(await screen.findByText(/Parsed 2 job link\(s\); CSV opportunities_alert\.csv/)).toBeInTheDocument();
  expect(body(sent(spy, "POST", "/alerts/import")[0])).toEqual({ text: "New job: LLM engineer https://www.upwork.com/jobs/~01", platform_hint: "" });
});

test("safeUrl only lets http(s) through; ago() reads naturally", () => {
  expect(safeUrl("https://a.example/x")).toBe("https://a.example/x");
  expect(safeUrl(" HTTP://a.example ")).toBe("HTTP://a.example");
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "//evil.example", "", null, undefined]) expect(safeUrl(bad as any)).toBe("");
  expect([ago(0), ago(5), ago(90), ago(3000), ago(null)]).toEqual(["just now", "5 min ago", "1 h ago", "2 d ago", "—"]);
});

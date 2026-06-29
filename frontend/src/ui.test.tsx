import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import Overview from "./pages/Overview";
import Opportunities from "./pages/Opportunities";
import RunSummary from "./pages/RunSummary";
import { fmtBudget } from "./format";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
afterEach(() => vi.restoreAllMocks());
const route = (table: Record<string, unknown>, fallback: unknown = []) => (u: any, init?: any) => {
  const url = String(u);
  const key = Object.keys(table).find((k) => url.includes(k));
  const v = key ? table[key] : fallback;
  return json(typeof v === "function" ? (v as any)(url, init) : v);
};
const COUNTS = { runs: 3, opportunities: 12, leads: 5, emails: 9 };

const overview = (over: object = {}) => ({ opportunities_total: 0, new_since_previous_run: 0, relevant: 0, awaiting_review: 0, proposals_drafted: 0, applications_submitted: 0,
  replies: 0, interviews: 0, won: 0, lost: 0, research_failures: 0, cost_estimated_usd: 0, cost_actual_usd: 0, month_spend_usd: 0, monthly_budget_usd: 10, last_run: null,
  contacts_total: 0, auth_enabled: true, ...over });

test("overview shows loading, then an honest empty state without sample data", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": COUNTS }, overview()) as any);
  render(<Overview go={() => {}} />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText(/No opportunities yet/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing on this page is sample data/)).toBeInTheDocument();
});

test("overview shows database numbers", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": COUNTS }, overview({ opportunities_total: 74, interviews: 2 })) as any);
  render(<Overview go={() => {}} />);
  expect(await screen.findByText("74")).toBeInTheDocument();
});

test("error state offers retry", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => json({ detail: "boom" }, 500)).mockImplementation(route({ "/export/all/counts": COUNTS }, overview()) as any);
  render(<Overview go={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  fireEvent.click(screen.getByText("Retry"));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(spy.mock.calls.filter((c) => String(c[0]).includes("/overview"))).toHaveLength(2);   // the overview itself was asked for twice
});

test("backend unreachable is explained", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fail"));
  render(<Overview go={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the server/);
});

test("opportunities empty state", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((u) => json(String(u).includes("/sources") ? [] : { total: 0, items: [] }));
  render(<Opportunities openId={null} setOpenId={() => {}} />);
  expect(await screen.findByText(/No opportunities match/)).toBeInTheDocument();
});

const run = (over: object = {}) => ({ id: 3, status: "completed", profile_name: "p", retry_count: 0, sources_queried: ["a"], discovered: 5, stored: 2, new_count: 2,
  rejected_irrelevant: 3, rejected_duplicate: 0, selected_for_review: 1, companies_researched: 0, drafts_generated: 0, cost_usd: 0, duration_s: 4, started_at: null,
  source_results: { a: { status: "ok", fetched: 5 } }, errors: [], incomplete_notes: [], export_status: "ok", exports: [], info_notes: [], ...over });

test("completed run shows CSV filename, rows and download link", () => {
  render(<RunSummary run={run({ exports: [{ kind: "opportunities", status: "ok", filename: "opportunities_2026-10-26_10-00-00.csv", row_count: 2, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/api/exports/9/download" }] })} />);
  const a = screen.getByRole("link", { name: /opportunities_2026-10-26_10-00-00\.csv/ });
  expect(a).toHaveAttribute("href", "/api/exports/9/download");
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

test("budget formatting never invents values", () => {
  expect(fmtBudget({ budget_min: null, budget_max: null, currency: "", rate_type: "" })).toBe("not published");
  expect(fmtBudget({ budget_min: 40, budget_max: 60, currency: "USD", rate_type: "hourly" })).toBe("40–60 USD / hourly");
});

import Leads from "./pages/Leads";

const lead = { id: 5, title: "Python engineer", company_name: "Acme", url: "https://news.ycombinator.com/item?id=5", fit_score: 70, ease_score: 85,
  ease_signals: ["Company published an email to apply (+30)"], location_requirements: "Worldwide", engagement_type: "contract",
  contacts: [{ id: 1, email: "jobs@acme.example", type: "role / generic mailbox", purpose: "application_invited", eligibility: "eligible", basis: "published for applications",
    source_url: "https://news.ycombinator.com/item?id=5", found_at: "2026-10-26T10:00:00Z", context: "To apply, email jobs@acme.example" }] };

test("leads: empty state explains what to do", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": { runs: 0, opportunities: 0, leads: 0, emails: 0 }, "/leads": { total: 0, emails: [], items: [] } }) as any);
  render(<Leads openOpp={() => {}} />);
  expect(await screen.findByText(/No leads yet/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Download ALL runs in ONE file/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Only the emails/ })).toBeInTheDocument();
});

test("leads: shows email with its source link, eligibility and why it looks easy", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": COUNTS, "/leads": { total: 1, emails: ["jobs@acme.example"], items: [lead] } }) as any);
  render(<Leads openOpp={() => {}} />);
  expect(await screen.findByText("jobs@acme.example")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "found here" })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(screen.getByText(/Company published an email to apply/)).toBeInTheDocument();
  expect(screen.getAllByText("eligible").length).toBeGreaterThan(0);
});

test("leads: the one-file download is the main button and links to the Excel export", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": COUNTS, "/leads": { total: 1, emails: ["jobs@acme.example"], items: [lead] } }) as any);
  render(<Leads openOpp={() => {}} />);
  const main = await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ });
  expect(main).toHaveAttribute("href", "/api/export/all?format=xlsx");
  expect(screen.getByRole("link", { name: /or as one CSV/ })).toHaveAttribute("href", "/api/export/all?format=csv");
  expect(screen.getByText(/12 opportunities · 5 leads you can act on \(email, good fit, open to Tunisia\) · 9 emails in total · 0 prospects · 3 runs/)).toBeInTheDocument();
});

test("leads: emails-only button creates the CSV and reports the file", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(((u: any, init?: any) =>
    String(u).includes("/exports/emails") && init?.method === "POST"
      ? json({ status: "ok", filename: "emails_all_2026.csv", row_count: 1, download_url: "/api/exports/7/download" })
      : route({ "/export/all/counts": COUNTS, "/leads": { total: 1, emails: ["jobs@acme.example"], items: [lead] } })(u, init)) as any);
  const loc = { href: "" } as any;
  Object.defineProperty(window, "location", { value: loc, writable: true });
  render(<Leads openOpp={() => {}} />);
  await screen.findByText("jobs@acme.example");
  fireEvent.click(screen.getByRole("button", { name: /Only the emails/ }));
  expect(await screen.findByText(/emails_all_2026\.csv created with 1 emails/)).toBeInTheDocument();
  expect(loc.href).toBe("/api/exports/7/download");
  expect(spy).toHaveBeenCalled();
});

test("run card shows the emails CSV and count", () => {
  render(<RunSummary run={run({ emails_found: 4, exports: [
    { kind: "opportunities", status: "ok", filename: "opportunities_x.csv", row_count: 9, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/api/exports/1/download" },
    { kind: "emails", status: "ok", filename: "emails_x.csv", row_count: 4, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/api/exports/2/download" }] })} />);
  expect(screen.getByRole("link", { name: /emails_x\.csv/ })).toHaveAttribute("href", "/api/exports/2/download");
  expect(screen.getByTestId("emails-export")).toHaveTextContent("4 emails");
});

import Runs from "./pages/Runs";

const exp = (over: object) => ({ id: 1, run_id: 1, kind: "opportunities", status: "ok", filename: "a.csv", row_count: 1, created_at: "2026-10-26T10:00:00Z",
  run_status: "completed", download_url: "/api/exports/1/download", error: "", ...over });

test("runs page: one-file download on top, ZIP of individual files tucked in the archive", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": COUNTS, "/exports": [exp({}), exp({ id: 2, kind: "emails", filename: "e.csv" })], "/runs": [] }) as any);
  render(<Runs go={() => {}} />);
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toHaveAttribute("href", "/api/exports/../export/all?format=xlsx".replace("/exports/..", ""));
  const archive = screen.getByTestId("archive");
  expect(archive.tagName).toBe("DETAILS");
  expect(archive).not.toHaveAttribute("open");                                    // individual files are hidden by default
  const zip = await screen.findByRole("link", { name: /Download all of them \(ZIP\)/ });
  expect(zip).toHaveAttribute("href", "/api/exports/download-all");
  fireEvent.change(screen.getByLabelText("which CSVs"), { target: { value: "emails" } });
  expect(screen.getByRole("link", { name: /Download all of them/ })).toHaveAttribute("href", "/api/exports/download-all?kind=emails");
  expect(screen.getByText(/1 file\(s\) in one ZIP/)).toBeInTheDocument();
});

test("runs page: nothing exported yet disables both downloads", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": { runs: 0, opportunities: 0, leads: 0, emails: 0 }, "/exports": [], "/runs": [] }) as any);
  render(<Runs go={() => {}} />);
  expect(await screen.findByRole("button", { name: /Download ALL runs in ONE file/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Download all of them/ })).toBeDisabled();
  expect(await screen.findByText(/Nothing to download yet/)).toBeInTheDocument();
});

test("run card offers a ZIP of that run's two CSVs", () => {
  render(<RunSummary run={run({ id: 8, exports: [
    { kind: "opportunities", status: "ok", filename: "o.csv", row_count: 2, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/x/1" },
    { kind: "emails", status: "ok", filename: "e.csv", row_count: 1, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/x/2" }] })} />);
  expect(screen.getByRole("link", { name: /Download both CSVs of this run/ })).toHaveAttribute("href", "/api/exports/download-all?run_id=8");
});

import Research from "./pages/Research";
import RunRow from "./pages/RunRow";
import OneFile from "./pages/OneFile";
import LiveProjects from "./pages/LiveProjects";
import Settings from "./pages/Settings";
import { safeUrl, ago } from "./format";

const PROFILES = [
  { id: 1, name: "AI/LLM and RAG projects", params: { keywords: ["llm"], required_skills: [], sources: ["remotive"] }, is_preset: true },
  { id: 7, name: "AI / ML projects: contract & freelance only", params: { keywords: ["machine learning"], required_skills: [], sources: ["jobicy", "wwr"], strict_engagement: true }, is_preset: true },
];
const SOURCES = [{ key: "jobicy", name: "Jobicy (public API)", kind: "api", enabled: true, verified: true, docs_url: "https://jobicy.com", terms_url: "", notes: "", checked_at: "2026-10-27" },
  { key: "freelancer_live", name: "Freelancer.com: live projects (not stored)", kind: "live", enabled: true, verified: true, docs_url: "javascript:alert(1)", terms_url: "https://www.freelancer.com/about/apiterms", notes: "no storing", checked_at: "2026-10-27" }];

test("research: preselects the AI/ML saved search, shows ONE download and compact runs (no per-run buttons)", async () => {
  const runs = [1, 2, 3].map((i) => run({ id: i, exports: [{ kind: "opportunities", status: "ok", filename: `o${i}.csv`, row_count: 2, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: `/x/${i}` }] }));
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/profiles": PROFILES, "/sources": SOURCES, "/export/all/counts": COUNTS, "/runs": runs }) as any);
  render(<Research go={() => {}} />);
  const select = (await screen.findByLabelText("Saved search")) as HTMLSelectElement;
  await waitFor(() => expect(select.value).toBe("7"));
  expect(screen.getByText(/only listings that say contract, freelance or part-time/)).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toBeInTheDocument();
  const rows = await screen.findAllByTestId("run-row");
  expect(rows).toHaveLength(3);
  // compact: no CSV link, no ZIP button and no "Export CSV" button is visible until a run is opened
  expect(screen.queryByRole("link", { name: /o1\.csv/ })).not.toBeInTheDocument();
  expect(screen.queryByText("Export CSV")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Run 1 details" }));
  expect(screen.getByRole("link", { name: /o1\.csv/ })).toBeInTheDocument();
  expect(screen.getByTestId("run-files").tagName).toBe("DETAILS");
});

test("research: custom search offers the strict contract/freelance option", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/profiles": PROFILES, "/sources": SOURCES, "/export/all/counts": COUNTS, "/runs": [] }) as any);
  render(<Research go={() => {}} />);
  fireEvent.change(await screen.findByLabelText("Saved search"), { target: { value: "custom" } });
  expect(await screen.findByLabelText(/Only listings that say contract \/ freelance \/ part-time/)).toBeInTheDocument();
  expect(screen.getByLabelText(/Jobicy \(public API\)/)).toBeInTheDocument();
});

test("run row: running run opens by itself, finished run stays closed", () => {
  const { unmount } = render(<RunRow run={run({ status: "running", current_source: "jobicy" })} />);
  expect(screen.getByText(/Now querying/)).toBeInTheDocument();
  unmount();
  render(<RunRow run={run({ status: "completed" })} />);
  expect(screen.queryByText("Sources queried")).not.toBeInTheDocument();
});

test("one-file panel: counts, Excel and CSV links; disabled when empty", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": COUNTS }) as any);
  const { unmount } = render(<OneFile />);
  expect(await screen.findByRole("link", { name: /Download ALL runs in ONE file \(Excel\)/ })).toHaveAttribute("href", "/api/export/all?format=xlsx");
  expect(screen.getByText(/Summary, Leads, Opportunities, Prospects, Emails, Runs/)).toBeInTheDocument();
  unmount();
  vi.restoreAllMocks();
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/export/all/counts": { runs: 0, opportunities: 0, leads: 0, emails: 0 } }) as any);
  render(<OneFile />);
  expect(await screen.findByRole("button", { name: /Download ALL runs in ONE file/ })).toBeDisabled();
});

const PROJECT = { id: 11, title: "LLM agent for support", url: "https://www.freelancer.com/projects/machine-learning/LLM-agent-11", type: "fixed", budget_min: 250, budget_max: 750,
  currency: "USD", currency_sign: "$", budget_max_usd: 750, bids: 4, bid_avg: 300, competition: "few bids", age_minutes: 25, skills: ["Python", "LLM"], excerpt: "Build an agent", fit: 71, worth: 78, urgent: false, matched_skills: ["python"] };

test("live projects: loading, then results with competition, safe link and the no-storage notice", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/live/freelancer": { queries: ["llm"], total_matches: 1, items: [PROJECT, { ...PROJECT, id: 12, title: "Evil", url: "javascript:alert(1)", competition: "crowded", bids: 150 }], cached_for_minutes: 15, notice: "x" } }) as any);
  render(<LiveProjects />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(screen.getByText(/do not allow storing its data/)).toBeInTheDocument();
  const link = await screen.findByRole("link", { name: /LLM agent for support/ });
  expect(link).toHaveAttribute("href", "https://www.freelancer.com/projects/machine-learning/LLM-agent-11");
  expect(screen.getByText("few bids")).toBeInTheDocument();
  expect(screen.getByText("crowded")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Evil/ })).not.toBeInTheDocument();         // javascript: is plain text, never a link
  expect(screen.getByText(/Evil/)).toBeInTheDocument();
});

test("live projects: error and empty states", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ detail: "Freelancer.com asked us to slow down." }, 502));
  const { unmount } = render(<LiveProjects />);
  expect(await screen.findByRole("alert")).toHaveTextContent("slow down");
  unmount();
  vi.restoreAllMocks();
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/live/freelancer": { queries: [], total_matches: 0, items: [], cached_for_minutes: 15, notice: "x" } }) as any);
  render(<LiveProjects />);
  expect(await screen.findByText(/No open projects match/)).toBeInTheDocument();
});

test("live projects: Search sends the chosen filters", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/live/freelancer": { queries: [], total_matches: 0, items: [], cached_for_minutes: 15, notice: "x" } }) as any);
  render(<LiveProjects />);
  await screen.findByText(/No open projects match/);
  fireEvent.change(screen.getByLabelText("max bids"), { target: { value: "10" } });
  fireEvent.change(screen.getByLabelText("sort"), { target: { value: "newest" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(spy.mock.calls.some((c) => String(c[0]).includes("max_bids=10") && String(c[0]).includes("sort=newest"))).toBe(true));
});

test("settings: live source is labelled, unsafe docs link is dropped, resources list is shown", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(route({ "/sources": SOURCES, "/portfolio": [], "/usage": { events: [], month_spend_usd: 0, monthly_budget_usd: 10, llm_price_note: "" } }) as any);
  render(<Settings />);
  expect(await screen.findByText("live view only (not stored)")).toBeInTheDocument();
  const hrefs = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
  expect(hrefs.some((h) => (h ?? "").startsWith("javascript:"))).toBe(false);
  const res = screen.getByTestId("resources");
  expect(res).toHaveTextContent("Freelancer.com: machine learning");
  expect(res).toHaveTextContent("Reddit r/forhire");
  expect(res).toHaveTextContent("never reads it");
});

test("safeUrl only lets http(s) through; ago() reads naturally", () => {
  expect(safeUrl("https://a.example/x")).toBe("https://a.example/x");
  expect(safeUrl(" HTTP://a.example ")).toBe("HTTP://a.example");
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "//evil.example", "", null, undefined]) expect(safeUrl(bad as any)).toBe("");
  expect([ago(0), ago(5), ago(90), ago(3000), ago(null)]).toEqual(["just now", "5 min ago", "1 h ago", "2 d ago", "—"]);
});

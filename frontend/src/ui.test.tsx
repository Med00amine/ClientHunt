import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import Overview from "./pages/Overview";
import Opportunities from "./pages/Opportunities";
import RunSummary from "./pages/RunSummary";
import { fmtBudget } from "./format";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
afterEach(() => vi.restoreAllMocks());

const overview = (over: object = {}) => ({ opportunities_total: 0, new_since_previous_run: 0, relevant: 0, awaiting_review: 0, proposals_drafted: 0, applications_submitted: 0,
  replies: 0, interviews: 0, won: 0, lost: 0, research_failures: 0, cost_estimated_usd: 0, cost_actual_usd: 0, month_spend_usd: 0, monthly_budget_usd: 10, last_run: null,
  contacts_total: 0, auth_enabled: true, ...over });

test("overview shows loading, then an honest empty state without sample data", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json(overview()));
  render(<Overview go={() => {}} />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText(/No opportunities yet/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing on this page is sample data/)).toBeInTheDocument();
});

test("overview shows database numbers", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json(overview({ opportunities_total: 74, interviews: 2 })));
  render(<Overview go={() => {}} />);
  expect(await screen.findByText("74")).toBeInTheDocument();
});

test("error state offers retry", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementationOnce(() => json({ detail: "boom" }, 500)).mockImplementation(() => json(overview()));
  render(<Overview go={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  fireEvent.click(screen.getByText("Retry"));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(spy).toHaveBeenCalledTimes(2);
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
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ total: 0, emails: [], items: [] }));
  render(<Leads openOpp={() => {}} />);
  expect(await screen.findByText(/No leads yet/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Download all emails/ })).toBeInTheDocument();
});

test("leads: shows email with its source link, eligibility and why it looks easy", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ total: 1, emails: ["jobs@acme.example"], items: [lead] }));
  render(<Leads openOpp={() => {}} />);
  expect(await screen.findByText("jobs@acme.example")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "found here" })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(screen.getByText(/Company published an email to apply/)).toBeInTheDocument();
  expect(screen.getAllByText("eligible").length).toBeGreaterThan(0);
});

test("leads: download button creates the CSV and reports the file", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation((u, init) =>
    String(u).includes("/exports/emails") && init?.method === "POST"
      ? json({ status: "ok", filename: "emails_all_2026.csv", row_count: 1, download_url: "/api/exports/7/download" })
      : json({ total: 1, emails: ["jobs@acme.example"], items: [lead] }));
  const loc = { href: "" } as any;
  Object.defineProperty(window, "location", { value: loc, writable: true });
  render(<Leads openOpp={() => {}} />);
  await screen.findByText("jobs@acme.example");
  fireEvent.click(screen.getByRole("button", { name: /Download all emails/ }));
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

test("runs page: one ZIP button for all CSVs, filterable by kind", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((u) => json(String(u).includes("/exports") ? [exp({}), exp({ id: 2, kind: "emails", filename: "e.csv" })] : []));
  render(<Runs go={() => {}} />);
  const zip = await screen.findByRole("link", { name: /Download ALL CSVs \(ZIP\)/ });
  expect(zip).toHaveAttribute("href", "/api/exports/download-all");
  expect(screen.getByText(/2 file\(s\) in one ZIP/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("which CSVs"), { target: { value: "emails" } });
  expect(screen.getByRole("link", { name: /Download ALL CSVs/ })).toHaveAttribute("href", "/api/exports/download-all?kind=emails");
  expect(screen.getByText(/1 file\(s\) in one ZIP/)).toBeInTheDocument();
});

test("runs page: ZIP button is disabled when nothing was exported yet", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((u) => json([]));
  render(<Runs go={() => {}} />);
  expect(await screen.findByRole("button", { name: /Download ALL CSVs/ })).toBeDisabled();
});

test("run card offers a ZIP of that run's two CSVs", () => {
  render(<RunSummary run={run({ id: 8, exports: [
    { kind: "opportunities", status: "ok", filename: "o.csv", row_count: 2, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/x/1" },
    { kind: "emails", status: "ok", filename: "e.csv", row_count: 1, created_at: "2026-10-26T10:00:00Z", run_status: "completed", download_url: "/x/2" }] })} />);
  expect(screen.getByRole("link", { name: /Download both CSVs of this run/ })).toHaveAttribute("href", "/api/exports/download-all?run_id=8");
});

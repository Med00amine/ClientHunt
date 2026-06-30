import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import Prospects from "./pages/Prospects";
import Pipeline from "./pages/Pipeline";
import { OppDrawer, ProspectDrawer } from "./pages/Drawers";
import { body, json, renderApp, sent, serve } from "./testing";

afterEach(() => vi.restoreAllMocks());
const META = {
  offers: { rag_assistant: { label: "Question-answering assistant over your own documents (RAG)", audience: "a", deliverable: "A working pilot", first_step: "A 30-minute call" },
            subcontract_capacity: { label: "Extra delivery capacity for an agency or consultancy", audience: "a", deliverable: "Well-scoped tasks", first_step: "One small paid task" } },
  categories: { company: { label: "Company that may need something built", offer: "rag_assistant" }, agency: { label: "Agency or firm that may subcontract", offer: "subcontract_capacity" },
                network: { label: "Network or marketplace to join", offer: "network_application" } },
};

const mailbox = { id: 1, email: "partners@northwind.example", eligibility: "eligible", purpose: "partner_invited", basis: "The site invites freelancers", source_url: "https://northwind.example/contact", found_at: "2026-10-27T10:00:00Z" };
const general = { id: 2, email: "hello@northwind.example", eligibility: "review_required", purpose: "b2b_mailbox", basis: "Unsolicited: identify yourself", source_url: "https://northwind.example/contact", found_at: "2026-10-27T10:00:00Z" };
const prospect = (over: object = {}) => ({ id: 21, name: "Northwind Docs", website: "https://northwind.example", category: "company", offer: "rag_assistant", offer_label: META.offers.rag_assistant.label,
  evidence_url: "https://directory.example/nw", evidence_quote: "Offers staff augmentation", research_status: "done", need_score: 65, signals: ["Public site mentions AI / machine learning (+20)", "Publishes a role mailbox (+10)"],
  relevance: 40, recommended_action: "Review the evidence, approve one fact, then draft a pitch to the published mailbox", last_verified_at: null, added_at: null, summary: [], contacts: [mailbox, general],
  draft_status: "none", application_status: "none", review_status: "new", ...over });

// ---------------------------------------------------------------- Prospects page
test("prospects: honest empty state with the add form open", async () => {
  serve({ "/prospects/meta": META, "/prospects?": { total: 0, items: [] } });
  renderApp(<Prospects />);
  expect(await screen.findByText(/No prospects yet/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing here is sample data/)).toBeInTheDocument();
  expect(screen.getByLabelText("Websites, one per line")).toBeInTheDocument();
  expect(screen.getByText(/nothing is ever sent/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("Add companies, agencies or networks").closest("details")).toHaveAttribute("open"));
});

test("prospects: a row shows signs, mailboxes with where they were found, status, and refuses an unsafe website link", async () => {
  serve({ "/prospects/meta": META, "/prospects?": { total: 2, items: [prospect({ application_status: "submitted" }),
    prospect({ id: 22, name: "Evil Co", website: "javascript:alert(1)", research_status: "failed", contacts: [], need_score: 0, signals: [], offer_label: "" })] } });
  renderApp(<Prospects />);
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

test("prospects: a row opens its drawer over the page; a network shows no score", async () => {
  const net = prospect({ id: 41, name: "LD Talent", website: "https://www.ldtalentwork.com", category: "network", offer: "network_application", offer_label: "", need_score: 0, signals: [],
    contacts: [{ ...mailbox, id: 9, email: "info@ldtalentwork.com", source_url: "https://www.ldtalentwork.com/" }] });
  serve({ "/prospects/meta": META, "/prospects?": { total: 1, items: [net] } });
  const { ctx } = renderApp(<Prospects />);
  const row = (await screen.findAllByRole("row")).find((r) => r.textContent?.includes("LD Talent"))!;
  expect(within(row).getAllByRole("cell")[0]).toHaveTextContent("—");                      // no number in the "signs of need" column
  fireEvent.click(row);
  expect(ctx.open).toHaveBeenCalledWith("prospect", 41);
});

test("prospects: adding sends the lines with the chosen kind, reports what was refused and keeps only those lines", async () => {
  const spy = serve({ "/prospects/meta": META, "POST /prospects": { created: [prospect()], errors: [{ website: "http://localhost", error: "Private or local addresses are not allowed" }] },
    "/prospects?": { total: 0, items: [] } });
  renderApp(<Prospects />);
  await screen.findByText(/No prospects yet/);
  fireEvent.change(screen.getByLabelText("Websites, one per line"), { target: { value: "northwind.example\n\nhttp://localhost\n" } });
  fireEvent.change(screen.getByLabelText("What are they?"), { target: { value: "agency" } });
  fireEvent.change(screen.getByLabelText("Link"), { target: { value: "https://directory.example/nw" } });
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

test("prospects: the add form stays open after the first prospect is added, so its confirmation is still on screen", async () => {
  let added = false;
  serve({ "/prospects/meta": META, "POST /prospects": () => { added = true; return json({ created: [prospect()], errors: [] }); },
    "/prospects?": () => json(added ? { total: 1, items: [prospect()] } : { total: 0, items: [] }) });
  renderApp(<Prospects />);
  await screen.findByText(/No prospects yet/);
  const form = screen.getByText("Add companies, agencies or networks").closest("details")!;
  await waitFor(() => expect(form).toHaveAttribute("open"));
  fireEvent.change(screen.getByLabelText("Websites, one per line"), { target: { value: "northwind.example" } });
  fireEvent.click(screen.getByRole("button", { name: "Add prospects" }));
  expect(await screen.findByText(/Added or updated 1\./)).toBeInTheDocument();
  expect(await screen.findByText("Northwind Docs")).toBeInTheDocument();                  // the list now has a row...
  expect(form).toHaveAttribute("open");                                                   // ...and the form did not fold itself away
});

test("prospects: an empty submission is refused without calling the server", async () => {
  const spy = serve({ "/prospects/meta": META, "/prospects?": { total: 0, items: [] } });
  renderApp(<Prospects />);
  await screen.findByText(/No prospects yet/);
  fireEvent.click(screen.getByRole("button", { name: "Add prospects" }));
  expect(await screen.findByText(/Paste at least one website/)).toBeInTheDocument();
  expect(sent(spy, "POST", "/prospects")).toHaveLength(0);
});

test("prospects: filters are sent to the server", async () => {
  const spy = serve({ "/prospects/meta": META, "/prospects?": { total: 0, items: [] } });
  renderApp(<Prospects />);
  await screen.findByText(/No prospects yet/);
  fireEvent.change(screen.getByLabelText("category filter"), { target: { value: "agency" } });
  fireEvent.click(screen.getByLabelText(/only with a published mailbox/));
  await waitFor(() => expect(spy.mock.calls.some((c) => String(c[0]).includes("category=agency&only_with_mailbox=true"))).toBe(true));
});

// ---------------------------------------------------------------- Prospect drawer
const detail = (over: object = {}) => ({ id: 21, title: "Northwind Docs", url: "https://northwind.example", source: "prospect", company: { id: 1, name: "Northwind Docs", website: "https://northwind.example", description: "We automate invoices.", research_status: "done", last_error: "" },
  evidence: [{ id: 51, kind: "fact", claim: "Page title: Northwind", excerpt: "Northwind Docs – paperwork automation", source_url: "https://northwind.example/", retrieved_at: "2026-10-27T10:00:00Z", confidence: "high", approved: false },
             { id: 52, kind: "hypothesis", claim: "Hypothesis (unverified inference): maybe", excerpt: "", source_url: "https://northwind.example/", retrieved_at: "2026-10-27T10:00:00Z", confidence: "low", approved: false }],
  drafts: [], application: null, contacts: [], history: [], ...over });
const draft = (over: object = {}) => ({ id: 31, version: 1, body: "Hello,\n\nI build things.", status: "draft", generator: "template", est_cost_usd: 0, rationale: "Built from the offer", warnings: ["Replace the placeholders"], portfolio_ids: ["neurogrid"], evidence_ids: [], ...over });

test("a network's drawer says why it has no score", async () => {
  const net = prospect({ id: 41, name: "LD Talent", website: "https://www.ldtalentwork.com", category: "network", offer: "network_application", offer_label: "", need_score: 0, signals: [] });
  serve({ "/opportunities/41": detail({ id: 41, title: "LD Talent" }), "/prospects/meta": META, "/prospects": { total: 1, items: [net] } });
  render(<ProspectDrawer id={41} close={() => {}} />);
  const dlg = await screen.findByRole("dialog", { name: "Prospect detail" });
  expect(await within(dlg).findByText(/A network is not scored: it does not need work done/)).toBeInTheDocument();
  expect(within(dlg).queryByText(/Public signs they may need this/)).not.toBeInTheDocument();
});

test("prospect drawer: why it is on the list, signs, mailboxes with their basis, evidence approval and a pitch that says 'I sent this myself'", async () => {
  const spy = serve({ "POST /evidence/51": { ok: true }, "POST /opportunities/21/drafts": draft(), "POST /opportunities/21/applications": { id: 1 },
    "/opportunities/21": detail({ drafts: [draft({ status: "approved", warnings: [] })] }), "/prospects/meta": META, "/prospects": { total: 1, items: [prospect()] } });
  render(<ProspectDrawer id={21} close={() => {}} />);
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

test("prospect drawer: changing the offer patches it and tells the page; a refused removal keeps the drawer open", async () => {
  const close = vi.fn(), changed = vi.fn();
  const spy = serve({ "PATCH /prospects/21": prospect(), "POST /prospects/21/research": prospect({ research_status: "researching" }),
    "DELETE /prospects/21": () => json({ detail: "An application is recorded for this prospect; it cannot be removed" }, 409),
    "/opportunities/21": detail(), "/prospects/meta": META, "/prospects": { total: 1, items: [prospect()] } });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<ProspectDrawer id={21} close={close} onChanged={changed} />);
  const dlg = await screen.findByRole("dialog", { name: "Prospect detail" });
  await within(dlg).findByText(/Public signs/);
  fireEvent.change(within(dlg).getByLabelText("offer"), { target: { value: "subcontract_capacity" } });
  await waitFor(() => expect(sent(spy, "PATCH", "/prospects/21")).toHaveLength(1));
  expect(body(sent(spy, "PATCH", "/prospects/21")[0])).toEqual({ offer: "subcontract_capacity" });
  await waitFor(() => expect(changed).toHaveBeenCalled());                                // the list behind the drawer reloads
  fireEvent.click(within(dlg).getByRole("button", { name: "Read the site again" }));
  await waitFor(() => expect(sent(spy, "POST", "/prospects/21/research")).toHaveLength(1));
  fireEvent.click(within(dlg).getByRole("button", { name: "Remove" }));
  expect(await within(dlg).findByText(/cannot be removed/)).toBeInTheDocument();
  expect(close).not.toHaveBeenCalled();                                                   // a refused removal must not close the drawer
});

// ---------------------------------------------------------------- Listing drawer
const OPP = (over: object = {}) => ({ id: 5, title: "Contract Python engineer", url: "https://news.ycombinator.com/item?id=5", source: "hn_hiring", engagement_type: "contract", remote_status: "remote",
  listing_status: "open", review_status: "new", fit_score: 72, score_override: null, score_components: { points: { skills: 30 }, max: { skills: 40 } }, fit_explanation: "Python matches",
  company_name: "Acme", budget_min: null, budget_max: null, currency: "", rate_type: "", posted_at: "2026-10-26T10:00:00Z", deadline: null, location_requirements: "Worldwide",
  recommended_action: "Draft a proposal", ease_score: 55, ease_signals: ["Company published an email to apply (+30)"],
  contacts: [{ id: 1, email: "jobs@acme.example", eligibility: "eligible", basis: "published for applications", source_url: "https://news.ycombinator.com/item?id=5", found_at: "2026-10-26T10:00:00Z" }],
  drafts: [], application: null, required_skills: ["python"], matched_skills: ["python"], missing_requirements: [], portfolio_evidence: [], description: "We need a Python engineer",
  company: { id: 1, name: "Acme", website: "https://acme.example", description: "", research_status: "done", last_error: "", website_source: "" }, evidence: [], history: [], ...over });

test("listing drawer: score, the published email with its source, and the actions in one place", async () => {
  const spy = serve({ "PATCH /opportunities/5": OPP({ review_status: "shortlisted" }), "/opportunities/5": OPP() });
  const changed = vi.fn();
  render(<OppDrawer id={5} close={() => {}} onChanged={changed} />);
  const dlg = await screen.findByRole("dialog", { name: "Opportunity detail" });
  expect(await within(dlg).findByText("jobs@acme.example")).toBeInTheDocument();
  expect(within(dlg).getByRole("link", { name: "found here" })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(within(dlg).getByRole("link", { name: /Open original listing/ })).toHaveAttribute("href", "https://news.ycombinator.com/item?id=5");
  expect(within(dlg).getByText("published for applications")).toBeInTheDocument();
  fireEvent.click(within(dlg).getByRole("button", { name: "Shortlist" }));
  await waitFor(() => expect(sent(spy, "PATCH", "/opportunities/5")).toHaveLength(1));
  expect(body(sent(spy, "PATCH", "/opportunities/5")[0])).toEqual({ review_status: "shortlisted" });
  await waitFor(() => expect(changed).toHaveBeenCalled());
});

test("listing drawer: a draft with warnings cannot be approved until you say you reviewed them", async () => {
  const spy = serve({ "POST /drafts/31/approve": { ok: true }, "/opportunities/5": OPP({ drafts: [draft()] }) });
  render(<OppDrawer id={5} close={() => {}} />);
  const dlg = await screen.findByRole("dialog", { name: "Opportunity detail" });
  const approve = await within(dlg).findByRole("button", { name: "Approve" });
  expect(approve).toBeDisabled();
  expect(within(dlg).getByText("Replace the placeholders")).toBeInTheDocument();
  fireEvent.click(within(dlg).getByLabelText("I reviewed these warnings"));
  expect(approve).toBeEnabled();
  fireEvent.click(approve);
  await waitFor(() => expect(sent(spy, "POST", "/drafts/31/approve")).toHaveLength(1));
  expect(body(sent(spy, "POST", "/drafts/31/approve")[0])).toEqual({ acknowledge_warnings: true });
});

test("listing drawer: the score can be corrected and reset", async () => {
  const spy = serve({ "PATCH /opportunities/5": OPP(), "/opportunities/5": OPP({ score_override: 90 }) });
  render(<OppDrawer id={5} close={() => {}} />);
  const dlg = await screen.findByRole("dialog", { name: "Opportunity detail" });
  const field = (await within(dlg).findByLabelText("Correct score")) as HTMLInputElement;
  expect(field.value).toBe("90");
  fireEvent.change(field, { target: { value: "55" } });
  fireEvent.click(within(dlg).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(sent(spy, "PATCH", "/opportunities/5")).toHaveLength(1));
  expect(body(sent(spy, "PATCH", "/opportunities/5")[0])).toEqual({ score_override: 55 });
  fireEvent.click(within(dlg).getByRole("button", { name: "Reset" }));
  await waitFor(() => expect(sent(spy, "PATCH", "/opportunities/5")).toHaveLength(2));
  expect(body(sent(spy, "PATCH", "/opportunities/5")[1])).toEqual({ clear_score_override: true });
});

// ---------------------------------------------------------------- Pipeline: your own follow-ups
test("pipeline: you can log your own follow-up as well as their reply, and a pitch opens as a prospect", async () => {
  const app = { id: 4, opportunity_id: 21, draft_id: 31, status: "submitted", submitted_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-20T10:00:00Z", notes: "", title: "Northwind Docs",
    company_name: "Northwind GmbH", url: "https://northwind.example", source: "prospect", conversations: [{ id: 1, direction: "out", at: "2026-10-24T10:00:00Z", summary: "Follow-up sent" }, { id: 2, direction: "in", at: "2026-10-25T10:00:00Z", summary: "Thanks, tell me more" }] };
  const spy = serve({ "POST /applications/4/conversations": app, "/applications": [app] });
  const { ctx } = renderApp(<Pipeline />);
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
  expect(ctx.open).toHaveBeenCalledWith("prospect", 21);
});

test("pipeline: a marketplace application opens as a listing; with nothing recorded it says how one gets here", async () => {
  const app = { id: 5, opportunity_id: 8, draft_id: 1, status: "replied", submitted_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-20T10:00:00Z", notes: "", title: "RAG developer",
    company_name: "RAG developer", url: "https://www.upwork.com/jobs/~1", source: "alert_upwork", conversations: [] };
  serve({ "/applications": [app] });
  const { ctx, unmount } = renderApp(<Pipeline />);
  fireEvent.click(await screen.findByRole("button", { name: "Open" }));
  expect(ctx.open).toHaveBeenCalledWith("opp", 8);
  expect(screen.getByRole("link", { name: "original listing" })).toBeInTheDocument();
  unmount();
  vi.restoreAllMocks();
  serve({ "/applications": [] });
  renderApp(<Pipeline />);
  expect(await screen.findByText(/Nothing recorded yet/)).toBeInTheDocument();
});

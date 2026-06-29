import { ExtLink } from "../components";
import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtDate, fmtUsd, safeUrl } from "../format";


const RESOURCES = [
  { name: "Freelancer.com: machine learning", url: "https://www.freelancer.com/jobs/machine-learning/", what: "Clients post AI/ML projects every day (see the Live projects tab for a ranked, live view).", how: "Bid on the site. Many bids per project: pick fresh ones with few bids." },
  { name: "Freelancer.com: artificial intelligence", url: "https://www.freelancer.com/jobs/artificial-intelligence/", what: "The AI category of the same marketplace.", how: "Turn on its email alerts, then paste them into Alert import." },
  { name: "Upwork", url: "https://www.upwork.com/freelance-jobs/machine-learning/", what: "The largest marketplace. Scraping is not allowed and its API needs approval.", how: "Save a search, turn on email alerts, paste the alert text into Alert import." },
  { name: "Contra", url: "https://contra.com/opportunities", what: "Independent-professional marketplace with open opportunities.", how: "Browse and apply on the site; use its notifications." },
  { name: "PeoplePerHour", url: "https://www.peopleperhour.com/freelance-jobs/technology-programming", what: "UK-based freelance marketplace, programming category.", how: "Use its email alerts and paste them into Alert import." },
  { name: "Guru", url: "https://www.guru.com/d/jobs/", what: "Long-running freelance marketplace.", how: "Use its job alerts." },
  { name: "Wellfound", url: "https://wellfound.com/jobs", what: "Startup jobs, including contract roles.", how: "Filter for remote and contract; set alerts." },
  { name: "A.Team", url: "https://www.a.team/", what: "Network of independent engineers. It posts roles like “Senior Independent AI Engineer” (also seen in We Work Remotely).", how: "Apply to join the network; its roles also arrive through the We Work Remotely source." },
  { name: "Toptal", url: "https://www.toptal.com/talent/apply", what: "Vetted freelancer network: clients are matched to you after you pass screening.", how: "A slower path, but clients come to you." },
  { name: "Braintrust", url: "https://www.usebraintrust.com/", what: "Talent network with a jobs board for freelancers.", how: "Create a profile and apply to jobs." },
  { name: "Turing", url: "https://www.turing.com/jobs", what: "Remote developer matching platform.", how: "Apply once and be matched to roles." },
  { name: "Arc", url: "https://arc.dev/remote-jobs", what: "Remote developer jobs, including contract roles.", how: "Filter by contract; set alerts." },
  { name: "Reddit r/forhire", url: "https://www.reddit.com/r/forhire/", what: "People post “[Hiring]” projects. Reddit's robots.txt blocks automated reading, so the app never reads it.", how: "Read it yourself and reply on Reddit." },
  { name: "Hacker News: “Freelancer? Seeking freelancer?” threads", url: "https://hn.algolia.com/?dateRange=pastYear&query=Seeking%20freelancer&sort=byDate&type=story", what: "Posted monthly until October 2025. No newer thread exists (checked 2026-10-27), so what is left is stale.", how: "Skip it. The monthly “Who is hiring?” thread is already a source." },
  { name: "Zindi", url: "https://zindi.africa/competitions", what: "Africa-focused data science and AI challenges with prizes (competitions, not client work).", how: "Good for visibility and practice." },
];

export default function Settings() {
  const sources = useLoad(() => api("/sources"));
  const portfolio = useLoad(() => api("/portfolio"));
  const usage = useLoad(() => api("/usage"));
  const [alert, setAlert] = useState("");
  const [plat, setPlat] = useState("");
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const [m, setM] = useState({ title: "", url: "", company_name: "", company_website: "", description: "" });
  const wrap = async (fn: () => Promise<string>) => { try { setMsg({ kind: "ok", text: await fn() }); } catch (e: any) { setMsg({ kind: "error", text: e.message }); } };
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) setAlert(await f.text()); };
  return (
    <>
      <h2>Sources &amp; settings</h2>
      {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
      <h3>Sources</h3>
      <Async state={sources}>{(s: any[]) => (
        <div className="scroll"><table><thead><tr><th>Source</th><th>Access</th><th>Status</th><th>Notes (checked {s[0]?.checked_at})</th></tr></thead><tbody>
          {s.map((x) => (<tr key={x.key}><td><b>{x.name}</b><div>{safeUrl(x.docs_url) && <ExtLink href={x.docs_url}>docs</ExtLink>} {safeUrl(x.terms_url) && <ExtLink href={x.terms_url}>terms</ExtLink>}</div></td><td>{x.kind}</td>
            <td><span className={`chip ${x.kind === "unavailable" ? "warn" : "ok"}`}>{x.kind === "unavailable" ? "not available / needs authorisation" : x.kind === "live" ? "live view only (not stored)" : "usable"}</span>{!x.verified && <span className="chip warn">terms not fully verified</span>}</td><td>{x.notes}</td></tr>))}
        </tbody></table></div>)}</Async>
      <div className="cols">
        <div className="panel"><h3>Alert import (Upwork, Contra, PeoplePerHour, Guru, Wellfound…)</h3>
          <p className="muted">Create saved searches with email alerts on the platform, then paste the alert email (or upload the .eml). It is parsed locally; links are kept so you can apply on the platform yourself.</p>
          <textarea value={alert} onChange={(e) => setAlert(e.target.value)} aria-label="alert email text" style={{ minHeight: 140 }} />
          <div className="row"><input type="file" accept=".eml,.txt,.html" onChange={onFile} aria-label="alert file" /><input placeholder="platform hint (optional)" value={plat} onChange={(e) => setPlat(e.target.value)} />
            <button className="primary" disabled={alert.length < 10} onClick={() => wrap(async () => { const r = await api("/alerts/import", { body: { text: alert, platform_hint: plat } }); setAlert(""); return `Parsed ${r.parsed} job link(s); CSV ${r.run.exports[0]?.filename ?? "n/a"}`; })}>Import</button></div></div>
        <div className="panel"><h3>Add a listing manually</h3>
          {(["title", "url", "company_name", "company_website"] as const).map((k) => (<div key={k}><label>{k.replace("_", " ")}</label><input aria-label={k.replace("_", " ")} value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })} /></div>))}
          <label>description</label><textarea aria-label="description" style={{ minHeight: 80 }} value={m.description} onChange={(e) => setM({ ...m, description: e.target.value })} />
          <div style={{ marginTop: 8 }}><button onClick={() => wrap(async () => { await api("/opportunities/manual", { body: m }); setM({ title: "", url: "", company_name: "", company_website: "", description: "" }); return "Added. See Opportunities."; })}>Add</button></div></div>
      </div>
      <h3>More places to find AI / ML / development projects</h3>
      <p className="muted">These sites do not allow automated reading (or have no public API), so the app does not scrape them. Open them yourself, set up saved searches with email alerts, and paste the alerts into Alert import above.</p>
      <div className="scroll" data-testid="resources"><table><thead><tr><th>Where</th><th>What it is</th><th>How to use it</th></tr></thead><tbody>
        {RESOURCES.map((r) => (<tr key={r.name}><td><a href={r.url} target="_blank" rel="noreferrer"><b>{r.name} ↗</b></a></td><td>{r.what}</td><td>{r.how}</td></tr>))}
      </tbody></table></div>
      <h3>Portfolio evidence (only verified items are cited in drafts)</h3>
      <Async state={portfolio}>{(p: any[]) => (<>{p.map((x) => (
        <div className="panel" key={x.id} style={{ marginBottom: 8 }}>
          <div className="row"><b>{x.title}</b><span className={`chip ${x.verified ? "ok" : "warn"}`}>{x.verified ? "verified" : "unverified"}</span><span style={{ flex: 1 }} />
            <button onClick={() => wrap(async () => { await api(`/portfolio/${x.id}`, { method: "PATCH", body: { verified: !x.verified } }); portfolio.reload(true); return "Updated. Click “Rescore all” to apply."; })}>{x.verified ? "Mark unverified" : "I confirm this is accurate"}</button></div>
          <div className="muted">{x.summary} {safeUrl(x.url) && <ExtLink href={x.url}>{x.url}</ExtLink>}</div><div className="muted">Note: {x.verified_note}</div></div>))}
        <button onClick={() => wrap(async () => `Rescored ${(await api("/opportunities/rescore", { method: "POST" })).rescored} opportunities`)}>Rescore all</button></>)}</Async>
      <h3>Usage &amp; cost</h3>
      <Async state={usage} empty={(u: any) => (u.events.length ? null : "No paid usage recorded. Free sources cost $0; template drafts cost $0.")}>{(u: any) => (<>
        <p>This month: {fmtUsd(u.month_spend_usd)} of ${u.monthly_budget_usd} budget. <span className="muted">{u.llm_price_note}</span></p>
        <table><thead><tr><th>When</th><th>Kind</th><th>Provider</th><th>Cost</th><th>Estimated</th></tr></thead><tbody>{u.events.slice(0, 20).map((e: any, i: number) => (<tr key={i}><td>{fmtDate(e.at)}</td><td>{e.kind}</td><td>{e.provider}</td><td>{fmtUsd(e.cost_usd)}</td><td>{e.estimated ? "yes" : "no"}</td></tr>))}</tbody></table></>)}</Async>
      <h3>Backup</h3>
      <button onClick={() => wrap(async () => `Backup written: ${(await api("/admin/backup", { method: "POST" })).path}`)}>Back up database now</button>
    </>
  );
}

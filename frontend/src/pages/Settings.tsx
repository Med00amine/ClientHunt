import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtDate, fmtUsd } from "../format";

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
          {s.map((x) => (<tr key={x.key}><td><b>{x.name}</b><div><a href={x.docs_url} target="_blank" rel="noreferrer">docs</a> {x.terms_url && <a href={x.terms_url} target="_blank" rel="noreferrer">terms</a>}</div></td><td>{x.kind}</td>
            <td><span className={`chip ${x.kind === "unavailable" ? "warn" : "ok"}`}>{x.kind === "unavailable" ? "not available / needs authorisation" : "usable"}</span>{!x.verified && <span className="chip warn">terms not fully verified</span>}</td><td>{x.notes}</td></tr>))}
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
      <h3>Portfolio evidence (only verified items are cited in drafts)</h3>
      <Async state={portfolio}>{(p: any[]) => (<>{p.map((x) => (
        <div className="panel" key={x.id} style={{ marginBottom: 8 }}>
          <div className="row"><b>{x.title}</b><span className={`chip ${x.verified ? "ok" : "warn"}`}>{x.verified ? "verified" : "unverified"}</span><span style={{ flex: 1 }} />
            <button onClick={() => wrap(async () => { await api(`/portfolio/${x.id}`, { method: "PATCH", body: { verified: !x.verified } }); portfolio.reload(true); return "Updated. Click “Rescore all” to apply."; })}>{x.verified ? "Mark unverified" : "I confirm this is accurate"}</button></div>
          <div className="muted">{x.summary} {x.url && <a href={x.url} target="_blank" rel="noreferrer">{x.url}</a>}</div><div className="muted">Note: {x.verified_note}</div></div>))}
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

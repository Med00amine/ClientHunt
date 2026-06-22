import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtBudget, fmtDate, fmtUsd } from "../format";

export default function Opportunities({ openId, setOpenId }: { openId: number | null; setOpenId: (id: number | null) => void }) {
  const [f, setF] = useState({ q: "", source: "", min_score: 0, sort: "score", show_excluded: false });
  const qs = `q=${encodeURIComponent(f.q)}&source=${f.source}&min_score=${f.min_score}&sort=${f.sort}&show_excluded=${f.show_excluded}`;
  const list = useLoad(() => api(`/opportunities?${qs}`), [qs]);
  const sources = useLoad(() => api("/sources"));
  return (
    <>
      <h2>Opportunities</h2>
      <div className="row" style={{ marginBottom: 10 }}>
        <input placeholder="Search title / company / text" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} aria-label="search" />
        <select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} aria-label="source filter"><option value="">All sources</option>
          {(sources.data ?? []).map((s: any) => <option key={s.key} value={s.key}>{s.key}</option>)}<option value="alert_upwork">alert_upwork</option></select>
        <label style={{ display: "inline" }}>min score <input type="number" style={{ width: 70 }} value={f.min_score} onChange={(e) => setF({ ...f, min_score: Number(e.target.value) })} /></label>
        <select value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value })} aria-label="sort"><option value="score">Best fit</option><option value="ease">Easiest to reach</option><option value="newest">Newest found</option><option value="posted">Posted date</option></select>
        <label style={{ display: "inline" }}><input type="checkbox" checked={f.show_excluded} onChange={(e) => setF({ ...f, show_excluded: e.target.checked })} /> show excluded</label>
      </div>
      <Async state={list} empty={(d: any) => (d.items.length ? null : "No opportunities match. Run a research or import alerts first; nothing here is sample data.")}>
        {(d: any) => (<>
          <p className="muted">{d.total} opportunities (score is a prioritisation heuristic, not a prediction of winning).</p>
          <div className="scroll"><table><thead><tr><th>Fit</th><th title="heuristic: how easy it looks to reach the client">Easy</th><th>Title</th><th>Source</th><th>Company</th><th>Budget</th><th>Posted</th><th>Location</th><th>Next action</th><th>Research</th><th>Link</th></tr></thead><tbody>
            {d.items.map((o: any) => (
              <tr key={o.id} className="click" onClick={() => setOpenId(o.id)}>
                <td className="score">{Math.round(o.fit_score)}{o.score_override != null && <span className="chip warn">edited</span>}</td>
                <td>{Math.round(o.ease_score)}{o.apply_method === "email" && <span className="chip ok">email</span>}</td>
                <td>{o.title.slice(0, 90)} {o.review_status !== "new" && <span className="chip">{o.review_status}</span>}</td><td>{o.source}</td><td>{o.company_name || <span className="muted">unknown</span>}</td>
                <td>{fmtBudget(o)}</td><td>{o.posted_at ? new Date(o.posted_at).toLocaleDateString() : "—"}</td><td>{o.location_requirements.slice(0, 40) || "unknown"}</td>
                <td>{o.recommended_action}</td><td>{o.research_status}</td>
                <td><a href={o.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>Open ↗</a></td></tr>))}
          </tbody></table></div></>)}
      </Async>
      {openId && <Detail id={openId} close={() => { setOpenId(null); list.reload(true); }} />}
    </>
  );
}

function Detail({ id, close }: { id: number; close: () => void }) {
  const st = useLoad(() => api(`/opportunities/${id}`), [id]);
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const [site, setSite] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<any>, ok?: string) => {
    setBusy(true); setMsg(null);
    try { const r = await fn(); if (ok) setMsg({ kind: "ok", text: ok }); st.reload(true); return r; }
    catch (e: any) { setMsg({ kind: "error", text: e.message + (e.detail?.warnings ? ": " + e.detail.warnings.join("; ") : "") }); }
    finally { setBusy(false); }
  };
  return (
    <aside className="detail" role="dialog" aria-label="Opportunity detail">
      <div className="row"><button onClick={close}>✕ Close</button></div>
      <Async state={st}>
        {(o: any) => (<>
          <h2>{o.title}</h2>
          <div className="row"><a href={o.url} target="_blank" rel="noreferrer"><b>Open original listing ↗</b></a><span className="chip">{o.source}</span><span className="chip">{o.engagement_type}</span><span className="chip">{o.remote_status}</span>
            <span className={`chip ${o.listing_status === "open" ? "ok" : "warn"}`}>listing {o.listing_status}</span></div>
          {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
          <div className="cols" style={{ marginTop: 8 }}>
            <div className="panel"><div className="score" style={{ fontSize: 28 }}>{Math.round(o.fit_score)}<span className="muted" style={{ fontSize: 14 }}> / 100</span></div>
              {o.score_components?.points && Object.entries(o.score_components.points).map(([k, v]: any) => (
                <div key={k}><div className="row"><span style={{ width: 90 }}>{k}</span><span className="muted">{v} / {o.score_components.max[k]}</span></div>
                  <div className="bar"><span style={{ width: `${(v / o.score_components.max[k]) * 100}%` }} /></div></div>))}
              <p>{o.fit_explanation}</p>
              <div className="row"><label style={{ display: "inline" }}>Correct score <input type="number" min={0} max={100} style={{ width: 70 }} id="ov" defaultValue={o.score_override ?? ""} /></label>
                <button onClick={() => run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { score_override: Number((document.getElementById("ov") as HTMLInputElement).value) } }))}>Save</button>
                {o.score_override != null && <button onClick={() => run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { clear_score_override: true } }))}>Reset</button>}</div>
            </div>
            <div className="panel">
              <div><b>Company:</b> {o.company_name || "not named in listing"}</div>
              <div><b>Budget:</b> {fmtBudget(o)}</div><div><b>Posted:</b> {fmtDate(o.posted_at)}</div><div><b>Deadline:</b> {o.deadline ? fmtDate(o.deadline) : "not stated"}</div>
              <div><b>Location:</b> {o.location_requirements || "not stated"}</div><div><b>Last verified:</b> {fmtDate(o.last_verified_at)}</div>
              <div><b>Next action:</b> {o.recommended_action}</div>
              <div className="row" style={{ marginTop: 6 }}>
                <button onClick={() => run(() => api(`/opportunities/${id}/recheck`, { method: "POST" }).then((r) => setMsg({ kind: "ok", text: r.message })))} disabled={busy}>Re-check listing</button>
                {o.review_status !== "excluded" ? <button className="danger" onClick={() => { const r = prompt("Why exclude it?") ?? ""; run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { review_status: "excluded", exclusion_reason: r } })); }}>Exclude</button>
                  : <button onClick={() => run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { review_status: "new" } }))}>Restore</button>}
                <button onClick={() => run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { review_status: "shortlisted" } }))}>Shortlist</button></div>
            </div>
          </div>
          <h3>Easy to reach: {Math.round(o.ease_score)} / 100 <span className="muted" style={{ fontSize: 12 }}>(heuristic, not a hiring prediction)</span></h3>
          {(o.ease_signals ?? []).length ? o.ease_signals.map((x: string) => <div className="muted" key={x}>• {x}</div>) : <p className="muted">No easy-to-reach signals found.</p>}
          <h3>Published emails</h3>
          {(o.contacts ?? []).length === 0 ? <p className="muted">No email published for this listing. Use “Research company” to look for a careers/contact mailbox on the company's own site.</p> : o.contacts.map((c: any) => (
            <div className="panel" key={c.id} style={{ marginBottom: 6 }}><b>{c.email}</b> <span className="chip">{c.eligibility.replace("_", " ")}</span>
              <div className="muted">{c.basis}</div><div className="muted">Found: <a href={c.source_url} target="_blank" rel="noreferrer">{c.source_url}</a> · {fmtDate(c.found_at)}</div></div>))}
          <h3>Skills</h3>
          <div>Required (detected): {o.required_skills.map((s: string) => <span className="chip" key={s}>{s}</span>)}</div>
          <div>Matched with yours: {o.matched_skills.map((s: string) => <span className="chip ok" key={s}>{s}</span>)}</div>
          <div>Missing / concerns: {o.missing_requirements.length ? o.missing_requirements.map((s: string) => <span className="chip warn" key={s}>{s}</span>) : "none detected"}</div>
          <h3>Relevant portfolio</h3>
          {o.portfolio_evidence.length === 0 ? <p className="muted">No portfolio item overlaps this listing.</p> : o.portfolio_evidence.map((e: any) => (
            <div key={e.id}>{e.title} <span className={`chip ${e.verified ? "ok" : "warn"}`}>{e.verified ? "verified" : "unverified – not cited"}</span> <span className="muted">{e.overlap.join(", ")}</span></div>))}
          <h3>Description</h3><pre className="draft">{o.description}</pre>
          <h3>Company intelligence</h3>
          {!o.company ? <p className="muted">The listing does not name a company; no research is possible.</p> : (<>
            <div className="row"><input style={{ minWidth: 260 }} placeholder="Official website https://…" defaultValue={o.company.website} onChange={(e) => setSite(e.target.value)} aria-label="company website" />
              <button onClick={() => run(async () => { if (site) await api(`/opportunities/${id}`, { method: "PATCH", body: { company_website: site } }); return api(`/opportunities/${id}/research`, { method: "POST" }); }, "Research finished")} disabled={busy}>Research company</button></div>
            <p className="muted">Website source: {o.company.website_source || "none"} · status: {o.company.research_status}{o.company.last_error && ` · ${o.company.last_error}`}. Pages are fetched respecting robots.txt; retrieved text is treated as untrusted data.</p>
            {o.company.description && <p>{o.company.description}</p>}
            {o.evidence.filter((e: any) => e.kind === "fact").map((e: any) => (
              <div className="fact" key={e.id}><b>Verified excerpt</b> · {e.claim}<div className="muted">“{e.excerpt}” — <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_url}</a> · {fmtDate(e.retrieved_at)} · {e.confidence}</div>
                <label style={{ display: "inline" }}><input type="checkbox" checked={e.approved} onChange={(ev) => run(() => api(`/evidence/${e.id}`, { body: { approved: ev.target.checked } }))} /> approve for use in proposals</label></div>))}
            {o.evidence.filter((e: any) => e.kind === "hypothesis").map((e: any) => (<div className="hyp" key={e.id}><b>Hypothesis (not a fact, never used in drafts)</b> · {e.claim}</div>))}
          </>)}
          <h3>Proposal drafts</h3>
          <div className="row"><button className="primary" onClick={() => run(() => api(`/opportunities/${id}/drafts`, { method: "POST" }), "Draft generated")} disabled={busy}>{o.drafts.length ? "Regenerate draft" : "Generate proposal draft"}</button>
            <span className="muted">Drafts are never sent. You submit on the platform yourself.</span></div>
          {o.drafts.map((d: any) => <Draft key={d.id} d={d} oppId={id} run={run} />)}
          {o.application && (<><h3>Application</h3><p>Recorded as <b>{o.application.status}</b> on {fmtDate(o.application.submitted_at)}. Track it in the Pipeline tab.</p></>)}
          {o.history.length > 0 && (<><h3>Change history</h3>{o.history.map((h: any, i: number) => <div className="muted" key={i}>{fmtDate(h.at)}: {JSON.stringify(h.change)}</div>)}</>)}
        </>)}
      </Async>
    </aside>
  );
}

function Draft({ d, oppId, run }: { d: any; oppId: number; run: (fn: () => Promise<any>, ok?: string) => Promise<any> }) {
  const [body, setBody] = useState(d.body);
  const [ack, setAck] = useState(false);
  const dirty = body !== d.body;
  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <div className="row"><b>v{d.version}</b><span className={`chip ${d.status === "approved" ? "ok" : d.status === "rejected" ? "bad" : ""}`}>{d.status}</span><span className="chip">{d.generator}</span><span className="muted">est. cost {fmtUsd(d.est_cost_usd)}</span></div>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} aria-label={`draft v${d.version}`} />
      <p className="muted"><b>Personalisation rationale:</b> {d.rationale}</p>
      {d.warnings.length > 0 && (<div className="alert warn"><b>Unsupported-claim warnings</b><ul>{d.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>
        <label style={{ display: "inline" }}><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I reviewed these warnings</label></div>)}
      <div className="muted">Portfolio evidence cited: {d.portfolio_ids.join(", ") || "none"} · approved facts used: {d.evidence_ids.length}</div>
      <div className="row" style={{ marginTop: 8 }}>
        <button onClick={() => run(() => api(`/drafts/${d.id}`, { method: "PATCH", body: { body } }), "Saved (approval reset if text changed)")} disabled={!dirty}>Save edit</button>
        <button className="primary" disabled={dirty || d.status === "approved" || (d.warnings.length > 0 && !ack)} onClick={() => run(() => api(`/drafts/${d.id}/approve`, { body: { acknowledge_warnings: ack } }), "Approved. Now submit it on the platform yourself.")}>Approve</button>
        <button className="danger" onClick={() => run(() => api(`/drafts/${d.id}/reject`, { method: "POST" }))}>Reject</button>
        {d.status === "approved" && <button onClick={() => run(() => api(`/opportunities/${oppId}/applications`, { body: { draft_id: d.id } }), "Application recorded")}>I submitted this on the platform</button>}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { fmtBudget, fmtDate } from "../format";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Mail, Notice } from "../ui";
import { Draft, EvidenceList, PITCH_WORDS, useActions } from "./shared";

const STATUS: Record<string, [string, string]> = {
  not_started: ["not read yet", ""], researching: ["reading the site…", "warn"], done: ["site read", "ok"],
  no_evidence: ["nothing useful found", "warn"], failed: ["could not read it", "bad"], no_website: ["no website", "bad"],
};
export const CATEGORY = { company: "Company", agency: "Agency", network: "Network" } as Record<string, string>;
export { STATUS };

type Drawer = { id: number; close: () => void; onChanged?: () => void };

function Frame({ label, close, children }: { label: string; close: () => void; children: React.ReactNode }) {
  return (
    <aside className="detail" role="dialog" aria-label={label}>
      <div className="row"><button onClick={close}>✕ Close</button></div>
      {children}
    </aside>
  );
}

function ScoreFix({ o, id, run }: { o: any; id: number; run: (fn: () => Promise<any>) => void }) {
  const [v, setV] = useState(String(o.score_override ?? ""));
  return (
    <div className="row">
      <label className="in">Correct score <input type="number" min={0} max={100} style={{ width: 70 }} value={v} onChange={(e) => setV(e.target.value)} /></label>
      <button disabled={v === ""} onClick={() => run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { score_override: Number(v) } }))}>Save</button>
      {o.score_override != null && <button onClick={() => run(() => api(`/opportunities/${id}`, { method: "PATCH", body: { clear_score_override: true } }))}>Reset</button>}
    </div>
  );
}

// ---------------------------------------------------------------- a listing
export function OppDrawer({ id, close, onChanged }: Drawer) {
  const st = useLoad(() => api(`/opportunities/${id}`), [id]);
  const [site, setSite] = useState("");
  const { msg, setMsg, busy, run } = useActions(() => { st.reload(true); onChanged?.(); });
  const patch = (body: object) => run(() => api(`/opportunities/${id}`, { method: "PATCH", body }));
  return (
    <Frame label="Opportunity detail" close={close}>
      <Async state={st}>
        {(o: any) => (<>
          <h2 style={{ margin: "8px 0" }}>{o.title}</h2>
          <div className="row"><ExtLink href={o.url}><b>Open original listing ↗</b></ExtLink><Chip>{o.source}</Chip>{o.engagement_type !== "unknown" && <Chip>{o.engagement_type}</Chip>}{o.remote_status !== "unknown" && <Chip>{o.remote_status}</Chip>}
            <Chip tone={o.listing_status === "open" ? "ok" : "warn"}>listing {o.listing_status}</Chip></div>
          <Notice msg={msg} />
          <div className="row" style={{ margin: "8px 0" }}>
            <button onClick={() => patch({ review_status: "shortlisted" })} disabled={busy}>Shortlist</button>
            {o.review_status !== "excluded"
              ? <button className="danger" onClick={() => { const r = prompt("Why exclude it?") ?? ""; patch({ review_status: "excluded", exclusion_reason: r }); }}>Exclude</button>
              : <button onClick={() => patch({ review_status: "new" })}>Restore</button>}
            <button disabled={busy} onClick={() => run(() => api(`/opportunities/${id}/recheck`, { method: "POST" }).then((r) => setMsg({ kind: "ok", text: r.message })))}>Re-check listing</button>
          </div>

          <div className="cols">
            <div className="panel">
              <div className="score" style={{ fontSize: 28 }}>{Math.round(o.fit_score)}<span className="muted" style={{ fontSize: 14 }}> / 100 fit</span></div>
              {o.score_components?.points && Object.entries(o.score_components.points).map(([k, v]: any) => (
                <div key={k}><div className="row"><span style={{ width: 90 }}>{k}</span><span className="muted">{v} / {o.score_components.max[k]}</span></div>
                  <div className="bar"><span style={{ width: `${(v / o.score_components.max[k]) * 100}%` }} /></div></div>))}
              <p>{o.fit_explanation}</p>
              <Fold title="Correct the score" plain><ScoreFix o={o} id={id} run={run} /></Fold>
            </div>
            <div className="panel">
              <div><b>Company:</b> {o.company_name || "not named in listing"}</div>
              <div><b>Budget:</b> {fmtBudget(o)}</div>
              <div><b>Posted:</b> {fmtDate(o.posted_at)}</div>
              <div><b>Location:</b> {o.location_requirements || "not stated"}</div>
              {o.deadline && <div><b>Deadline:</b> {fmtDate(o.deadline)}</div>}
              <div><b>Next action:</b> {o.recommended_action}</div>
            </div>
          </div>

          <h3>Published email</h3>
          {(o.contacts ?? []).length === 0 ? <p className="muted">None for this listing.</p> : o.contacts.map((c: any) => <Mail key={c.id} c={c} detail />)}
          {(o.ease_signals ?? []).length > 0 && (
            <Fold title={`Why it looks easy to reach: ${Math.round(o.ease_score)} / 100`}>{o.ease_signals.map((x: string) => <div className="muted" key={x}>• {x}</div>)}<div className="muted">A heuristic, not a hiring prediction.</div></Fold>)}

          <h3>Proposal draft</h3>
          <div className="muted">{o.portfolio_evidence.length === 0 ? "No portfolio item overlaps this listing." : "Your portfolio for this listing:"}{" "}
            {o.portfolio_evidence.map((e: any) => <Chip key={e.id} tone={e.verified ? "ok" : "warn"} title={e.overlap.join(", ")}>{e.title}{e.verified ? "" : " (unverified, not cited)"}</Chip>)}</div>
          <div className="row"><button className="primary" onClick={() => run(() => api(`/opportunities/${id}/drafts`, { method: "POST" }), "Draft generated")} disabled={busy}>{o.drafts.length ? "Regenerate draft" : "Generate proposal draft"}</button>
            <span className="muted">Never sent by ClientHunt.</span></div>
          {o.drafts.map((d: any) => <Draft key={d.id} d={d} oppId={id} run={run} />)}
          {o.application && <p>Recorded as <b>{o.application.status}</b> on {fmtDate(o.application.submitted_at)}. Track it in Pipeline.</p>}

          <h3>Details</h3>
          <Fold title="Skills">
            <div>Required: {o.required_skills.map((s: string) => <Chip key={s}>{s}</Chip>)}</div>
            <div>Matched with yours: {o.matched_skills.map((s: string) => <Chip tone="ok" key={s}>{s}</Chip>)}</div>
            <div>Missing / concerns: {o.missing_requirements.length ? o.missing_requirements.map((s: string) => <Chip tone="warn" key={s}>{s}</Chip>) : "none detected"}</div>
          </Fold>
          <Fold title="Description"><pre className="draft">{o.description}</pre></Fold>
          <Fold title="Company research">
            {!o.company ? <p className="muted">The listing does not name a company, so there is nothing to research.</p> : (<>
              <div className="row"><input style={{ minWidth: 260 }} placeholder="Official website https://…" defaultValue={o.company.website} onChange={(e) => setSite(e.target.value)} aria-label="company website" />
                <button onClick={() => run(async () => { if (site) await api(`/opportunities/${id}`, { method: "PATCH", body: { company_website: site } }); return api(`/opportunities/${id}/research`, { method: "POST" }); }, "Research finished")} disabled={busy}>Research company</button></div>
              <div className="muted">status: {o.company.research_status}{o.company.last_error && ` · ${o.company.last_error}`}. Only their public pages are read (robots.txt respected).</div>
              {o.company.description && <p>{o.company.description}</p>}
              <EvidenceList evidence={o.evidence} run={run} />
            </>)}
          </Fold>
          {o.history.length > 0 && <Fold title="Change history">{o.history.map((h: any, i: number) => <div className="muted" key={i}>{fmtDate(h.at)}: {JSON.stringify(h.change)}</div>)}</Fold>}
        </>)}
      </Async>
    </Frame>
  );
}

// ---------------------------------------------------------------- a prospect
export function ProspectDrawer({ id, close, onChanged }: Drawer) {
  const meta = useLoad(() => api("/prospects/meta")).data;
  const st = useLoad(() => api(`/opportunities/${id}`), [id]);
  const row = useLoad(() => api("/prospects"), [id]);
  const reloadAll = () => { st.reload(true); row.reload(true); onChanged?.(); };
  const { msg, setMsg, busy, run } = useActions(reloadAll);
  const p = row.data?.items.find((x: any) => x.id === id);
  useEffect(() => { if (p?.research_status === "researching") { const t = setTimeout(reloadAll, 2500); return () => clearTimeout(t); } }, [p?.research_status, row.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const patch = (body: object) => run(() => api(`/prospects/${id}`, { method: "PATCH", body }));
  const offer = p ? meta?.offers?.[p.offer] : null;
  const [label, tone] = STATUS[p?.research_status] ?? [p?.research_status, ""];
  return (
    <Frame label="Prospect detail" close={close}>
      <Async state={st}>
        {(o: any) => !p ? <p className="muted">Loading…</p> : (<>
          <h2 style={{ margin: "8px 0" }}>{p.name}</h2>
          <div className="row"><ExtLink href={p.website}><b>Open their website ↗</b></ExtLink><Chip>{CATEGORY[p.category] ?? p.category}</Chip><Chip tone={tone}>{label}</Chip>
            {o.application && <Chip tone="ok">contacted {fmtDate(o.application.submitted_at)}</Chip>}</div>
          <Notice msg={msg} />
          <div className="panel" style={{ marginTop: 8 }}>
            <b>Why it is on your list</b>
            {p.evidence_quote || p.evidence_url ? (<div>{p.evidence_quote && <>“{p.evidence_quote}”</>} {p.evidence_url && <ExtLink href={p.evidence_url}>source ↗</ExtLink>}</div>)
              : <div className="muted">You added it yourself.</div>}
            {offer && <div className="muted" style={{ marginTop: 6 }}><b>You would deliver:</b> {offer.deliverable} <b>First step:</b> {offer.first_step}</div>}
            <Fold title="Change kind or offer" plain>
              <div className="row">
                <label className="in">Kind <select value={p.category} onChange={(e) => patch({ category: e.target.value })} aria-label="kind">
                  {Object.entries(meta?.categories ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</select></label>
                <label className="in">Offer <select value={p.offer} onChange={(e) => patch({ offer: e.target.value })} aria-label="offer">
                  {Object.entries(meta?.offers ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</select></label>
              </div>
            </Fold>
          </div>

          {p.category === "network"
            ? <p className="muted">A network is not scored: it does not need work done. Read its own words below, then check who can apply, location limits and hours.</p>
            : (<>
              <h3>Public signs they may need this: {Math.round(p.need_score)} / 100 <span className="muted" style={{ fontSize: 12 }}>(hints, not proof)</span></h3>
              {p.signals.length ? p.signals.map((s: string) => <div className="muted" key={s}>• {s}</div>) : <p className="muted">No signs found yet{p.research_status === "not_started" ? ": read the site first" : ""}.</p>}
            </>)}

          <h3>Mailboxes the company published</h3>
          {p.contacts.length === 0 ? <p className="muted">None found. Use a contact form on their site if they have one.</p> : p.contacts.map((c: any) => <Mail key={c.id} c={c} detail />)}

          <h3>What their site says</h3>
          {o.company?.description && <p>{o.company.description}</p>}
          {o.evidence.length === 0 ? <p className="muted">Nothing kept yet.</p> : <EvidenceList evidence={o.evidence} run={run} />}

          <h3>Pitch</h3>
          <div className="row"><button className="primary" disabled={busy} onClick={() => run(() => api(`/opportunities/${id}/drafts`, { method: "POST" }), "Pitch drafted")}>{o.drafts.length ? "Regenerate pitch" : "Draft a pitch"}</button>
            <span className="muted">Never sent by ClientHunt. Built from the offer, your verified portfolio and the sentences you approved.</span></div>
          {o.drafts.map((d: any) => <Draft key={d.id} d={d} oppId={id} run={run} words={PITCH_WORDS} />)}
          {o.application && <p>Recorded as <b>{o.application.status}</b>. Log replies in Pipeline.</p>}

          <div className="row" style={{ marginTop: 16 }}>
            <button disabled={busy || p.research_status === "researching"} onClick={() => run(() => api(`/prospects/${id}/research`, { method: "POST" }).then(() => setMsg({ kind: "ok", text: "Reading their website again…" })))}>Read the site again</button>
            <button className="danger" disabled={busy || !!o.application} title={o.application ? "Contacted prospects stay in the record" : ""}
              onClick={() => { if (confirm("Remove this prospect and its saved mailboxes and drafts?")) run(() => api(`/prospects/${id}`, { method: "DELETE" })).then((r) => { if (r) close(); }); }}>Remove</button>
          </div>
        </>)}
      </Async>
    </Frame>
  );
}

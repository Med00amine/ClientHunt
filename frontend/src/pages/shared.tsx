import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { fmtDate, fmtUsd } from "../format";
import { Chip, Msg } from "../ui";

export type Run = (fn: () => Promise<any>, ok?: string) => Promise<any>;

/** Runs an action, shows its outcome, and reloads the thing on screen. Errors carry the server's warnings when it sends some. */
export function useActions(reload: (silent?: boolean) => void) {
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);
  const run: Run = async (fn, ok) => {
    setBusy(true); setMsg(null);
    try { const r = await fn(); if (ok) setMsg({ kind: "ok", text: ok }); reload(true); return r; }
    catch (e: any) { setMsg({ kind: "error", text: e.message + (e.detail?.warnings ? ": " + e.detail.warnings.join("; ") : "") }); }
    finally { setBusy(false); }
  };
  return { msg, setMsg, busy, run };
}

/** What the buttons of a draft say. A listing is answered on its platform; a prospect is written to by the user. */
export type Words = { approved: string; sent: string; recorded: string };
export const LISTING_WORDS: Words = { approved: "Approved. Now submit it on the platform yourself.", sent: "I submitted this on the platform", recorded: "Application recorded" };
export const PITCH_WORDS: Words = { approved: "Approved. Now send it yourself, from your own mailbox or the site's contact form.", sent: "I sent this myself", recorded: "Recorded as contacted" };

export function Draft({ d, oppId, run, words = LISTING_WORDS }: { d: any; oppId: number; run: Run; words?: Words }) {
  const [body, setBody] = useState(d.body);
  const [ack, setAck] = useState(false);
  const dirty = body !== d.body;
  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <div className="row"><b>v{d.version}</b><Chip tone={d.status === "approved" ? "ok" : d.status === "rejected" ? "bad" : ""}>{d.status}</Chip><Chip>{d.generator}</Chip><span className="muted">est. cost {fmtUsd(d.est_cost_usd)}</span></div>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} aria-label={`draft v${d.version}`} />
      <div className="muted">{d.rationale}{d.portfolio_ids.length > 0 && ` · cites: ${d.portfolio_ids.join(", ")}`}</div>
      {d.warnings.length > 0 && (<div className="alert warn"><b>Unsupported-claim warnings</b><ul>{d.warnings.map((w: string) => <li key={w}>{w}</li>)}</ul>
        <label className="in"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I reviewed these warnings</label></div>)}
      <div className="row" style={{ marginTop: 8 }}>
        <button onClick={() => run(() => api(`/drafts/${d.id}`, { method: "PATCH", body: { body } }), "Saved (approval reset if text changed)")} disabled={!dirty}>Save edit</button>
        <button className="primary" disabled={dirty || d.status === "approved" || (d.warnings.length > 0 && !ack)} onClick={() => run(() => api(`/drafts/${d.id}/approve`, { body: { acknowledge_warnings: ack } }), words.approved)}>Approve</button>
        <button className="danger" onClick={() => run(() => api(`/drafts/${d.id}/reject`, { method: "POST" }))}>Reject</button>
        {d.status === "approved" && <button onClick={() => run(() => api(`/opportunities/${oppId}/applications`, { body: { draft_id: d.id } }), words.recorded)}>{words.sent}</button>}
      </div>
    </div>
  );
}

/** Verbatim excerpts from the company's own pages (approve the ones a draft may quote) and the unverified hypotheses. */
export function EvidenceList({ evidence, run }: { evidence: any[]; run: Run }) {
  return (
    <>
      {evidence.filter((e) => e.kind === "fact").map((e) => (
        <div className="fact" key={e.id}><b>Verified excerpt</b> · {e.claim}<div className="muted">“{e.excerpt}” — <ExtLink href={e.source_url}>{e.source_url}</ExtLink> · {fmtDate(e.retrieved_at)} · {e.confidence}</div>
          <label className="in"><input type="checkbox" checked={e.approved} onChange={(ev) => run(() => api(`/evidence/${e.id}`, { body: { approved: ev.target.checked } }))} /> approve for use in proposals</label></div>))}
      {evidence.filter((e) => e.kind === "hypothesis").map((e) => (<div className="hyp" key={e.id}><b>Hypothesis (not a fact, never used in drafts)</b> · {e.claim}</div>))}
    </>
  );
}

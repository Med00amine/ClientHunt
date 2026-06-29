import { ExtLink } from "../components";
import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtDate, safeUrl } from "../format";
import OneFile from "./OneFile";

const ELIG: Record<string, string> = { eligible: "ok", review_required: "warn", not_eligible: "bad", unknown: "" };

export default function Leads({ openOpp }: { openOpp: (id: number) => void }) {
  const [f, setF] = useState({ has_email: true, hide_restricted: true, min_ease: 0, min_fit: 35, q: "" });
  const qs = `has_email=${f.has_email}&hide_restricted=${f.hide_restricted}&min_ease=${f.min_ease}&min_fit=${f.min_fit}&q=${encodeURIComponent(f.q)}`;
  const st = useLoad(() => api(`/leads?${qs}`), [qs]);
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const download = async () => {
    setBusy(true); setMsg(null);
    try {
      const ex = await api("/exports/emails", { method: "POST" });
      if (ex.status !== "ok") throw new Error(ex.error || "Export failed");
      setMsg({ kind: "ok", text: `${ex.filename} created with ${ex.row_count} emails. Downloading…` });
      window.location.href = ex.download_url;
    } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
    setBusy(false);
  };
  const copy = async (emails: string[]) => {
    try { await navigator.clipboard.writeText(emails.join("\n")); setMsg({ kind: "ok", text: `${emails.length} emails copied.` }); }
    catch { setMsg({ kind: "error", text: "Copy is blocked by the browser. Use the CSV download." }); }
  };

  return (
    <>
      <h2>Leads: companies hiring now, with their published email</h2>
      <p className="muted">
        These are companies that posted a job or project and published an address to reply to (or a careers/jobs mailbox on their own website).
        Sorted by fit for you plus how easy it looks to reach them. Every email shows where it was found and when. Emails are never guessed.
      </p>
      <OneFile title="Download the leads (and everything else) in ONE file" />
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="row">
          <button onClick={download} disabled={busy}>⬇ Only the emails (CSV)</button>
          <button onClick={() => copy(st.data?.emails ?? [])} disabled={!st.data?.emails?.length}>Copy the {st.data?.emails?.length ?? 0} emails shown</button>
          <span className="muted">The Excel file has a Leads sheet with the same rows, plus where each email was found.</span>
        </div>
        {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
      </div>
      <div className="row" style={{ marginBottom: 10 }}>
        <input placeholder="Search company / title / text" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} aria-label="search leads" />
        <label style={{ display: "inline" }}><input type="checkbox" checked={f.has_email} onChange={(e) => setF({ ...f, has_email: e.target.checked })} /> only with an email</label>
        <label style={{ display: "inline" }}><input type="checkbox" checked={f.hide_restricted} onChange={(e) => setF({ ...f, hide_restricted: e.target.checked })} /> hide “US only / must live there”</label>
        <label style={{ display: "inline" }}>min easy-to-reach <input type="number" style={{ width: 70 }} value={f.min_ease} onChange={(e) => setF({ ...f, min_ease: Number(e.target.value) })} /></label>
        <label style={{ display: "inline" }}>min fit for you <input type="number" style={{ width: 70 }} value={f.min_fit} onChange={(e) => setF({ ...f, min_fit: Number(e.target.value) })} /></label>
      </div>
      <Async state={st} empty={(d: any) => (d.items.length ? null : "No leads yet. Go to Research and run “Easy to reach: hiring now, apply by email”.")}>
        {(d: any) => (
          <div className="scroll"><table><thead><tr><th title="How easy it looks to reach the client and be considered. A heuristic, not a hiring prediction.">Easy to reach</th><th>Fit</th><th>Company / role</th><th>Email (where found)</th><th>Why it looks easy</th><th>Listing</th></tr></thead><tbody>
            {d.items.map((o: any) => (
              <tr key={o.id}>
                <td className="score">{Math.round(o.ease_score)}</td>
                <td>{Math.round(o.fit_score)}</td>
                <td><b>{o.company_name || "company not named"}</b><div className="muted">{o.title.slice(0, 110)}</div>
                  <div className="muted">{o.location_requirements.slice(0, 60) || "location not stated"} · {o.engagement_type}</div>
                  <button onClick={() => openOpp(o.id)} style={{ marginTop: 4 }}>Details / draft</button></td>
                <td>{o.contacts.length === 0 ? <span className="muted">no email published</span> : o.contacts.map((c: any) => (
                  <div key={c.id} style={{ marginBottom: 6 }}>
                    <b>{c.email}</b> <span className={`chip ${ELIG[c.eligibility]}`} title={c.basis}>{c.eligibility.replace("_", " ")}</span>
                    <div className="muted">{c.type} · <ExtLink href={c.source_url}>found here</ExtLink> {fmtDate(c.found_at)}</div>
                    {c.context && <div className="muted" style={{ fontStyle: "italic" }}>“…{c.context.slice(0, 140)}…”</div>}
                  </div>))}</td>
                <td>{(o.ease_signals ?? []).map((s: string) => <div key={s} className="muted">• {s}</div>)}</td>
                <td><ExtLink href={o.url}>Open ↗</ExtLink></td>
              </tr>))}
          </tbody></table></div>
        )}
      </Async>
      <p className="muted"><b>eligible</b> = the company published this address to receive applications (use it only to apply or ask about that role). <b>review required</b> = general mailbox or free-mail address: check before writing. Anyone who asks not to be contacted should be added under Contacts → Suppress.</p>
    </>
  );
}

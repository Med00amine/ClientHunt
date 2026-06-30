import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { useApp } from "../ctx";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Mail, Msg, Notice, Table } from "../ui";

/** Every stored listing in one list: by default the ones that published an email, best match first. Click a row to read it and draft. */
export default function Listings() {
  const { open, rev } = useApp();
  const [f, setF] = useState({ q: "", has_email: true, hide_restricted: true, sort: "best", min_fit: 35, min_ease: 0, source: "", show_excluded: false });
  const set = (k: string, v: any) => setF({ ...f, [k]: v });
  const qs = new URLSearchParams(Object.entries(f).map(([k, v]) => [k, String(v)])).toString();
  const st = useLoad(() => api(`/leads?${qs}`), [qs, rev]);
  const sources = useLoad(() => api("/sources"));
  const [msg, setMsg] = useState<Msg>(null);
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
  const emails: string[] = st.data?.emails ?? [];

  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder="Search company / title / text" value={f.q} onChange={(e) => set("q", e.target.value)} aria-label="search listings" />
        <label className="in"><input type="checkbox" checked={f.has_email} onChange={(e) => set("has_email", e.target.checked)} /> only with an email</label>
        <label className="in"><input type="checkbox" checked={f.hide_restricted} onChange={(e) => set("hide_restricted", e.target.checked)} /> hide “US only / must live there”</label>
        <select value={f.sort} onChange={(e) => set("sort", e.target.value)} aria-label="sort">
          <option value="best">Best match</option><option value="fit">Best fit</option><option value="ease">Easiest to reach</option><option value="newest">Newest found</option>
        </select>
        <span className="grow" />
        <button onClick={() => copy(emails)} disabled={!emails.length}>Copy {emails.length} emails</button>
        <button onClick={download} disabled={busy}>⬇ Emails (CSV)</button>
      </div>
      <Notice msg={msg} />
      <Fold title="More filters" plain>
        <div className="row">
          <label className="in">min fit <input type="number" style={{ width: 70 }} value={f.min_fit} onChange={(e) => set("min_fit", Number(e.target.value))} /></label>
          <label className="in" title="Heuristic: how easy it looks to reach the client">min easy-to-reach <input type="number" style={{ width: 70 }} value={f.min_ease} onChange={(e) => set("min_ease", Number(e.target.value))} /></label>
          <select value={f.source} onChange={(e) => set("source", e.target.value)} aria-label="source filter"><option value="">All sources</option>
            {(sources.data ?? []).map((s: any) => <option key={s.key} value={s.key}>{s.key}</option>)}<option value="alert_upwork">alert_upwork</option></select>
          <label className="in"><input type="checkbox" checked={f.show_excluded} onChange={(e) => set("show_excluded", e.target.checked)} /> show excluded</label>
        </div>
      </Fold>
      <Async state={st} empty={(d: any) => (d.items.length ? null : "No listings match. Run a search above, or untick “only with an email”.")}>
        {(d: any) => (
          <Table head={[<span title="Fit for you; below it, how easy the client looks to reach (a heuristic, not a hiring prediction)">Fit</span>, "Company / role", "Published email", ""]}>
            {d.items.map((o: any) => (
              <tr key={o.id} className="click" onClick={() => open("opp", o.id)}>
                <td className="nw"><span className="score">{Math.round(o.fit_score)}</span>{o.score_override != null && <Chip tone="warn">edited</Chip>}<div className="muted">easy {Math.round(o.ease_score)}</div></td>
                <td><b>{o.company_name || <span className="muted">company not named</span>}</b>
                  <div className="muted">{o.title.slice(0, 100)}</div>
                  <Chip>{o.engagement_type}</Chip><Chip>{o.location_requirements.slice(0, 40) || "location not stated"}</Chip><Chip>{o.source}</Chip>{o.review_status !== "new" && <Chip>{o.review_status}</Chip>}</td>
                <td>{o.contacts.length === 0 ? <span className="muted">no email published</span> : o.contacts.map((c: any) => <Mail key={c.id} c={c} />)}</td>
                <td className="nw"><ExtLink href={o.url} onClick={(e) => e.stopPropagation()}>Listing ↗</ExtLink></td>
              </tr>))}
          </Table>
        )}
      </Async>
    </>
  );
}

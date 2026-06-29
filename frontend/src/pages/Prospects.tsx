import { useEffect, useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { fmtDate } from "../format";
import { Async, useLoad } from "../hooks";
import OneFile from "./OneFile";
import { Draft, EvidenceList, PITCH_WORDS, useActions } from "./shared";

const ELIG: Record<string, string> = { eligible: "ok", review_required: "warn", not_eligible: "bad", unknown: "" };
const STATUS: Record<string, [string, string]> = {
  not_started: ["not read yet", ""], researching: ["reading the site…", "warn"], done: ["site read", "ok"],
  no_evidence: ["nothing useful found", "warn"], failed: ["could not read it", "bad"], no_website: ["no website", "bad"],
};
const CATEGORY = { company: "Company", agency: "Agency", network: "Network" } as Record<string, string>;

export default function Prospects({ openId, setOpenId }: { openId: number | null; setOpenId: (id: number | null) => void }) {
  const [category, setCategory] = useState("");
  const [onlyMailbox, setOnlyMailbox] = useState(false);
  const [poll, setPoll] = useState(0);
  const qs = `category=${category}&only_with_mailbox=${onlyMailbox}`;
  const list = useLoad(() => api(`/prospects?${qs}`), [qs], poll);
  const meta = useLoad(() => api("/prospects/meta"));
  useEffect(() => { setPoll(list.data?.items.some((p: any) => p.research_status === "researching") ? 3000 : 0); }, [list.data]);

  return (
    <>
      <h2>Prospects: companies and agencies you choose to approach</h2>
      <p className="muted">
        Add the website of a company that may need something built, an agency that may subcontract, or a network you want to join. ClientHunt reads
        <b> their own public pages</b> (robots.txt respected), keeps the sentences it quotes, and lists the mailboxes the company published, each with the page and date.
        It never sends anything. A published mailbox is for business enquiries, so a pitch there is <b>unsolicited</b>: it stays “review” unless the site itself invites freelancers.
      </p>
      <AddForm meta={meta.data} onAdded={() => list.reload(true)} />
      <div className="row" style={{ margin: "12px 0 8px" }}>
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="category filter">
          <option value="">All kinds</option><option value="company">Companies</option><option value="agency">Agencies</option><option value="network">Networks</option>
        </select>
        <label style={{ display: "inline" }}><input type="checkbox" checked={onlyMailbox} onChange={(e) => setOnlyMailbox(e.target.checked)} /> only with a published mailbox</label>
        <span className="muted">Also included, as the “Prospects” sheet, in the one-file download below.</span>
      </div>
      <Async state={list} empty={(d: any) => (d.items.length ? null : "No prospects yet. Paste one or more websites above. Nothing here is sample data.")}>
        {(d: any) => (
          <div className="scroll"><table><thead><tr>
            <th title="Public signs that a company may need this work. Hints, not proof.">Signs of need</th><th>Who</th><th>Offer</th><th>Mailboxes the company published</th><th>Status</th><th>Next step</th></tr></thead><tbody>
            {d.items.map((p: any) => {
              const [label, tone] = STATUS[p.research_status] ?? [p.research_status, ""];
              return (
                <tr key={p.id} className="click" onClick={() => setOpenId(p.id)}>
                  <td className="score">{p.category === "network" ? <span className="muted" title="A network does not need work done, so it is not scored. Read its own words on who can apply.">—</span> : Math.round(p.need_score)}</td>
                  <td><b>{p.name}</b> <span className="chip">{CATEGORY[p.category] ?? p.category}</span><div><ExtLink href={p.website} onClick={(e) => e.stopPropagation()}>{p.website.replace(/^https?:\/\//, "")} ↗</ExtLink></div></td>
                  <td>{p.offer_label || <span className="muted">—</span>}</td>
                  <td>{p.contacts.length === 0 ? <span className="muted">none found</span> : p.contacts.map((c: any) => (
                    <div key={c.id}><b>{c.email}</b> <span className={`chip ${ELIG[c.eligibility]}`} title={c.basis}>{c.eligibility.replace("_", " ")}</span>
                      <div className="muted"><ExtLink href={c.source_url} onClick={(e) => e.stopPropagation()}>found here</ExtLink> {fmtDate(c.found_at)}</div></div>))}</td>
                  <td><span className={`chip ${tone}`}>{label}</span>{p.application_status !== "none" && <span className="chip ok">contacted</span>}
                    {p.draft_status !== "none" && p.application_status === "none" && <span className="chip">draft {p.draft_status}</span>}</td>
                  <td>{p.recommended_action}</td>
                </tr>);
            })}
          </tbody></table></div>
        )}
      </Async>
      <OneFile title="Download the prospects (and everything else) in ONE file" />
      {openId && <ProspectDetail id={openId} meta={meta.data} close={() => { setOpenId(null); list.reload(true); }} onChanged={() => list.reload(true)} />}
    </>
  );
}

function AddForm({ meta, onAdded }: { meta: any; onAdded: () => void }) {
  const [f, setF] = useState({ sites: "", category: "company", offer: "", evidence_url: "", evidence_quote: "", research: true });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const sites = f.sites.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
    if (!sites.length) { setMsg({ kind: "error", text: "Paste at least one website, one per line." }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await api("/prospects", { body: { research: f.research, items: sites.slice(0, 25).map((website) => ({ website, category: f.category, offer: f.offer, evidence_url: f.evidence_url.trim(), evidence_quote: f.evidence_quote.trim() })) } });
      const bad = r.errors.map((x: any) => `${x.website}: ${x.error}`);
      setMsg({ kind: bad.length ? "warn" : "ok", text: `Added or updated ${r.created.length}.${f.research && r.created.length ? " Reading their websites now…" : ""}${bad.length ? " Not added: " + bad.join("; ") : ""}` });
      if (r.created.length) { setF({ ...f, sites: bad.length ? sites.filter((s) => r.errors.some((x: any) => x.website === s)).join("\n") : "" }); onAdded(); }
    } catch (x: any) { setMsg({ kind: "error", text: x.message }); }
    setBusy(false);
  };
  return (
    <form className="panel" onSubmit={submit} aria-label="Add prospects">
      <div className="cols">
        <div>
          <label htmlFor="sites">Websites, one per line</label>
          <textarea id="sites" style={{ minHeight: 90 }} placeholder={"https://company.example\nagency.example"} value={f.sites} onChange={(e) => setF({ ...f, sites: e.target.value })} />
        </div>
        <div>
          <label htmlFor="cat">What are they?</label>
          <select id="cat" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value, offer: "" })}>
            {Object.entries(meta?.categories ?? { company: { label: "Company that may need something built" } }).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <label htmlFor="offer">What would you offer?</label>
          <select id="offer" value={f.offer} onChange={(e) => setF({ ...f, offer: e.target.value })}>
            <option value="">Choose from what their site says</option>
            {Object.entries(meta?.offers ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}
          </select>
          <label style={{ display: "inline-block", marginTop: 8 }}><input type="checkbox" checked={f.research} onChange={(e) => setF({ ...f, research: e.target.checked })} /> read their website now</label>
        </div>
        <div>
          <label htmlFor="eurl">Where did you see they may need help? (link, optional)</label>
          <input id="eurl" style={{ width: "100%" }} placeholder="https://…" value={f.evidence_url} onChange={(e) => setF({ ...f, evidence_url: e.target.value })} />
          <label htmlFor="equote">What it said (a sentence or a note, optional)</label>
          <textarea id="equote" style={{ minHeight: 60 }} value={f.evidence_quote} onChange={(e) => setF({ ...f, evidence_quote: e.target.value })} maxLength={600} />
          <div className="muted">Saved with every site in this submission. Add one at a time for different notes.</div>
        </div>
      </div>
      <div className="row" style={{ marginTop: 10 }}><button className="primary" disabled={busy}>Add prospects</button>
        <span className="muted">Public websites only. Private addresses, logins and non-web links are refused.</span></div>
      {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
    </form>
  );
}

function ProspectDetail({ id, meta, close, onChanged }: { id: number; meta: any; close: () => void; onChanged: () => void }) {
  const st = useLoad(() => api(`/opportunities/${id}`), [id], 0);
  const row = useLoad(() => api("/prospects"), [id], 0);
  const reloadAll = () => { st.reload(true); row.reload(true); onChanged(); };
  const { msg, setMsg, busy, run } = useActions(reloadAll);
  const p = row.data?.items.find((x: any) => x.id === id);
  useEffect(() => { if (p?.research_status === "researching") { const t = setTimeout(reloadAll, 2500); return () => clearTimeout(t); } }, [p?.research_status, row.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const patch = (body: object) => run(() => api(`/prospects/${id}`, { method: "PATCH", body }));
  const offer = p ? meta?.offers?.[p.offer] : null;
  return (
    <aside className="detail" role="dialog" aria-label="Prospect detail">
      <div className="row"><button onClick={close}>✕ Close</button></div>
      <Async state={st}>
        {(o: any) => !p ? <p className="muted">Loading…</p> : (<>
          <h2>{p.name}</h2>
          <div className="row"><ExtLink href={p.website}><b>Open their website ↗</b></ExtLink><span className="chip">{CATEGORY[p.category] ?? p.category}</span>
            <span className={`chip ${(STATUS[p.research_status] ?? ["", ""])[1]}`}>{(STATUS[p.research_status] ?? [p.research_status])[0]}</span>
            {o.application && <span className="chip ok">contacted {fmtDate(o.application.submitted_at)}</span>}</div>
          {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
          <div className="panel" style={{ marginTop: 8 }}>
            <b>Why it is on your list</b>
            {p.evidence_quote || p.evidence_url ? (<div>{p.evidence_quote && <>“{p.evidence_quote}”</>} {p.evidence_url && <ExtLink href={p.evidence_url}>source ↗</ExtLink>}</div>)
              : <div className="muted">You added it yourself; nothing else is recorded.</div>}
            <div className="row" style={{ marginTop: 8 }}>
              <label style={{ display: "inline" }}>Kind <select value={p.category} onChange={(e) => patch({ category: e.target.value })} aria-label="kind">
                {Object.entries(meta?.categories ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</select></label>
              <label style={{ display: "inline" }}>Offer <select value={p.offer} onChange={(e) => patch({ offer: e.target.value })} aria-label="offer">
                {Object.entries(meta?.offers ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</select></label>
            </div>
            {offer && <p className="muted" style={{ marginBottom: 0 }}><b>You would deliver:</b> {offer.deliverable} <b>First step:</b> {offer.first_step}</p>}
          </div>
          {p.category === "network" ? <p className="muted" style={{ marginTop: 12 }}>A network is not scored: it does not need work done. Read what its own page says below, then check who can apply, any location limit and the hours it expects before you spend time on it.</p> : (<>
            <h3>Public signs they may need this: {Math.round(p.need_score)} / 100 <span className="muted" style={{ fontSize: 12 }}>(hints from their own site, not proof)</span></h3>
            {p.signals.length ? p.signals.map((s: string) => <div className="muted" key={s}>• {s}</div>) : <p className="muted">No signs found yet{p.research_status === "not_started" ? ": read the site first" : ""}.</p>}
          </>)}
          <h3>Mailboxes the company published</h3>
          {p.contacts.length === 0 ? <p className="muted">None found on the pages read. Look for a contact form on their site, and write only through what they offer.</p> : p.contacts.map((c: any) => (
            <div className="panel" key={c.id} style={{ marginBottom: 6 }}><b>{c.email}</b> <span className={`chip ${ELIG[c.eligibility]}`}>{c.eligibility.replace("_", " ")}</span>
              <div className="muted">{c.basis}</div><div className="muted">Found: <ExtLink href={c.source_url}>{c.source_url}</ExtLink> · {fmtDate(c.found_at)}</div></div>))}
          <h3>What their site says</h3>
          {o.company?.description && <p>{o.company.description}</p>}
          {o.evidence.length === 0 ? <p className="muted">Nothing kept yet. Approve a sentence below to let your pitch quote it.</p> : <EvidenceList evidence={o.evidence} run={run} />}
          <h3>Pitch</h3>
          <div className="row"><button className="primary" disabled={busy} onClick={() => run(() => api(`/opportunities/${id}/drafts`, { method: "POST" }), "Pitch drafted")}>{o.drafts.length ? "Regenerate pitch" : "Draft a pitch"}</button>
            <span className="muted">Never sent by ClientHunt. Written from the offer, your verified portfolio and the sentences you approved; a pitch is never machine-generated.</span></div>
          {o.drafts.map((d: any) => <Draft key={d.id} d={d} oppId={id} run={run} words={PITCH_WORDS} />)}
          {o.application && (<p>Recorded as <b>{o.application.status}</b>. Log replies and follow-ups in the Pipeline tab.</p>)}
          <h3>Manage</h3>
          <div className="row">
            <button disabled={busy || p.research_status === "researching"} onClick={() => run(() => api(`/prospects/${id}/research`, { method: "POST" }).then(() => setMsg({ kind: "ok", text: "Reading their website again…" })))}>Read the site again</button>
            <button className="danger" disabled={busy || !!o.application} title={o.application ? "Contacted prospects stay in the record" : ""}
              onClick={() => { if (confirm("Remove this prospect and its saved mailboxes and drafts?")) run(() => api(`/prospects/${id}`, { method: "DELETE" })).then((r) => { if (r) close(); }); }}>Remove</button>
          </div>
        </>)}
      </Async>
    </aside>
  );
}

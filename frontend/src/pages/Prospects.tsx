import { useEffect, useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { useApp } from "../ctx";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Mail, Msg, Notice, Table } from "../ui";
import { CATEGORY, STATUS } from "./Drawers";

export default function Prospects() {
  const { open, rev } = useApp();
  const [category, setCategory] = useState("");
  const [onlyMailbox, setOnlyMailbox] = useState(false);
  const [poll, setPoll] = useState(0);
  const qs = `category=${category}&only_with_mailbox=${onlyMailbox}`;
  const list = useLoad(() => api(`/prospects?${qs}`), [qs, rev], poll);
  const meta = useLoad(() => api("/prospects/meta"));
  useEffect(() => { setPoll(list.data?.items.some((p: any) => p.research_status === "researching") ? 3000 : 0); }, [list.data]);
  // Open the add form for an empty list, decided once: adding the first prospect must not close the form on its own confirmation.
  const [startOpen, setStartOpen] = useState<boolean | undefined>(undefined);
  useEffect(() => { if (list.data && startOpen === undefined) setStartOpen(list.data.items.length === 0); }, [list.data, startOpen]);

  return (
    <>
      <h2 className="sr">Prospects</h2>
      <Fold title="Add companies, agencies or networks" open={startOpen}>
        <AddForm meta={meta.data} onAdded={() => list.reload(true)} />
      </Fold>
      <div className="row" style={{ margin: "12px 0 8px" }}>
        <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="category filter">
          <option value="">All kinds</option><option value="company">Companies</option><option value="agency">Agencies</option><option value="network">Networks</option>
        </select>
        <label className="in"><input type="checkbox" checked={onlyMailbox} onChange={(e) => setOnlyMailbox(e.target.checked)} /> only with a published mailbox</label>
      </div>
      <Async state={list} empty={(d: any) => (d.items.length ? null : "No prospects yet. Paste one or more websites above. Nothing here is sample data.")}>
        {(d: any) => (
          <Table head={[<span title="Public signs that a company may need this work. Hints, not proof.">Signs of need</span>, "Who", "Mailboxes the company published", "Status and next step"]}>
            {d.items.map((p: any) => {
              const [label, tone] = STATUS[p.research_status] ?? [p.research_status, ""];
              return (
                <tr key={p.id} className="click" onClick={() => open("prospect", p.id)}>
                  <td className="score">{p.category === "network" ? <span className="muted" title="A network does not need work done, so it is not scored.">—</span> : Math.round(p.need_score)}</td>
                  <td><b>{p.name}</b> <Chip>{CATEGORY[p.category] ?? p.category}</Chip>
                    <div><ExtLink href={p.website} onClick={(e) => e.stopPropagation()}>{p.website.replace(/^https?:\/\//, "")} ↗</ExtLink></div>
                    {p.offer_label && <div className="muted">{p.offer_label}</div>}</td>
                  <td>{p.contacts.length === 0 ? <span className="muted">none found</span> : p.contacts.map((c: any) => <Mail key={c.id} c={c} />)}</td>
                  <td><Chip tone={tone}>{label}</Chip>{p.application_status !== "none" && <Chip tone="ok">contacted</Chip>}
                    {p.draft_status !== "none" && p.application_status === "none" && <Chip>draft {p.draft_status}</Chip>}
                    <div className="muted">{p.recommended_action}</div></td>
                </tr>);
            })}
          </Table>
        )}
      </Async>
    </>
  );
}

function AddForm({ meta, onAdded }: { meta: any; onAdded: () => void }) {
  const [f, setF] = useState({ sites: "", category: "company", offer: "", evidence_url: "", evidence_quote: "", research: true });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
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
    <form onSubmit={submit} aria-label="Add prospects">
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
          <label className="in" style={{ display: "block", marginTop: 8 }}><input type="checkbox" checked={f.research} onChange={(e) => setF({ ...f, research: e.target.checked })} /> read their website now</label>
        </div>
      </div>
      <Fold title="Where did you see they may need help? (optional)" plain>
        <label htmlFor="eurl">Link</label>
        <input id="eurl" style={{ width: "100%" }} placeholder="https://…" value={f.evidence_url} onChange={(e) => setF({ ...f, evidence_url: e.target.value })} />
        <label htmlFor="equote">What it said (a sentence or a note)</label>
        <textarea id="equote" style={{ minHeight: 60 }} value={f.evidence_quote} onChange={(e) => setF({ ...f, evidence_quote: e.target.value })} maxLength={600} />
      </Fold>
      <div className="row" style={{ marginTop: 10 }}><button className="primary" disabled={busy}>Add prospects</button>
        <span className="muted">Only their public pages are read; nothing is ever sent. Private addresses and non-web links are refused.</span></div>
      <Notice msg={msg} />
    </form>
  );
}

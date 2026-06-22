import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";

export default function Contacts() {
  const [q, setQ] = useState("");
  const [elig, setElig] = useState("");
  const list = useLoad(() => api(`/contacts?limit=50&q=${encodeURIComponent(q)}&eligibility=${elig}`), [q, elig]);
  const [msg, setMsg] = useState("");
  const [nc, setNc] = useState({ email: "", name: "", company_name: "", source_url: "" });
  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    const form = new FormData(); form.append("file", file);
    setMsg("Importing…");
    try { const r = await api("/contacts/import", { form }); setMsg(`Imported ${r.imported}, duplicates ${r.duplicates}, invalid ${r.invalid}. DB backup: ${r.backup ?? "n/a"}`); list.reload(true); } catch (x: any) { setMsg(x.message); }
  };
  const setEligibility = async (id: number) => {
    const basis = prompt("Basis for marking this contact eligible (country rule checked / existing relationship / etc.)");
    if (basis === null) return;
    try { await api(`/contacts/${id}/eligibility`, { method: "PATCH", body: { value: "eligible", basis } }); list.reload(true); } catch (x: any) { alert(x.message); }
  };
  const suppress = async (email: string) => { await api("/suppressions", { body: { email, reason: "manual opt-out/suppress" } }); list.reload(true); };
  const add = async () => { try { await api("/contacts", { body: nc }); setNc({ email: "", name: "", company_name: "", source_url: "" }); list.reload(true); } catch (x: any) { alert(x.message); } };
  return (
    <>
      <h2>Contacts (separate from opportunities)</h2>
      <div className="alert warn">Having an email address does <b>not</b> make someone eligible for outreach. Imported contacts have no recorded source and stay <b>unknown</b>. Nothing here is emailed by this app.</div>
      <div className="cols">
        <div className="panel"><b>Import .xlsx</b><p className="muted">Reads the first sheet; needs an “email” column. The original file is never modified. A database backup is made first.</p><input type="file" accept=".xlsx" onChange={upload} aria-label="Import contacts file" />{msg && <p role="status">{msg}</p>}</div>
        <div className="panel"><b>Add a public business contact</b>
          <label>Email</label><input aria-label="Email" value={nc.email} onChange={(e) => setNc({ ...nc, email: e.target.value })} />
          <label>Name (optional)</label><input aria-label="Name (optional)" value={nc.name} onChange={(e) => setNc({ ...nc, name: e.target.value })} />
          <label>Company</label><input aria-label="Company" value={nc.company_name} onChange={(e) => setNc({ ...nc, company_name: e.target.value })} />
          <label>Source URL (required)</label><input aria-label="Source URL (required)" value={nc.source_url} onChange={(e) => setNc({ ...nc, source_url: e.target.value })} placeholder="https://…" />
          <div style={{ marginTop: 8 }}><button onClick={add}>Add</button></div></div>
      </div>
      <div className="row" style={{ margin: "12px 0" }}><input placeholder="Search email / name / company" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={elig} onChange={(e) => setElig(e.target.value)} aria-label="eligibility filter"><option value="">All eligibility</option>{["unknown", "review_required", "eligible", "not_eligible"].map((x) => <option key={x}>{x}</option>)}</select></div>
      <Async state={list} empty={(d: any) => (d.total ? null : "No contacts match. Import a file or add one with its source.")}>
        {(d: any) => (<>
          <p className="muted">{d.total} contacts · {Object.entries(d.by_eligibility).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
          <div className="scroll"><table><thead><tr><th>Email</th><th>Name</th><th>Company</th><th>Provenance</th><th>Eligibility</th><th></th></tr></thead><tbody>
            {d.items.map((c: any) => (<tr key={c.id}><td>{c.email} {c.is_generic && <span className="chip">generic</span>}</td><td>{c.name}</td><td>{c.company_name}</td>
              <td>{c.provenance_missing ? <span className="chip bad">source missing</span> : <a href={c.source_url} target="_blank" rel="noreferrer">source</a>}</td>
              <td><span className="chip">{c.outreach_eligibility}</span>{c.suppressed && <span className="chip bad">suppressed</span>}</td>
              <td><button onClick={() => setEligibility(c.id)} disabled={c.suppressed || c.provenance_missing} title={c.provenance_missing ? "Record a source URL first" : ""}>Mark eligible</button> <button className="danger" onClick={() => suppress(c.email)}>Suppress</button></td></tr>))}
          </tbody></table></div></>)}
      </Async>
    </>
  );
}

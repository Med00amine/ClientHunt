import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Msg, Notice, Table } from "../ui";

/** Addresses kept apart from listings. Having an address never makes someone eligible; only a recorded source and a basis do. */
export default function Contacts() {
  const [q, setQ] = useState("");
  const [elig, setElig] = useState("");
  const list = useLoad(() => api(`/contacts?limit=50&q=${encodeURIComponent(q)}&eligibility=${elig}`), [q, elig]);
  const [msg, setMsg] = useState<Msg>(null);
  const blank = { email: "", name: "", company_name: "", source_url: "" };
  const [nc, setNc] = useState(blank);
  const fail = (x: any) => setMsg({ kind: "error", text: x.message });
  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    const form = new FormData(); form.append("file", file);
    setMsg({ kind: "ok", text: "Importing…" });
    try { const r = await api("/contacts/import", { form }); setMsg({ kind: "ok", text: `Imported ${r.imported}, duplicates ${r.duplicates}, invalid ${r.invalid}. DB backup: ${r.backup ?? "n/a"}` }); list.reload(true); } catch (x) { fail(x); }
  };
  const setEligibility = async (id: number) => {
    const basis = prompt("Basis for marking this contact eligible (country rule checked / existing relationship / etc.)");
    if (basis === null) return;
    try { await api(`/contacts/${id}/eligibility`, { method: "PATCH", body: { value: "eligible", basis } }); list.reload(true); } catch (x) { fail(x); }
  };
  const suppress = async (email: string) => { try { await api("/suppressions", { body: { email, reason: "manual opt-out/suppress" } }); list.reload(true); } catch (x) { fail(x); } };
  const add = async () => { try { await api("/contacts", { body: nc }); setNc(blank); list.reload(true); } catch (x) { fail(x); } };
  return (
    <>
      <div className="alert warn">An email address does <b>not</b> make someone eligible for outreach. Imported contacts have no recorded source and stay <b>unknown</b>. Nothing here is emailed by this app.</div>
      <Notice msg={msg} />
      <Fold title="Import a spreadsheet or add one contact">
        <div className="cols">
          <div><b>Import .xlsx</b> <span className="muted">First sheet, with an “email” column. A database backup is made first.</span>
            <div><input type="file" accept=".xlsx" onChange={upload} aria-label="Import contacts file" /></div></div>
          <div><b>Add a public business contact</b>
            {([["email", "Email"], ["name", "Name (optional)"], ["company_name", "Company"], ["source_url", "Source URL (required)"]] as const).map(([k, label]) => (
              <div key={k}><label>{label}</label><input aria-label={label} value={nc[k]} onChange={(e) => setNc({ ...nc, [k]: e.target.value })} placeholder={k === "source_url" ? "https://…" : ""} /></div>))}
            <div style={{ marginTop: 8 }}><button onClick={add}>Add</button></div></div>
        </div>
      </Fold>
      <div className="row" style={{ margin: "12px 0" }}><input placeholder="Search email / name / company" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={elig} onChange={(e) => setElig(e.target.value)} aria-label="eligibility filter"><option value="">All eligibility</option>{["unknown", "review_required", "eligible", "not_eligible"].map((x) => <option key={x}>{x}</option>)}</select></div>
      <Async state={list} empty={(d: any) => (d.total ? null : "No contacts match. Import a file or add one with its source.")}>
        {(d: any) => (<>
          <p className="muted">{d.total} contacts · {Object.entries(d.by_eligibility).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
          <Table head={["Email", "Name", "Company", "Provenance", "Eligibility", ""]}>
            {d.items.map((c: any) => (<tr key={c.id}><td>{c.email} {c.is_generic && <Chip>generic</Chip>}</td><td>{c.name}</td><td>{c.company_name}</td>
              <td>{c.provenance_missing ? <Chip tone="bad">source missing</Chip> : <ExtLink href={c.source_url}>source</ExtLink>}</td>
              <td><Chip>{c.outreach_eligibility}</Chip>{c.suppressed && <Chip tone="bad">suppressed</Chip>}</td>
              <td><button onClick={() => setEligibility(c.id)} disabled={c.suppressed || c.provenance_missing} title={c.provenance_missing ? "Record a source URL first" : ""}>Mark eligible</button> <button className="danger" onClick={() => suppress(c.email)}>Suppress</button></td></tr>))}
          </Table>
        </>)}
      </Async>
    </>
  );
}

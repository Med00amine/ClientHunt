import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtDate } from "../format";

const STATUSES = ["submitted", "replied", "interview", "won", "lost", "withdrawn"];

export default function Pipeline({ openOpp }: { openOpp: (id: number) => void }) {
  const apps = useLoad(() => api("/applications"));
  const [note, setNote] = useState<Record<number, string>>({});
  const setStatus = async (id: number, status: string) => { await api(`/applications/${id}`, { method: "PATCH", body: { status } }); apps.reload(true); };
  const addNote = async (id: number) => { if (!note[id]) return; await api(`/applications/${id}/conversations`, { body: { direction: "in", summary: note[id] } }); setNote({ ...note, [id]: "" }); apps.reload(true); };
  return (
    <>
      <h2>Pipeline</h2>
      <p className="muted">Applications appear here only after you record that you submitted them on the platform. Drafting or approving a proposal never creates an application.</p>
      <Async state={apps} empty={(a: any[]) => (a.length ? null : "No applications recorded yet. Open an opportunity, approve a draft, submit it on the platform yourself, then record it.")}>
        {(a: any[]) => a.map((x) => (
          <div className="panel" key={x.id} style={{ marginBottom: 10 }}>
            <div className="row"><b>{x.title}</b> <span className="muted">{x.company_name}</span><span style={{ flex: 1 }} />
              <select aria-label="status" value={x.status} onChange={(e) => setStatus(x.id, e.target.value)}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
              <button onClick={() => openOpp(x.opportunity_id)}>Open</button></div>
            <div className="muted">Submitted {fmtDate(x.submitted_at)} · <a href={x.url} target="_blank" rel="noreferrer">original listing</a></div>
            {x.conversations.map((c: any) => <div key={c.id} className="muted">{fmtDate(c.at)} [{c.direction}] {c.summary}</div>)}
            <div className="row"><input placeholder="Log a reply / note" value={note[x.id] ?? ""} onChange={(e) => setNote({ ...note, [x.id]: e.target.value })} /><button onClick={() => addNote(x.id)}>Add</button></div>
          </div>))}
      </Async>
    </>
  );
}

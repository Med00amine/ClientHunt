import { ExtLink } from "../components";
import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtDate, safeUrl } from "../format";

const STATUSES = ["submitted", "replied", "interview", "won", "lost", "withdrawn"];

export default function Pipeline({ openOpp }: { openOpp: (id: number, pitch: boolean) => void }) {
  const apps = useLoad(() => api("/applications"));
  const [note, setNote] = useState<Record<number, string>>({});
  const [dir, setDir] = useState<Record<number, string>>({});
  const setStatus = async (id: number, status: string) => { await api(`/applications/${id}`, { method: "PATCH", body: { status } }); apps.reload(true); };
  const addNote = async (id: number) => { if (!note[id]) return; await api(`/applications/${id}/conversations`, { body: { direction: dir[id] ?? "in", summary: note[id] } }); setNote({ ...note, [id]: "" }); apps.reload(true); };
  return (
    <>
      <h2>Pipeline</h2>
      <p className="muted">Applications and pitches appear here only after you record that you submitted or sent them yourself. Drafting or approving never creates one. Log your replies and your own follow-ups too: the Strategy tab uses them to tell you what is due.</p>
      <Async state={apps} empty={(a: any[]) => (a.length ? null : "Nothing recorded yet. Open an opportunity or a prospect, approve a draft, send it yourself, then record it.")}>
        {(a: any[]) => a.map((x) => (
          <div className="panel" key={x.id} style={{ marginBottom: 10 }}>
            <div className="row"><b>{x.title}</b> {x.company_name !== x.title && <span className="muted">{x.company_name}</span>}<span style={{ flex: 1 }} />
              <select aria-label="status" value={x.status} onChange={(e) => setStatus(x.id, e.target.value)}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
              <button onClick={() => openOpp(x.opportunity_id, x.source === "prospect")}>Open</button></div>
            <div className="muted">Recorded {fmtDate(x.submitted_at)} · <ExtLink href={x.url}>{x.source === "prospect" ? "their website" : "original listing"}</ExtLink></div>
            {x.conversations.map((c: any) => <div key={c.id} className="muted">{fmtDate(c.at)} · {c.direction === "out" ? "I wrote" : "they wrote"}: {c.summary}</div>)}
            <div className="row"><select aria-label="note type" value={dir[x.id] ?? "in"} onChange={(e) => setDir({ ...dir, [x.id]: e.target.value })}><option value="in">They wrote</option><option value="out">I followed up</option></select>
              <input placeholder="Log what was said" value={note[x.id] ?? ""} onChange={(e) => setNote({ ...note, [x.id]: e.target.value })} /><button onClick={() => addNote(x.id)}>Add</button></div>
          </div>))}
      </Async>
    </>
  );
}

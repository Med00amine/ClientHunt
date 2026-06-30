import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { useApp } from "../ctx";
import { fmtDate } from "../format";
import { Async, useLoad } from "../hooks";
import { List } from "../ui";

const STATUSES = ["submitted", "replied", "interview", "won", "lost", "withdrawn"];

/** Only what you recorded yourself: a message you sent, the replies, your follow-ups. Today uses it to tell you what is due. */
export default function Pipeline() {
  const { open, rev } = useApp();
  const apps = useLoad(() => api("/applications"), [rev]);
  const [note, setNote] = useState<Record<number, string>>({});
  const [dir, setDir] = useState<Record<number, string>>({});
  const setStatus = async (id: number, status: string) => { await api(`/applications/${id}`, { method: "PATCH", body: { status } }); apps.reload(true); };
  const addNote = async (id: number) => { if (!note[id]) return; await api(`/applications/${id}/conversations`, { body: { direction: dir[id] ?? "in", summary: note[id] } }); setNote({ ...note, [id]: "" }); apps.reload(true); };
  return (
    <>
      <h2 className="sr">Pipeline</h2>
      <Async state={apps} empty={(a: any[]) => (a.length ? null : "Nothing recorded yet. Approve a draft, send it yourself, then record it from the draft.")}>
        {(a: any[]) => (
          <List>{a.map((x) => (
            <div className="item" key={x.id} style={{ alignItems: "flex-start" }}>
              <div className="main">
                <div className="row"><b>{x.title}</b>{x.company_name !== x.title && <span className="muted">{x.company_name}</span>}</div>
                <div className="muted">Recorded {fmtDate(x.submitted_at)} · <ExtLink href={x.url}>{x.source === "prospect" ? "their website" : "original listing"}</ExtLink></div>
                {x.conversations.map((c: any) => <div key={c.id} className="muted">{fmtDate(c.at)} · {c.direction === "out" ? "I wrote" : "they wrote"}: {c.summary}</div>)}
                <div className="row" style={{ marginTop: 6 }}>
                  <select aria-label="note type" value={dir[x.id] ?? "in"} onChange={(e) => setDir({ ...dir, [x.id]: e.target.value })}><option value="in">They wrote</option><option value="out">I followed up</option></select>
                  <input className="grow" placeholder="Log what was said" value={note[x.id] ?? ""} onChange={(e) => setNote({ ...note, [x.id]: e.target.value })} /><button onClick={() => addNote(x.id)}>Add</button>
                </div>
              </div>
              <select aria-label="status" value={x.status} onChange={(e) => setStatus(x.id, e.target.value)}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
              <button onClick={() => open(x.source === "prospect" ? "prospect" : "opp", x.opportunity_id)}>Open</button>
            </div>))}</List>
        )}
      </Async>
    </>
  );
}

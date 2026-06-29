import { useState } from "react";
import { duration, fmtDate } from "../format";
import RunSummary from "./RunSummary";

/** One compact line per run; click to open the full details. Active runs open by themselves. */
export default function RunRow({ run, onChange }: { run: any; onChange?: () => void }) {
  const active = run.status === "pending" || run.status === "running";
  const [open, setOpen] = useState(false);
  const shown = open || active;
  const tone = run.status === "completed" ? "ok" : run.status === "failed" ? "bad" : "warn";
  return (
    <div className="runrow" data-testid="run-row">
      <button className="rowhead" onClick={() => setOpen(!open)} aria-expanded={shown} aria-label={`Run ${run.id} details`}>
        <span className={`chip ${tone}`}>{run.status}</span>
        <b>#{run.id}</b>
        <span className="grow">{run.profile_name}</span>
        <span className="muted">{run.discovered} fetched → <b>{run.stored}</b> kept</span>
        <span className="muted">{run.emails_found ?? 0} emails</span>
        <span className="muted">{duration(run.duration_s)}</span>
        <span className="muted">{fmtDate(run.started_at ?? run.created_at)}</span>
        <span aria-hidden>{shown ? "▲" : "▼"}</span>
      </button>
      {shown && <RunSummary run={run} onChange={onChange} />}
    </div>
  );
}

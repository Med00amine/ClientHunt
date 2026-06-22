import { api } from "../api";
import { duration, fmtDate, fmtUsd } from "../format";

export default function RunSummary({ run, onChange }: { run: any; onChange?: () => void }) {
  const ex = (run.exports ?? []).filter((e: any) => e.kind === "opportunities");
  const latest = ex[0];
  const emailEx = (run.exports ?? []).filter((e: any) => e.kind === "emails" && e.status === "ok")[0];
  const act = async (path: string) => { try { await api(path, { method: "POST" }); } catch (e: any) { alert(e.message); } onChange?.(); };
  const active = run.status === "pending" || run.status === "running";
  return (
    <div className="panel" data-testid="run-summary">
      <div className="row">
        <b>Run #{run.id}</b> <span className={`chip ${run.status === "completed" ? "ok" : run.status === "failed" ? "bad" : "warn"}`}>{run.status}</span>
        <span className="muted">{run.profile_name}</span>
        {run.retry_count > 0 && <span className="chip">retry {run.retry_count}</span>}
        <span style={{ flex: 1 }} />
        {active && <button className="danger" onClick={() => act(`/runs/${run.id}/cancel`)}>Cancel</button>}
        {run.status === "failed" || run.status === "cancelled" || run.status === "partial" ? <button onClick={() => act(`/runs/${run.id}/retry`)}>Retry run</button> : null}
      </div>
      {run.status === "running" && <p className="muted">Now querying: <b>{run.current_source || "processing…"}</b></p>}
      <div className="grid" style={{ margin: "10px 0" }}>
        {[["Sources queried", (run.sources_queried ?? []).length], ["Fetched", run.discovered], ["Stored & scored", run.stored], ["New", run.new_count],
          ["Rejected: irrelevant", run.rejected_irrelevant], ["Rejected: duplicate", run.rejected_duplicate], ["Selected for review (≥40)", run.selected_for_review],
          ["Emails found", run.emails_found ?? 0], ["Companies researched", run.companies_researched], ["Drafts generated", run.drafts_generated], ["API cost", fmtUsd(run.cost_usd)],
          ["Duration", duration(run.duration_s)], ["Started", fmtDate(run.started_at)]].map(([l, n]) => (
          <div key={String(l)}><div className="n" style={{ fontSize: 18, fontWeight: 600 }}>{String(n)}</div><div className="l muted">{l}</div></div>))}
      </div>
      <div className="scroll">
        <table><thead><tr><th>Source</th><th>Status</th><th>Fetched</th><th>Detail</th></tr></thead><tbody>
          {Object.entries(run.source_results ?? {}).map(([k, v]: any) => (
            <tr key={k}><td>{k}</td><td><span className={`chip ${v.status === "ok" ? "ok" : v.status === "failed" ? "bad" : "warn"}`}>{v.status}</span></td><td>{v.fetched ?? "—"}</td><td>{v.error ?? ""}</td></tr>))}
        </tbody></table>
      </div>
      {(run.errors ?? []).map((e: string, i: number) => <div className="alert error" key={i}>{e}</div>)}
      {(run.incomplete_notes ?? []).map((e: string, i: number) => <div className="alert warn" key={i}>Incomplete: {e}</div>)}
      {(run.info_notes ?? []).map((e: string, i: number) => <div className="alert" key={i}>{e}</div>)}
      <h3>CSV export</h3>
      {run.export_status === "failed" && <div className="alert error">The export failed. <button onClick={() => act(`/runs/${run.id}/export`)}>Retry export</button></div>}
      {latest && latest.status === "ok" ? (
        <p>
          <a href={latest.download_url}>⬇ {latest.filename}</a> · {latest.row_count} rows · created {fmtDate(latest.created_at)}
          {latest.run_status !== "completed" && <span className="chip warn">run was {latest.run_status}</span>}
        </p>
      ) : !active && run.status !== "failed" ? <p className="muted">No export yet.</p> : null}
      {emailEx && (
        <p data-testid="emails-export">
          <a href={emailEx.download_url}><b>⬇ {emailEx.filename}</b></a> · {emailEx.row_count} emails (company-published, with source link) · created {fmtDate(emailEx.created_at)}
        </p>
      )}
      {ex.length > 0 && emailEx && <p><a className="btn" href={`/api/exports/download-all?run_id=${run.id}`}>⬇ Download both CSVs of this run (ZIP)</a></p>}
      {!active && run.status !== "failed" && <button onClick={() => act(`/runs/${run.id}/export`)}>Export CSV</button>}
      {run.status === "failed" && <p className="muted">No CSV is produced for a failed run.</p>}
    </div>
  );
}

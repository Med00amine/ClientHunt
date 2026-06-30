import { useState } from "react";
import { api } from "../api";
import { duration, fmtDate, fmtUsd } from "../format";
import { Chip, Msg, Notice, Stat, Table, runTone } from "../ui";

export default function RunSummary({ run, onChange }: { run: any; onChange?: () => void }) {
  const [msg, setMsg] = useState<Msg>(null);
  const ex = (run.exports ?? []).filter((e: any) => e.kind === "opportunities");
  const latest = ex[0];
  const emailEx = (run.exports ?? []).filter((e: any) => e.kind === "emails" && e.status === "ok")[0];
  const act = async (path: string) => { try { await api(path, { method: "POST" }); setMsg(null); } catch (e: any) { setMsg({ kind: "error", text: e.message }); } onChange?.(); };
  const active = run.status === "pending" || run.status === "running";
  return (
    <div className="panel" data-testid="run-summary">
      <div className="row">
        <b>Run #{run.id}</b> <Chip tone={runTone(run.status)}>{run.status}</Chip>
        <span className="muted">{run.profile_name}</span>
        {run.retry_count > 0 && <Chip>retry {run.retry_count}</Chip>}
        <span className="grow" />
        {active && <button className="danger" onClick={() => act(`/runs/${run.id}/cancel`)}>Cancel</button>}
        {run.status === "failed" || run.status === "cancelled" || run.status === "partial" ? <button onClick={() => act(`/runs/${run.id}/retry`)}>Retry run</button> : null}
      </div>
      <Notice msg={msg} />
      {run.status === "running" && <p className="muted">Now querying: <b>{run.current_source || "processing…"}</b></p>}
      <div className="stats" style={{ margin: "10px 0" }}>
        <Stat n={(run.sources_queried ?? []).length} label="Sources queried" /><Stat n={run.discovered} label="Fetched" /><Stat n={run.stored} label="Stored & scored" /><Stat n={run.new_count} label="New" />
        <Stat n={run.rejected_irrelevant} label="Rejected: irrelevant" /><Stat n={run.rejected_duplicate} label="Rejected: duplicate" /><Stat n={run.selected_for_review} label="Selected for review (≥40)" />
        <Stat n={run.emails_found ?? 0} label="Emails found" /><Stat n={run.companies_researched} label="Companies researched" /><Stat n={run.drafts_generated} label="Drafts generated" />
        <Stat n={fmtUsd(run.cost_usd)} label="API cost" /><Stat n={duration(run.duration_s)} label="Duration" /><Stat n={fmtDate(run.started_at)} label="Started" />
      </div>
      <Table head={["Source", "Status", "Fetched", "Detail"]}>
        {Object.entries(run.source_results ?? {}).map(([k, v]: any) => (
          <tr key={k}><td>{k}</td><td><Chip tone={v.status === "ok" ? "ok" : v.status === "failed" ? "bad" : "warn"}>{v.status}</Chip></td><td>{v.fetched ?? "—"}</td><td>{v.error ?? ""}</td></tr>))}
      </Table>
      {(run.errors ?? []).map((e: string, i: number) => <div className="alert error" key={i}>{e}</div>)}
      {(run.incomplete_notes ?? []).map((e: string, i: number) => <div className="alert warn" key={i}>Incomplete: {e}</div>)}
      {(run.info_notes ?? []).map((e: string, i: number) => <div className="alert" key={i}>{e}</div>)}
      {run.export_status === "failed" && <div className="alert error">The export of this run failed. <button onClick={() => act(`/runs/${run.id}/export`)}>Retry export</button></div>}
      {!active && run.status !== "failed" && !latest && run.export_status !== "failed" && (
        <p className="muted">No files yet. <button onClick={() => act(`/runs/${run.id}/export`)}>Create this run's CSV files</button></p>
      )}
      {run.status === "failed" && <p className="muted">No CSV is produced for a failed run.</p>}
      {(latest || emailEx) && (
        <details data-testid="run-files">
          <summary>Files of this run ({(latest ? 1 : 0) + (emailEx ? 1 : 0)} CSV)</summary>
          {latest && latest.status === "ok" && (
            <p>
              <a href={latest.download_url}>⬇ {latest.filename}</a> · {latest.row_count} rows · created {fmtDate(latest.created_at)}
              {latest.run_status !== "completed" && <Chip tone="warn">run was {latest.run_status}</Chip>}
            </p>
          )}
          {emailEx && (
            <p data-testid="emails-export">
              <a href={emailEx.download_url}><b>⬇ {emailEx.filename}</b></a> · {emailEx.row_count} emails (company-published, with source link) · created {fmtDate(emailEx.created_at)}
            </p>
          )}
          {ex.length > 0 && emailEx && <p><a className="btn" href={`/api/exports/download-all?run_id=${run.id}`}>⬇ Download both CSVs of this run (ZIP)</a></p>}
        </details>
      )}
    </div>
  );
}

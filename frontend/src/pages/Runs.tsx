import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { duration, fmtDate, fmtUsd } from "../format";
import OneFile from "./OneFile";

export default function Runs({ go }: { go: (t: any) => void }) {
  const runs = useLoad(() => api("/runs?limit=100"), [], 4000);
  const exps = useLoad(() => api("/exports"), [], 8000);
  const [kind, setKind] = useState("");
  const okFiles = (exps.data ?? []).filter((e: any) => e.status === "ok" && (!kind || e.kind === kind));
  const emailsExport = async () => { try { await api("/exports/emails", { method: "POST" }); exps.reload(true); } catch (e: any) { alert(e.message); } };
  const retry = async (id: number) => { try { await api(`/runs/${id}/export`, { method: "POST" }); exps.reload(true); runs.reload(true); } catch (e: any) { alert(e.message); } };
  return (
    <>
      <h2>Runs &amp; exports</h2>
      <OneFile />
      <h3>Run history</h3>
      <Async state={runs} empty={(r: any[]) => (r.length ? null : "No runs yet.")}>
        {(r: any[]) => (
          <div className="scroll"><table><thead><tr><th>#</th><th>Search</th><th>Status</th><th>Started</th><th>Duration</th><th>Kept</th><th>New</th><th>Cost</th><th>Retries</th><th>Last error</th></tr></thead><tbody>
            {r.map((x) => (<tr key={x.id}><td>{x.id}</td><td>{x.profile_name}</td><td><span className={`chip ${x.status === "completed" ? "ok" : x.status === "failed" ? "bad" : "warn"}`}>{x.status}</span></td>
              <td>{fmtDate(x.started_at)}</td><td>{duration(x.duration_s)}</td><td>{x.stored}</td><td>{x.new_count}</td><td>{fmtUsd(x.cost_usd)}</td><td>{x.retry_count}</td><td>{x.last_error?.slice(0, 80)}</td></tr>))}
          </tbody></table></div>
        )}
      </Async>
      <details style={{ marginTop: 16 }} data-testid="archive">
        <summary><b>Individual files (archive)</b> · every run's own CSVs, kept and never overwritten</summary>
        <div className="panel" style={{ margin: "10px 0" }}>
          <div className="row">
            {okFiles.length ? (
              <a className="btn" href={`/api/exports/download-all${kind ? `?kind=${kind}` : ""}`}>⬇ Download all of them (ZIP)</a>
            ) : (
              <button disabled>⬇ Download all of them (ZIP)</button>
            )}
            <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="which CSVs">
              <option value="">All CSVs</option><option value="opportunities">Only opportunities</option><option value="emails">Only emails</option>
            </select>
            <span className="muted">{okFiles.length} file(s) in one ZIP, with a manifest.csv.</span>
            <button onClick={emailsExport}>Create “all emails” CSV</button>
          </div>
        </div>
        <Async state={exps} empty={(r: any[]) => (r.length ? null : "No exports yet. One is created automatically when a run completes.")}>
          {(r: any[]) => (
            <div className="scroll"><table><thead><tr><th>File</th><th>Kind</th><th>Run</th><th>Created</th><th>Rows</th><th>Status</th><th></th></tr></thead><tbody>
              {r.map((e) => (<tr key={e.id}><td>{e.status === "ok" ? <a href={e.download_url}>{e.filename}</a> : "—"}</td><td>{e.kind}</td><td>{e.run_id ?? ""} {e.run_status && e.run_status !== "completed" ? <span className="chip warn">{e.run_status}</span> : null}</td>
                <td>{fmtDate(e.created_at)}</td><td>{e.row_count}</td><td><span className={`chip ${e.status === "ok" ? "ok" : "bad"}`}>{e.status}</span> {e.error}</td>
                <td>{e.status === "failed" && e.run_id ? <button onClick={() => retry(e.run_id)}>Retry</button> : null}</td></tr>))}
            </tbody></table></div>
          )}
        </Async>
      </details>
    </>
  );
}

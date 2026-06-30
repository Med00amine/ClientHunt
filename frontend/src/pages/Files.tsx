import { useState } from "react";
import { api } from "../api";
import { fmtDate, fmtUsd } from "../format";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Msg, Notice, Table } from "../ui";
import OneFile from "./OneFile";
import RunRow from "./RunRow";

/** The one download, the history of runs, the per-run files (archive), what it cost, and a backup. */
export default function Files() {
  const runs = useLoad(() => api("/runs?limit=30"), [], 4000);
  const exps = useLoad(() => api("/exports"), [], 8000);
  const usage = useLoad(() => api("/usage"));
  const [kind, setKind] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const okFiles = (exps.data ?? []).filter((e: any) => e.status === "ok" && (!kind || e.kind === kind));
  const wrap = async (fn: () => Promise<string | void>) => { try { const t = await fn(); setMsg(t ? { kind: "ok", text: t } : null); } catch (e: any) { setMsg({ kind: "error", text: e.message }); } };
  const emailsExport = () => wrap(async () => { await api("/exports/emails", { method: "POST" }); exps.reload(true); });
  const retry = (id: number) => wrap(async () => { await api(`/runs/${id}/export`, { method: "POST" }); exps.reload(true); runs.reload(true); });
  return (
    <>
      <OneFile />
      <Notice msg={msg} />

      <h3>Runs</h3>
      <Async state={runs} empty={(r: any[]) => (r.length ? null : "No runs yet. Start one under Find work.")}>
        {(r: any[]) => r.map((run) => <RunRow key={run.id} run={run} onChange={() => runs.reload(true)} />)}
      </Async>

      <Fold title="Individual files (archive)" testId="archive">
        <div className="row" style={{ marginBottom: 8 }}>
          {okFiles.length ? <a className="btn" href={`/api/exports/download-all${kind ? `?kind=${kind}` : ""}`}>⬇ Download all of them (ZIP)</a> : <button disabled>⬇ Download all of them (ZIP)</button>}
          <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="which CSVs">
            <option value="">All CSVs</option><option value="opportunities">Only opportunities</option><option value="emails">Only emails</option>
          </select>
          <span className="muted">{okFiles.length} file(s) in one ZIP, with a manifest.csv.</span>
          <button onClick={emailsExport}>Create “all emails” CSV</button>
        </div>
        <Async state={exps} empty={(r: any[]) => (r.length ? null : "No exports yet. One is created automatically when a run completes.")}>
          {(r: any[]) => (
            <Table head={["File", "Kind", "Run", "Created", "Rows", "Status", ""]}>
              {r.map((e) => (<tr key={e.id}><td>{e.status === "ok" ? <a href={e.download_url}>{e.filename}</a> : "—"}</td><td>{e.kind}</td><td>{e.run_id ?? ""} {e.run_status && e.run_status !== "completed" ? <Chip tone="warn">{e.run_status}</Chip> : null}</td>
                <td>{fmtDate(e.created_at)}</td><td>{e.row_count}</td><td><Chip tone={e.status === "ok" ? "ok" : "bad"}>{e.status}</Chip> {e.error}</td>
                <td>{e.status === "failed" && e.run_id ? <button onClick={() => retry(e.run_id)}>Retry</button> : null}</td></tr>))}
            </Table>
          )}
        </Async>
      </Fold>

      <h3>Cost</h3>
      <Async state={usage}>{(u: any) => (<>
        <p>This month: {fmtUsd(u.month_spend_usd)} of ${u.monthly_budget_usd} budget. <span className="muted">{u.events.length ? u.llm_price_note : "No paid usage recorded: free sources and template drafts cost $0."}</span></p>
        {u.events.length > 0 && <Fold title={`Paid usage (${u.events.length})`}>
          <Table head={["When", "Kind", "Provider", "Cost", "Estimated"]}>{u.events.slice(0, 20).map((e: any, i: number) => (
            <tr key={i}><td>{fmtDate(e.at)}</td><td>{e.kind}</td><td>{e.provider}</td><td>{fmtUsd(e.cost_usd)}</td><td>{e.estimated ? "yes" : "no"}</td></tr>))}</Table>
        </Fold>}
      </>)}</Async>

      <h3>Backup</h3>
      <button onClick={() => wrap(async () => `Backup written: ${(await api("/admin/backup", { method: "POST" })).path}`)}>Back up database now</button>
    </>
  );
}

import { api } from "../api";
import { useLoad } from "../hooks";

type Counts = { runs: number; opportunities: number; leads: number; emails: number; prospects?: number };

function useCounts() {
  const counts = useLoad(() => api("/export/all/counts"), [], 15000);
  const n = counts.data as Counts | null;
  const empty = !n || (n.runs === 0 && n.opportunities === 0 && !(n.prospects ?? 0));
  const csvOk = !!n && (n.runs > 0 || n.opportunities > 0);      // the flat CSV lists opportunities; prospects are in the Excel file
  return { n, empty, csvOk, error: counts.error };
}

/** Always in the header: the single download of everything. */
export function DownloadButton() {
  const { empty } = useCounts();
  return empty
    ? <button disabled title="Nothing to download yet">⬇ Download all</button>
    : <a className="btn" href="/api/export/all?format=xlsx" title="Everything from all runs in one Excel file">⬇ Download all</a>;
}

/** The single download with its totals: everything from ALL runs in ONE file (Excel, or one flat CSV). */
export default function OneFile() {
  const { n, empty, csvOk, error } = useCounts();
  return (
    <div className="panel" data-testid="onefile">
      <div className="row">
        {empty ? (
          <button className="primary" disabled>⬇ Download ALL runs in ONE file (Excel)</button>
        ) : (
          <a className="btn primary" href="/api/export/all?format=xlsx">⬇ Download ALL runs in ONE file (Excel)</a>
        )}
        {!empty && csvOk && <a className="btn" href="/api/export/all?format=csv">or as one CSV</a>}
      </div>
      <p className="muted" style={{ marginBottom: 0 }}>
        {error && !n
          ? "Could not read the totals right now."
          : empty
            ? "Nothing to download yet. Run a research or add a prospect first."
            : `${n!.opportunities} opportunities · ${n!.leads} leads you can act on (email, good fit, open to Tunisia) · ${n!.emails} emails in total · ${n!.prospects ?? 0} prospects · ${n!.runs} runs. Excel sheets: Summary, Leads, Opportunities, Prospects, Emails, Runs.`}
      </p>
    </div>
  );
}

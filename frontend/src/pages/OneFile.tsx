import { api } from "../api";
import { useLoad } from "../hooks";

/** The single download: everything from ALL runs in ONE file (Excel, or one flat CSV). */
export default function OneFile({ title = "Everything from all runs in ONE file" }: { title?: string }) {
  const counts = useLoad(() => api("/export/all/counts"), [], 15000);
  const n = counts.data as { runs: number; opportunities: number; leads: number; emails: number; prospects?: number } | null;
  const empty = !n || (n.runs === 0 && n.opportunities === 0 && !(n.prospects ?? 0));
  const csvOk = !!n && (n.runs > 0 || n.opportunities > 0);      // the flat CSV lists opportunities; prospects are in the Excel file
  return (
    <div className="panel onefile" data-testid="onefile">
      <b>{title}</b>
      <div className="row" style={{ marginTop: 8 }}>
        {empty ? (
          <button className="primary big" disabled>⬇ Download ALL runs in ONE file (Excel)</button>
        ) : (
          <a className="btn primary big" href="/api/export/all?format=xlsx">⬇ Download ALL runs in ONE file (Excel)</a>
        )}
        {!empty && csvOk && <a className="btn" href="/api/export/all?format=csv">or as one CSV</a>}
      </div>
      <p className="muted" style={{ marginBottom: 0 }}>
        {counts.error && !n
          ? "Could not read the totals right now."
          : empty
            ? "Nothing to download yet. Run a research or add a prospect first."
            : `${n!.opportunities} opportunities · ${n!.leads} leads you can act on (email, good fit, open to Tunisia) · ${n!.emails} emails in total · ${n!.prospects ?? 0} prospects · ${n!.runs} runs. Each opportunity appears once. Excel sheets: Summary, Leads, Opportunities, Prospects, Emails, Runs.`}
      </p>
    </div>
  );
}

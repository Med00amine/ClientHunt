import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { fmtDate, fmtUsd } from "../format";
import RunSummary from "./RunSummary";

export default function Overview({ go }: { go: (t: any) => void }) {
  const st = useLoad(() => api("/overview"), [], 10000);
  return (
    <>
      <h2>Overview</h2>
      <Async state={st}>
        {(o) => {
          const cards: [string, number | string][] = [
            ["Hiring emails found", o.emails_found ?? 0], ["Apply-by-email leads", o.apply_by_email_leads ?? 0], ["Opportunities discovered", o.opportunities_total], ["New since previous run", o.new_since_previous_run],
            ["Relevant (score ≥ 40)", o.relevant], ["Awaiting review", o.awaiting_review],
            ["Proposals drafted", o.proposals_drafted], ["Applications submitted", o.applications_submitted],
            ["Replies", o.replies], ["Interviews", o.interviews], ["Contracts won", o.won], ["Contracts lost", o.lost],
            ["Research failures", o.research_failures], ["Cost estimated", fmtUsd(o.cost_estimated_usd)],
            ["Cost actual", fmtUsd(o.cost_actual_usd)], ["Month spend / budget", `${fmtUsd(o.month_spend_usd)} / $${o.monthly_budget_usd}`],
          ];
          return (
            <>
              {!o.auth_enabled && <div className="alert warn">No APP_PASSWORD is set: fine on your own machine, but set one before exposing this app on a network.</div>}
              {o.opportunities_total === 0 && (
                <div className="empty">No opportunities yet. Go to <a href="#" onClick={(e) => { e.preventDefault(); go("Research"); }}>Research</a> and click <b>Run Research</b>. Nothing on this page is sample data.</div>
              )}
              <div className="grid" style={{ marginTop: 12 }}>
                {cards.map(([l, n]) => (<div className="card" key={l}><div className="n">{n}</div><div className="l">{l}</div></div>))}
              </div>
              <p className="muted">Costs marked “estimated” use prices from your .env, which are not verified against provider price lists.</p>
              {o.last_run && (<><h3>Last completed run · {fmtDate(o.last_run.finished_at)}</h3><RunSummary run={o.last_run} /></>)}
            </>
          );
        }}
      </Async>
    </>
  );
}

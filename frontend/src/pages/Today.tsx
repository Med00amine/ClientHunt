import { api } from "../api";
import { useApp } from "../ctx";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, List, Mail, Notice, Stat } from "../ui";
import { useActions } from "./shared";

const STAGE: Record<string, string> = {
  first: "Day 4 or later: one short follow-up.", last: "Day 10 or later: the last follow-up, then stop.",
  close: "No answer after two follow-ups, or 21 days: close it.",
};

function LeadRow({ o, mail }: { o: any; mail: boolean }) {
  const { open } = useApp();
  return (
    <div className="item">
      <span className="score" title="Fit for you">{o.fit}</span>
      <div className="main">
        <b>{o.company || "company not named"}</b> <span className="muted">{o.title.slice(0, 90)}</span>
        <div>
          <Chip>{o.engagement}</Chip><Chip tone={o.location_check === "restricted" ? "bad" : "ok"}>{o.location_check === "unknown" ? "location not stated" : `location: ${o.location_check}`}</Chip>
          {o.has_draft && <Chip tone="ok">draft ready</Chip>}
        </div>
        {mail && o.emails.map((e: any) => <Mail key={e.email} c={e} />)}
      </div>
      <button onClick={() => open("opp", o.id)}>Open</button>
    </div>
  );
}

function Leads({ title, block, mail, none }: { title: string; block: any; mail: boolean; none: string }) {
  const { go } = useApp();
  return (
    <>
      <h3>{title}</h3>
      {block.items.length === 0 ? <p className="muted">{none}</p> : <List>{block.items.map((o: any) => <LeadRow key={o.id} o={o} mail={mail} />)}</List>}
      {block.total > block.items.length && <p className="muted"><a href="#/find" onClick={(e) => { e.preventDefault(); go("find"); }}>{block.total - block.items.length} more in Find work</a></p>}
    </>
  );
}

export default function Today() {
  const { open, go, rev } = useApp();
  const ov = useLoad(() => api("/overview"), [rev]);
  const st = useLoad(() => api("/strategy"), [rev]);
  const { msg, run } = useActions(() => st.reload(true));
  const o = ov.data;
  return (
    <>
      <h2 className="sr">Today</h2>
      {o && !o.auth_enabled && <div className="alert warn">No APP_PASSWORD is set: fine on your own machine, but set one before exposing this app on a network.</div>}
      {o && o.opportunities_total === 0 && !o.prospects && (
        <div className="empty">No opportunities yet. Go to <a href="#/find" onClick={(e) => { e.preventDefault(); go("find"); }}>Find work</a> and click <b>Run search</b>. Nothing here is sample data.</div>
      )}
      <Async state={st}>
        {(d: any) => {
          const t = d.today;
          return (
            <>
              <div className="stats">
                <Stat n={t.apply_by_email.total} label="to write (email published)" />
                <Stat n={t.follow_ups.total} label="follow-ups due" />
                <Stat n={t.prospects.to_research.total} label="prospects to read" />
                {o && <><Stat n={o.applications_submitted} label="sent" /><Stat n={o.replies} label="replies" /><Stat n={o.won} label="won" /></>}
              </div>
              <Notice msg={msg} />
              <Fold title={t.time_plan.label}><ol style={{ margin: 0, paddingLeft: 18 }}>{t.time_plan.steps.map((s: any) => <li key={s.task}><b>{s.minutes} min</b> · {s.task}</li>)}</ol></Fold>

              <Leads title="Write to these: they published an email" block={t.apply_by_email} mail none="None fit you right now. Run a search under Find work." />
              <Leads title="Apply on the listing: no email published" block={t.apply_by_link} mail={false} none="None right now." />

              <h3>Follow-ups due</h3>
              {t.follow_ups.items.length === 0
                ? <p className="muted">Nothing is due{t.follow_ups.waiting ? `; ${t.follow_ups.waiting} sent message${t.follow_ups.waiting === 1 ? " is" : "s are"} still inside the waiting time` : ""}. Log what you send in Pipeline.</p>
                : <List>{t.follow_ups.items.map((f: any) => (
                  <div className="item" key={f.application_id}>
                    <div className="main"><b>{f.title.slice(0, 90)}</b> <span className="muted">{f.company}</span> <Chip>{f.days} days ago</Chip>
                      <div className="muted">{STAGE[f.stage]}</div></div>
                    {f.stage !== "close" && <button onClick={() => run(() => api(`/applications/${f.application_id}/conversations`, { body: { direction: "out", summary: "Follow-up sent" } }), "Logged. The next follow-up date is counted from the first message.")}>I sent the follow-up</button>}
                    <button className={f.stage === "close" ? "primary" : ""} onClick={() => run(() => api(`/applications/${f.application_id}`, { method: "PATCH", body: { status: "lost" } }), "Closed as lost.")}>Close it (no reply)</button>
                    <button onClick={() => open(f.kind === "pitch" ? "prospect" : "opp", f.opportunity_id)}>Open</button>
                  </div>))}</List>}

              <h3>Prospects</h3>
              <div className="cols">
                {([["To read", t.prospects.to_research, "None waiting."], ["Ready to pitch", t.prospects.ready, "None ready. Add a company, agency or network under Prospects."]] as const).map(([label, b, none]) => (
                  <div key={label}><b>{label} ({b.total})</b>
                    {b.items.length === 0 ? <p className="muted">{none}</p> : <List>{b.items.map((p: any) => (
                      <div className="item" key={p.id}><span className="main">{p.name} <Chip>{p.category}</Chip>
                        {label === "Ready to pitch" && <span className="muted"> {p.mailboxes ? `${p.mailboxes} mailbox${p.mailboxes === 1 ? "" : "es"}` : "no mailbox: use their form"}</span>}</span>
                        <button onClick={() => open("prospect", p.id)}>Open</button></div>))}</List>}
                  </div>))}
              </div>

              {t.portfolio.unverified.length > 0 && (
                <div className="alert warn" style={{ marginTop: 16 }}>{t.portfolio.unverified.length} portfolio item{t.portfolio.unverified.length === 1 ? " is" : "s are"} not verified, so drafts cannot cite {t.portfolio.unverified.length === 1 ? "it" : "them"}.{" "}
                  <button onClick={() => go("data", "portfolio")}>Verify</button></div>)}
            </>
          );
        }}
      </Async>
    </>
  );
}

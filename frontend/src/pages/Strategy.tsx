import { ReactNode, useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { Async, useLoad } from "../hooks";

type Go = (tab: any, id?: number) => void;
const ELIG: Record<string, string> = { eligible: "ok", review_required: "warn", not_eligible: "bad", unknown: "" };
const SECTIONS: [string, string][] = [["today", "Today"], ["market", "What clients ask for"], ["offers", "What to offer"], ["channels", "Where clients come from"],
  ["networks", "Networks"], ["writing", "How to write"], ["spend", "Spending $50–200"], ["rules", "Rules"], ["numbers", "Your numbers"]];
const STAGE: Record<string, string> = {
  first: "Day 4 or later: send one short follow-up.", last: "Day 10 or later: send the last follow-up, then stop.",
  close: "No answer after two follow-ups, or 21 days: close it and move on.",
};
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return <section id={`strategy-${id}`} aria-labelledby={`h-${id}`} style={{ marginTop: 28 }}><h2 id={`h-${id}`}>{title}</h2>{children}</section>;
}

export default function Strategy({ go }: { go: Go }) {
  const st = useLoad(() => api("/strategy"));
  const tracked = useLoad(() => api("/prospects"));
  const jump = (id: string) => document.getElementById(`strategy-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <>
      <div className="row"><h2 style={{ margin: 0 }}>Strategy: who to write to, what to offer, and why</h2><span style={{ flex: 1 }} /><button onClick={() => { st.reload(true); tracked.reload(true); }}>Refresh</button></div>
      <Async state={st}>
        {(d: any) => (<>
          <p className="muted">
            Counts come from your own database. Facts about outside organisations were read on <b>{d.checked}</b> and each links to its page. Nothing here is a forecast or a promise of work;
            it tells you where to spend a limited number of hours, and the numbers at the bottom show whether it is working.
          </p>
          <nav className="row" aria-label="Strategy sections" style={{ marginBottom: 4 }}>
            {SECTIONS.map(([id, label]) => <button key={id} onClick={() => jump(id)}>{label}</button>)}
          </nav>
          <Today d={d} go={go} reload={() => { st.reload(true); tracked.reload(true); }} />
          <Market d={d} />
          <Offers d={d} />
          <Channels d={d} go={go} />
          <Networks d={d} tracked={tracked.data?.items ?? []} go={go} onAdded={() => tracked.reload(true)} />
          <Writing d={d} />
          <Spend d={d} />
          <Rules d={d} />
          <Numbers d={d} />
        </>)}
      </Async>
    </>
  );
}

// ---------------------------------------------------------------- today
function LeadTable({ items, go, showEmail }: { items: any[]; go: Go; showEmail: boolean }) {
  return (
    <div className="scroll"><table><thead><tr><th>Fit</th><th>Easy</th><th>Company / role</th>{showEmail && <th>Published email</th>}<th></th></tr></thead><tbody>
      {items.map((o) => (
        <tr key={o.id}>
          <td className="score">{o.fit}</td><td>{o.ease}</td>
          <td><b>{o.company || "company not named"}</b><div className="muted">{o.title.slice(0, 100)}</div>
            <span className="chip">{o.engagement}</span><span className={`chip ${o.location_check === "restricted" ? "bad" : "ok"}`}>{o.location_check === "unknown" ? "location not stated" : `location: ${o.location_check}`}</span>
            <span className="chip">{o.source}</span>{o.has_draft && <span className="chip ok">draft ready</span>}</td>
          {showEmail && <td>{o.emails.map((e: any) => (<div key={e.email}><b>{e.email}</b> <span className={`chip ${ELIG[e.eligibility]}`}>{e.eligibility.replace("_", " ")}</span>
            <div className="muted"><ExtLink href={e.source_url}>where it was published</ExtLink></div></div>))}</td>}
          <td><button onClick={() => go("Opportunities", o.id)}>Details / draft</button> <ExtLink href={o.url}>Open ↗</ExtLink></td>
        </tr>))}
    </tbody></table></div>
  );
}

function Today({ d, go, reload }: { d: any; go: Go; reload: () => void }) {
  const t = d.today;
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const act = async (fn: () => Promise<any>, ok: string) => {
    setMsg(null);
    try { await fn(); setMsg({ kind: "ok", text: ok }); reload(); } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
  };
  return (
    <Section id="today" title="Today">
      <div className="panel">
        <b>{t.time_plan.label}</b>
        <ol style={{ margin: "6px 0 0 18px", padding: 0 }}>{t.time_plan.steps.map((s: any) => <li key={s.task}><b>{s.minutes} min</b> · {s.task}</li>)}</ol>
      </div>
      {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}

      <h3>Write to these: they published an email</h3>
      {t.apply_by_email.items.length === 0
        ? <p className="muted">No open lead with a published email fits you right now. Run <b>Research</b> (Best matches) to refresh, or work through the prospects below.</p>
        : <LeadTable items={t.apply_by_email.items} go={go} showEmail />}
      {t.apply_by_email.total > t.apply_by_email.items.length && <p className="muted">{t.apply_by_email.total - t.apply_by_email.items.length} more in the Leads tab.</p>}
      <p className="muted">Contract and freelance work comes first, then work that does not say, then employment. Restricted-to-other-countries listings are never shown here.</p>

      <h3>Apply on the listing: contract or freelance, no email published</h3>
      {t.apply_by_link.items.length === 0
        ? <p className="muted">None right now.</p> : <LeadTable items={t.apply_by_link.items} go={go} showEmail={false} />}
      {t.apply_by_link.total > t.apply_by_link.items.length && <p className="muted">{t.apply_by_link.total - t.apply_by_link.items.length} more in Opportunities (filter by engagement).</p>}

      <h3>Follow-ups due</h3>
      {t.follow_ups.items.length === 0
        ? <p className="muted">Nothing is due{t.follow_ups.waiting ? `; ${t.follow_ups.waiting} sent message${t.follow_ups.waiting === 1 ? " is" : "s are"} still inside the waiting time` : ""}. Log what you send in the Pipeline tab so this list can work.</p>
        : t.follow_ups.items.map((f: any) => (
          <div className="panel" key={f.application_id} style={{ marginBottom: 6 }}>
            <div className="row"><b>{f.title.slice(0, 90)}</b><span className="muted">{f.company}</span><span className="chip">{f.days} days ago</span><span className="chip">{f.kind}</span></div>
            <div className="muted">{STAGE[f.stage]}</div>
            <div className="row" style={{ marginTop: 6 }}>
              {f.stage !== "close" && <button onClick={() => act(() => api(`/applications/${f.application_id}/conversations`, { body: { direction: "out", summary: "Follow-up sent" } }), "Logged. The next follow-up date is counted from the first message.")}>I sent the follow-up</button>}
              <button onClick={() => act(() => api(`/applications/${f.application_id}`, { method: "PATCH", body: { status: "lost" } }), "Closed as lost.")} className={f.stage === "close" ? "primary" : ""}>Close it (no reply)</button>
              <button onClick={() => go(f.kind === "pitch" ? "Prospects" : "Opportunities", f.opportunity_id)}>Open</button>
            </div>
          </div>))}

      <h3>Prospects</h3>
      <div className="cols">
        <div className="panel"><b>To read ({t.prospects.to_research.total})</b>
          {t.prospects.to_research.items.length === 0 ? <p className="muted">None waiting.</p> : t.prospects.to_research.items.map((p: any) => (
            <div key={p.id} className="row"><span>{p.name}</span><span className="chip">{p.category}</span><button onClick={() => go("Prospects", p.id)}>Open</button></div>))}</div>
        <div className="panel"><b>Ready to pitch ({t.prospects.ready.total})</b>
          {t.prospects.ready.items.length === 0 ? <p className="muted">None ready. Add a company or agency you chose under Prospects.</p> : t.prospects.ready.items.map((p: any) => (
            <div key={p.id} className="row"><span>{p.name}</span><span className="chip">{p.category}</span>{p.category !== "network" && <span className="muted">signs {p.need_score}</span>}
              <span className="muted">{p.mailboxes ? `${p.mailboxes} mailbox${p.mailboxes === 1 ? "" : "es"}` : "no mailbox: use their form"}</span><button onClick={() => go("Prospects", p.id)}>Open</button></div>))}</div>
      </div>
      <p className="muted">{t.prospects.total} prospect{t.prospects.total === 1 ? "" : "s"} in total, {t.prospects.contacted} contacted.</p>

      <h3>Make your drafts stronger</h3>
      {t.portfolio.unverified.length === 0 ? <p className="muted">Every portfolio item is verified.</p> : (<>
        <p className="muted">Only portfolio items you verified can be cited. {t.portfolio.verified} verified, {t.portfolio.unverified.length} not:</p>
        {t.portfolio.unverified.map((p: any) => <div key={p.id} className="muted">• <b>{p.title}</b>: {p.note}</div>)}
        <p className="muted">Verify what is true (or add the repository link) under Sources &amp; settings.</p></>)}
    </Section>
  );
}

// ---------------------------------------------------------------- market
function Market({ d }: { d: any }) {
  const m = d.market;
  const gaps = m.skills.filter((s: any) => !s.verified_evidence).slice(0, 3);
  return (
    <Section id="market" title="What clients ask for (in your own data)">
      {m.fitting_listings === 0 ? <p className="muted">No stored listing fits you yet, so there is nothing to count. Run Research first.</p> : (<>
        <p>{m.fitting_listings} stored listings fit you and are not restricted to other countries.{" "}
          {Object.entries(m.engagement).map(([k, v]) => `${v} ${k === "unknown" ? "do not say whether it is contract or employment" : k.replace("_", "-")}`).join(", ")}.</p>
        <h3>Skills they ask for</h3>
        {m.skills.map((s: any) => (
          <div key={s.skill} style={{ marginBottom: 6 }}>
            <div className="row"><b style={{ width: 150 }}>{s.skill}</b><span className="muted">{s.count} listings · {s.share_percent}%</span>
              <span className={`chip ${s.verified_evidence ? "ok" : "warn"}`}>{s.verified_evidence ? "your verified work shows it" : "no verified work shows it"}</span></div>
            <div className="bar"><span style={{ width: `${s.share_percent}%` }} /></div>
          </div>))}
        {gaps.length > 0 && <div className="alert warn">Most asked for with no verified example of yours: <b>{gaps.map((g: any) => `${g.skill} (${g.share_percent}%)`).join(", ")}</b>. One small, honest, working example of each is the best use of an hour before you write more messages.</div>}
        <h3>Where the useful ones come from</h3>
        <div className="scroll"><table><thead><tr><th>Source</th><th>Fit you</th><th>Contract / freelance</th><th>With a published email</th></tr></thead><tbody>
          {m.sources.map((s: any) => <tr key={s.source}><td>{s.source}</td><td>{s.fitting}</td><td>{s.contract_or_freelance}</td><td>{s.with_email}</td></tr>)}</tbody></table></div>
      </>)}
      <h3>What the market pays</h3>
      <p className={m.hourly.median_usd == null ? "muted" : ""}>{m.hourly.median_usd != null && <b>Median ${m.hourly.median_usd}/hour (range ${m.hourly.min_usd} to ${m.hourly.max_usd}). </b>}{m.hourly.note}</p>
    </Section>
  );
}

// ---------------------------------------------------------------- offers
function Offers({ d }: { d: any }) {
  return (
    <Section id="offers" title="What to offer">
      <p className="muted">Sell what you can show. An offer is marked ready when one of your <b>verified</b> portfolio items shows its defining skill. Small, fixed-scope pilots are easiest to say yes to.</p>
      <div className="cols">
        {d.offers.map((o: any) => (
          <div className="panel" key={o.key}>
            <div className="row"><b>{o.label}</b></div>
            <span className={`chip ${o.ready ? "ok" : "warn"}`}>{o.ready ? `ready: ${o.backed_by.join(", ")}` : `add a verified ${o.core_skill} example first`}</span>
            <p className="muted" style={{ margin: "6px 0" }}>For: {o.audience}</p>
            <div><b>You deliver:</b> {o.deliverable}</div>
            <div><b>First step:</b> {o.first_step}</div>
          </div>))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- channels
function Channels({ d, go }: { d: any; go: Go }) {
  return (
    <Section id="channels" title="Where clients come from, and how much attention each deserves">
      <p className="muted">The share is a starting point for your weekly hours. Change it with your own results (see “Your numbers”).</p>
      <div className="cols">
        {d.channels.map((c: any) => (
          <div className="panel" key={c.key}>
            <div className="row"><b>{c.name}</b><span style={{ flex: 1 }} /><span className="chip">{c.share}% of your time</span></div>
            <div className="bar"><span style={{ width: `${c.share}%` }} /></div>
            <p style={{ marginBottom: 4 }}>{c.what}</p>
            <div><b>Why:</b> {c.why}</div>
            <div className="alert warn" style={{ margin: "6px 0" }}><b>Honestly:</b> {c.honest}</div>
            <ul style={{ margin: "4px 0 6px 18px", padding: 0 }}>{c.how.map((h: string) => <li key={h}>{h}</li>)}</ul>
            {["Leads", "Live projects", "Prospects", "Settings"].includes(c.tab) &&
              <button onClick={() => go({ Leads: "Leads (emails)", "Live projects": "Live projects", Prospects: "Prospects", Settings: "Sources & settings" }[c.tab as string])}>Open {c.tab}</button>}
          </div>))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- networks
function Networks({ d, tracked, go, onAdded }: { d: any; tracked: any[]; go: Go; onAdded: () => void }) {
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const have = new Map(tracked.map((p) => [host(p.website), p.id]));
  const add = async (n: any) => {
    setMsg(null);
    try {
      const r = await api("/prospects", { body: { research: true, items: [{ website: n.url, name: n.name, category: "network", evidence_url: n.url, evidence_quote: n.quote }] } });
      setMsg(r.errors.length ? { kind: "error", text: r.errors[0].error } : { kind: "ok", text: `${n.name} is in Prospects; ClientHunt is reading its site.` });
      onAdded();
    } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
  };
  return (
    <Section id="networks" title="Networks you can apply to">
      <p className="muted">Each row is what the network's own page said on {d.checked}. Apply to two or three, once, with your strongest verified project. None of this is a promise of work, and several are very selective.</p>
      {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
      <div className="scroll"><table><thead><tr><th>Network</th><th>How to apply</th><th>Its own words</th><th>Location and hours</th><th>The bar</th><th></th></tr></thead><tbody>
        {d.networks.map((n: any) => (
          <tr key={n.key}>
            <td><b><ExtLink href={n.url}>{n.name} ↗</ExtLink></b></td>
            <td>{n.how_to_apply}{n.email && <div><b>{n.email}</b></div>}</td>
            <td>“{n.quote}”</td>
            <td>{n.location}<div className="muted">{n.hours}</div></td>
            <td>{n.bar}</td>
            <td>{have.has(host(n.url)) ? <button onClick={() => go("Prospects", have.get(host(n.url)))}>Tracked</button> : <button onClick={() => add(n)}>Track in Prospects</button>}</td>
          </tr>))}
      </tbody></table></div>
      {d.not_now.map((x: any) => <div className="alert warn" key={x.name}><b>Not a fit right now: <ExtLink href={x.url}>{x.name}</ExtLink>.</b> {x.reason}</div>)}
    </Section>
  );
}

// ---------------------------------------------------------------- writing
function Writing({ d }: { d: any }) {
  return (
    <Section id="writing" title="How to write, and when to follow up">
      <div className="cols">
        <div className="panel"><b>One message, up to {d.message.max_words} words</b>
          {d.message.parts.map((p: any) => <div key={p.part}><b>{p.part}:</b> {p.text}</div>)}
          <div style={{ marginTop: 8 }}><b>Never:</b></div><ul style={{ margin: "4px 0 0 18px", padding: 0 }}>{d.message.never.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
        <div className="panel"><b>Follow-up rhythm</b>
          <ul style={{ margin: "6px 0 0 18px", padding: 0 }}>{d.follow_up.text.map((x: string) => <li key={x}>{x}</li>)}</ul>
          <b style={{ display: "block", marginTop: 12 }}>Your week</b>
          {d.week.map((w: any) => <div key={w.when}><b>{w.when}:</b> {w.task}</div>)}</div>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- spend
function Spend({ d }: { d: any }) {
  return (
    <Section id="spend" title="Spending your $50–200">
      <p className="muted">{d.spend_plan.budget}</p>
      <div className="scroll"><table><thead><tr><th>What</th><th>Cost</th><th>Why</th></tr></thead><tbody>
        {d.spend_plan.items.map((i: any) => <tr key={i.item}><td><b>{i.item}</b></td><td>{i.cost}</td><td>{i.note}</td></tr>)}</tbody></table></div>
    </Section>
  );
}

// ---------------------------------------------------------------- rules and the Upwork question
function Rules({ d }: { d: any }) {
  const w = d.why_not_upwork;
  return (
    <Section id="rules" title="Rules that protect your income">
      <ul style={{ margin: "0 0 0 18px", padding: 0 }}>{d.rules.map((r: string) => <li key={r}>{r}</li>)}</ul>
      <h3>Why there is no Upwork scraper</h3>
      <div className="panel">
        <p style={{ marginTop: 0 }}><b>Asked:</b> {w.asked} <b>{w.answer}</b></p>
        <b>Why not</b>
        <ul style={{ margin: "4px 0 8px 18px", padding: 0 }}>{w.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
        <b>What ClientHunt does instead</b>
        <ul style={{ margin: "4px 0 8px 18px", padding: 0 }}>{w.instead.map((r: string) => <li key={r}>{r}</li>)}</ul>
        <div className="muted">Read it yourself: {w.sources.map((s: any, i: number) => <span key={s.url}>{i > 0 && " · "}<ExtLink href={s.url}>{s.title} ↗</ExtLink></span>)}</div>
        <div className="muted">{w.note}</div>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- numbers
function Numbers({ d }: { d: any }) {
  const f = d.funnel, inc = d.income;
  const [a, setA] = useState({ ...inc.assumptions });
  const billable = Math.max(0.1, a.hours_per_day * a.days_per_month * a.billable_share);
  const num = (k: string, v: string) => setA({ ...a, [k]: Math.max(0, Number(v) || 0) });
  return (
    <Section id="numbers" title="Your numbers">
      <div className="grid">
        <div className="card"><div className="n">{f.messages_sent}</div><div className="l">messages logged ({f.pitches} to prospects)</div></div>
        <div className="card"><div className="n">{f.replies}</div><div className="l">replies{f.reply_rate_percent != null && ` · ${f.reply_rate_percent}%`}</div></div>
        <div className="card"><div className="n">{f.won}</div><div className="l">won{f.win_rate_percent != null && ` · ${f.win_rate_percent}%`}</div></div>
      </div>
      <p className="muted">{f.note}</p>
      <h3>Income arithmetic</h3>
      <p className="muted">{inc.note}</p>
      <div className="row">
        <label style={{ display: "inline" }}>hours per day <input type="number" step="0.5" min={0} style={{ width: 70 }} value={a.hours_per_day} onChange={(e) => num("hours_per_day", e.target.value)} aria-label="hours per day" /></label>
        <label style={{ display: "inline" }}>days per month <input type="number" min={0} max={31} style={{ width: 70 }} value={a.days_per_month} onChange={(e) => num("days_per_month", e.target.value)} aria-label="days per month" /></label>
        <label style={{ display: "inline" }}>billable share <input type="number" step="0.1" min={0} max={1} style={{ width: 70 }} value={a.billable_share} onChange={(e) => num("billable_share", e.target.value)} aria-label="billable share" /></label>
        <span className="muted">= {Math.round(billable * 10) / 10} billable hours a month</span>
      </div>
      <div className="scroll"><table style={{ marginTop: 8 }}><thead><tr><th>Monthly target</th><th>Hourly rate needed</th>{inc.rows[0].projects.map((p: any) => <th key={p.price}>projects at ${p.price}</th>)}</tr></thead><tbody>
        {inc.rows.map((r: any) => (
          <tr key={r.target}><td><b>${r.target}</b></td><td>${Math.round(r.target / billable)}/h</td>{inc.rows[0].projects.map((p: any) => <td key={p.price}>{Math.ceil(r.target / p.price)}</td>)}</tr>))}
      </tbody></table></div>
    </Section>
  );
}

import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { useApp } from "../ctx";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Msg, Notice, Stat, Table } from "../ui";

const CHANNEL_TAB: Record<string, [string, string, string]> = { Leads: ["find", "", "Find work"], "Live projects": ["find", "live", "Live projects"], Prospects: ["prospects", "", "Prospects"], Settings: ["data", "portfolio", "Portfolio"] };
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

/** The reasoning behind what Today asks of you. Reference material: every section is closed until you want it. */
export default function Plan() {
  const st = useLoad(() => api("/strategy"));
  const tracked = useLoad(() => api("/prospects"));
  return (
    <>
      <h2 className="sr">Plan</h2>
      <Async state={st}>
        {(d: any) => (<>
          <p className="muted">Counts come from your own database. Facts about outside organisations were read on <b>{d.checked}</b> and each links to its page. Nothing here is a forecast or a promise of work.</p>
          <Fold title="What clients ask for"><Market d={d} /></Fold>
          <Fold title="What to offer"><Offers d={d} /></Fold>
          <Fold title="Where clients come from"><Channels d={d} /></Fold>
          <Fold title="Networks you can apply to"><Networks d={d} tracked={tracked.data?.items ?? []} onAdded={() => tracked.reload(true)} /></Fold>
          <Fold title="How to write, and when to follow up"><Writing d={d} /></Fold>
          <Fold title="Spending your $50–200"><Spend d={d} /></Fold>
          <Fold title="Rules that protect your income"><Rules d={d} /></Fold>
          <Fold title="Your numbers"><Numbers d={d} /></Fold>
        </>)}
      </Async>
    </>
  );
}

function Market({ d }: { d: any }) {
  const m = d.market;
  const gaps = m.skills.filter((s: any) => !s.verified_evidence).slice(0, 3);
  return (
    <>
      {m.fitting_listings === 0 ? <p className="muted">No stored listing fits you yet, so there is nothing to count. Run a search first.</p> : (<>
        <p>{m.fitting_listings} stored listings fit you and are not restricted to other countries.{" "}
          {Object.entries(m.engagement).map(([k, v]) => `${v} ${k === "unknown" ? "do not say whether it is contract or employment" : k.replace("_", "-")}`).join(", ")}.</p>
        {m.skills.slice(0, 8).map((s: any) => (
          <div key={s.skill} style={{ marginBottom: 6 }}>
            <div className="row"><b style={{ width: 150 }}>{s.skill}</b><span className="muted">{s.count} listing{s.count === 1 ? "" : "s"} · {s.share_percent}%</span>
              <Chip tone={s.verified_evidence ? "ok" : "warn"}>{s.verified_evidence ? "your verified work shows it" : "no verified work shows it"}</Chip></div>
            <div className="bar"><span style={{ width: `${s.share_percent}%` }} /></div>
          </div>))}
        {gaps.length > 0 && <div className="alert warn">Most asked for with no verified example of yours: <b>{gaps.map((g: any) => `${g.skill} (${g.share_percent}%)`).join(", ")}</b>. One small, honest, working example of each is the best use of an hour before you write more messages.</div>}
        <h3>Where the useful ones come from</h3>
        <Table head={["Source", "Fit you", "Contract / freelance", "With a published email"]}>
          {m.sources.map((s: any) => <tr key={s.source}><td>{s.source}</td><td>{s.fitting}</td><td>{s.contract_or_freelance}</td><td>{s.with_email}</td></tr>)}
        </Table>
      </>)}
      <h3>What the market pays</h3>
      <p className={m.hourly.median_usd == null ? "muted" : ""}>{m.hourly.median_usd != null && <b>Median ${m.hourly.median_usd}/hour (range ${m.hourly.min_usd} to ${m.hourly.max_usd}). </b>}{m.hourly.note}</p>
    </>
  );
}

function Offers({ d }: { d: any }) {
  return (
    <div className="cols">
      {d.offers.map((o: any) => (
        <div className="panel" key={o.key}>
          <b>{o.label}</b>
          <div><Chip tone={o.ready ? "ok" : "warn"}>{o.ready ? `ready: ${o.backed_by.join(", ")}` : `add a verified ${o.core_skill} example first`}</Chip></div>
          <div><b>You deliver:</b> {o.deliverable}</div>
          <div><b>First step:</b> {o.first_step}</div>
        </div>))}
    </div>
  );
}

function Channels({ d }: { d: any }) {
  const { go } = useApp();
  return (
    <div className="cols">
      {d.channels.map((c: any) => (
        <div className="panel" key={c.key}>
          <div className="row"><b className="grow">{c.name}</b><Chip>{c.share}% of your time</Chip></div>
          <div className="bar"><span style={{ width: `${c.share}%` }} /></div>
          <p>{c.what}</p>
          <div className="alert warn"><b>Honestly:</b> {c.honest}</div>
          {CHANNEL_TAB[c.tab] && <button onClick={() => go(CHANNEL_TAB[c.tab][0], CHANNEL_TAB[c.tab][1])}>Open {CHANNEL_TAB[c.tab][2]}</button>}
        </div>))}
    </div>
  );
}

function Networks({ d, tracked, onAdded }: { d: any; tracked: any[]; onAdded: () => void }) {
  const { open } = useApp();
  const [msg, setMsg] = useState<Msg>(null);
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
    <>
      <p className="muted">What each network's own page said on {d.checked}. Apply to two or three, once, with your strongest verified project; several are very selective.</p>
      <Notice msg={msg} />
      <Table head={["Network", "How to apply", "Its own words", "Location, hours, the bar", ""]}>
        {d.networks.map((n: any) => (
          <tr key={n.key}>
            <td><b><ExtLink href={n.url}>{n.name} ↗</ExtLink></b></td>
            <td>{n.how_to_apply}{n.email && <div><b>{n.email}</b></div>}</td>
            <td>“{n.quote}”</td>
            <td>{n.location}<div className="muted">{n.hours}</div><div className="muted">{n.bar}</div></td>
            <td>{have.has(host(n.url)) ? <button onClick={() => open("prospect", have.get(host(n.url))!)}>Tracked</button> : <button onClick={() => add(n)}>Track in Prospects</button>}</td>
          </tr>))}
      </Table>
      {d.not_now.map((x: any) => <div className="alert warn" key={x.name}><b>Not a fit right now: <ExtLink href={x.url}>{x.name}</ExtLink>.</b> {x.reason}</div>)}
    </>
  );
}

function Writing({ d }: { d: any }) {
  return (
    <div className="cols">
      <div><b>One message, up to {d.message.max_words} words</b>
        {d.message.parts.map((p: any) => <div key={p.part}><b>{p.part}:</b> {p.text}</div>)}
        <b style={{ display: "block", marginTop: 8 }}>Never:</b><ul>{d.message.never.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
      <div><b>Follow-up rhythm</b><ul>{d.follow_up.text.map((x: string) => <li key={x}>{x}</li>)}</ul>
        <b>Your week</b>{d.week.map((w: any) => <div key={w.when}><b>{w.when}:</b> {w.task}</div>)}</div>
    </div>
  );
}

function Spend({ d }: { d: any }) {
  return (
    <>
      <p className="muted">{d.spend_plan.budget}</p>
      <Table head={["What", "Cost", "Why"]}>
        {d.spend_plan.items.map((i: any) => <tr key={i.item}><td><b>{i.item}</b></td><td>{i.cost}</td><td>{i.note}</td></tr>)}
      </Table>
    </>
  );
}

function Rules({ d }: { d: any }) {
  const w = d.why_not_upwork;
  return (
    <>
      <ul>{d.rules.map((r: string) => <li key={r}>{r}</li>)}</ul>
      <Fold title="Why there is no Upwork scraper">
        <p style={{ marginTop: 0 }}><b>Asked:</b> {w.asked} <b>{w.answer}</b></p>
        <b>Why not</b><ul>{w.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
        <b>What ClientHunt does instead</b><ul>{w.instead.map((r: string) => <li key={r}>{r}</li>)}</ul>
        <div className="muted">Read it yourself: {w.sources.map((s: any, i: number) => <span key={s.url}>{i > 0 && " · "}<ExtLink href={s.url}>{s.title} ↗</ExtLink></span>)}</div>
        <div className="muted">{w.note}</div>
      </Fold>
    </>
  );
}

function Numbers({ d }: { d: any }) {
  const f = d.funnel, inc = d.income;
  const [a, setA] = useState({ ...inc.assumptions });
  const billable = Math.max(0.1, a.hours_per_day * a.days_per_month * a.billable_share);
  const num = (k: string, v: string) => setA({ ...a, [k]: Math.max(0, Number(v) || 0) });
  const field = (k: string, label: string, props: object) => (
    <label className="in">{label} <input type="number" style={{ width: 70 }} value={a[k]} onChange={(e) => num(k, e.target.value)} aria-label={label} {...props} /></label>);
  return (
    <>
      <div className="stats">
        <Stat n={f.messages_sent} label={`messages logged (${f.pitches} to prospects)`} />
        <Stat n={f.replies} label={`replies${f.reply_rate_percent != null ? ` · ${f.reply_rate_percent}%` : ""}`} />
        <Stat n={f.won} label={`won${f.win_rate_percent != null ? ` · ${f.win_rate_percent}%` : ""}`} />
      </div>
      <p className="muted">{f.note}</p>
      <h3>Income arithmetic</h3>
      <p className="muted">{inc.note}</p>
      <div className="row">
        {field("hours_per_day", "hours per day", { step: "0.5", min: 0 })}
        {field("days_per_month", "days per month", { min: 0, max: 31 })}
        {field("billable_share", "billable share", { step: "0.1", min: 0, max: 1 })}
        <span className="muted">= {Math.round(billable * 10) / 10} billable hours a month</span>
      </div>
      <Table head={["Monthly target", "Hourly rate needed", ...inc.rows[0].projects.map((p: any) => `projects at $${p.price}`)]}>
        {inc.rows.map((r: any) => (
          <tr key={r.target}><td><b>${r.target}</b></td><td>${Math.round(r.target / billable)}/h</td>{inc.rows[0].projects.map((p: any) => <td key={p.price}>{Math.ceil(r.target / p.price)}</td>)}</tr>))}
      </Table>
    </>
  );
}

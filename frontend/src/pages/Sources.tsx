import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { safeUrl } from "../format";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Msg, Notice, Table } from "../ui";

const RESOURCES = [
  { name: "Upwork", url: "https://www.upwork.com/freelance-jobs/machine-learning/", what: "The largest marketplace. Scraping is not allowed and its API needs approval.", how: "Save a search, turn on email alerts, paste the alert text into the import box above." },
  { name: "Contra", url: "https://contra.com/opportunities", what: "Independent-professional marketplace with open opportunities.", how: "Browse and apply on the site; use its notifications." },
  { name: "PeoplePerHour", url: "https://www.peopleperhour.com/freelance-jobs/technology-programming", what: "UK-based freelance marketplace, programming category.", how: "Use its email alerts and paste them into the import box above." },
  { name: "Guru", url: "https://www.guru.com/d/jobs/", what: "Long-running freelance marketplace.", how: "Use its job alerts." },
  { name: "Wellfound", url: "https://wellfound.com/jobs", what: "Startup jobs, including contract roles.", how: "Filter for remote and contract; set alerts." },
  { name: "A.Team", url: "https://www.a.team/", what: "Network of independent engineers. It posts roles like “Senior Independent AI Engineer” (also seen in We Work Remotely).", how: "Apply to join the network; its roles also arrive through the We Work Remotely source." },
  { name: "Toptal", url: "https://www.toptal.com/talent/apply", what: "Vetted freelancer network: clients are matched to you after you pass screening.", how: "A slower path, but clients come to you." },
  { name: "Braintrust", url: "https://www.usebraintrust.com/", what: "Talent network with a jobs board for freelancers.", how: "Create a profile and apply to jobs." },
  { name: "Turing", url: "https://www.turing.com/jobs", what: "Remote developer matching platform.", how: "Apply once and be matched to roles." },
  { name: "Arc", url: "https://arc.dev/remote-jobs", what: "Remote developer jobs, including contract roles.", how: "Filter by contract; set alerts." },
  { name: "Reddit r/forhire", url: "https://www.reddit.com/r/forhire/", what: "People post “[Hiring]” projects. Reddit's robots.txt blocks automated reading, so the app never reads it.", how: "Read it yourself and reply on Reddit." },
  { name: "Hacker News: “Freelancer? Seeking freelancer?” threads", url: "https://hn.algolia.com/?dateRange=pastYear&query=Seeking%20freelancer&sort=byDate&type=story", what: "Posted monthly until October 2025. No newer thread exists (checked 2026-10-27), so what is left is stale.", how: "Skip it. The monthly “Who is hiring?” thread is already a source." },
  { name: "Zindi", url: "https://zindi.africa/competitions", what: "Africa-focused data science and AI challenges with prizes (competitions, not client work).", how: "Good for visibility and practice." },
];

const status = (kind: string): [string, string] =>
  kind === "unavailable" ? ["not available / needs authorisation", "warn"] : kind === "live" ? ["live view only (not stored)", "ok"] : ["usable", "ok"];

/** Where listings come from, and the two ways to bring in the ones no source can read for you. */
export default function Sources() {
  const sources = useLoad(() => api("/sources"));
  const [alert, setAlert] = useState("");
  const [plat, setPlat] = useState("");
  const [msg, setMsg] = useState<Msg>(null);
  const empty = { title: "", url: "", company_name: "", company_website: "", description: "" };
  const [m, setM] = useState(empty);
  const wrap = async (fn: () => Promise<string>) => { try { setMsg({ kind: "ok", text: await fn() }); } catch (e: any) { setMsg({ kind: "error", text: e.message }); } };
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) setAlert(await f.text()); };
  return (
    <>
      <Notice msg={msg} />
      <div className="cols">
        <div className="panel"><b>Import an alert email</b><div className="muted">Upwork, Contra, PeoplePerHour, Guru, Wellfound… parsed locally.</div>
          <textarea value={alert} onChange={(e) => setAlert(e.target.value)} aria-label="alert email text" style={{ minHeight: 120 }} />
          <div className="row"><input type="file" accept=".eml,.txt,.html" onChange={onFile} aria-label="alert file" /><input placeholder="platform hint (optional)" value={plat} onChange={(e) => setPlat(e.target.value)} />
            <button className="primary" disabled={alert.length < 10} onClick={() => wrap(async () => { const r = await api("/alerts/import", { body: { text: alert, platform_hint: plat } }); setAlert(""); return `Parsed ${r.parsed} job link(s); CSV ${r.run.exports[0]?.filename ?? "n/a"}`; })}>Import</button></div></div>
        <div className="panel"><b>Add a listing by hand</b>
          {(["title", "url", "company_name", "company_website"] as const).map((k) => (<div key={k}><label>{k.replace("_", " ")}</label><input aria-label={k.replace("_", " ")} value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })} /></div>))}
          <label>description</label><textarea aria-label="description" style={{ minHeight: 60 }} value={m.description} onChange={(e) => setM({ ...m, description: e.target.value })} />
          <div style={{ marginTop: 8 }}><button onClick={() => wrap(async () => { await api("/opportunities/manual", { body: m }); setM(empty); return "Added. See Find work."; })}>Add</button></div></div>
      </div>

      <h3>Sources</h3>
      <Async state={sources}>{(s: any[]) => (
        <Table head={["Source", "Status", `Notes (checked ${s[0]?.checked_at})`]}>
          {s.map((x) => { const [label, tone] = status(x.kind); return (
            <tr key={x.key}><td><b>{x.name}</b><div>{safeUrl(x.docs_url) && <ExtLink href={x.docs_url}>docs</ExtLink>} {safeUrl(x.terms_url) && <ExtLink href={x.terms_url}>terms</ExtLink>}</div></td>
              <td><Chip tone={tone}>{label}</Chip>{!x.verified && <Chip tone="warn">terms not fully verified</Chip>}</td><td>{x.notes}</td></tr>); })}
        </Table>)}</Async>

      <h3>Other places to look</h3>
      <Fold title={`${RESOURCES.length} sites that do not allow automated reading: open them yourself`} testId="resources">
        <Table head={["Where", "What it is", "How to use it"]}>
          {RESOURCES.map((r) => (<tr key={r.name}><td><a href={r.url} target="_blank" rel="noreferrer"><b>{r.name} ↗</b></a></td><td>{r.what}</td><td>{r.how}</td></tr>))}
        </Table>
      </Fold>
    </>
  );
}

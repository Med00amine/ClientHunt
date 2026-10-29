import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { ago } from "../format";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Table } from "../ui";

const DEFAULT_Q = "machine learning, LLM, RAG, AI agent, NLP, computer vision, python, data science, FastAPI, AWS, chatbot, OpenAI, GPT, AI, automation, scraping, data engineer, Django";
const SOURCES: [string, string][] = [["hn_freelance", "HN: Seeking freelancer"], ["hn_hiring", "HN: Who is hiring (contract / part-time)"], ["reddit", "Reddit [Hiring] posts"],
  ["mastodon", "Mastodon #hiring / #freelance"], ["boards", "Remote boards (contract only)"]];

/** One quiet line: how many posts each source gave. A source that is busy or down is named, not shouted. */
function SourceLine({ sources }: { sources: Record<string, any> }) {
  return (
    <p className="muted" data-testid="source-line">
      {Object.entries(sources).map(([k, s], i) => (
        <span key={k} title={s.error ?? s.note ?? ""}>{i > 0 && " · "}{s.name}: {s.ok ? `${s.matching ?? s.posts} matching` : "unavailable right now"}</span>))}
    </p>
  );
}
const FROM: Record<string, string> = { text: "written in the post", address: "read from the address", poster: "the account that posted", post: "the post header", domain: "read from the email domain" };

type Row = { name: string; email: string; company: string; name_from: string; company_from: string; invited?: boolean; post_title?: string; post_url?: string; source_name?: string };

function csv(rows: Row[]) {
  const q = (v = "") => `"${String(v).replace(/"/g, '""')}"`;
  return ["Name,Email,Company,Post,Link", ...rows.map((r) => [r.name, r.email, r.company, r.post_title, r.post_url].map(q).join(","))].join("\n");
}

function download(rows: Row[]) {
  const url = URL.createObjectURL(new Blob([csv(rows)], { type: "text/csv" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "client-emails.csv" });
  a.click();
  URL.revokeObjectURL(url);
}

/** Name / Email / Company. Each guessed value says where it came from (hover), so a guess never looks like a fact. */
export function EmailTable({ rows, withPost }: { rows: Row[]; withPost?: boolean }) {
  return (
    <Table head={["Name", "Email", "Company", ...(withPost ? ["Post"] : [])]}>
      {rows.map((r, i) => (
        <tr key={r.email + i}>
          <td title={r.name ? `Name ${FROM[r.name_from] ?? ""}` : ""}>{r.name || <span className="muted">not given</span>}{r.name_from === "address" && <span className="muted"> *</span>}</td>
          <td><a href={`mailto:${r.email}`}>{r.email}</a>{r.invited && <Chip tone="ok" title="The post invites you to write to this address">invited</Chip>}</td>
          <td title={r.company ? `Company ${FROM[r.company_from] ?? ""}` : ""}>{r.company || <span className="muted">not given</span>}{r.company_from === "domain" && <span className="muted"> *</span>}</td>
          {withPost && <td><ExtLink href={r.post_url}>{(r.post_title ?? "").slice(0, 60)} ↗</ExtLink><div className="muted">{r.source_name}</div></td>}
        </tr>))}
    </Table>
  );
}

function Extractor() {
  const [text, setText] = useState("");
  const [rows, setRows] = useState<Row[] | null>(null);
  const [err, setErr] = useState("");
  const run = async () => {
    setErr("");
    try { setRows((await api<{ rows: Row[] }>("/tools/extract-emails", { body: { text } })).rows); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Fold title="Find the client emails in any text (paste a post, a page or an email thread)" plain>
      <textarea aria-label="text to search for emails" style={{ minHeight: 120 }} value={text} onChange={(e) => setText(e.target.value)}
        placeholder={"Paste text here. Example:\nWe're hiring an ML engineer at Acme Labs. Contact Jane Doe <jane@acme-labs.example> to apply."} />
      <div className="row" style={{ margin: "6px 0" }}>
        <button className="primary" disabled={!text.trim()} onClick={run}>Find emails</button>
        {rows && rows.length > 0 && <button onClick={() => download(rows)}>⬇ Download CSV</button>}
        {err && <span className="bad">{err}</span>}
      </div>
      {rows && (rows.length ? <EmailTable rows={rows} /> : <p className="muted">No usable email address in this text.</p>)}
    </Fold>
  );
}

export default function LiveProjects() {
  const [form, setForm] = useState({ q: DEFAULT_Q, sources: SOURCES.map(([k]) => k), only_email: false, sort: "best" });
  const [applied, setApplied] = useState(form);
  const qs = new URLSearchParams({ q: applied.q, sources: applied.sources.join(","), only_email: String(applied.only_email), sort: applied.sort, limit: "120" }).toString();
  const st = useLoad(() => api(`/live/projects?${qs}`), [qs]);
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });
  const toggle = (k: string) => set("sources", form.sources.includes(k) ? form.sources.filter((s) => s !== k) : [...form.sources, k]);
  return (
    <>
      <div className="alert" style={{ borderColor: "var(--accent)" }}>
        Clients asking for help right now on Hacker News, Reddit, Mastodon and remote job boards, read through their public APIs and feeds, with the emails they published. Nothing is stored: open the post and reply or email the client yourself.
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input aria-label="search words" className="grow" value={form.q} onChange={(e) => set("q", e.target.value)} />
        <select aria-label="sort" value={form.sort} onChange={(e) => set("sort", e.target.value)}><option value="best">Best chance first</option><option value="newest">Newest first</option></select>
        <button className="primary" onClick={() => (JSON.stringify(applied) === JSON.stringify(form) ? st.reload() : setApplied(form))}>Search</button>
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        {SOURCES.filter(([k]) => k !== "reddit" || (st.data as any)?.reddit_configured).map(([k, label]) => <label key={k} className="in"><input type="checkbox" checked={form.sources.includes(k)} onChange={() => toggle(k)} /> {label}</label>)}
        <label className="in"><input type="checkbox" checked={form.only_email} onChange={(e) => set("only_email", e.target.checked)} /> only posts with an email</label>
      </div>
      <Extractor />
      <Async state={st} empty={(d: any) => (d.items.length ? null : "No client posts match. Add more search words or tick more sources.")}>
        {(d: any) => (
          <>
            <SourceLine sources={d.sources} />
            {d.emails.length > 0 && (
              <>
                <div className="row"><h3 style={{ margin: "12px 0 4px" }}>Client emails ({d.emails.length})</h3>
                  <button onClick={() => download(d.emails)}>⬇ Download CSV</button></div>
                <p className="muted">* = guessed from the email address, not written in the post. Hover a name or company to see where it came from.</p>
                <EmailTable rows={d.emails} withPost />
              </>
            )}
            <h3 style={{ margin: "12px 0 4px" }}>Posts ({d.total_matches})</h3>
            <p className="muted">Kept in memory for {d.cached_for_minutes} minutes.</p>
            <Table head={[<span title="Skill fit, plus a published email, plus freshness. A heuristic.">Chance</span>, "Post", "Emails", "Posted"]}>
              {d.items.map((p: any) => (
                <tr key={p.id}>
                  <td className="score">{Math.round(p.worth)}</td>
                  <td><ExtLink href={p.url}><b>{p.title}</b> ↗</ExtLink> <Chip>{p.source_name}</Chip>{p.engagement !== "unknown" && <Chip>{p.engagement.replace("_", "-")}</Chip>}
                    <div className="muted">{p.excerpt.slice(0, 200)}{p.excerpt.length > 200 ? "…" : ""}</div>
                    <div>{p.matched_skills.slice(0, 6).map((s: string) => <Chip key={s}>{s}</Chip>)}</div></td>
                  <td>{p.emails.length ? p.emails.map((e: Row) => <div key={e.email}><a href={`mailto:${e.email}`}>{e.email}</a></div>) : <span className="muted">reply on the post</span>}</td>
                  <td>{p.age_minutes != null ? ago(p.age_minutes) : ""}<div className="muted">{p.poster}</div></td>
                </tr>))}
            </Table>
          </>
        )}
      </Async>
    </>
  );
}

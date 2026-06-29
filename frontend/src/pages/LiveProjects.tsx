import { ExtLink } from "../components";
import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import { ago, safeUrl } from "../format";

const DEFAULT_Q = "machine learning, LLM, RAG chatbot, AI agent, NLP, computer vision";
const TONE: Record<string, string> = { "few bids": "ok", "some bids": "warn", crowded: "bad" };

export default function LiveProjects() {
  const [form, setForm] = useState({ q: DEFAULT_Q, min_usd: 100, min_hourly_usd: 20, max_bids: 0, kind: "", sort: "best" });
  const [applied, setApplied] = useState(form);
  const qs = new URLSearchParams({ q: applied.q, min_usd: String(applied.min_usd), min_hourly_usd: String(applied.min_hourly_usd),
    max_bids: String(applied.max_bids), kind: applied.kind, sort: applied.sort, limit: "60" }).toString();
  const st = useLoad(() => api(`/live/freelancer?${qs}`), [qs]);
  const set = (k: string, v: any) => setForm({ ...form, [k]: v });
  return (
    <>
      <h2>Live projects: clients who need AI / ML work right now</h2>
      <div className="alert" style={{ borderColor: "var(--accent)" }}>
        Shown live from Freelancer.com's public API. <b>Its terms do not allow storing its data</b>, so these projects are never saved, exported or added to your runs.
        You bid on Freelancer.com yourself. Open the project to read the full brief.
      </div>
      <div className="panel" style={{ marginBottom: 12 }}>
        <label htmlFor="lq">Search words (comma-separated, up to 6)</label>
        <input id="lq" style={{ width: "100%" }} value={form.q} onChange={(e) => set("q", e.target.value)} />
        <div className="row" style={{ marginTop: 8 }}>
          <label style={{ display: "inline" }}>fixed price ≥ $ <input aria-label="min fixed budget" type="number" style={{ width: 80 }} value={form.min_usd} onChange={(e) => set("min_usd", Number(e.target.value))} /></label>
          <label style={{ display: "inline" }}>hourly ≥ $ <input aria-label="min hourly rate" type="number" style={{ width: 70 }} value={form.min_hourly_usd} onChange={(e) => set("min_hourly_usd", Number(e.target.value))} /></label>
          <label style={{ display: "inline" }}>at most <input aria-label="max bids" type="number" style={{ width: 70 }} value={form.max_bids} onChange={(e) => set("max_bids", Number(e.target.value))} /> bids (0 = any)</label>
          <select aria-label="type" value={form.kind} onChange={(e) => set("kind", e.target.value)}><option value="">Fixed and hourly</option><option value="fixed">Fixed price</option><option value="hourly">Hourly</option></select>
          <select aria-label="sort" value={form.sort} onChange={(e) => set("sort", e.target.value)}><option value="best">Best chance first</option><option value="newest">Newest first</option><option value="fewest_bids">Fewest bids first</option></select>
          <button className="primary" onClick={() => (JSON.stringify(applied) === JSON.stringify(form) ? st.reload() : setApplied(form))}>Search</button>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>“Chance” = how well it matches your skills, minus competition (many bids), plus a little for being fresh. It is a heuristic. Few bids and posted recently is the best combination.</p>
      </div>
      <Async state={st} empty={(d: any) => (d.items.length ? null : "No open projects match. Lower the budget limits or change the search words.")}>
        {(d: any) => (
          <>
            <p className="muted">{d.total_matches} matching open projects (showing {d.items.length}). Results are kept in memory for {d.cached_for_minutes} minutes.</p>
            <div className="scroll"><table><thead><tr><th title="match with your skills, minus competition">Chance</th><th>Project</th><th>Budget</th><th>Bids</th><th>Posted</th><th>Fit</th></tr></thead><tbody>
              {d.items.map((p: any) => (
                <tr key={p.id}>
                  <td className="score">{Math.round(p.worth)}</td>
                  <td><ExtLink href={p.url}><b>{p.title}</b> ↗</ExtLink>{p.urgent && <span className="chip warn">urgent</span>}
                    <div className="muted">{p.excerpt.slice(0, 170)}{p.excerpt.length > 170 ? "…" : ""}</div>
                    <div>{p.skills.slice(0, 6).map((s: string) => <span className="chip" key={s}>{s}</span>)}</div></td>
                  <td>{p.currency_sign}{p.budget_min.toFixed(0)}–{p.budget_max.toFixed(0)} {p.currency}{p.type === "hourly" ? " / h" : ""}
                    <div className="muted">{p.budget_max_usd != null ? `≈ $${p.budget_max_usd.toFixed(0)} max` : ""} · {p.type}</div></td>
                  <td>{p.bids} <span className={`chip ${TONE[p.competition]}`}>{p.competition}</span></td>
                  <td>{ago(p.age_minutes)}</td>
                  <td>{Math.round(p.fit)}</td>
                </tr>))}
            </tbody></table></div>
          </>
        )}
      </Async>
    </>
  );
}

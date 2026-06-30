import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { ago } from "../format";
import { Async, useLoad } from "../hooks";
import { Chip, Fold, Table } from "../ui";

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
      <div className="alert" style={{ borderColor: "var(--accent)" }}>
        Live from Freelancer.com's public API. Its terms do not allow storing its data, so these projects are never saved or exported. You bid on Freelancer.com yourself.
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input aria-label="search words" className="grow" value={form.q} onChange={(e) => set("q", e.target.value)} />
        <label className="in">at most <input aria-label="max bids" type="number" style={{ width: 60 }} value={form.max_bids} onChange={(e) => set("max_bids", Number(e.target.value))} /> bids (0 = any)</label>
        <select aria-label="sort" value={form.sort} onChange={(e) => set("sort", e.target.value)}><option value="best">Best chance first</option><option value="newest">Newest first</option><option value="fewest_bids">Fewest bids first</option></select>
        <button className="primary" onClick={() => (JSON.stringify(applied) === JSON.stringify(form) ? st.reload() : setApplied(form))}>Search</button>
      </div>
      <Fold title="Budget filters" plain>
        <div className="row">
          <label className="in">fixed price ≥ $ <input aria-label="min fixed budget" type="number" style={{ width: 80 }} value={form.min_usd} onChange={(e) => set("min_usd", Number(e.target.value))} /></label>
          <label className="in">hourly ≥ $ <input aria-label="min hourly rate" type="number" style={{ width: 70 }} value={form.min_hourly_usd} onChange={(e) => set("min_hourly_usd", Number(e.target.value))} /></label>
          <select aria-label="type" value={form.kind} onChange={(e) => set("kind", e.target.value)}><option value="">Fixed and hourly</option><option value="fixed">Fixed price</option><option value="hourly">Hourly</option></select>
        </div>
      </Fold>
      <Async state={st} empty={(d: any) => (d.items.length ? null : "No open projects match. Lower the budget limits or change the search words.")}>
        {(d: any) => (
          <>
            <p className="muted">{d.total_matches} matching open projects (showing {d.items.length}), kept in memory for {d.cached_for_minutes} minutes.</p>
            <Table head={[<span title="How well it matches your skills, minus competition, plus a little for being fresh. A heuristic.">Chance</span>, "Project", "Budget", "Bids"]}>
              {d.items.map((p: any) => (
                <tr key={p.id}>
                  <td className="score">{Math.round(p.worth)}</td>
                  <td><ExtLink href={p.url}><b>{p.title}</b> ↗</ExtLink>{p.urgent && <Chip tone="warn">urgent</Chip>}
                    <div className="muted">{p.excerpt.slice(0, 170)}{p.excerpt.length > 170 ? "…" : ""}</div>
                    <div>{p.skills.slice(0, 6).map((s: string) => <Chip key={s}>{s}</Chip>)}</div></td>
                  <td>{p.currency_sign}{p.budget_min.toFixed(0)}–{p.budget_max.toFixed(0)} {p.currency}{p.type === "hourly" ? " / h" : ""}
                    <div className="muted">{p.budget_max_usd != null ? `≈ $${p.budget_max_usd.toFixed(0)} max · ` : ""}{p.type}</div></td>
                  <td>{p.bids} <Chip tone={TONE[p.competition]}>{p.competition}</Chip><div className="muted">{ago(p.age_minutes)}</div></td>
                </tr>))}
            </Table>
          </>
        )}
      </Async>
    </>
  );
}

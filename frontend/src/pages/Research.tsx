import { useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import RunSummary from "./RunSummary";

const ENGAGEMENTS = ["contract", "freelance", "part_time", "full_time"];
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function Research({ go }: { go: (t: any, id?: number) => void }) {
  const profiles = useLoad(() => api("/profiles"));
  const sources = useLoad(() => api("/sources"));
  const runs = useLoad(() => api("/runs?limit=5"), [], 2500);
  const [profileId, setProfileId] = useState<number | "custom">(0 as any);
  const [f, setF] = useState<any>({ name: "Custom search", keywords: "python, fastapi", skills: "python", remote_only: true, engagement: ["contract", "freelance", "part_time"],
    min_rate: "", country: "", posted_within_days: 30, max_results: 100, max_budget_usd: 1, min_fit: 20, sources: ["remotive", "remoteok", "himalayas", "hn_hiring"], max_companies: 10, max_drafts: 3, require_email: false, min_ease: 0 });
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const toggle = (k: string, v: string) => set(k, f[k].includes(v) ? f[k].filter((x: string) => x !== v) : [...f[k], v]);

  const start = async () => {
    setBusy(true); setMsg(null);
    try {
      const body = profileId === "custom"
        ? { search: { name: f.name, keywords: csv(f.keywords), required_skills: csv(f.skills), sources: f.sources, remote_only: f.remote_only, engagement_types: f.engagement,
            min_rate: f.min_rate === "" ? null : Number(f.min_rate), country: f.country, posted_within_days: Number(f.posted_within_days) || null,
            max_results: Number(f.max_results), max_budget_usd: Number(f.max_budget_usd), min_fit: Number(f.min_fit), max_companies: Number(f.max_companies), max_drafts: Number(f.max_drafts), require_email: f.require_email, min_ease: Number(f.min_ease) } }
        : { profile_id: profileId || profiles.data?.[0]?.id };
      const r = await api("/runs", { body });
      setMsg({ kind: "ok", text: `Run #${r.id} queued.` });
      runs.reload(true);
    } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
    setBusy(false);
  };
  const saveProfile = async () => {
    try {
      await api("/profiles", { body: { name: f.name, params: { name: f.name, keywords: csv(f.keywords), required_skills: csv(f.skills), sources: f.sources, remote_only: f.remote_only, engagement_types: f.engagement,
        posted_within_days: Number(f.posted_within_days) || null, max_results: Number(f.max_results), max_budget_usd: Number(f.max_budget_usd), min_fit: Number(f.min_fit), require_email: f.require_email, min_ease: Number(f.min_ease) } } });
      profiles.reload(true); setMsg({ kind: "ok", text: "Profile saved." });
    } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
  };

  return (
    <>
      <h2>Research</h2>
      <div className="panel">
        <label htmlFor="prof">Saved search</label>
        {profiles.error && <div className="alert error" role="alert">{profiles.error}</div>}
        <select id="prof" value={profileId as any} onChange={(e) => setProfileId(e.target.value === "custom" ? "custom" : Number(e.target.value))}>
          {(profiles.data ?? []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
          <option value="custom">Custom search…</option>
        </select>
        {profileId !== "custom" && profiles.data && (
          <p className="muted">{(() => { const p = profiles.data.find((x: any) => x.id === (profileId || profiles.data[0].id)); return p ? `Keywords: ${p.params.keywords.join(", ")} · skills: ${p.params.required_skills.join(", ")} · sources: ${p.params.sources.join(", ")}` : ""; })()}</p>
        )}
        {profileId === "custom" && (
          <div className="cols">
            <div>
              <label>Name</label><input aria-label="Name" value={f.name} onChange={(e) => set("name", e.target.value)} />
              <label>Keywords (comma-separated)</label><input aria-label="Keywords (comma-separated)" value={f.keywords} onChange={(e) => set("keywords", e.target.value)} />
              <label>Required skills</label><input aria-label="Required skills" value={f.skills} onChange={(e) => set("skills", e.target.value)} />
              <label>Country / time-zone requirement (excludes listings restricted elsewhere)</label><input aria-label="Country / time-zone requirement (excludes listings restricted elsewhere)" value={f.country} onChange={(e) => set("country", e.target.value)} placeholder="e.g. Tunisia" />
              <label>Min hourly rate (when published)</label><input aria-label="Min hourly rate (when published)" type="number" value={f.min_rate} onChange={(e) => set("min_rate", e.target.value)} />
            </div>
            <div>
              <label>Sources</label>
              {(sources.data ?? []).filter((s: any) => s.kind === "api").map((s: any) => (
                <div key={s.key}><label style={{ display: "inline" }}><input type="checkbox" checked={f.sources.includes(s.key)} onChange={() => toggle("sources", s.key)} /> {s.name}</label></div>))}
              <p className="muted">Upwork, Fiverr and similar platforms are not API sources here; use Sources &amp; settings → Alert import.</p>
              <label>Engagement type</label>
              {ENGAGEMENTS.map((e) => (<label key={e} style={{ display: "inline", marginRight: 8 }}><input type="checkbox" checked={f.engagement.includes(e)} onChange={() => toggle("engagement", e)} /> {e.replace("_", " ")}</label>))}
              <div><label style={{ display: "inline" }}><input type="checkbox" checked={f.remote_only} onChange={(e) => set("remote_only", e.target.checked)} /> Remote only</label></div>
              <div><label style={{ display: "inline" }}><input type="checkbox" checked={f.require_email} onChange={(e) => set("require_email", e.target.checked)} /> Only listings with an email to apply</label></div>
              <label>Min “easy to reach” score (0–100)</label><input aria-label="Min “easy to reach” score (0–100)" type="number" value={f.min_ease} onChange={(e) => set("min_ease", e.target.value)} />
            </div>
            <div>
              <label>Posted within (days)</label><input aria-label="Posted within (days)" type="number" value={f.posted_within_days} onChange={(e) => set("posted_within_days", e.target.value)} />
              <label>Max results</label><input aria-label="Max results" type="number" value={f.max_results} onChange={(e) => set("max_results", e.target.value)} />
              <label>Min fit score to keep</label><input aria-label="Min fit score to keep" type="number" value={f.min_fit} onChange={(e) => set("min_fit", e.target.value)} />
              <label>Max research budget for this run (USD)</label><input aria-label="Max research budget for this run (USD)" type="number" step="0.1" value={f.max_budget_usd} onChange={(e) => set("max_budget_usd", e.target.value)} />
              <label>Max companies researched</label><input aria-label="Max companies researched" type="number" value={f.max_companies} onChange={(e) => set("max_companies", e.target.value)} />
              <label>Max drafts generated</label><input aria-label="Max drafts generated" type="number" value={f.max_drafts} onChange={(e) => set("max_drafts", e.target.value)} />
            </div>
          </div>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={start} disabled={busy}>Run Research</button>
          {profileId === "custom" && <button onClick={saveProfile}>Save as profile</button>}
        </div>
        {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
      </div>
      <h3>Recent runs</h3>
      <Async state={runs} empty={(r: any[]) => (r.length ? null : "No runs yet. Pick a saved search and click Run Research.")}>
        {(r: any[]) => r.map((run) => <div key={run.id} style={{ marginBottom: 12 }}><RunSummary run={run} onChange={() => runs.reload(true)} />
          {run.status !== "pending" && run.status !== "running" && <p><a href="#" onClick={(e) => { e.preventDefault(); go("Opportunities"); }}>Review opportunities →</a></p>}</div>)}
      </Async>
    </>
  );
}

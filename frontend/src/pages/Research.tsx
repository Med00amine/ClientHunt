import { useEffect, useState } from "react";
import { api } from "../api";
import { Async, useLoad } from "../hooks";
import OneFile from "./OneFile";
import RunRow from "./RunRow";

const ENGAGEMENTS = ["contract", "freelance", "part_time", "full_time"];
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const FIRST_CHOICE = "AI / ML projects"; // the saved search to preselect

export default function Research({ go }: { go: (t: any, id?: number) => void }) {
  const profiles = useLoad(() => api("/profiles"));
  const sources = useLoad(() => api("/sources"));
  const runs = useLoad(() => api("/runs?limit=8"), [], 2500);
  const [profileId, setProfileId] = useState<number | "custom" | null>(null);
  const [f, setF] = useState<any>({ name: "Custom search", keywords: "machine learning, llm, python", skills: "", remote_only: true, engagement: ["contract", "freelance", "part_time"],
    min_rate: "", country: "", posted_within_days: 30, max_results: 100, max_budget_usd: 1, min_fit: 30, sources: [], max_companies: 10, max_drafts: 3,
    require_email: false, min_ease: 0, strict_engagement: false });
  const [msg, setMsg] = useState<{ kind: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const toggle = (k: string, v: string) => set(k, f[k].includes(v) ? f[k].filter((x: string) => x !== v) : [...f[k], v]);

  const list: any[] = profiles.data ?? [];
  const defaultId = (list.find((p) => p.name.startsWith(FIRST_CHOICE)) ?? list[0])?.id ?? null;
  const chosen = profileId ?? defaultId;
  useEffect(() => {
    if (sources.data && f.sources.length === 0) set("sources", sources.data.filter((s: any) => s.kind === "api" && s.enabled).map((s: any) => s.key));
  }, [sources.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const searchBody = (full: boolean) => ({
    name: f.name, keywords: csv(f.keywords), required_skills: csv(f.skills), sources: f.sources, remote_only: f.remote_only, engagement_types: f.engagement,
    posted_within_days: Number(f.posted_within_days) || null, max_results: Number(f.max_results), max_budget_usd: Number(f.max_budget_usd), min_fit: Number(f.min_fit),
    require_email: f.require_email, min_ease: Number(f.min_ease), strict_engagement: f.strict_engagement,
    ...(full ? { min_rate: f.min_rate === "" ? null : Number(f.min_rate), country: f.country, max_companies: Number(f.max_companies), max_drafts: Number(f.max_drafts) } : {}),
  });
  const start = async () => {
    setBusy(true); setMsg(null);
    try {
      const body = chosen === "custom" ? { search: searchBody(true) } : { profile_id: chosen };
      const r = await api("/runs", { body });
      setMsg({ kind: "ok", text: `Run #${r.id} started. It appears below in a few seconds.` });
      runs.reload(true);
    } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
    setBusy(false);
  };
  const saveProfile = async () => {
    try {
      await api("/profiles", { body: { name: f.name, params: searchBody(false) } });
      profiles.reload(true); setMsg({ kind: "ok", text: "Saved search added to the list." });
    } catch (e: any) { setMsg({ kind: "error", text: e.message }); }
  };
  const current = list.find((p) => p.id === chosen);

  return (
    <>
      <h2>Research</h2>
      <div className="panel">
        <label htmlFor="prof">Saved search</label>
        {profiles.error && <div className="alert error" role="alert">{profiles.error}</div>}
        <select id="prof" value={(chosen ?? "") as any} onChange={(e) => setProfileId(e.target.value === "custom" ? "custom" : Number(e.target.value))}>
          {list.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
          <option value="custom">Custom search…</option>
        </select>
        {chosen !== "custom" && current && (
          <p className="muted">
            Keywords: {current.params.keywords.join(", ")}
            {current.params.strict_engagement ? " · only listings that say contract, freelance or part-time" : ""}
            {current.params.require_email ? " · only listings with an email" : ""} · sources: {current.params.sources.join(", ")}
          </p>
        )}
        {chosen === "custom" && (
          <div className="cols">
            <div>
              <label>Name</label><input aria-label="Name" value={f.name} onChange={(e) => set("name", e.target.value)} />
              <label>Keywords (comma-separated)</label><input aria-label="Keywords (comma-separated)" value={f.keywords} onChange={(e) => set("keywords", e.target.value)} />
              <label>Required skills</label><input aria-label="Required skills" value={f.skills} onChange={(e) => set("skills", e.target.value)} />
              <label>Country / time-zone requirement (excludes listings restricted elsewhere)</label><input aria-label="Country" value={f.country} onChange={(e) => set("country", e.target.value)} placeholder="e.g. Tunisia" />
              <label>Min hourly rate (when published)</label><input aria-label="Min hourly rate" type="number" value={f.min_rate} onChange={(e) => set("min_rate", e.target.value)} />
            </div>
            <div>
              <label>Sources</label>
              {(sources.data ?? []).filter((s: any) => s.kind === "api").map((s: any) => (
                <div key={s.key}><label style={{ display: "inline" }}><input type="checkbox" checked={f.sources.includes(s.key)} onChange={() => toggle("sources", s.key)} /> {s.name}</label></div>))}
              <p className="muted">Upwork and similar platforms use Sources &amp; settings → Alert import. Freelancer.com is on the Live projects tab.</p>
              <label>Engagement type</label>
              {ENGAGEMENTS.map((e) => (<label key={e} style={{ display: "inline", marginRight: 8 }}><input type="checkbox" checked={f.engagement.includes(e)} onChange={() => toggle("engagement", e)} /> {e.replace("_", " ")}</label>))}
              <div><label style={{ display: "inline" }}><input type="checkbox" checked={f.strict_engagement} onChange={(e) => set("strict_engagement", e.target.checked)} /> Only listings that say contract / freelance / part-time (skip “not stated”)</label></div>
              <div><label style={{ display: "inline" }}><input type="checkbox" checked={f.remote_only} onChange={(e) => set("remote_only", e.target.checked)} /> Remote only</label></div>
              <div><label style={{ display: "inline" }}><input type="checkbox" checked={f.require_email} onChange={(e) => set("require_email", e.target.checked)} /> Only listings with an email to apply</label></div>
              <label>Min “easy to reach” score (0–100)</label><input aria-label="Min easy to reach" type="number" value={f.min_ease} onChange={(e) => set("min_ease", e.target.value)} />
            </div>
            <div>
              <label>Posted within (days)</label><input aria-label="Posted within days" type="number" value={f.posted_within_days} onChange={(e) => set("posted_within_days", e.target.value)} />
              <label>Max results</label><input aria-label="Max results" type="number" value={f.max_results} onChange={(e) => set("max_results", e.target.value)} />
              <label>Min fit score to keep</label><input aria-label="Min fit score" type="number" value={f.min_fit} onChange={(e) => set("min_fit", e.target.value)} />
              <label>Max research budget for this run (USD)</label><input aria-label="Max budget" type="number" step="0.1" value={f.max_budget_usd} onChange={(e) => set("max_budget_usd", e.target.value)} />
              <label>Max companies researched</label><input aria-label="Max companies" type="number" value={f.max_companies} onChange={(e) => set("max_companies", e.target.value)} />
              <label>Max drafts generated</label><input aria-label="Max drafts" type="number" value={f.max_drafts} onChange={(e) => set("max_drafts", e.target.value)} />
            </div>
          </div>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="primary" onClick={start} disabled={busy || chosen == null}>Run Research</button>
          {chosen === "custom" && <button onClick={saveProfile}>Save as saved search</button>}
        </div>
        {msg && <div className={`alert ${msg.kind}`} role="status">{msg.text}</div>}
      </div>

      <OneFile />

      <h3>Recent runs</h3>
      <Async state={runs} empty={(r: any[]) => (r.length ? null : "No runs yet. Pick a saved search and click Run Research.")}>
        {(r: any[]) => (
          <>
            {r.map((run) => <RunRow key={run.id} run={run} onChange={() => runs.reload(true)} />)}
            <p><a href="#" onClick={(e) => { e.preventDefault(); go("Opportunities"); }}>Review the opportunities →</a> · <a href="#" onClick={(e) => { e.preventDefault(); go("Leads (emails)"); }}>See the leads with emails →</a></p>
          </>
        )}
      </Async>
    </>
  );
}

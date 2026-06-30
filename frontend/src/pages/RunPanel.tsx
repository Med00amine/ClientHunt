import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useApp } from "../ctx";
import { useLoad } from "../hooks";
import { Fold, Msg, Notice } from "../ui";
import RunRow from "./RunRow";

const ENGAGEMENTS = ["contract", "freelance", "part_time", "full_time"];
const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const FIRST_CHOICE = "AI / ML projects"; // the saved search to preselect
const isActive = (r: any) => r?.status === "pending" || r?.status === "running";

/** Pick a saved search and run it. A custom search opens its form; the newest run shows below and opens itself while it works. */
export default function RunPanel() {
  const { bump } = useApp();
  const profiles = useLoad(() => api("/profiles"));
  const sources = useLoad(() => api("/sources"));
  const [poll, setPoll] = useState(0);
  const runs = useLoad(() => api("/runs?limit=1"), [], poll);
  const [profileId, setProfileId] = useState<number | "custom" | null>(null);
  const [f, setF] = useState<any>({ name: "Custom search", keywords: "machine learning, llm, python", skills: "", remote_only: true, engagement: ["contract", "freelance", "part_time"],
    min_rate: "", country: "", posted_within_days: 30, max_results: 100, max_budget_usd: 1, min_fit: 30, sources: [], max_companies: 10, max_drafts: 3,
    require_email: false, min_ease: 0, strict_engagement: false });
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const toggle = (k: string, v: string) => set(k, f[k].includes(v) ? f[k].filter((x: string) => x !== v) : [...f[k], v]);

  const latest = runs.data?.[0];
  const wasActive = useRef(false);
  useEffect(() => {
    setPoll(isActive(latest) ? 2500 : 0);
    if (wasActive.current && !isActive(latest)) bump();            // a run just finished: the listings behind this panel have new rows
    wasActive.current = isActive(latest);
  }, [latest?.status, latest?.id]); // eslint-disable-line react-hooks/exhaustive-deps

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
      const r = await api("/runs", { body: chosen === "custom" ? { search: searchBody(true) } : { profile_id: chosen } });
      setMsg({ kind: "ok", text: `Run #${r.id} started.` });
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
  const num = (label: string, k: string, extra: object = {}) => (<><label>{label}</label><input aria-label={label} type="number" value={f[k]} onChange={(e) => set(k, e.target.value)} {...extra} /></>);

  return (
    <div className="panel" style={{ marginBottom: 12 }}>
      <div className="row">
        <label className="in" htmlFor="prof">Saved search</label>
        <select id="prof" value={(chosen ?? "") as any} onChange={(e) => setProfileId(e.target.value === "custom" ? "custom" : Number(e.target.value))}>
          {list.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
          <option value="custom">Custom search…</option>
        </select>
        <button className="primary" onClick={start} disabled={busy || chosen == null}>Run search</button>
        {chosen === "custom" && <button onClick={saveProfile}>Save as saved search</button>}
      </div>
      {profiles.error && <div className="alert error" role="alert">{profiles.error}</div>}
      {chosen !== "custom" && current && (
        <div className="muted">
          {current.params.keywords.slice(0, 5).join(", ")}{current.params.keywords.length > 5 ? ` +${current.params.keywords.length - 5} more` : ""}
          {current.params.strict_engagement ? " · only listings that say contract, freelance or part-time" : ""}
          {current.params.require_email ? " · only listings with an email" : ""}
        </div>
      )}
      {chosen === "custom" && (
        <>
          <div className="cols">
            <div>
              <label>Name</label><input aria-label="Name" value={f.name} onChange={(e) => set("name", e.target.value)} />
              <label>Keywords (comma-separated)</label><input aria-label="Keywords (comma-separated)" value={f.keywords} onChange={(e) => set("keywords", e.target.value)} />
              <label>Country / time-zone requirement</label><input aria-label="Country" value={f.country} onChange={(e) => set("country", e.target.value)} placeholder="e.g. Tunisia" />
            </div>
            <div>
              <label>Sources</label>
              {(sources.data ?? []).filter((s: any) => s.kind === "api").map((s: any) => (
                <div key={s.key}><label className="in"><input type="checkbox" checked={f.sources.includes(s.key)} onChange={() => toggle("sources", s.key)} /> {s.name}</label></div>))}
              <label>Engagement type</label>
              {ENGAGEMENTS.map((e) => (<label key={e} className="in" style={{ marginRight: 8 }}><input type="checkbox" checked={f.engagement.includes(e)} onChange={() => toggle("engagement", e)} /> {e.replace("_", " ")}</label>))}
              <div><label className="in"><input type="checkbox" checked={f.strict_engagement} onChange={(e) => set("strict_engagement", e.target.checked)} /> Only listings that say contract / freelance / part-time (skip “not stated”)</label></div>
            </div>
          </div>
          <Fold title="Limits and extra filters" plain>
            <div className="cols">
              <div>
                <label>Required skills</label><input aria-label="Required skills" value={f.skills} onChange={(e) => set("skills", e.target.value)} />
                {num("Min hourly rate", "min_rate")}
                {num("Min easy to reach", "min_ease")}
                <div><label className="in"><input type="checkbox" checked={f.remote_only} onChange={(e) => set("remote_only", e.target.checked)} /> Remote only</label></div>
                <div><label className="in"><input type="checkbox" checked={f.require_email} onChange={(e) => set("require_email", e.target.checked)} /> Only listings with an email to apply</label></div>
              </div>
              <div>
                {num("Posted within days", "posted_within_days")}
                {num("Max results", "max_results")}
                {num("Min fit score", "min_fit")}
                {num("Max budget", "max_budget_usd", { step: "0.1" })}
                {num("Max companies", "max_companies")}
                {num("Max drafts", "max_drafts")}
              </div>
            </div>
          </Fold>
        </>
      )}
      <Notice msg={msg} />
      {latest && <div style={{ marginTop: 8 }}><RunRow run={latest} onChange={() => runs.reload(true)} /></div>}
    </div>
  );
}

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, setUnauthorizedHandler } from "./api";
import { AppCtx, DrawerKind } from "./ctx";
import Data from "./pages/Data";
import { OppDrawer, ProspectDrawer } from "./pages/Drawers";
import Find from "./pages/Find";
import { DownloadButton } from "./pages/OneFile";
import Pipeline from "./pages/Pipeline";
import Plan from "./pages/Plan";
import Prospects from "./pages/Prospects";
import Today from "./pages/Today";

const TABS = [["today", "Today"], ["find", "Find work"], ["prospects", "Prospects"], ["pipeline", "Pipeline"], ["plan", "Plan"], ["data", "Data"]] as const;

function Login({ onDone }: { onDone: () => void }) {
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try { await api("/auth/login", { body: { password: pw } }); onDone(); } catch (x: any) { setErr(x.message); }
  };
  return (
    <main style={{ maxWidth: 360 }}>
      <h2>ClientHunt</h2>
      <form onSubmit={submit} className="panel">
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoFocus />
        <div className="row" style={{ marginTop: 10 }}><button className="primary">Sign in</button></div>
        {err && <div className="alert error" role="alert">{err}</div>}
      </form>
    </main>
  );
}

/** The place you are lives in the address (#/find/live), so a reload or the Back button keeps it. */
function useRoute() {
  const read = () => { const [tab = "", sub = ""] = location.hash.replace(/^#\/?/, "").split("/"); return { tab: TABS.some(([k]) => k === tab) ? tab : "today", sub }; };
  const [route, setRoute] = useState(read);
  useEffect(() => { const f = () => setRoute(read()); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  const go = useCallback((tab: string, sub = "") => { location.hash = `/${tab}${sub ? "/" + sub : ""}`; }, []);
  return { ...route, go };
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [drawer, setDrawer] = useState<{ kind: DrawerKind; id: number } | null>(null);
  const [rev, setRev] = useState(0);
  const { tab, sub, go } = useRoute();
  const bump = useCallback(() => setRev((r) => r + 1), []);
  const open = useCallback((kind: DrawerKind, id: number) => setDrawer({ kind, id }), []);
  const ctx = useMemo(() => ({ open, go, rev, bump }), [open, go, rev, bump]);

  const check = () => api("/auth/me").then((m) => setAuthed(m.authenticated)).catch(() => setAuthed(true));
  useEffect(() => { setUnauthorizedHandler(() => setAuthed(false)); check(); }, []);
  useEffect(() => { setDrawer(null); }, [tab]);                                       // a drawer belongs to the page it was opened on
  const close = useCallback(() => { setDrawer(null); bump(); }, [bump]);
  useEffect(() => {
    if (!drawer) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [drawer, close]);

  if (authed === null) return <main><p className="muted">Loading…</p></main>;
  if (!authed) return <Login onDone={check} />;

  return (
    <AppCtx.Provider value={ctx}>
      <header className="top">
        <h1>ClientHunt</h1>
        <nav aria-label="Main">
          {TABS.map(([k, label]) => <button key={k} aria-current={k === tab ? "page" : undefined} onClick={() => go(k)}>{label}</button>)}
        </nav>
        <DownloadButton />
        <button onClick={() => api("/auth/logout", { method: "POST" }).then(check)}>Sign out</button>
      </header>
      <main>
        {tab === "today" && <Today />}
        {tab === "find" && <Find sub={sub} />}
        {tab === "prospects" && <Prospects />}
        {tab === "pipeline" && <Pipeline />}
        {tab === "plan" && <Plan />}
        {tab === "data" && <Data sub={sub} />}
      </main>
      {drawer?.kind === "opp" && <OppDrawer id={drawer.id} close={close} onChanged={bump} />}
      {drawer?.kind === "prospect" && <ProspectDrawer id={drawer.id} close={close} onChanged={bump} />}
    </AppCtx.Provider>
  );
}

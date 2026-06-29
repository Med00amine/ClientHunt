import { useEffect, useState } from "react";
import { api, setUnauthorizedHandler } from "./api";
import Overview from "./pages/Overview";
import Research from "./pages/Research";
import Opportunities from "./pages/Opportunities";
import Runs from "./pages/Runs";
import Pipeline from "./pages/Pipeline";
import Contacts from "./pages/Contacts";
import Leads from "./pages/Leads";
import LiveProjects from "./pages/LiveProjects";
import Settings from "./pages/Settings";
import Prospects from "./pages/Prospects";
import Strategy from "./pages/Strategy";

const TABS = ["Overview", "Strategy", "Research", "Leads (emails)", "Prospects", "Live projects", "Opportunities", "Runs & exports", "Pipeline", "Contacts", "Sources & settings"] as const;
type Tab = (typeof TABS)[number];

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

export default function App() {
  const [tab, setTab] = useState<Tab>("Overview");
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [openOpp, setOpenOpp] = useState<number | null>(null);
  const [openProspect, setOpenProspect] = useState<number | null>(null);

  const check = () => api("/auth/me").then((m) => setAuthed(m.authenticated)).catch(() => setAuthed(true));
  useEffect(() => { setUnauthorizedHandler(() => setAuthed(false)); check(); }, []);

  if (authed === null) return <main><p className="muted">Loading…</p></main>;
  if (!authed) return <Login onDone={check} />;

  const go = (t: Tab, id?: number) => { setTab(t); if (id) (t === "Prospects" ? setOpenProspect : setOpenOpp)(id); };
  return (
    <>
      <header className="top">
        <h1>ClientHunt</h1>
        <nav aria-label="Main">
          {TABS.map((t) => (
            <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>
          ))}
        </nav>
        <button onClick={() => api("/auth/logout", { method: "POST" }).then(check)}>Sign out</button>
      </header>
      <main>
        {tab === "Overview" && <Overview go={go} />}
        {tab === "Strategy" && <Strategy go={go} />}
        {tab === "Research" && <Research go={go} />}
        {tab === "Leads (emails)" && <Leads openOpp={(id) => go("Opportunities", id)} />}
        {tab === "Prospects" && <Prospects openId={openProspect} setOpenId={setOpenProspect} />}
        {tab === "Live projects" && <LiveProjects />}
        {tab === "Opportunities" && <Opportunities openId={openOpp} setOpenId={setOpenOpp} />}
        {tab === "Runs & exports" && <Runs go={go} />}
        {tab === "Pipeline" && <Pipeline openOpp={(id, pitch) => go(pitch ? "Prospects" : "Opportunities", id)} />}
        {tab === "Contacts" && <Contacts />}
        {tab === "Sources & settings" && <Settings />}
      </main>
    </>
  );
}

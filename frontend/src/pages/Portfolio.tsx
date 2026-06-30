import { useState } from "react";
import { api } from "../api";
import { ExtLink } from "../components";
import { safeUrl } from "../format";
import { Async, useLoad } from "../hooks";
import { Chip, List, Msg, Notice } from "../ui";

/** Only items you confirmed are ever cited in a draft. */
export default function Portfolio() {
  const portfolio = useLoad(() => api("/portfolio"));
  const [msg, setMsg] = useState<Msg>(null);
  const wrap = async (fn: () => Promise<string>) => { try { setMsg({ kind: "ok", text: await fn() }); } catch (e: any) { setMsg({ kind: "error", text: e.message }); } };
  return (
    <>
      <p className="muted">Only items you verified are cited in drafts.</p>
      <Notice msg={msg} />
      <Async state={portfolio}>{(p: any[]) => (<>
        <List>{p.map((x) => (
          <div className="item" key={x.id}>
            <div className="main"><b>{x.title}</b> <Chip tone={x.verified ? "ok" : "warn"}>{x.verified ? "verified" : "unverified"}</Chip>
              <div className="muted">{x.summary} {safeUrl(x.url) && <ExtLink href={x.url}>{x.url}</ExtLink>}</div>
              {x.verified_note && <div className="muted">Note: {x.verified_note}</div>}</div>
            <button onClick={() => wrap(async () => { await api(`/portfolio/${x.id}`, { method: "PATCH", body: { verified: !x.verified } }); portfolio.reload(true); return "Updated. Click “Rescore all” to apply."; })}>{x.verified ? "Mark unverified" : "I confirm this is accurate"}</button>
          </div>))}</List>
        <div className="row" style={{ marginTop: 8 }}>
          <button onClick={() => wrap(async () => `Rescored ${(await api("/opportunities/rescore", { method: "POST" })).rescored} opportunities`)}>Rescore all</button>
        </div>
      </>)}</Async>
    </>
  );
}

import { ReactNode } from "react";
import { ExtLink } from "./components";
import { fmtDate } from "./format";

export type Msg = { kind: string; text: string } | null;

/** The one place an outcome (ok / warn / error) is shown. */
export function Notice({ msg }: { msg: Msg }) {
  return msg ? <div className={`alert ${msg.kind}`} role="status">{msg.text}</div> : null;
}

export const ELIG: Record<string, string> = { eligible: "ok", review_required: "warn", not_eligible: "bad", unknown: "" };
export const words = (s: string) => s.replace(/_/g, " ");
export const runTone = (status: string) => (status === "completed" ? "ok" : status === "failed" ? "bad" : "warn");

export function Chip({ tone = "", title, children }: { tone?: string; title?: string; children: ReactNode }) {
  return <span className={`chip ${tone}`} title={title}>{children}</span>;
}

type Mailbox = { email: string; eligibility: string; source_url?: string; found_at?: string | null; basis?: string };

/** One mailbox the company published: the address, whether it may be used, and the page it came from. */
export function Mail({ c, detail }: { c: Mailbox; detail?: boolean }) {
  return (
    <div className="mail">
      <b>{c.email}</b> <Chip tone={ELIG[c.eligibility]} title={c.basis}>{words(c.eligibility)}</Chip>{" "}
      <span className="nw"><ExtLink href={c.source_url} title={c.found_at ? fmtDate(c.found_at) : undefined} onClick={(e) => e.stopPropagation()}>found here</ExtLink></span>
      {detail && c.basis && <div className="muted">{c.basis}</div>}
    </div>
  );
}

export function Stat({ n, label }: { n: ReactNode; label: string }) {
  return <div className="stat"><div className="n">{n}</div><div className="l">{label}</div></div>;
}

/** Collapsed by default: the page shows headings, the detail is one click away. */
export function Fold({ title, children, open, testId, plain }: { title: ReactNode; children: ReactNode; open?: boolean; testId?: string; plain?: boolean }) {
  return <details className={plain ? "fold plain" : "fold"} open={open} data-testid={testId}><summary>{title}</summary><div className="body">{children}</div></details>;
}

/** A second level of navigation inside a tab. */
export function SubNav<T extends string>({ items, value, onPick, label }: { items: [T, string][]; value: T; onPick: (v: T) => void; label: string }) {
  return (
    <nav className="sub" aria-label={label}>
      {items.map(([k, t]) => <button key={k} className={k === value ? "active" : ""} aria-current={k === value ? "page" : undefined} onClick={() => onPick(k)}>{t}</button>)}
    </nav>
  );
}

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return <div className="scroll"><table><thead><tr>{head.map((h, i) => <th key={i}>{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>;
}

/** Rows of one list share a single border instead of one box each. */
export function List({ children }: { children: ReactNode }) {
  return <div className="list">{children}</div>;
}

import { ReactNode } from "react";
import { safeUrl } from "./format";

/** External link that only exists for http(s) addresses. Anything else (javascript:, data:, ...) is shown as plain text. */
export function ExtLink({ href, children, onClick }: { href?: string | null; children: ReactNode; onClick?: (e: React.MouseEvent) => void }) {
  const u = safeUrl(href);
  return u ? (
    <a href={u} target="_blank" rel="noreferrer noopener" onClick={onClick}>{children}</a>
  ) : (
    <span className="muted" title="Link removed: not an http(s) address">{children}</span>
  );
}

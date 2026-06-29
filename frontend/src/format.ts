export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : "—");
export const fmtUsd = (n?: number | null) => (n == null ? "—" : `$${n.toFixed(n < 1 ? 4 : 2)}`);
export const fmtBudget = (o: { budget_min: number | null; budget_max: number | null; currency: string; rate_type: string }) => {
  if (o.budget_min == null && o.budget_max == null) return "not published";
  const r = o.budget_min != null && o.budget_max != null && o.budget_min !== o.budget_max ? `${o.budget_min}–${o.budget_max}` : `${o.budget_max ?? o.budget_min}`;
  return `${r} ${o.currency}${o.rate_type ? " / " + o.rate_type : ""}`.trim();
};
export const duration = (s?: number | null) => (s == null ? "—" : s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`);

/** Only http(s) links are ever rendered as clickable; anything else (javascript:, data:, ...) becomes "". */
export const safeUrl = (u?: string | null): string => (u && /^https?:\/\//i.test(u.trim()) ? u.trim() : "");
export const ago = (min?: number | null) => (min == null ? "—" : min < 1 ? "just now" : min < 60 ? `${min} min ago` : min < 1440 ? `${Math.floor(min / 60)} h ago` : `${Math.floor(min / 1440)} d ago`);

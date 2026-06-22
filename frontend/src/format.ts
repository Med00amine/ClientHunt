export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : "—");
export const fmtUsd = (n?: number | null) => (n == null ? "—" : `$${n.toFixed(n < 1 ? 4 : 2)}`);
export const fmtBudget = (o: { budget_min: number | null; budget_max: number | null; currency: string; rate_type: string }) => {
  if (o.budget_min == null && o.budget_max == null) return "not published";
  const r = o.budget_min != null && o.budget_max != null && o.budget_min !== o.budget_max ? `${o.budget_min}–${o.budget_max}` : `${o.budget_max ?? o.budget_min}`;
  return `${r} ${o.currency}${o.rate_type ? " / " + o.rate_type : ""}`.trim();
};
export const duration = (s?: number | null) => (s == null ? "—" : s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`);

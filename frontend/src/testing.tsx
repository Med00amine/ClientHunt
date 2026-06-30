import { render } from "@testing-library/react";
import { ReactElement } from "react";
import { vi } from "vitest";
import { AppCtx } from "./ctx";

export const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

/** Routes by URL substring and optional method ("POST /x"); the first matching key wins, so list the specific ones first. */
export function serve(table: Record<string, unknown>, fallback: unknown = []) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(((u: any, init?: any) => {
    const url = String(u), method = init?.method ?? "GET";
    const key = Object.keys(table).find((k) => { const [m, frag] = k.includes(" ") ? k.split(" ") : ["GET", k]; return m === method && url.includes(frag); });
    const v = key ? table[key] : fallback;
    return typeof v === "function" ? (v as any)(url, init) : json(v);
  }) as any);
}
export const sent = (spy: any, method: string, frag: string) => spy.mock.calls.filter((c: any) => (c[1]?.method ?? "GET") === method && String(c[0]).includes(frag));
export const body = (call: any) => JSON.parse(call[1].body);

/** Renders a page inside the shell's context, with spies for "open a record" and "go to a tab". */
export function renderApp(ui: ReactElement) {
  const ctx = { open: vi.fn(), go: vi.fn(), rev: 0, bump: vi.fn() };
  return { ctx, ...render(<AppCtx.Provider value={ctx}>{ui}</AppCtx.Provider>) };
}

export const COUNTS = { runs: 3, opportunities: 12, leads: 5, emails: 9, prospects: 0 };
export const NO_COUNTS = { runs: 0, opportunities: 0, leads: 0, emails: 0, prospects: 0 };

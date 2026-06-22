import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const reload = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { reload(); }, [reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(() => reload(true), pollMs);
    return () => clearInterval(t);
  }, [pollMs, reload]);
  return { data, error, loading, reload };
}

export function Async<T>({ state, empty, children }: {
  state: { data: T | null; error: string | null; loading: boolean; reload: () => void };
  empty?: (d: T) => string | null;
  children: (d: T) => ReactNode;
}) {
  if (state.loading && !state.data) return <p className="muted" role="status">Loading…</p>;
  if (state.error && !state.data)
    return (
      <div className="alert error" role="alert">
        {state.error} <button onClick={() => state.reload()}>Retry</button>
      </div>
    );
  if (!state.data) return null;
  const msg = empty?.(state.data);
  if (msg) return <p className="empty">{msg}</p>;
  return <>{children(state.data)}</>;
}

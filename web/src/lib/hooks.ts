import { useCallback, useEffect, useState } from "react";
import { apiErrorText, request } from "./api";

export function useGet<T>(path: string, deps: unknown[] = [], opts: { pollMs?: number } = {}):
  { data: T | null; error: string; loading: boolean; refetch: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    request<T>(path)
      .then((d) => { if (alive) { setData(d); setError(""); } })
      .catch((e) => { if (alive) setError(apiErrorText(e)); })
      .finally(() => { if (alive) setLoading(false); });
    if (opts.pollMs) {
      const id = window.setInterval(refetch, opts.pollMs);
      return () => { alive = false; window.clearInterval(id); };
    }
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick]);

  return { data, error, loading, refetch };
}

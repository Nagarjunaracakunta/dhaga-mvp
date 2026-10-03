import { useCallback, useEffect, useState } from "react";

// Load data on mount (and when deps change). Returns { data, error, loading, reload }.
export function useApi(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true });

  const load = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await fn();
      setState({ data, error: null, loading: false });
    } catch (error) {
      setState({ data: null, error, loading: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}

// Shared formatters
export const pct = (x, digits = 1) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(digits)}%`);
export const inr = (x) => (x === null || x === undefined ? "–" : `₹${Number(x).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`);
export const num = (x) => (x === null || x === undefined ? "–" : Number(x).toLocaleString("en-IN"));
export const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "–");
export const time = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "");
export const label = (s) => (s ? s.replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "–");

"use client";
import * as React from "react";

/** Run an async action with busy + error state (errors come from the Flask API and are safe to show). */
export function useAction() {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const run = React.useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }, []);
  return { busy, error, setError, run };
}

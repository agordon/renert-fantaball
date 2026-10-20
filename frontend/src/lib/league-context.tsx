"use client";
import * as React from "react";
import { api } from "@/lib/api";
import type { LeagueSummary, Me } from "@/lib/types";

type Ctx = {
  me: Me | null; leagues: LeagueSummary[]; league: LeagueSummary | null; loading: boolean; error: string | null;
  setLeagueId: (id: number) => void; reload: () => Promise<void>;
};
const C = React.createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => React.useContext(C);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = React.useState<Me | null>(null);
  const [leagues, setLeagues] = React.useState<LeagueSummary[]>([]);
  const [leagueId, setId] = React.useState<number | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    try {
      const [m, l] = await Promise.all([api<Me>("/me"), api<LeagueSummary[]>("/leagues")]);
      setMe(m); setLeagues(l); setError(null);
      const stored = Number(localStorage.getItem("fb.league"));
      setId((cur) => (cur && l.some((x) => x.id === cur) ? cur : l.some((x) => x.id === stored) ? stored : l[0]?.id ?? null));
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }, []);
  React.useEffect(() => { reload(); }, [reload]);

  const setLeagueId = (id: number) => { localStorage.setItem("fb.league", String(id)); setId(id); };
  const league = leagues.find((l) => l.id === leagueId) ?? null;
  return <C.Provider value={{ me, leagues, league, loading, error, setLeagueId, reload }}>{children}</C.Provider>;
}

/** Fetch helper bound to the current league; reloads when the league or its sim day/status changes. */
export function useLeagueData<T>(path: string | null, deps: unknown[] = []) {
  const { league } = useApp();
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const url = league && path !== null ? `/leagues/${league.id}${path}` : null;
  const load = React.useCallback(async () => {
    if (!url) return;
    try { setData(await api<T>(url)); setError(null); } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }, [url]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  React.useEffect(() => { setLoading(true); load(); }, [load, league?.current_day, league?.status, ...deps]);
  return { data, error, loading, reload: load, setData };
}

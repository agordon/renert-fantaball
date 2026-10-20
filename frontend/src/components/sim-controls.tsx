"use client";
import { FastForward, Play } from "lucide-react";
import { api } from "@/lib/api";
import { useApp } from "@/lib/league-context";
import { useAction } from "@/lib/use-action";
import { Button, SimBadge } from "@/components/ui";

/** Demo simulator: reveals the next simulated game day(s). Commissioner only (also enforced by the server). */
export function SimControls() {
  const { league, reload } = useApp();
  const { busy, error, run } = useAction();
  if (!league || league.status !== "active") return null;
  const over = league.current_day >= league.season_days;
  const go = (days: number) => run(async () => { await api(`/leagues/${league.id}/simulate`, { method: "POST", body: { days } }); await reload(); });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SimBadge text={`Sim day ${league.current_day}/${league.season_days} · week ${league.current_week}`} />
      {league.is_commissioner && !over && (
        <>
          <Button size="sm" onClick={() => go(1)} disabled={busy}><Play className="h-3 w-3" />Sim day</Button>
          <Button size="sm" onClick={() => go(7)} disabled={busy}><FastForward className="h-3 w-3" />Sim week</Button>
        </>
      )}
      {over && <span className="text-xs text-ink3">Regular season complete</span>}
      {error && <span role="alert" className="text-xs text-bad">{error}</span>}
    </div>
  );
}

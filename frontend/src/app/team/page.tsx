"use client";
import * as React from "react";
import Link from "next/link";
import { Sparkles, Trash2 } from "lucide-react";
import { useApp, useLeagueData } from "@/lib/league-context";
import { api } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import type { Player } from "@/lib/types";
import { Badge, Button, Card, ErrorBox, InjuryBadge, PageHeader, PosBadge, Select, DataBadge, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import { PlayerProfile } from "@/components/player-modals";
import { cn, fmt } from "@/lib/utils";

 
export default function TeamPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

function canFill(slot: string, p: Player, slotPositions: Record<string, string[]>) {
  const injured = p.injury !== "HEALTHY";
  if (slot === "BN") return true;
  if (slot === "IR") return injured;
  if (injured) return false;
  if (slot === "UTIL") return true;
  return (slotPositions[slot] ?? []).some((x) => p.positions.split(",").includes(x));
}

function Inner() {
  const { league, reload } = useApp();
  const [viewTeam, setViewTeam] = React.useState<number | null>(null);
  const { data: info } = useLeagueData<any>("");
  const { data, error, loading, reload: refresh, setData } = useLeagueData<any>(viewTeam ? `/team?team_id=${viewTeam}` : "/team", [viewTeam]);
  const [grid, setGrid] = React.useState<(number | null)[]>([]);
  const [sel, setSel] = React.useState<number | null>(null);   // selected player id
  const [profile, setProfile] = React.useState<number | null>(null);
  const { busy, error: actErr, run, setError } = useAction();

  const players: Player[] = React.useMemo(() => data?.players ?? [], [data]);
  const byId = React.useMemo(() => new Map(players.map((p) => [p.id, p])), [players]);

  React.useEffect(() => {      // rebuild the slot grid from the server's roster
    if (!data) return;
    const used = new Set<number>();
    setGrid((data.slots as string[]).map((s) => {
      const p = players.find((x) => x.slot === s && !used.has(x.id));
      if (p) used.add(p.id);
      return p ? p.id : null;
    }));
  }, [data, players]);

  if (error) return <ErrorBox message={error} onRetry={refresh} />;
  if (loading && !data) return <Spinner />;
  if (!data) return null;
  const readOnly = data.team.is_me === false;
  const slots: string[] = data.slots;
  const slotPos = data.slot_positions;
  const selPlayer = sel ? byId.get(sel) : undefined;
  const fromIdx = sel ? grid.indexOf(sel) : -1;

  const move = (toIdx: number) => {
    if (!selPlayer || fromIdx < 0 || toIdx === fromIdx || readOnly) return;
    const next = [...grid];
    const occupant = next[toIdx];
    if (!canFill(slots[toIdx], selPlayer, slotPos)) { setError(`${selPlayer.name} cannot play ${slots[toIdx]}`); return; }
    if (occupant) {
      const o = byId.get(occupant)!;
      if (canFill(slots[fromIdx], o, slotPos)) { next[fromIdx] = occupant; }
      else {
        const free = next.findIndex((v, i) => v === null && slots[i] === "BN");
        if (free < 0) { setError(`${o.name} cannot move to ${slots[fromIdx]} and your bench is full`); return; }
        next[free] = occupant; next[fromIdx] = null;
      }
    } else next[fromIdx] = null;
    next[toIdx] = selPlayer.id;
    setGrid(next); setSel(null); setError(null);
    const assignment: Record<string, string> = {};
    next.forEach((id, i) => { if (id) assignment[id] = slots[i]; });
    run(async () => {
      try { setData(await api(`/leagues/${league!.id}/lineup`, { method: "PUT", body: { assignment } })); }
      catch (e) { await refresh(); throw e; }
    });
  };

  const optimize = (keep: boolean) => run(async () => { setData(await api(`/leagues/${league!.id}/lineup/auto`, { method: "POST", body: { keep_on: keep } })); });
  const dropPlayer = (p: Player) => { if (confirm(`Drop ${p.name}? He becomes a free agent.`)) run(async () => { setData(await api(`/leagues/${league!.id}/add-drop`, { method: "POST", body: { drop_id: p.id } })); await reload(); }); };

  const starters = grid.map((id, i) => ({ id, slot: slots[i] })).filter((x) => x.slot !== "BN" && x.slot !== "IR");
  const projStarters = starters.reduce((s, x) => s + (x.id ? (byId.get(x.id)!.proj * byId.get(x.id)!.games_left_week) : 0), 0);

  return (
    <>
      <PageHeader title={data.team.name} sub={<>{data.team.manager} · lineup editor <DataBadge /></>}
        action={<div className="flex flex-wrap items-center gap-2">
          <Select aria-label="View team" value={viewTeam ?? ""} onChange={(e) => { setViewTeam(e.target.value ? Number(e.target.value) : null); setSel(null); }}>
            <option value="">My team</option>{(info?.teams ?? []).filter((t: any) => !t.is_me).map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>
          {!readOnly && <Button onClick={() => optimize(false)} disabled={busy}><Sparkles className="h-4 w-4" />Optimize lineup</Button>}
          {!readOnly && <label className="flex items-center gap-1.5 text-xs text-ink2"><input type="checkbox" className="accent-teal" checked={data.auto_lineup} onChange={(e) => optimize(e.target.checked)} />Auto-set daily</label>}
        </div>} />
      {readOnly && <p className="mb-3 text-sm text-amber">Viewing another team (read-only).</p>}
      {actErr && <div className="mb-3"><ErrorBox message={actErr} /></div>}
      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Card pad={false} title={undefined}>
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5 text-xs text-ink3">
            <span>{readOnly ? "Click a player for details" : selPlayer ? <>Moving <b className="text-teal">{selPlayer.name}</b> - choose a highlighted slot</> : "Select a player, then click an eligible slot"}</span>
            <span>Starters projected this week: <b className="num text-ink">{projStarters.toFixed(0)}</b> pts</span>
          </div>
          <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-ink3"><tr className="border-b border-line"><th className="w-16 p-2 text-left">Slot</th><th className="p-2 text-left">Player</th><th className="p-2 text-right">G left</th><th className="p-2 text-right">FP/G</th><th className="p-2 text-right">L5</th><th className="p-2 text-right">Proj</th><th className="w-8" /></tr></thead>
            <tbody>
              {slots.map((slot, i) => {
                const p = grid[i] ? byId.get(grid[i]!) : undefined;
                const target = !!selPlayer && i !== fromIdx && canFill(slot, selPlayer, slotPos);
                const isBenchStart = slot === "BN" && slots[i - 1] !== "BN";
                const isIr = slot === "IR";
                return (
                  <tr key={i} onClick={() => (target ? move(i) : undefined)} className={cn("border-b border-line/60 transition-colors", target && "cursor-pointer bg-teal/10 hover:bg-teal/20", (isBenchStart || isIr) && "border-t-2 border-t-line", p && sel === p.id && "bg-blue/15")}>
                    <td className="p-2"><Badge tone={slot === "BN" || slot === "IR" ? "neutral" : "teal"} className="w-11 justify-center">{slot}</Badge></td>
                    <td className="p-2">{p ? (
                      <div className="flex items-center gap-2">
                        {!readOnly && <input type="radio" name="sel" aria-label={`Select ${p.name}`} checked={sel === p.id} onChange={() => { setSel(sel === p.id ? null : p.id); setError(null); }} onClick={(e) => { e.stopPropagation(); if (sel === p.id) setSel(null); }} className="accent-blue" />}
                        <div><button className="font-medium hover:text-teal" onClick={(e) => { e.stopPropagation(); setProfile(p.id); }}>{p.name}</button>
                          <div className="flex items-center text-[11px] text-ink3"><PosBadge positions={p.positions} /><span className="mx-1">·</span>{p.team}<InjuryBadge status={p.injury} note={p.injury_note} /></div></div>
                      </div>) : <span className="text-xs text-ink3">{target ? "Move here" : "Empty"}</span>}</td>
                    <td className="num p-2 text-right text-ink2">{p?.games_left_week ?? ""}</td>
                    <td className="num p-2 text-right">{p ? fmt(p.fpg) : ""}</td>
                    <td className="num p-2 text-right">{p ? fmt(p.last5) : ""}</td>
                    <td className="num p-2 text-right font-semibold text-teal">{p ? p.proj.toFixed(1) : ""}</td>
                    <td className="p-1">{p && !readOnly && <button aria-label={`Drop ${p.name}`} onClick={(e) => { e.stopPropagation(); dropPlayer(p); }} className="rounded p-1 text-ink3 hover:bg-bad/10 hover:text-bad"><Trash2 className="h-3.5 w-3.5" /></button>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>

        {data.gm && (
          <div className="space-y-4">
            <Card title="Roster strengths & weaknesses" action={<Badge tone="blue">Fantasy GM</Badge>}>
              <p className="mb-2 text-xs text-ink2">{data.gm.summary}</p>
              <div className="space-y-1.5">
                {data.gm.strengths.map((s: any) => (
                  <div key={s.position} className="flex items-center gap-2 text-sm">
                    <span className="num w-8 text-ink3">{s.position}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded bg-panel2"><div className={cn("h-full", s.label === "strength" ? "bg-good" : s.label === "weakness" ? "bg-bad" : "bg-blue")} style={{ width: `${((s.of - s.league_rank + 1) / s.of) * 100}%` }} /></div>
                    <span className="w-24 text-right text-xs text-ink3">#{s.league_rank} of {s.of} · {s.label}</span>
                  </div>))}
              </div>
              <p className="mt-2 text-[11px] text-ink3">Bench depth: avg projection {data.gm.bench.avg_proj} (#{data.gm.bench.league_rank} of {data.gm.bench.of}).</p>
            </Card>
            <Card title="Recommendations">
              {data.gm.suggestions.length === 0 && <p className="text-sm text-ink3">No changes recommended right now.</p>}
              <ul className="space-y-2">{data.gm.suggestions.map((s: any, i: number) => (
                <li key={i} className="rounded-md border border-line bg-panel2 p-2.5 text-sm"><div className="flex items-center justify-between font-medium">{s.title}<Badge tone="good">+{Math.round(s.impact)}</Badge></div><p className="mt-1 text-xs text-ink3">{s.detail}</p></li>))}</ul>
              <p className="mt-2 text-[11px] text-ink3">{data.gm.method}</p>
            </Card>
            <Card title="Schedule: games left this week">
              <div className="flex flex-wrap gap-1">{data.gm.schedule.map((s: any) => <Badge key={s.athlete_id} tone={s.games_left === 0 ? "bad" : "neutral"}>{s.name.split(" ")[1]} · {s.games_left}</Badge>)}</div>
              <Link href="/players?status=available" className="mt-3 inline-block text-xs text-teal hover:underline">Browse free agents →</Link>
            </Card>
          </div>
        )}
      </div>
      <PlayerProfile id={profile} onClose={() => setProfile(null)} />
    </>
  );
}

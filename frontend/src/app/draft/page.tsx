"use client";
import * as React from "react";
import Link from "next/link";
import { Bot, Clock, FastForward, Gavel, ListPlus, Play, Search, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import { useApiData, useApp } from "@/lib/league-context";
import type { DataStatus } from "@/lib/api-types";
import { useAction } from "@/lib/use-action";
import { Badge, Button, Card, Empty, ErrorBox, Input, PageHeader, Select, SimBadge, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import { cn } from "@/lib/utils";

 
export default function DraftPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

const POS_COLOR: Record<string, string> = { PG: "bg-blue/20 border-blue/40", SG: "bg-teal/20 border-teal/40", SF: "bg-amber/20 border-amber/40", PF: "bg-[#a78bfa33] border-[#a78bfa66]", C: "bg-bad/20 border-bad/40" };

function Inner() {
  const { league, reload } = useApp();
  const [st, setSt] = React.useState<any>(null);
  const [assist, setAssist] = React.useState<any>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [secs, setSecs] = React.useState<number | null>(null);
  const [q, setQ] = React.useState("");
  const [pos, setPos] = React.useState("");
  const [picked, setPicked] = React.useState<number | null>(null);
  const act = useAction();
  const lid = league!.id;
  const { data: dataStatus } = useApiData<DataStatus>(league!.is_simulated ? null : "/data/status");

  const load = React.useCallback(async () => {
    try { setSt(await api(`/leagues/${lid}/draft`)); setError(null); } catch (e) { setError((e as Error).message); }
  }, [lid]);
  React.useEffect(() => { setSt(null); load(); }, [load]);

  const session = st?.session;
  const live = session?.status === "live";
  const myTurn = live && session.on_clock_team_id === st.my_team_id;
  const onClock = st?.teams.find((t: any) => t.id === session?.on_clock_team_id);

  // Merge a light state (no player pool) into the full state
  const merge = (next: any) => setSt((cur: any) => ({ ...cur, ...next, pool: next.pool?.length ? next.pool : cur?.pool ?? [] }));

  // Computer picks: one at a time so the board animates
  React.useEffect(() => {
    if (!live || myTurn || !onClock) return;
    if (!onClock.is_bot && (secs ?? 1) > 0) return;       // a human's clock is still running
    const t = setTimeout(async () => {
      try { merge(await api(`/leagues/${lid}/draft/advance`, { method: "POST", body: {} })); } catch (e) { setError((e as Error).message); }
    }, onClock.is_bot ? 350 : 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, myTurn, session?.current_pick, onClock?.id, secs === 0]);

  // Countdown
  React.useEffect(() => { setSecs(session?.seconds_left ?? null); }, [session?.current_pick, session?.seconds_left]);
  React.useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setSecs((s) => (s == null ? s : Math.max(0, s - 1))), 1000);
    return () => clearInterval(t);
  }, [live]);
  React.useEffect(() => { if (myTurn && secs === 0) load(); }, [secs, myTurn, load]);   // server auto-picks for an expired human clock

  // Strategy assistant (whenever it is my turn)
  React.useEffect(() => {
    if (myTurn) api(`/leagues/${lid}/draft/assistant`).then(setAssist).catch(() => setAssist(null));
  }, [myTurn, session?.current_pick, lid]);
  React.useEffect(() => { if (session?.status === "complete") reload(); }, [session?.status, reload]);

  const drafted = React.useMemo(() => new Set<number>((st?.picks ?? []).map((p: any) => p.athlete.id)), [st?.picks]);
  const pool = React.useMemo(() => (st?.pool ?? []).filter((p: any) => !drafted.has(p.id)), [st?.pool, drafted]);
  const shown = pool.filter((p: any) => (!q || p.name.toLowerCase().includes(q.toLowerCase())) && (!pos || p.positions.split(",").includes(pos))).slice(0, 80);
  const queue: number[] = (st?.queue ?? []).filter((id: number) => !drafted.has(id));
  const byId = React.useMemo(() => new Map<number, any>((st?.pool ?? []).map((p: any) => [p.id, p])), [st?.pool]);

  const doPick = (id: number) => act.run(async () => { merge(await api(`/leagues/${lid}/draft/pick`, { method: "POST", body: { athlete_id: id } })); setPicked(null); });
  const saveQueue = (ids: number[]) => { setSt((c: any) => ({ ...c, queue: ids })); api(`/leagues/${lid}/draft/queue`, { method: "PUT", body: { athlete_ids: ids } }).catch((e) => setError(e.message)); };
  const simAll = (to_end: boolean) => act.run(async () => merge(await api(`/leagues/${lid}/draft/sim`, { method: "POST", body: { to_end } })));

  if (error && !st) return <ErrorBox message={error} onRetry={load} />;
  if (!st) return <Spinner />;

  // ---------------------------------------------------------------- not started
  if (!session) {
    return (
      <>
        <PageHeader title="Draft Room" sub={league!.name} />
        <Card>
          <div className="space-y-4">
            <p className="text-sm text-ink2">Snake draft · {st.num_teams} teams · {st.teams.length < st.num_teams ? `${st.num_teams - st.teams.length} open seats will be filled by computer managers` : "all seats filled"}. The draft order is randomized when you start.</p>
            <div className="flex flex-wrap gap-2">{st.teams.map((t: any) => <Badge key={t.id} tone={t.is_me ? "teal" : "neutral"}>{t.name}{t.is_bot ? " (computer)" : ""}</Badge>)}</div>
            {act.error && <ErrorBox message={act.error} />}
            {st.is_commissioner ? <StartForm onStart={(pick_seconds) => act.run(async () => { setSt(await api(`/leagues/${lid}/draft/start`, { method: "POST", body: { pick_seconds } })); await reload(); })} busy={act.busy} />
              : <p className="text-sm text-ink3">Waiting for the commissioner to start the draft.</p>}
          </div>
        </Card>
      </>
    );
  }

  // ---------------------------------------------------------------- board
  const n = st.num_teams;
  const cols = [...st.teams].sort((a: any, b: any) => (a.draft_slot ?? 0) - (b.draft_slot ?? 0));
  const pickAt = new Map<number, any>(st.picks.map((p: any) => [p.overall, p]));
  const overallFor = (round: number, slot: number) => (round - 1) * n + (round % 2 ? slot : n - slot + 1);
  const rounds: number[] = Array.from({ length: session.rounds }, (_, i) => i + 1);
  const myPicks = st.picks.filter((p: any) => p.team_id === st.my_team_id);

  return (
    <>
      <PageHeader title="Draft Room" sub={<>{league!.name} · snake draft <SimBadge text="Simulated player pool" /></>}
        action={live && st.is_commissioner ? <div className="flex gap-2">
          <Button size="sm" onClick={() => simAll(false)} disabled={act.busy || myTurn}><FastForward className="h-3.5 w-3.5" />Sim to my pick</Button>
          <Button size="sm" onClick={() => confirm("Auto-draft every remaining pick, including yours?") && simAll(true)} disabled={act.busy}><Bot className="h-3.5 w-3.5" />Auto-draft the rest</Button></div> : undefined} />
      {(error || act.error) && <div className="mb-3"><ErrorBox message={(act.error ?? error)!} /></div>}
      {dataStatus && dataStatus.counts.player_game_stats === 0 && (
        <div role="note" className="mb-3 rounded-md border border-amber/40 bg-amber/10 p-3 text-sm text-amber">No player statistics have been imported yet, so rankings and projections are placeholders (alphabetical). {dataStatus.limitations[0] ?? "Import box scores from the Data Admin page for meaningful values."}</div>
      )}

      <div className={cn("mb-4 flex flex-wrap items-center gap-4 rounded-lg border p-4", myTurn ? "border-teal/60 bg-teal/10" : "border-line bg-panel")}>
        {live ? <>
          <Gavel className={cn("h-5 w-5", myTurn ? "text-teal" : "text-ink3")} />
          <div><div className="text-xs text-ink3">Pick {session.current_pick} of {session.total_picks} · Round {session.current_round}</div>
            <div className="font-medium">{myTurn ? "You are on the clock" : `${onClock?.name ?? ""} ${onClock?.is_bot ? "(computer) is picking…" : "is on the clock"}`}</div></div>
          <div className="ml-auto flex items-center gap-2"><Clock className="h-4 w-4 text-ink3" /><span className={cn("num text-2xl font-semibold", (secs ?? 99) <= 10 && myTurn && "text-bad")} aria-live="off">{secs ?? "-"}s</span></div>
        </> : <><Sparkles className="h-5 w-5 text-teal" /><div className="font-medium">Draft complete - {session.total_picks} picks made</div><Link href="/team" className="ml-auto"><Button variant="primary">View my team</Button></Link></>}
      </div>

      <div className="grid gap-4 2xl:grid-cols-[1fr_380px]">
        <div className="min-w-0 space-y-4">
          <Card title="Draft board" pad={false}>
            <div className="max-h-80 overflow-auto">
              <table className="w-full min-w-[760px] border-separate border-spacing-0.5 text-[11px]">
                <thead className="sticky top-0 z-10 bg-panel"><tr><th className="w-8" />{cols.map((t: any) => <th key={t.id} className={cn("truncate px-1 py-1 text-left font-medium", t.is_me ? "text-teal" : "text-ink3")}>{t.name}</th>)}</tr></thead>
                <tbody>{rounds.map((r) => (
                  <tr key={r}><td className="num text-center text-ink3">{r}</td>
                    {cols.map((t: any) => {
                      const ov = overallFor(r, t.draft_slot); const p = pickAt.get(ov); const cur = live && ov === session.current_pick;
                      return <td key={t.id} className={cn("h-9 rounded border px-1 align-top", p ? POS_COLOR[p.athlete.positions.split(",")[0]] : "border-line/60", cur && "animate-pulse !border-teal ring-1 ring-teal")}>
                        {p ? <><div className="truncate font-medium leading-tight">{p.athlete.name}</div><div className="text-[10px] text-ink3">{p.athlete.positions.replace(",", "/")} · {p.athlete.team}{p.auto ? " · auto" : ""}</div></> : <span className="num text-ink3">{ov}</span>}</td>;
                    })}</tr>))}</tbody>
              </table>
            </div>
          </Card>

          {live && (
            <Card title="Available players" pad={false} action={<span className="text-xs text-ink3">{pool.length} left</span>}>
              <div className="flex flex-wrap gap-2 border-b border-line p-3">
                <div className="relative min-w-48 flex-1"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink3" /><Input aria-label="Search available players" className="pl-8" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
                <Select aria-label="Position" value={pos} onChange={(e) => setPos(e.target.value)}><option value="">All</option>{["PG", "SG", "SF", "PF", "C"].map((p) => <option key={p}>{p}</option>)}</Select>
              </div>
              <div className="max-h-[420px] overflow-auto">
                <table className="w-full text-sm"><thead className="sticky top-0 bg-panel text-[11px] uppercase tracking-wider text-ink3"><tr><th className="p-2 text-left">Rank</th><th className="p-2 text-left">Player</th><th className="p-2 text-right">Age</th><th className="p-2 text-right">Proj FP/G</th><th className="w-40" /></tr></thead>
                  <tbody>{shown.map((p: any) => (
                    <tr key={p.id} onClick={() => setPicked(p.id)} className={cn("cursor-pointer border-t border-line/60 hover:bg-panel2/60", picked === p.id && "bg-blue/15")}>
                      <td className="num p-2 text-ink3">{p.rank}</td>
                      <td className="p-2"><span className="font-medium">{p.name}</span><div className="text-[11px] text-ink3">{p.positions.replace(",", "/")} · {p.team}{p.injury !== "HEALTHY" && <Badge tone="amber" className="ml-1.5">{p.injury}</Badge>}</div></td>
                      <td className="num p-2 text-right text-ink2">{p.age ?? "-"}</td><td className="num p-2 text-right font-semibold text-teal">{p.proj.toFixed(1)}</td>
                      <td className="p-2 text-right"><div className="flex justify-end gap-1">
                        <Button size="sm" aria-label={`Queue ${p.name}`} onClick={(e) => { e.stopPropagation(); if (!queue.includes(p.id)) saveQueue([...queue, p.id]); }}><ListPlus className="h-3 w-3" /></Button>
                        <Button size="sm" variant="primary" disabled={!myTurn || act.busy} onClick={(e) => { e.stopPropagation(); doPick(p.id); }}>Draft</Button></div></td>
                    </tr>))}</tbody></table>
                {!shown.length && <Empty>No players match.</Empty>}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {live && picked && byId.get(picked) && !drafted.has(picked) && (
            <Card title="Selected player"><div className="flex items-start justify-between"><div><div className="font-medium">{byId.get(picked).name}</div><div className="text-xs text-ink3">{byId.get(picked).positions.replace(",", "/")} · {byId.get(picked).team} · age {byId.get(picked).age ?? "-"} · rank #{byId.get(picked).rank}</div>
              <div className="mt-1 text-sm">Projected <b className="num text-teal">{byId.get(picked).proj.toFixed(1)}</b> FP/G</div></div>
              <Button variant="primary" disabled={!myTurn || act.busy} onClick={() => doPick(picked)}>Draft</Button></div></Card>
          )}
          {live && <AssistantPanel a={assist} myTurn={myTurn} onPick={doPick} busy={act.busy} />}
          {live && (
            <Card title={`Your queue (${queue.length})`}>
              {!queue.length ? <p className="text-xs text-ink3">Queue players with the + button. If your clock runs out, the first available queued player is drafted for you.</p> :
                <ol className="space-y-1 text-sm">{queue.map((id) => byId.get(id) && (
                  <li key={id} className="flex items-center justify-between"><span>{byId.get(id).name} <span className="text-[11px] text-ink3">{byId.get(id).positions.replace(",", "/")}</span></span>
                    <span className="flex gap-1"><Button size="sm" variant="ghost" disabled={!myTurn} onClick={() => doPick(id)}>Draft</Button><button aria-label="Remove from queue" className="rounded p-1 text-ink3 hover:text-bad" onClick={() => saveQueue(queue.filter((x) => x !== id))}><X className="h-3.5 w-3.5" /></button></span></li>))}</ol>}
            </Card>
          )}
          <Card title={`Your picks (${myPicks.length}/${session.rounds})`}>
            <ul className="space-y-1 text-sm">{myPicks.map((p: any) => <li key={p.overall} className="flex justify-between"><span><span className="num mr-2 text-ink3">{p.overall}</span>{p.athlete.name}</span><span className="text-[11px] text-ink3">{p.athlete.positions.replace(",", "/")}</span></li>)}</ul>
            {!myPicks.length && <p className="text-xs text-ink3">No picks yet.</p>}
          </Card>
        </div>
      </div>
    </>
  );
}

function StartForm({ onStart, busy }: { onStart: (secs: number) => void; busy: boolean }) {
  const [secs, setSecs] = React.useState(45);
  return <div className="flex flex-wrap items-end gap-3"><label className="text-xs text-ink3">Pick clock<Select value={secs} onChange={(e) => setSecs(Number(e.target.value))} className="mt-1 block">{[15, 30, 45, 60, 90].map((s) => <option key={s} value={s}>{s} seconds</option>)}</Select></label>
    <Button variant="primary" disabled={busy} onClick={() => onStart(secs)}><Play className="h-4 w-4" />Start draft</Button></div>;
}

function AssistantPanel({ a, myTurn, onPick, busy }: { a: any; myTurn: boolean; onPick: (id: number) => void; busy: boolean }) {
  if (!a) return <Card title="Draft strategy assistant" action={<Badge tone="blue">Explainable</Badge>}><p className="text-xs text-ink3">Recommendations appear when you are on the clock.</p></Card>;
  return (
    <Card title="Draft strategy assistant" action={<Badge tone="blue">Explainable</Badge>}>
      <div className="space-y-3">
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wider text-ink3">Best available for you</div>
          <ul className="space-y-1.5">{a.best_available.slice(0, 5).map((r: any, i: number) => (
            <li key={r.id} className="rounded-md border border-line bg-panel2 p-2">
              <div className="flex items-center justify-between"><div className="text-sm font-medium">{i + 1}. {r.name} <span className="text-[11px] font-normal text-ink3">{r.positions.replace(",", "/")} · {r.team}</span></div>
                <Button size="sm" variant={i === 0 ? "primary" : "outline"} disabled={!myTurn || busy} onClick={() => onPick(r.id)}>Draft</Button></div>
              <div className="mt-1 flex flex-wrap gap-1"><Badge tone="teal">VOR {r.vor > 0 ? "+" : ""}{r.vor}</Badge>{r.fills_need && <Badge tone="good">fills need</Badge>}<Badge title="Estimated chance he is still available at your next pick">{Math.round(r.survive_prob * 100)}% back at next pick</Badge></div>
              <p className="mt-1 text-[11px] text-ink3">{r.reasons.join(" · ")}</p></li>))}</ul>
        </div>
        <div><div className="mb-1 text-[11px] uppercase tracking-wider text-ink3">Positions of need</div>
          <div className="flex flex-wrap gap-1">{Object.keys(a.positions_of_need).length ? Object.entries(a.positions_of_need).map(([p, n]) => <Badge key={p} tone="amber">{p} × {n as number}</Badge>) : <span className="text-xs text-ink3">Starting lineup filled</span>}</div></div>
        <div><div className="mb-1 text-[11px] uppercase tracking-wider text-ink3">Remaining depth (players above replacement)</div>
          <div className="grid grid-cols-5 gap-1 text-center text-xs">{Object.entries(a.depth).map(([p, d]: any) => <div key={p} className="rounded border border-line bg-panel2 p-1"><div className="text-ink3">{p}</div><div className="num text-sm font-semibold">{d.above_replacement}</div></div>)}</div></div>
        <div><div className="mb-1 text-[11px] uppercase tracking-wider text-ink3">Roster balance</div>
          <div className="flex gap-1.5 text-xs">{Object.entries(a.balance).map(([p, n]) => <span key={p} className="num text-ink2">{p} {n as number}</span>)}</div></div>
        {a.steals.length > 0 && <div><div className="mb-1 text-[11px] uppercase tracking-wider text-ink3">Potential steals</div>
          <ul className="text-xs text-ink2">{a.steals.map((s: any) => <li key={s.id}>{s.name} - ranked #{s.rank}, still on the board (+{s.falls_by} picks of value)</li>)}</ul></div>}
        {a.opportunity_cost && <div className="rounded-md border border-amber/30 bg-amber/10 p-2 text-xs text-ink2"><b className="text-amber">Opportunity cost.</b> {a.opportunity_cost.explanation}</div>}
        <p className="text-[10px] text-ink3">{a.method}</p>
      </div>
    </Card>
  );
}

"use client";
import * as React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useApp, useLeagueData } from "@/lib/league-context";
import { Badge, Button, Card, ErrorBox, PageHeader, SimBadge, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import { SimControls } from "@/components/sim-controls";
import { cn } from "@/lib/utils";

 
export default function MatchupsPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

function Inner() {
  const { league } = useApp();
  const [week, setWeek] = React.useState<number | null>(null);
  const q = week ? `?week=${week}` : "";
  const { data, error, loading, reload } = useLeagueData<any>(league?.status === "active" ? `/matchup${q}` : null, [week]);
  const { data: all } = useLeagueData<any>(league?.status === "active" ? `/matchups${q}` : null, [week]);
  if (league?.status !== "active") return <><PageHeader title="Matchups" /><Card><p className="text-sm text-ink3">Matchups start once the draft is complete.</p></Card></>;
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (loading && !data) return <Spinner />;
  if (!data) return null;

  const m = data.matchup, w = data.week;
  const mineHome = m.home.team_id === data.my_team_id;
  const me = mineHome ? m.home : m.away, opp = mineHome ? m.away : m.home;
  const days: number[] = Array.from({ length: m.last_day - m.first_day + 1 }, (_, i) => m.first_day + i);
  const lead = me.points - opp.points;

  return (
    <>
      <PageHeader title="Matchup Center" sub={<>Week {w} of {data.total_weeks} <SimBadge /></>} action={<SimControls />} />
      <div className="mb-4 flex items-center gap-2">
        <Button size="sm" disabled={w <= 1} onClick={() => setWeek(w - 1)} aria-label="Previous week"><ChevronLeft className="h-4 w-4" /></Button>
        <span className="num text-sm">Week {w}</span>
        <Button size="sm" disabled={w >= data.total_weeks} onClick={() => setWeek(w + 1)} aria-label="Next week"><ChevronRight className="h-4 w-4" /></Button>
        {w !== data.current_week && <Button size="sm" variant="ghost" onClick={() => setWeek(null)}>Current week</Button>}
        {m.final ? <Badge tone="good">Final</Badge> : w === data.current_week ? <Badge tone="teal">Live · day {m.current_day}</Badge> : <Badge>Upcoming</Badge>}
      </div>

      <Card>
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <Side name={me.name} manager={me.manager} points={me.points} proj={me.projected} color="text-teal" />
          <div className="text-center"><div className="text-xs text-ink3">{m.final ? "Final" : "Margin"}</div><div className={cn("num text-lg font-semibold", lead > 0 ? "text-good" : lead < 0 ? "text-bad" : "")}>{lead > 0 ? "+" : ""}{lead.toFixed(1)}</div></div>
          <Side name={opp.name} manager={opp.manager} points={opp.points} proj={opp.projected} color="text-amber" right />
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs"><thead className="text-ink3"><tr><th className="p-1.5 text-left">Daily scoring</th>{days.map((d) => <th key={d} className="p-1.5 text-right">D{d}</th>)}<th className="p-1.5 text-right">Total</th></tr></thead>
            <tbody>
              {[["You", me, "text-teal"], ["Opp", opp, "text-amber"]].map(([l, s, c]: any) => (
                <tr key={l} className="border-t border-line"><td className={cn("p-1.5 font-medium", c)}>{s.name}</td>{days.map((d) => <td key={d} className="num p-1.5 text-right text-ink2">{d > m.current_day ? "·" : (s.daily_totals[d] ?? 0).toFixed(0)}</td>)}<td className="num p-1.5 text-right font-semibold">{s.points.toFixed(1)}</td></tr>))}
            </tbody></table>
        </div>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Roster title={me.name} team={me} days={days} cur={m.current_day} />
        <Roster title={opp.name} team={opp} days={days} cur={m.current_day} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title={`Week ${w} around the league`}>
          <ul className="space-y-1 text-sm">{all?.matchups.map((x: any) => (
            <li key={x.id} className={cn("flex items-center justify-between rounded px-2 py-1", x.mine && "bg-teal/10")}>
              <span className="truncate">{x.home}</span><span className="num mx-2 shrink-0 text-ink2">{x.home_score.toFixed(0)} - {x.away_score.toFixed(0)}</span><span className="truncate text-right">{x.away}</span></li>))}</ul>
        </Card>
        <Card title="Your results this season">
          {data.history.length === 0 ? <p className="text-sm text-ink3">No completed weeks yet.</p> : (
            <table className="w-full text-sm"><tbody>{data.history.map((h: any) => (
              <tr key={h.week} className="border-b border-line/50"><td className="num w-10 py-1 text-ink3">W{h.week}</td><td className="truncate">{h.opponent}</td>
                <td className="num text-right">{h.points.toFixed(0)} - {h.opponent_points.toFixed(0)}</td>
                <td className="w-8 text-right"><Badge tone={h.points > h.opponent_points ? "good" : "bad"}>{h.points > h.opponent_points ? "W" : "L"}</Badge></td></tr>))}</tbody></table>)}
        </Card>
      </div>
    </>
  );
}

function Side({ name, manager, points, proj, color, right }: { name: string; manager: string; points: number; proj: number; color: string; right?: boolean }) {
  return <div className={right ? "text-right" : ""}><div className="font-medium">{name}</div><div className="text-xs text-ink3">{manager}</div>
    <div className={cn("num text-4xl font-semibold", color)}>{points.toFixed(1)}</div><div className="text-xs text-ink3">Projected final <span className="num text-ink2">{proj.toFixed(0)}</span></div></div>;
}

function Roster({ title, team, days, cur }: { title: string; team: any; days: number[]; cur: number }) {
  const starters = team.players.filter((p: any) => p.slot && p.slot !== "BN" && p.slot !== "IR");
  const bench = team.players.filter((p: any) => !p.slot || p.slot === "BN" || p.slot === "IR");
  const row = (p: any, dim?: boolean) => (
    <tr key={p.athlete_id} className={cn("border-t border-line/50", dim && "text-ink3")}>
      <td className="w-10 p-1.5"><Badge className="w-9 justify-center">{p.slot ?? "-"}</Badge></td>
      <td className="p-1.5">{p.name}<span className="ml-1 text-[11px] text-ink3">{p.team}</span></td>
      <td className="num p-1.5 text-right text-ink3">{p.games_played}/{p.games_played + p.games_left}</td>
      <td className="num p-1.5 text-right">{(dim ? p.bench_points : p.points).toFixed(1)}</td>
      <td className="num p-1.5 text-right text-ink3">{p.proj_rest ? `+${p.proj_rest.toFixed(0)}` : ""}</td>
    </tr>);
  return (
    <Card title={title} pad={false}>
      <table className="w-full text-sm"><thead className="text-[11px] uppercase tracking-wider text-ink3"><tr><th className="p-1.5" /><th className="p-1.5 text-left">Player</th><th className="p-1.5 text-right" title="Games played / total this week">GP</th><th className="p-1.5 text-right">Pts</th><th className="p-1.5 text-right" title="Projected additional points">Proj</th></tr></thead>
        <tbody>{starters.map((p: any) => row(p))}
          <tr><td colSpan={5} className="bg-panel2 px-1.5 py-1 text-[11px] uppercase tracking-wider text-ink3">Bench / IR · bench production {team.bench_points.toFixed(1)} (not counted)</td></tr>
          {bench.map((p: any) => row(p, true))}</tbody></table>
      <span className="sr-only">Current simulated day {cur}, week days {days[0]} to {days[days.length - 1]}</span>
    </Card>
  );
}

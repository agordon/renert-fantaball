"use client";
import * as React from "react";
import { WeeklyChart } from "@/components/charts";
import { useLeagueData } from "@/lib/league-context";
import { Badge, Card, ErrorBox, PageHeader, SimBadge, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import { cn } from "@/lib/utils";

 
export default function StandingsPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

function Inner() {
  const { data, error, loading, reload } = useLeagueData<any>("/standings");
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (loading && !data) return <Spinner />;
  if (!data) return null;
  const mine = data.standings.find((r: any) => r.team_id === data.my_team_id);
  return (
    <>
      <PageHeader title="Standings" sub={<>Head-to-head points · top 6 make the playoffs <SimBadge /></>} />
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Card pad={false}>
          <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-ink3"><tr className="border-b border-line"><th className="p-2 text-left">#</th><th className="p-2 text-left">Team</th><th className="p-2 text-right">W</th><th className="p-2 text-right">L</th><th className="p-2 text-right">T</th><th className="p-2 text-right">PF</th><th className="p-2 text-right">PA</th><th className="p-2 text-right">Streak</th><th className="p-2 text-left">Last 5</th></tr></thead>
            <tbody>{data.standings.map((r: any, i: number) => (
              <React.Fragment key={r.team_id}>
                <tr className={cn("border-b border-line/60", r.team_id === data.my_team_id && "bg-teal/10")}>
                  <td className="num p-2 text-ink3">{r.rank}</td>
                  <td className="p-2"><div className="font-medium">{r.team}</div><div className="text-[11px] text-ink3">{r.manager}{r.is_bot ? " · computer" : ""}</div></td>
                  <td className="num p-2 text-right">{r.w}</td><td className="num p-2 text-right">{r.l}</td><td className="num p-2 text-right text-ink3">{r.t}</td>
                  <td className="num p-2 text-right">{r.pf.toFixed(1)}</td><td className="num p-2 text-right text-ink3">{r.pa.toFixed(1)}</td>
                  <td className={cn("num p-2 text-right", r.streak.startsWith("W") ? "text-good" : r.streak.startsWith("L") ? "text-bad" : "")}>{r.streak}</td>
                  <td className="p-2"><span className="inline-flex gap-0.5">{r.last5.split("").map((c: string, j: number) => <span key={j} className={cn("grid h-5 w-5 place-items-center rounded text-[10px] font-semibold", c === "W" ? "bg-good/15 text-good" : c === "L" ? "bg-bad/15 text-bad" : "bg-panel2 text-ink3")}>{c}</span>)}</span></td>
                </tr>
                {i === 5 && <tr key="cut"><td colSpan={9} className="bg-panel2 px-2 py-0.5 text-center text-[10px] uppercase tracking-widest text-ink3">Playoff line</td></tr>}
              </React.Fragment>
            ))}</tbody></table></div>
        </Card>
        <div className="space-y-4">
          <Card title="Power rankings" action={<Badge tone="blue">Formula</Badge>}>
            <ol className="space-y-1 text-sm">{data.power.map((p: any) => (
              <li key={p.team_id} className={cn("flex items-center gap-2", p.team_id === data.my_team_id && "text-teal")}>
                <span className="num w-5 text-ink3">{p.rank}</span><span className="flex-1 truncate">{p.team}</span>
                <div className="h-1.5 w-20 overflow-hidden rounded bg-panel2"><div className="h-full bg-blue" style={{ width: `${p.power}%` }} /></div><span className="num w-10 text-right">{p.power.toFixed(0)}</span></li>))}</ol>
            <p className="mt-3 text-[11px] text-ink3">{data.formula}. Computed in <code>fantaball/leagues.py</code> (power_rankings).</p>
          </Card>
          {mine && <Card><p className="text-sm text-ink2">You are <b className="text-ink">#{mine.rank}</b> at {mine.w}-{mine.l}. {mine.playoff ? "You are currently in a playoff spot." : "You are currently outside the playoff line."}</p></Card>}
        </div>
      </div>
      <Card className="mt-4" title="Weekly scoring by team (your team highlighted)" action={<SimBadge />}>
        <WeeklyChart data={data} />
      </Card>
    </>
  );
}

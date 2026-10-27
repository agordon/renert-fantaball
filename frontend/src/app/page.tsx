"use client";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, Lightbulb } from "lucide-react";
import { useApp, useLeagueData } from "@/lib/league-context";
import { api } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import { Badge, Button, Card, Empty, ErrorBox, PageHeader, DataBadge, Spinner, Stat } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import type { DataBlock, RecentPerformance, UpcomingProGame } from "@/lib/api-types";
import { when } from "@/lib/utils";
import { ScoredThrough } from "@/components/scored-through";

 
export default function Dashboard() {
  return <NeedLeague><DashboardInner /></NeedLeague>;
}

const tip = { background: "#1a2028", border: "1px solid #252d38", borderRadius: 6, fontSize: 12 };

function DashboardInner() {
  const { league, reload } = useApp();
  const { data: d, error, loading, reload: refresh } = useLeagueData<any>("/dashboard");
  const act = useAction();
  if (loading && !d) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={refresh} />;
  if (!d || !league) return null;

  if (league.status !== "active") {
    return (
      <>
        <PageHeader title={league.name} sub="Your league is waiting for its draft." />
        <Card><div className="flex items-center justify-between gap-4">
          <p className="text-sm text-ink2">{league.status === "drafting" ? "The draft is live." : "Open the Draft Room to start the snake draft. Empty seats are filled by computer managers."}</p>
          <Link href="/draft"><Button variant="primary">Go to Draft Room <ArrowRight className="h-4 w-4" /></Button></Link>
        </div></Card>
      </>
    );
  }

  const m = d.matchup, rec = d.record;
  const applyAction = (s: any) => act.run(async () => {
    if (s.action.kind === "add_drop") await api(`/leagues/${league.id}/add-drop`, { method: "POST", body: { add_id: s.action.add_id, drop_id: s.action.drop_id } });
    else await api(`/leagues/${league.id}/lineup/auto`, { method: "POST", body: {} });
    await reload(); await refresh();
  });

  return (
    <>
      <PageHeader title="Dashboard" sub={`${league.name} · ${d.team.name}`} action={<ScoredThrough />} />
      <DataStrip data={d.data as DataBlock} />
      <div className="grid gap-4 lg:grid-cols-4">
        <Card><Stat label="Record" value={`${rec.w}-${rec.l}${rec.t ? `-${rec.t}` : ""}`} sub={`Streak ${rec.streak}`} /></Card>
        <Card><Stat label="Standing" value={`#${rec.rank}`} sub={rec.playoff ? "In playoff position" : "Outside playoff line"} tone={rec.playoff ? "good" : undefined} /></Card>
        <Card><Stat label="Points for" value={rec.pf.toLocaleString()} sub={`Against ${rec.pa.toLocaleString()}`} /></Card>
        <Card><Stat label="Pending trades" value={d.pending_trades} sub={<Link className="text-teal hover:underline" href="/trades">Review offers</Link>} /></Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {m && (
          <Card className="lg:col-span-2" title={`Week ${m.week} matchup`} action={<DataBadge />}>
            <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 py-2">
              <div><div className="text-xs text-ink3">{d.team.name}</div><div className="num text-3xl font-semibold text-teal">{m.my_points.toFixed(1)}</div><div className="text-xs text-ink3">proj. <span className="num">{m.my_projected.toFixed(0)}</span></div></div>
              <div className="text-xs text-ink3">vs</div>
              <div className="text-right"><div className="text-xs text-ink3">{m.opponent}</div><div className="num text-3xl font-semibold text-amber">{m.opp_points.toFixed(1)}</div><div className="text-xs text-ink3">proj. <span className="num">{m.opp_projected.toFixed(0)}</span></div></div>
            </div>
            <div className="mt-1" aria-label={`Projected win probability ${Math.round(m.win_prob * 100)} percent`}>
              <div className="flex h-2 overflow-hidden rounded bg-panel2"><div className="bg-teal" style={{ width: `${m.win_prob * 100}%` }} /><div className="ml-0.5 flex-1 bg-amber" /></div>
              <div className="mt-1 flex justify-between text-[11px] text-ink3"><span>Projected win chance {Math.round(m.win_prob * 100)}%</span><span>Estimate from projections · not a guarantee</span></div>
            </div>
            <div className="mt-3 text-right"><Link href="/matchups" className="text-xs text-teal hover:underline">Full player breakdown →</Link></div>
          </Card>
        )}
        <Card title="Roster GM" action={<Badge tone="blue">Rule-based</Badge>}>
          <p className="text-xs text-ink2">{d.gm.summary}</p>
          <ul className="mt-3 space-y-2">
            {d.gm.suggestions.slice(0, 3).map((s: any, i: number) => (
              <li key={i} className="rounded-md border border-line bg-panel2 p-2.5">
                <div className="flex items-center gap-1.5 text-sm font-medium"><Lightbulb className="h-3.5 w-3.5 text-amber" />{s.title}<Badge tone="good" className="ml-auto">+{Math.round(s.impact)} pts/wk</Badge></div>
                <p className="mt-1 text-xs text-ink3">{s.detail}</p>
                <Button size="sm" className="mt-2" disabled={act.busy} onClick={() => applyAction(s)}>{s.action.kind === "add_drop" ? "Make the move" : "Optimize lineup"}</Button>
              </li>
            ))}
            {!d.gm.suggestions.length && <Empty>Your roster looks well optimized.</Empty>}
          </ul>
          {act.error && <p role="alert" className="mt-2 text-xs text-bad">{act.error}</p>}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" title="Recent weekly scoring" action={<DataBadge />}>
          {d.recent_scores.length ? (
            <div className="h-56" role="img" aria-label="Bar chart of your weekly points versus your opponents">
              <ResponsiveContainer>
                <BarChart data={d.recent_scores} barGap={2} margin={{ left: -10, right: 4 }}>
                  <CartesianGrid stroke="#252d38" vertical={false} />
                  <XAxis dataKey="week" tickFormatter={(w) => `W${w}`} stroke="#7b8694" fontSize={11} tickLine={false} />
                  <YAxis stroke="#7b8694" fontSize={11} tickLine={false} axisLine={false} domain={[0, "auto"]} />
                  <Tooltip contentStyle={tip} cursor={{ fill: "#ffffff0a" }} labelFormatter={(w) => `Week ${w}`} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="points" name="You" fill="#2dd4bf" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="opponent_points" name="Opponent" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : <Empty>Scores appear after your first completed week of real games (they update with each data sync).</Empty>}
        </Card>
        <Card title="Upcoming games for your starters">
          {d.upcoming_games.map((day: any) => (
            <div key={day.day} className="mb-2">
              <div className="text-[11px] uppercase tracking-wider text-ink3">Day {day.day} · {day.games.length} starters play</div>
              <div className="mt-1 flex flex-wrap gap-1">{day.games.map((g: any, i: number) => <Badge key={i}>{g.player.split(" ")[1]} {g.home ? "vs" : "@"} {g.opponent}</Badge>)}</div>
            </div>
          ))}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Upcoming NBA games" action={<DataBadge />}>
          {(d.upcoming_nba_games as UpcomingProGame[]).length === 0 ? <Empty>No upcoming games are in the database. Sync the schedule from Data Admin.</Empty> : (
            <ul className="grid grid-cols-1 gap-1 text-sm sm:grid-cols-2">
              {(d.upcoming_nba_games as UpcomingProGame[]).slice(0, 10).map((g, i) => (
                <li key={i} className="flex items-center justify-between rounded border border-line bg-panel2 px-2 py-1"><span className="num">{g.away} @ {g.home}</span><span className="text-xs text-ink3">{g.date ? g.date.slice(5) : `D${g.day}`}</span></li>))}
            </ul>)}
        </Card>
        <Card title="Recent player performances" action={<DataBadge />}>
          {(d.recent_performances as RecentPerformance[]).length === 0 ? <Empty>No imported box scores yet.</Empty> : (
            <table className="w-full text-sm"><tbody>
              {(d.recent_performances as RecentPerformance[]).map((r, i) => (
                <tr key={i} className="border-b border-line/50"><td className="py-1">{r.name} <span className="text-[11px] text-ink3">{r.team}</span></td>
                  <td className="num text-right text-xs text-ink3">{r.line.pts ?? "-"} pts · {r.line.reb ?? "-"} reb · {r.line.ast ?? "-"} ast</td><td className="num w-14 text-right font-semibold text-teal">{r.fp.toFixed(1)}</td></tr>))}
            </tbody></table>)}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Standings" action={<Link href="/standings" className="text-xs text-teal hover:underline">All →</Link>}>
          <table className="w-full text-sm"><tbody>
            {d.standings_top.map((r: any) => (
              <tr key={r.team_id} className={r.team_id === d.team.id ? "text-teal" : ""}>
                <td className="num w-6 py-1 text-ink3">{r.rank}</td><td className="truncate">{r.team}</td>
                <td className="num text-right">{r.w}-{r.l}</td><td className="num w-20 text-right text-ink3">{r.pf.toFixed(0)}</td>
              </tr>))}
          </tbody></table>
        </Card>
        <Card title="Recent league activity" action={<Link href="/activity" className="text-xs text-teal hover:underline">All →</Link>}>
          <ul className="space-y-1.5 text-sm text-ink2">{d.activity.map((a: any) => <li key={a.id}>{a.message}</li>)}</ul>
        </Card>
      </div>
    </>
  );
}


const PROVIDER_NAMES: Record<string, string> = { highlightly: "Highlightly", balldontlie: "BALLDONTLIE" };

/** Where the numbers come from and how old they are (timestamp of the underlying statistics). */
function DataStrip({ data }: { data: DataBlock }) {
  if (!data) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-line bg-panel px-3 py-2 text-xs text-ink2">
      <span className="font-medium">Real NBA data · {PROVIDER_NAMES[data.source] ?? data.source}</span>
      {data.season != null && <span>Season {data.season}-{String(data.season + 1).slice(2)}</span>}
      <span>Last data sync: <b className="num text-ink">{data.last_sync ? when(data.last_sync) : "never"}</b></span>
      <span>Statistics as of: <b className="num text-ink">{data.stats_as_of ? when(data.stats_as_of) : "none imported yet"}</b></span>
      {data.scored_through && <span>Fantasy scoring through: <b className="num text-ink">{data.scored_through}</b></span>}
      <span className="text-ink3">Scores update after each sync - not live.</span>
    </div>
  );
}

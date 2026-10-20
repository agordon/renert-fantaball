"use client";
import * as React from "react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { useApp, useLeagueData } from "@/lib/league-context";
import { api } from "@/lib/api";
import { useAction } from "@/lib/use-action";
import { Badge, Button, Card, ErrorBox, PageHeader, Select, SimBadge, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import { WeeklyChart } from "@/components/charts";

 
export default function AnalyticsPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

function Inner() {
  const { league } = useApp();
  const st = useLeagueData<any>(league?.status === "active" ? "/standings" : null);
  const team = useLeagueData<any>(league?.status === "active" ? "/team" : null);
  if (league?.status !== "active") return <><PageHeader title="Analytics" /><Card><p className="text-sm text-ink3">Analytics unlock after the draft.</p></Card></>;
  if (st.error) return <ErrorBox message={st.error} onRetry={st.reload} />;
  if (st.loading && !st.data) return <Spinner />;
  const rows: any[] = st.data?.standings ?? [];
  const avgPf = rows.reduce((s, r) => s + r.pf, 0) / (rows.length || 1);
  const avgPa = rows.reduce((s, r) => s + r.pa, 0) / (rows.length || 1);
  const pts = rows.map((r) => ({ name: r.team, pf: r.pf, pa: r.pa, me: r.team_id === st.data.my_team_id }));
  const gm = team.data?.gm;

  return (
    <>
      <PageHeader title="Analytics" sub={<>League and roster analysis <SimBadge /></>} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Weekly scoring trends"><WeeklyChart data={st.data} /></Card>
        <Card title="Points for vs points against">
          {rows.some((r) => r.pf > 0) ? <>
            <div className="h-72" role="img" aria-label="Scatter plot of points for versus points against for each team">
              <ResponsiveContainer>
                <ScatterChart margin={{ left: -5, right: 12, top: 8 }}>
                  <CartesianGrid stroke="#252d38" />
                  <XAxis type="number" dataKey="pf" name="Points for" stroke="#7b8694" fontSize={11} domain={["dataMin - 100", "dataMax + 100"]} tickLine={false} />
                  <YAxis type="number" dataKey="pa" name="Points against" stroke="#7b8694" fontSize={11} domain={["dataMin - 100", "dataMax + 100"]} tickLine={false} />
                  <ZAxis range={[70, 70]} />
                  <ReferenceLine x={avgPf} stroke="#5b6675" strokeDasharray="4 4" /><ReferenceLine y={avgPa} stroke="#5b6675" strokeDasharray="4 4" />
                  <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ background: "#1a2028", border: "1px solid #252d38", borderRadius: 6, fontSize: 12 }} formatter={(v: any) => Number(v).toFixed(0)} labelFormatter={() => ""} />
                  <Scatter data={pts.filter((p) => !p.me)} fill="#7b8694" stroke="#141920" strokeWidth={2} />
                  <Scatter data={pts.filter((p) => p.me)} fill="#2dd4bf" stroke="#141920" strokeWidth={2} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[11px] text-ink3">Top-left of the dashed lines: scoring more than average while allowing less. Your team is teal.</p></> : <p className="py-10 text-center text-sm text-ink3">Available after the first completed week.</p>}
        </Card>
      </div>
      {gm && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card title="Fantasy GM report" action={<Badge tone="blue">Rule-based</Badge>}>
            <p className="text-sm text-ink2">{gm.summary}</p>
            <p className="mt-2 text-xs text-ink3">{gm.method}</p>
          </Card>
          <Card title="Schedule optimizer: games left this week">
            <div className="space-y-1 text-sm">{gm.schedule.map((s: any) => (
              <div key={s.athlete_id} className="flex items-center gap-2"><span className="w-40 truncate">{s.name}</span><div className="flex gap-0.5">{Array.from({ length: Math.max(s.games_left, 0) }).map((_, i) => <span key={i} className="h-2.5 w-4 rounded-sm bg-teal" />)}{s.games_left === 0 && <span className="text-xs text-bad">no games</span>}</div></div>))}</div>
          </Card>
        </div>)}
      <WhatIf />
    </>
  );
}

/** What-If Machine (foundation): re-score a past day with a different lineup choice, without changing league history. */
function WhatIf() {
  const { league } = useApp();
  const { data } = useLeagueData<any>("/team");
  const [day, setDay] = React.useState(Math.max(league?.current_day ?? 1, 1));
  const [inId, setIn] = React.useState("");
  const [outId, setOut] = React.useState("");
  const [res, setRes] = React.useState<any>(null);
  const act = useAction();
  const players: any[] = data?.players ?? [];
  return (
    <Card className="mt-4" title="What-If machine · start a different player" action={<Badge tone="amber">Foundation</Badge>}>
      <p className="mb-3 text-xs text-ink3">Pick a past simulated day, a player you started and a player you could have started. FantaBall re-scores that day using saved game logs. Nothing in your league changes.</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-ink3">Day<Select value={day} onChange={(e) => setDay(Number(e.target.value))} className="mt-1 block">{Array.from({ length: league?.current_day ?? 0 }, (_, i) => i + 1).reverse().map((d) => <option key={d} value={d}>Day {d}</option>)}</Select></label>
        <label className="text-xs text-ink3">Instead of (started)<Select value={outId} onChange={(e) => setOut(e.target.value)} className="mt-1 block"><option value="">Choose…</option>{players.filter((p) => p.slot !== "BN" && p.slot !== "IR").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></label>
        <label className="text-xs text-ink3">Start (from reserves)<Select value={inId} onChange={(e) => setIn(e.target.value)} className="mt-1 block"><option value="">Choose…</option>{players.filter((p) => p.slot === "BN" || p.slot === "IR").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></label>
        <Button variant="primary" disabled={!inId || !outId || act.busy} onClick={() => act.run(async () => setRes(await api(`/leagues/${league!.id}/what-if/lineup`, { method: "POST", body: { day, in_id: Number(inId), out_id: Number(outId) } })))}>Recalculate</Button>
      </div>
      {act.error && <div className="mt-2"><ErrorBox message={act.error} /></div>}
      {res && <p className="mt-3 text-sm">{res.explanation}</p>}
    </Card>
  );
}

"use client";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

 
export function WeeklyChart({ data }: { data: any }) {
  const mineName = data.standings.find((r: any) => r.team_id === data.my_team_id)?.team;
  const names: string[] = data.standings.map((r: any) => r.team);
  if (!data.weekly.length) return <p className="py-6 text-center text-sm text-ink3">The chart appears after the first completed week.</p>;
  return (
    <div className="h-72" role="img" aria-label="Line chart of weekly points for every team; your team is highlighted in teal">
      <ResponsiveContainer>
        <LineChart data={data.weekly} margin={{ left: -10, right: 12 }}>
          <CartesianGrid stroke="#252d38" vertical={false} />
          <XAxis dataKey="week" tickFormatter={(w) => `W${w}`} stroke="#7b8694" fontSize={11} tickLine={false} />
          <YAxis stroke="#7b8694" fontSize={11} tickLine={false} axisLine={false} domain={["dataMin - 100", "dataMax + 100"]} />
          <Tooltip contentStyle={{ background: "#1a2028", border: "1px solid #252d38", borderRadius: 6, fontSize: 12 }} labelFormatter={(w) => `Week ${w}`} itemSorter={(i: any) => -(i.value as number)} formatter={(v: any) => Number(v).toFixed(0)} />
          {names.filter((n) => n !== mineName).map((n) => <Line key={n} dataKey={n} stroke="#5b6675" strokeOpacity={0.55} strokeWidth={1.25} dot={false} isAnimationActive={false} />)}
          <Line dataKey={mineName} stroke="#2dd4bf" strokeWidth={2.5} dot={{ r: 3, stroke: "#141920", strokeWidth: 2 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

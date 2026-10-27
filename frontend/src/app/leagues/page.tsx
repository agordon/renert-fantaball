"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Ticket } from "lucide-react";
import { api } from "@/lib/api";
import { useApiData, useApp } from "@/lib/league-context";
import type { SportInfo } from "@/lib/api-types";
import { useAction } from "@/lib/use-action";
import { Badge, Button, Card, ErrorBox, Input, PageHeader, Select } from "@/components/ui";

 
export default function LeaguesPage() {
  const { leagues, league, setLeagueId, reload } = useApp();
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [teamName, setTeamName] = React.useState("");
  const [teams, setTeams] = React.useState(12);
  const { data: sports } = useApiData<SportInfo[]>("/sports");
  const choices = (sports ?? []).filter((x) => x.available);
  const [sportCode, setSportCode] = React.useState("");
  const sport = choices.find((x) => x.code === sportCode) ?? choices[0];
  const [scoring, setScoring] = React.useState<Record<string, number>>({});
  React.useEffect(() => { if (sport) setScoring({ ...sport.default_scoring }); }, [sport?.code]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [code, setCode] = React.useState("");
  const create = useAction();
  const join = useAction();

  const submitCreate = (e: React.FormEvent) => {
    e.preventDefault();
    create.run(async () => {
      const lg = await api<any>("/leagues", { method: "POST", body: { name, team_name: teamName || undefined, num_teams: teams, sport: sport?.code, scoring_rules: scoring } });
      await reload(); setLeagueId(lg.id); router.push("/draft");
    });
  };
  const submitJoin = (e: React.FormEvent) => {
    e.preventDefault();
    join.run(async () => { const lg = await api<any>("/leagues/join", { method: "POST", body: { code } }); await reload(); setLeagueId(lg.id); router.push("/"); });
  };

  return (
    <>
      <PageHeader title="My Leagues" sub="Create a league, or join one with an invitation code." />
      <div className="mb-6 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {leagues.map((l) => (
          <button key={l.id} onClick={() => { setLeagueId(l.id); router.push("/"); }} className={`rounded-lg border bg-panel p-4 text-left transition-colors hover:bg-panel2 ${l.id === league?.id ? "border-teal/60" : "border-line"}`}>
            <div className="flex items-start justify-between gap-2"><div className="font-medium">{l.name}</div>{l.id === league?.id && <Badge tone="teal">Selected</Badge>}</div>
            <div className="mt-1 text-xs text-ink3">{l.sport_name} · {l.num_teams} teams · Head-to-head points</div>
            <div className="mt-1"><Badge tone="teal">Real NBA data</Badge></div>
            <div className="mt-3 flex items-center gap-2 text-sm">
              {l.record ? <><span className="num font-semibold">{l.record.wins}-{l.record.losses}{l.record.ties ? `-${l.record.ties}` : ""}</span><span className="text-ink3">#{l.record.rank} of {l.num_teams}</span></>
                : <Badge tone="amber">{l.status === "drafting" ? "Draft in progress" : "Pre-draft"}</Badge>}
              {l.is_commissioner && <Badge tone="blue" className="ml-auto">Commissioner</Badge>}
            </div>
          </button>
        ))}
        {!leagues.length && <p className="text-sm text-ink3">No leagues yet.</p>}
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card title="Create a league">
          {sports && !choices.length ? (
            <div className="space-y-2 text-sm text-ink2">
              <p className="font-medium text-ink">There is no player data to build a league on yet.</p>
              <p>An administrator must import real NBA data first: set <code>BALLDONTLIE_API_KEY</code> in <code>.env</code> and run <code>npm run sync</code>, or use the <Link className="text-teal hover:underline" href="/admin">Data Admin</Link> page.</p>
            </div>
          ) : (
          <form onSubmit={submitCreate} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-xs text-ink3 sm:col-span-2">League name<Input required minLength={3} maxLength={50} value={name} onChange={(e) => setName(e.target.value)} placeholder="Friday Night Hoops" className="mt-1" /></label>
              <label className="text-xs text-ink3">Teams<Select value={teams} onChange={(e) => setTeams(Number(e.target.value))} className="mt-1 w-full">{[4, 6, 8, 10, 12, 14].map((n) => <option key={n} value={n}>{n} teams</option>)}</Select></label>
              <label className="text-xs text-ink3 sm:col-span-3">Your team name (optional)<Input maxLength={40} value={teamName} onChange={(e) => setTeamName(e.target.value)} className="mt-1" /></label>
            </div>
            <label className="block text-xs text-ink3">Data
              <Select value={sport?.code ?? ""} onChange={(e) => setSportCode(e.target.value)} className="mt-1 block w-full">
                {choices.map((c) => <option key={c.code} value={c.code}>{c.name} · {`real data (${c.season}-${String((c.season ?? 0) + 1).slice(2)})`} · {c.players} players</option>)}
              </Select></label>
            <fieldset>
              <legend className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink3">Head-to-head points scoring (points per stat)</legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(sport?.stats ?? {}).filter(([k]) => k in (sport?.default_scoring ?? {})).map(([k, label]) => (
                  <label key={k} className="text-xs text-ink3">{label}<Input type="number" step="0.1" min={-20} max={20} value={scoring[k] ?? ""} onChange={(e) => setScoring({ ...scoring, [k]: Number(e.target.value) })} className="num mt-1" /></label>))}
              </div>
              <p className="mt-2 text-xs text-ink3">Empty seats are filled by computer managers so you can draft immediately. Other categories, rotisserie and keeper formats are planned.</p>
            </fieldset>
            {create.error && <ErrorBox message={create.error} />}
            <Button type="submit" variant="primary" disabled={create.busy || !sport}><Plus className="h-4 w-4" />Create league</Button>
          </form>)}
        </Card>
        <Card title="Join with a code">
          <form onSubmit={submitJoin} className="space-y-3">
            <Input aria-label="Invitation code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="8-character code" maxLength={8} className="num uppercase tracking-widest" required />
            {join.error && <ErrorBox message={join.error} />}
            <Button type="submit" disabled={join.busy || code.length < 8}><Ticket className="h-4 w-4" />Join league</Button>
            <p className="text-xs text-ink3">Ask a commissioner for the code shown on their Settings page. If the league is full you take over a computer-controlled team.</p>
          </form>
        </Card>
      </div>
    </>
  );
}

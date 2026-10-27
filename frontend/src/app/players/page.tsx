"use client";
import * as React from "react";
import { ArrowDown, ArrowUp, GitCompare, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useApiData, useApp } from "@/lib/league-context";
import type { SportInfo } from "@/lib/api-types";
import { api } from "@/lib/api";
import type { Player } from "@/lib/types";
import { Badge, Button, Card, Empty, ErrorBox, InjuryBadge, Input, Modal, PageHeader, PosBadge, SimBadge, Select, Sparkline, Spinner } from "@/components/ui";
import { AddPlayerModal, PlayerProfile } from "@/components/player-modals";
import { cn, fmt } from "@/lib/utils";

 
const PAGE = 40;

export default function PlayersPage() {
  const { league } = useApp();
  return league ? <Inner /> : <SportScope />;
}

/** Without a league the player database still works: pick which imported data set to browse. */
function SportScope() {
  const { data: sports, error, loading } = useApiData<SportInfo[]>("/sports");
  const [code, setCode] = React.useState("");
  if (error) return <ErrorBox message={error} />;
  if (loading || !sports) return <Spinner />;
  const available = sports.filter((x) => x.available);
  if (!available.length) {
    return (
      <>
        <PageHeader title="Players" />
        <Card><div className="space-y-2 text-sm text-ink2">
          <p className="font-medium text-ink">No player data has been imported yet.</p>
          <p>An administrator needs to set <code>BALLDONTLIE_API_KEY</code> in <code>.env</code> and run <code>npm run sync</code> (or use the sync controls on the <Link className="text-teal hover:underline" href="/admin">Data Admin</Link> page).</p>
          <p className="text-ink3">The simulated demo players are only available when <code>FLASK_DEMO_DATA=true</code>.</p>
        </div></Card>
      </>
    );
  }
  const current = code || available[0].code;
  return <Inner sport={current} sportChoices={available} onSport={setCode} />;
}

function Inner({ sport, sportChoices, onSport }: { sport?: string; sportChoices?: SportInfo[]; onSport?: (c: string) => void } = {}) {
  const { league } = useApp();
  const [q, setQ] = React.useState("");
  const [dq, setDq] = React.useState("");
  const [pos, setPos] = React.useState("");
  const [team, setTeam] = React.useState("");
  const [status, setStatus] = React.useState("all");
  const [sort, setSort] = React.useState("proj");
  const [dir, setDir] = React.useState<"asc" | "desc">("desc");
  const [page, setPage] = React.useState(0);
  const [profile, setProfile] = React.useState<number | null>(null);
  const [adding, setAdding] = React.useState<Player | null>(null);
  const [picked, setPicked] = React.useState<number[]>([]);
  const [comparing, setComparing] = React.useState(false);

  React.useEffect(() => { const t = setTimeout(() => { setDq(q); setPage(0); }, 250); return () => clearTimeout(t); }, [q]);
  const qs = new URLSearchParams({ search: dq, pos, team, status, sort, dir, limit: String(PAGE), offset: String(page * PAGE) }).toString();
  const path = league ? `/leagues/${league.id}/players?${qs}` : `/data/players?sport=${sport}&${qs}`;
  const { data, error, loading, reload } = useApiData<any>(path, [league?.current_day]);

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  const labels: Record<string, string> = data?.stat_labels ?? {};
  const statCols = Object.keys(labels).filter((k) => k !== "min").slice(0, 7);
  const toggleSort = (k: string) => { if (sort === k) setDir(dir === "desc" ? "asc" : "desc"); else { setSort(k); setDir(k === "rank" || k === "name" ? "asc" : "desc"); } setPage(0); };
  const Th = ({ k, children, left }: { k: string; children: React.ReactNode; left?: boolean }) => (
    <th scope="col" aria-sort={sort === k ? (dir === "desc" ? "descending" : "ascending") : "none"} className={cn("whitespace-nowrap p-2 font-medium", left ? "text-left" : "text-right")}>
      <button onClick={() => toggleSort(k)} className={cn("inline-flex items-center gap-0.5 hover:text-ink", sort === k && "text-teal")}>{children}{sort === k && (dir === "desc" ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}</button>
    </th>
  );

  return (
    <>
      <PageHeader title="Players" sub={<>{league ? `Searchable player pool for ${league.name}` : "Player database"} <DataBadge data={data} /></>}
        action={<Button variant={picked.length >= 2 ? "primary" : "outline"} disabled={picked.length < 2} onClick={() => setComparing(true)}><GitCompare className="h-4 w-4" />Compare ({picked.length}/4)</Button>} />
      <Card pad={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-52 flex-1"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink3" /><Input aria-label="Search players" className="pl-8" placeholder="Search players…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
          {sportChoices && sportChoices.length > 1 && (
            <Select aria-label="Data set" value={sport} onChange={(e) => { onSport?.(e.target.value); setPage(0); }}>
              {sportChoices.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select>)}
          <Select aria-label="Position" value={pos} onChange={(e) => { setPos(e.target.value); setPage(0); }}><option value="">All positions</option>{(data?.positions ?? []).map((p: string) => <option key={p}>{p}</option>)}</Select>
          <Select aria-label="Pro team" value={team} onChange={(e) => { setTeam(e.target.value); setPage(0); }}><option value="">All teams</option>{(data?.teams ?? []).map((t: any) => <option key={t.abbr} value={t.abbr}>{t.abbr} · {t.name}</option>)}</Select>
          <Select aria-label="Availability" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
            {league ? <><option value="all">All players</option><option value="available">Free agents</option><option value="owned">Owned</option><option value="mine">My players</option></> : <option value="all">All players</option>}</Select>
        </div>
        {loading && !data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[920px] text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-ink3"><tr className="border-b border-line">
                <th className="w-8 p-2"><span className="sr-only">Compare</span></th>
                <Th k="name" left>Player</Th><Th k="age">Age</Th>
                <Th k="games_week">G/wk</Th><Th k="gp">GP</Th><Th k="fpg">FP/G</Th><Th k="last5">L5</Th><Th k="proj">Proj</Th>
                {statCols.map((k) => <Th key={k} k={`avg.${k}`}>{labels[k]}</Th>)}
                <th className="p-2 text-right font-medium">Trend</th><th className="p-2 text-left font-medium">Owner</th><th className="w-10" />
              </tr></thead>
              <tbody>
                {data?.players.map((p: Player) => (
                  <tr key={p.id} className="border-b border-line/60 hover:bg-panel2/60">
                    <td className="p-2"><input type="checkbox" aria-label={`Compare ${p.name}`} checked={picked.includes(p.id)} disabled={!picked.includes(p.id) && picked.length >= 4}
                      onChange={(e) => setPicked(e.target.checked ? [...picked, p.id] : picked.filter((x) => x !== p.id))} className="accent-teal" /></td>
                    <td className="p-2"><button className="text-left font-medium hover:text-teal" onClick={() => setProfile(p.id)}>{p.name}</button>
                      <div className="flex items-center text-[11px] text-ink3"><PosBadge positions={p.positions} /><span className="mx-1">·</span>{p.team}<InjuryBadge status={p.injury} /></div></td>
                    <td className="num p-2 text-right text-ink2">{p.age ?? "-"}</td>
                    <td className="num p-2 text-right text-ink2">{p.games_week}</td>
                    <td className="num p-2 text-right text-ink2">{p.gp}</td>
                    <td className="num p-2 text-right">{fmt(p.fpg)}</td>
                    <td className="num p-2 text-right">{fmt(p.last5)}</td>
                    <td className="num p-2 text-right font-semibold text-teal">{p.proj.toFixed(1)}</td>
                    {statCols.map((k) => <td key={k} className="num p-2 text-right text-ink2">{p.avg[k]?.toFixed(1) ?? "-"}</td>)}
                    <td className="p-2 text-right"><Sparkline values={p.recent} /></td>
                    <td className="p-2 text-xs">{!league ? <span className="text-ink3">-</span> : p.owner_team ? <span className="text-ink2">{p.owner_team}</span> : <Badge tone="good">FA</Badge>}</td>
                    <td className="p-2">{league && p.available && league.status === "active" && <Button size="sm" aria-label={`Add ${p.name}`} onClick={() => setAdding(p)}><Plus className="h-3 w-3" /></Button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!data?.players.length && <Empty>{data?.empty ? "No players have been imported for this data set yet." : "No players match these filters."}</Empty>}
          </div>
        )}
        <div className="flex items-center justify-between p-3 text-xs text-ink3">
          <span>{data ? `${data.total} players` : ""}</span>
          <div className="flex gap-2"><Button size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
            <Button size="sm" disabled={!data || (page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Next</Button></div>
        </div>
      </Card>
      <PlayerProfile id={profile} onClose={() => setProfile(null)} sport={league ? undefined : sport} />
      <AddPlayerModal player={adding} onClose={() => setAdding(null)} onDone={reload} />
      <CompareModal ids={comparing ? picked : null} onClose={() => setComparing(false)} labels={labels} />
    </>
  );
}

function CompareModal({ ids, onClose, labels }: { ids: number[] | null; onClose: () => void; labels: Record<string, string> }) {
  const { league } = useApp();
  const [players, setPlayers] = React.useState<Player[] | null>(null);
  React.useEffect(() => { setPlayers(null); if (ids && league) api<any>(`/leagues/${league.id}/compare?ids=${ids.join(",")}`).then((d) => setPlayers(d.players)); }, [ids, league]);
  const rows: [string, (p: Player) => number, number][] = [
    ["Projection (FP/G)", (p) => p.proj, 1], ["Season FP/G", (p) => p.fpg ?? 0, 1], ["Last 5 FP/G", (p) => p.last5 ?? 0, 1], ["Total FP", (p) => p.total, 0], ["Games played", (p) => p.gp, 0],
    ["Games this week", (p) => p.games_week, 0], ...Object.entries(labels).map(([k, l]) => [l, (p: Player) => p.avg[k] ?? 0, 1] as [string, (p: Player) => number, number]),
  ];
  return (
    <Modal open={ids !== null} onOpenChange={(o) => !o && onClose()} title="Player comparison" wide>
      {!players ? <Spinner /> : (
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line"><th className="p-2 text-left text-xs text-ink3">Stat</th>{players.map((p) => <th key={p.id} className="p-2 text-right"><div className="font-semibold">{p.name}</div><div className="text-[11px] font-normal text-ink3">{p.positions.replace(",", "/")} · {p.team}</div></th>)}</tr></thead>
          <tbody>{rows.map(([label, f, d]) => {
            const vals = players.map(f); const best = label.startsWith("TO") ? Math.min(...vals) : Math.max(...vals);
            return <tr key={label} className="border-b border-line/50"><td className="p-2 text-ink2">{label}</td>{vals.map((v, i) => <td key={i} className={cn("num p-2 text-right", v === best && "font-semibold text-teal")}>{v.toFixed(d)}</td>)}</tr>;
          })}</tbody>
        </table>
      )}
      <p className="mt-3 text-xs text-ink3">Best value in each row is highlighted. All statistics are simulated.</p>
    </Modal>
  );
}


/** Where the displayed statistics come from, from the API response itself (works without a league). */
function DataBadge({ data }: { data: { data_source?: string; as_of_day?: number } | null }) {
  if (!data?.data_source) return null;
  if (data.data_source === "demo") return <SimBadge force text="Simulated statistics" />;
  if (data.data_source === "mock") return <SimBadge force text="MOCK data - not real NBA statistics" />;
  return <Badge tone="teal">Real NBA data · BALLDONTLIE</Badge>;
}

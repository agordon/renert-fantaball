"use client";
import * as React from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { useApp } from "@/lib/league-context";
import { useAction } from "@/lib/use-action";
import { fmt } from "@/lib/utils";
import type { Player } from "@/lib/types";
import type { GameLogEntry, RuleSetInfo } from "@/lib/api-types";
import { Badge, Button, InjuryBadge, Modal, PosBadge, DataBadge, Select, Spinner } from "@/components/ui";

const tip = { background: "#1a2028", border: "1px solid #252d38", borderRadius: 6, fontSize: 12 };

interface Profile {
  player: Player;
  game_log: GameLogEntry[];
  upcoming: { day: number; date: string | null; opponent: string; home: boolean }[];
  stat_labels: Record<string, string>;
  rulesets: RuleSetInfo[];
  ruleset_id: number;
}

/**
 * Player profile. Opened from a league it starts with that league's scoring rules (and shows ownership);
 * with `sport` it works without any league. The "Scoring" menu re-scores the game log under any stored rule set.
 */
export function PlayerProfile({ id, onClose, sport }: { id: number | null; onClose: () => void; sport?: string; labels?: Record<string, string> }) {
  const { league } = useApp();
  const [d, setD] = React.useState<Profile | { error: string } | null>(null);
  const [rulesetId, setRulesetId] = React.useState<number | null>(null);
  const fromLeague = !sport && !!league && rulesetId === null;

  React.useEffect(() => { setRulesetId(null); }, [id]);
  React.useEffect(() => {
    setD(null);
    if (!id) return;
    const path = fromLeague ? `/leagues/${league!.id}/players/${id}` : `/data/players/${id}${rulesetId ? `?ruleset_id=${rulesetId}` : ""}`;
    api<Profile>(path).then(setD).catch((e: Error) => setD({ error: e.message }));
  }, [id, league, rulesetId, fromLeague]);

  const ok = d && !("error" in d) ? d : null;
  const p = ok?.player;
  const labels = ok?.stat_labels ?? {};
  const scored = ok ? ok.game_log.filter((g) => g.fp !== null) : [];
  return (
    <Modal open={id !== null} onOpenChange={(o) => !o && onClose()} title={p ? p.name : "Player"} wide>
      {!d ? <Spinner /> : "error" in d ? <p className="text-bad">{d.error}</p> : p && ok && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-ink2">
            <PosBadge positions={p.positions} /><span>{p.team_name}</span>{p.age != null && <span>· age {p.age}</span>}
            {p.height && <span>· {p.height}{p.weight ? `, ${p.weight} lb` : ""}</span>}
            <InjuryBadge status={p.injury} note={p.injury_note} />
            <DataBadge source={p.data_source} />
            <span className="ml-auto">{league && fromLeague ? (p.owner_team ? <Badge tone="blue">Owned by {p.owner_team}</Badge> : <Badge tone="good">Free agent</Badge>) : null}</span>
          </div>
          <label className="flex items-center gap-2 text-xs text-ink3">Scoring
            <Select aria-label="Scoring rules" value={ok.ruleset_id} onChange={(e) => setRulesetId(Number(e.target.value))}>
              {ok.rulesets.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </Select>
            <span>Fantasy points below use these weights.</span>
          </label>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[["Fantasy pts", p.gp ? p.total.toFixed(0) : "-"], ["FP / game", fmt(p.fpg)], ["Last 5", fmt(p.last5)], ["Projection", p.proj.toFixed(1)], ["Games", p.gp]].map(([l, v]) => (
              <div key={l as string} className="rounded-md border border-line bg-panel2 p-2.5"><div className="text-[11px] text-ink3">{l}</div><div className="num text-lg font-semibold">{v}</div></div>
            ))}
          </div>
          {p.gp === 0 && <p className="text-sm text-ink3">No game statistics have been imported for this player yet.</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">
            {Object.entries(labels).map(([k, l]) => <span key={k}>{l} <b className="num text-ink">{p.avg[k] !== undefined ? p.avg[k].toFixed(1) : "-"}</b></span>)}
          </div>
          {scored.length > 1 && (
            <div className="h-40" role="img" aria-label="Fantasy points per game">
              <ResponsiveContainer>
                <AreaChart data={[...scored].reverse()} margin={{ left: -15, right: 4 }}>
                  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} /><stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="#252d38" vertical={false} />
                  <XAxis dataKey="day" stroke="#7b8694" fontSize={11} tickLine={false} tickFormatter={(x) => `D${x}`} />
                  <YAxis stroke="#7b8694" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={tip} labelFormatter={(x) => `Day ${x}`} formatter={(v) => [Number(v).toFixed(1), "Fantasy pts"]} />
                  <Area dataKey="fp" stroke="#2dd4bf" strokeWidth={2} fill="url(#g)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink3">Upcoming · {ok.upcoming.length} games in 7 days</h3>
            <div className="flex flex-wrap gap-1">{ok.upcoming.map((g, i) => <Badge key={i}>{g.date ? g.date.slice(5) : `D${g.day}`} {g.home ? "vs" : "@"} {g.opponent}</Badge>)}{!ok.upcoming.length && <span className="text-xs text-ink3">No games scheduled.</span>}</div>
          </div>
          {ok.game_log.length > 0 && (
            <div className="max-h-48 overflow-y-auto rounded-md border border-line">
              <table className="w-full text-xs"><thead className="sticky top-0 bg-panel2 text-ink3"><tr><th className="p-1.5 text-left">Game</th>{Object.values(labels).map((l) => <th key={l} className="p-1.5 text-right">{l}</th>)}<th className="p-1.5 text-right">FP</th></tr></thead>
                <tbody>{ok.game_log.map((g) => (
                  <tr key={g.day} className="border-t border-line"><td className="p-1.5">{g.date ? g.date.slice(5) : `D${g.day}`}{g.opponent ? ` ${g.home ? "vs" : "@"} ${g.opponent}` : ""}</td>
                    {Object.keys(labels).map((k) => <td key={k} className="num p-1.5 text-right">{g.stats[k] ?? <span title="not reported by the data provider" className="text-ink3">-</span>}</td>)}
                    <td className="num p-1.5 text-right font-medium text-teal">{g.fp === null ? <span title="a needed stat was not reported, so this game is not scored" className="text-ink3">n/a</span> : g.fp.toFixed(1)}</td></tr>))}</tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/** Add a free agent; if the roster is full the user picks who to drop. */
export function AddPlayerModal({ player, onClose, onDone }: { player: Player | null; onClose: () => void; onDone: () => void }) {
  const { league, reload } = useApp();
  const [roster, setRoster] = React.useState<Player[] | null>(null);
  const [capacity, setCapacity] = React.useState(0);
  const [drop, setDrop] = React.useState<number | "">("");
  const { busy, error, run, setError } = useAction();
  React.useEffect(() => {
    setRoster(null); setDrop(""); setError(null);
    if (player && league) api<{ players: Player[]; slots: string[] }>(`/leagues/${league.id}/team`).then((t) => { setRoster(t.players); setCapacity(t.slots.length); });
  }, [player, league, setError]);
  const full = roster ? roster.length >= capacity : false;
  const submit = () => run(async () => {
    await api(`/leagues/${league!.id}/add-drop`, { method: "POST", body: { add_id: player!.id, drop_id: drop === "" ? null : drop } });
    await reload(); onDone(); onClose();
  });
  return (
    <Modal open={player !== null} onOpenChange={(o) => !o && onClose()} title={player ? `Add ${player.name}` : ""}>
      {!roster ? <Spinner /> : (
        <div className="space-y-3">
          <p className="text-sm text-ink2">{full ? "Your roster is full. Choose a player to drop." : "You have an open roster spot. You may also drop a player (optional)."}</p>
          <select aria-label="Player to drop" value={drop} onChange={(e) => setDrop(e.target.value ? Number(e.target.value) : "")} className="h-9 w-full rounded-md border border-line bg-panel2 px-2 text-sm">
            <option value="">{full ? "Select a player to drop…" : "Don't drop anyone"}</option>
            {[...roster].sort((a, b) => a.proj - b.proj).map((r) => <option key={r.id} value={r.id}>{r.name} ({r.positions.replace(",", "/")}) · proj {r.proj.toFixed(1)}</option>)}
          </select>
          {error && <p role="alert" className="text-sm text-bad">{error}</p>}
          <div className="flex justify-end gap-2"><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={busy || (full && drop === "")} onClick={submit}>Confirm</Button></div>
        </div>
      )}
    </Modal>
  );
}

"use client";
import * as React from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { useApp } from "@/lib/league-context";
import { useAction } from "@/lib/use-action";
import type { Player } from "@/lib/types";
import { Badge, Button, InjuryBadge, Modal, PosBadge, SimBadge, Spinner } from "@/components/ui";

 
const tip = { background: "#1a2028", border: "1px solid #252d38", borderRadius: 6, fontSize: 12 };

export function PlayerProfile({ id, onClose, labels }: { id: number | null; onClose: () => void; labels: Record<string, string> }) {
  const { league } = useApp();
  const [d, setD] = React.useState<any>(null);
  React.useEffect(() => {
    setD(null);
    if (id && league) api(`/leagues/${league.id}/players/${id}`).then(setD).catch(() => setD({ error: true }));
  }, [id, league]);
  const p: Player | undefined = d?.player;
  return (
    <Modal open={id !== null} onOpenChange={(o) => !o && onClose()} title={p ? p.name : "Player"} wide>
      {!d ? <Spinner /> : d.error ? <p className="text-bad">Could not load player.</p> : p && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-ink2">
            <PosBadge positions={p.positions} /><span>{p.team_name}</span><span>· age {p.age}</span><span>· preseason rank #{p.rank}</span><InjuryBadge status={p.injury} note={p.injury_note} />
            <SimBadge />
            <span className="ml-auto">{p.owner_team ? <Badge tone="blue">Owned by {p.owner_team}</Badge> : <Badge tone="good">Free agent</Badge>}</span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {[["Fantasy pts", p.total.toFixed(0)], ["FP / game", p.fpg.toFixed(1)], ["Last 5", p.last5.toFixed(1)], ["Projection", p.proj.toFixed(1)], ["Games", p.gp]].map(([l, v]) => (
              <div key={l as string} className="rounded-md border border-line bg-panel2 p-2.5"><div className="text-[11px] text-ink3">{l}</div><div className="num text-lg font-semibold">{v}</div></div>
            ))}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2">
            {Object.entries(labels).map(([k, l]) => <span key={k}>{l} <b className="num text-ink">{p.avg[k]?.toFixed(1) ?? "-"}</b></span>)}
          </div>
          {d.game_log.length > 1 && (
            <div className="h-40" role="img" aria-label="Fantasy points per game over the season">
              <ResponsiveContainer>
                <AreaChart data={[...d.game_log].reverse()} margin={{ left: -15, right: 4 }}>
                  <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2dd4bf" stopOpacity={0.35} /><stop offset="100%" stopColor="#2dd4bf" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid stroke="#252d38" vertical={false} />
                  <XAxis dataKey="day" stroke="#7b8694" fontSize={11} tickLine={false} tickFormatter={(x) => `D${x}`} />
                  <YAxis stroke="#7b8694" fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={tip} labelFormatter={(x) => `Day ${x}`} formatter={(v: any) => [Number(v).toFixed(1), "Fantasy pts"]} />
                  <Area dataKey="fp" stroke="#2dd4bf" strokeWidth={2} fill="url(#g)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
          <div>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink3">Next 7 days · {d.upcoming.length} games</h3>
            <div className="flex flex-wrap gap-1">{d.upcoming.map((g: any, i: number) => <Badge key={i}>D{g.day} {g.home ? "vs" : "@"} {g.opponent}</Badge>)}{!d.upcoming.length && <span className="text-xs text-ink3">No games scheduled.</span>}</div>
          </div>
          <div className="max-h-48 overflow-y-auto rounded-md border border-line">
            <table className="w-full text-xs"><thead className="sticky top-0 bg-panel2 text-ink3"><tr><th className="p-1.5 text-left">Day</th>{Object.values(labels).map((l) => <th key={l} className="p-1.5 text-right">{l}</th>)}<th className="p-1.5 text-right">FP</th></tr></thead>
              <tbody>{d.game_log.map((g: any) => <tr key={g.day} className="border-t border-line"><td className="p-1.5">{g.day}</td>{Object.keys(labels).map((k) => <td key={k} className="num p-1.5 text-right">{g.stats[k] ?? 0}</td>)}<td className="num p-1.5 text-right font-medium text-teal">{g.fp.toFixed(1)}</td></tr>)}</tbody>
            </table>
          </div>
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
    if (player && league) api<any>(`/leagues/${league.id}/team`).then((t) => { setRoster(t.players); setCapacity(t.slots.length); });
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

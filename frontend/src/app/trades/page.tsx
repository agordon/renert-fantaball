"use client";
import * as React from "react";
import { ArrowLeftRight, Check, X } from "lucide-react";
import { api } from "@/lib/api";
import { useApp, useLeagueData } from "@/lib/league-context";
import { useAction } from "@/lib/use-action";
import { Badge, Button, Card, Empty, ErrorBox, Modal, PageHeader, Segmented, Select, SimBadge, Spinner } from "@/components/ui";
import { NeedLeague } from "@/components/shell";
import { cn } from "@/lib/utils";

 
export default function TradesPage() {
  return <NeedLeague><Inner /></NeedLeague>;
}

function Inner() {
  const { league, reload } = useApp();
  const [tab, setTab] = React.useState<"machine" | "offers" | "history">("machine");
  const trades = useLeagueData<any>(league?.status === "active" ? "/trades" : null);
  const act = useAction();
  const [evalOffer, setEvalOffer] = React.useState<any>(null);
  if (league?.status !== "active") return <><PageHeader title="Trades" /><Card><p className="text-sm text-ink3">Trading opens after the draft.</p></Card></>;

  const respond = (id: number, what: "accept" | "decline") => act.run(async () => { await api(`/leagues/${league.id}/trades/${id}/${what}`, { method: "POST", body: {} }); await trades.reload(); await reload(); });
  const pendingCount = trades.data?.pending.filter((o: any) => o.incoming).length ?? 0;

  return (
    <>
      <PageHeader title="Trades" sub={<>Trade machine, offers and history <SimBadge /></>}
        action={<Segmented label="Trades view" value={tab} onChange={setTab} options={[{ value: "machine", label: "Trade machine" }, { value: "offers", label: `Offers${pendingCount ? ` (${pendingCount})` : ""}` }, { value: "history", label: "Completed" }]} />} />
      {act.error && <div className="mb-3"><ErrorBox message={act.error} /></div>}
      {tab === "machine" && <Machine onSent={() => { trades.reload(); }} />}
      {tab === "offers" && (trades.loading && !trades.data ? <Spinner /> : (
        <div className="space-y-3">
          {!trades.data?.pending.length && <Card><Empty>No pending offers.</Empty></Card>}
          {trades.data?.pending.map((o: any) => (
            <Card key={o.id}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm"><span><b>{o.from_team}</b> → <b>{o.to_team}</b></span>{o.incoming ? <Badge tone="amber">Incoming</Badge> : <Badge>Sent by you</Badge>}</div>
              <OfferSides o={o} />
              {o.note && <p className="mt-2 text-xs text-ink3">“{o.note}”</p>}
              <div className="mt-3 flex gap-2">
                {o.incoming ? <>
                  <Button size="sm" onClick={() => setEvalOffer(o)}>Evaluate</Button>
                  <Button size="sm" variant="primary" disabled={act.busy} onClick={() => respond(o.id, "accept")}><Check className="h-3 w-3" />Accept</Button>
                  <Button size="sm" variant="danger" disabled={act.busy} onClick={() => respond(o.id, "decline")}><X className="h-3 w-3" />Decline</Button></>
                  : <Button size="sm" variant="danger" disabled={act.busy} onClick={() => respond(o.id, "decline")}>Cancel offer</Button>}
              </div>
            </Card>))}
        </div>))}
      {tab === "history" && (
        <div className="space-y-3">
          {!trades.data?.completed.length && <Card><Empty>No completed trades yet.</Empty></Card>}
          {trades.data?.completed.map((o: any) => <Card key={o.id}><div className="text-sm"><b>{o.from_team}</b> ⇄ <b>{o.to_team}</b></div><OfferSides o={o} /></Card>)}
          {trades.data?.other.length > 0 && <Card title="Declined / cancelled"><ul className="space-y-1 text-sm text-ink3">{trades.data.other.map((o: any) => <li key={o.id}>{o.from_team} → {o.to_team}: {o.status}{o.response_note ? ` (${o.response_note})` : ""}</li>)}</ul></Card>}
        </div>)}
      <Modal open={!!evalOffer} onOpenChange={(o) => !o && setEvalOffer(null)} title="Evaluate this offer" wide>
        {evalOffer && <EvalOffer o={evalOffer} />}
      </Modal>
    </>
  );
}

function OfferSides({ o }: { o: any }) {
  const list = (ps: any[]) => <ul className="mt-1 space-y-0.5">{ps.map((p) => <li key={p.id} className="text-sm">{p.name} <span className="text-[11px] text-ink3">{p.positions.replace(",", "/")} · {p.team}</span></li>)}</ul>;
  return <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-start gap-3"><div><div className="text-[11px] uppercase tracking-wider text-ink3">{o.from_team} sends</div>{list(o.sends)}</div><ArrowLeftRight className="mt-4 h-4 w-4 text-ink3" /><div><div className="text-[11px] uppercase tracking-wider text-ink3">{o.to_team} sends</div>{list(o.receives)}</div></div>;
}

function EvalOffer({ o }: { o: any }) {
  const { league } = useApp();
  const [a, setA] = React.useState<any>(null);
  const [err, setErr] = React.useState<string | null>(null);
  React.useEffect(() => {
    // I am the recipient: I give what the proposer asked for ("receives") and get what they send
    api(`/leagues/${league!.id}/trades/analyze`, { method: "POST", body: { to_team_id: o.from_team_id, give_ids: o.receives.map((p: any) => p.id), get_ids: o.sends.map((p: any) => p.id) } }).then(setA).catch((e) => setErr(e.message));
  }, [o, league]);
  return err ? <ErrorBox message={err} /> : a ? <Analysis a={a} /> : <Spinner />;
}

function Machine({ onSent }: { onSent: () => void }) {
  const { league, reload } = useApp();
  const { data: info } = useLeagueData<any>("");
  const [partner, setPartner] = React.useState<number | "">("");
  const [mine, setMine] = React.useState<any[]>([]);
  const [theirs, setTheirs] = React.useState<any[]>([]);
  const [give, setGive] = React.useState<number[]>([]);
  const [get, setGet] = React.useState<number[]>([]);
  const [analysis, setAnalysis] = React.useState<any>(null);
  const [note, setNote] = React.useState("");
  const [result, setResult] = React.useState<any>(null);
  const act = useAction();
  const lid = league!.id;

  React.useEffect(() => { api<any>(`/leagues/${lid}/team`).then((t) => setMine(t.players)); }, [lid, league?.current_day]);
  React.useEffect(() => {
    setGive([]); setGet([]); setAnalysis(null); setResult(null);
    if (partner) api<any>(`/leagues/${lid}/team?team_id=${partner}`).then((t) => setTheirs(t.players)); else setTheirs([]);
  }, [partner, lid]);
  React.useEffect(() => {
    setAnalysis(null);
    if (!partner || !give.length || !get.length) return;
    const t = setTimeout(() => act.run(async () => setAnalysis(await api(`/leagues/${lid}/trades/analyze`, { method: "POST", body: { to_team_id: partner, give_ids: give, get_ids: get } }))), 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partner, give, get]);

  const toggle = (list: number[], set: (x: number[]) => void, id: number) => set(list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  const send = () => act.run(async () => { setResult(await api(`/leagues/${lid}/trades`, { method: "POST", body: { to_team_id: partner, give_ids: give, get_ids: get, note } })); setGive([]); setGet([]); setNote(""); onSent(); await reload(); });
  const col = (title: string, ps: any[], sel: number[], set: (x: number[]) => void) => (
    <Card title={title} pad={false}>
      <ul className="max-h-80 divide-y divide-line/60 overflow-y-auto">{ps.map((p) => (
        <li key={p.id}><label className={cn("flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-panel2", sel.includes(p.id) && "bg-teal/10")}>
          <input type="checkbox" className="accent-teal" checked={sel.includes(p.id)} onChange={() => toggle(sel, set, p.id)} />
          <span className="flex-1">{p.name}<span className="ml-1 text-[11px] text-ink3">{p.positions.replace(",", "/")} · {p.team}</span>{p.injury !== "HEALTHY" && <Badge tone="amber" className="ml-1.5">{p.injury}</Badge>}</span>
          <span className="num text-xs text-ink2">{p.proj.toFixed(1)}</span></label></li>))}</ul>
    </Card>);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3"><label className="text-xs text-ink3">Trade partner
        <Select aria-label="Trade partner" value={partner} onChange={(e) => setPartner(e.target.value ? Number(e.target.value) : "")} className="ml-2">
          <option value="">Choose a team…</option>{(info?.teams ?? []).filter((t: any) => !t.is_me).map((t: any) => <option key={t.id} value={t.id}>{t.name}{t.is_bot ? " (computer)" : ` · ${t.manager}`}</option>)}</Select></label>
        <span className="text-xs text-ink3">Select players on both sides (number = projected fantasy points per game).</span></div>
      {result && <div className={cn("rounded-md border p-3 text-sm", result.ai_response ? (result.ai_response.accepted ? "border-good/40 bg-good/10 text-good" : "border-amber/40 bg-amber/10 text-amber") : "border-teal/40 bg-teal/10 text-teal")}>
        {result.ai_response ? (result.ai_response.accepted ? "Trade accepted! Rosters have been updated." : `Declined by the computer manager: ${result.ai_response.reason}`) : "Offer sent. The other manager can accept or decline it."}</div>}
      {act.error && <ErrorBox message={act.error} />}
      <div className="grid gap-4 lg:grid-cols-2">{col("You send", mine, give, setGive)}{partner ? col("You receive", theirs, get, setGet) : <Card title="You receive"><Empty>Choose a trade partner first.</Empty></Card>}</div>
      {analysis && (<>
        <Analysis a={analysis} />
        <Card><div className="flex flex-wrap items-center gap-2"><input aria-label="Message" value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} placeholder="Optional message to the other manager" className="h-9 flex-1 rounded-md border border-line bg-panel2 px-3 text-sm focus:border-teal focus:outline-none" />
          <Button variant="primary" disabled={act.busy} onClick={send}>Send trade proposal</Button></div></Card></>)}
    </div>
  );
}

function Delta({ v, unit = "" }: { v: number; unit?: string }) {
  return <span className={cn("num font-semibold", v > 0 ? "text-good" : v < 0 ? "text-bad" : "text-ink3")}>{v > 0 ? "+" : ""}{v.toFixed(1)}{unit}</span>;
}

function Analysis({ a }: { a: any }) {
  const sides = [a.team_a, a.team_b];
  return (
    <Card title="Trade impact simulator" action={<Badge tone="blue">Estimate</Badge>}>
      <p className="mb-3 text-sm font-medium">{a.verdict}</p>
      <div className="grid gap-3 md:grid-cols-2">
        {sides.map((s: any) => (
          <div key={s.team_id} className="rounded-md border border-line bg-panel2 p-3">
            <div className="mb-2 font-medium">{s.name}</div>
            <dl className="grid grid-cols-3 gap-2 text-center text-xs text-ink3">
              <div><dt>Weekly pts</dt><dd className="mt-0.5 text-sm"><span className="num text-ink2">{s.before.weekly.toFixed(0)}</span> → <span className="num text-ink">{s.after.weekly.toFixed(0)}</span></dd><dd><Delta v={s.weekly_change} /></dd></div>
              <div><dt>Bench depth</dt><dd className="mt-0.5 text-sm"><span className="num text-ink2">{s.before.bench_depth.toFixed(1)}</span> → <span className="num text-ink">{s.after.bench_depth.toFixed(1)}</span></dd><dd><Delta v={s.depth_change} /></dd></div>
              <div><dt>Players</dt><dd className="num mt-0.5 text-sm">{s.before.n_players} → {s.after.n_players}</dd></div>
            </dl>
            <div className="mt-3 text-[11px] uppercase tracking-wider text-ink3">Best player by position (proj FP/G change)</div>
            <div className="mt-1 grid grid-cols-5 gap-1 text-center text-xs">{Object.entries(s.position_change).map(([p, v]: any) => <div key={p} className="rounded border border-line p-1"><div className="text-ink3">{p}</div><Delta v={v} /></div>)}</div>
            <div className="mt-3 text-[11px] uppercase tracking-wider text-ink3">Starters by position after trade</div>
            <div className="mt-1 flex gap-2 text-xs">{Object.entries(s.after.starters_by_position).map(([p, n]: any) => <span key={p} className={cn("num", s.before.starters_by_position[p] !== n ? "text-amber" : "text-ink2")}>{p} {n}</span>)}</div>
            <ul className="mt-3 space-y-1 text-xs text-ink2">{s.risks.map((r: string, i: number) => <li key={i} className="flex gap-1.5"><span className="text-amber">⚠</span>{r}</li>)}{!s.risks.length && <li className="text-ink3">No notable risks flagged.</li>}</ul>
          </div>))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
        <span>Rest-of-season value: {a.team_a.name} receives <b className="num">{a.value.a_receives}</b> · {a.team_b.name} receives <b className="num">{a.value.b_receives}</b></span>
        <Badge tone={a.ai_would_accept ? "good" : "amber"}>Computer manager would {a.ai_would_accept ? "accept" : "decline"}</Badge>
      </div>
      <p className="mt-3 text-[11px] text-ink3">{a.disclaimer} {a.method} (<code>fantaball/trade_analysis.py</code>)</p>
    </Card>
  );
}

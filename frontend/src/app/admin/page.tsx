"use client";
import * as React from "react";
import { CheckCircle2, CircleAlert, Play, RefreshCw, XCircle } from "lucide-react";
import { useApp } from "@/lib/league-context";
import { useAction } from "@/lib/use-action";
import { getDataStatus, getSyncRuns, startSync, type SyncJob, type SyncRequest } from "@/lib/client";
import type { DataStatus, SyncRun } from "@/lib/api-types";
import { ago, when } from "@/lib/utils";
import { Badge, Button, Card, ErrorBox, Input, PageHeader, Spinner, Stat } from "@/components/ui";

const TONE = { success: "good", partial: "amber", blocked: "bad", failed: "bad", running: "blue" } as const;

const JOBS: { job: SyncJob; label: string; hint: string; needsKey?: boolean }[] = [
  { job: "teams_players", label: "Sync teams", hint: "The 30 NBA teams. Players appear automatically when their box scores are imported." },
  { job: "schedule", label: "Sync full-season schedule", hint: "Every game of the season (a dozen or so requests); also anchors the season calendar." },
  { job: "stats", label: "Import missing box scores", hint: "Only final games whose player stats are missing (about one request per game)." },
  { job: "corrections", label: "Re-check recent corrections", hint: "Re-fetches the last 3 days of box scores and applies official corrections." },
  { job: "scores", label: "Recalculate fantasy scores", hint: "Rebuilds stored fantasy points and league totals from the imported stats (no API calls)." },
  { job: "daily", label: "Run the daily sync", hint: "Everything above in the right order - what the scheduler runs." },
];

export default function AdminPage() {
  const { me } = useApp();
  const [status, setStatus] = React.useState<DataStatus | null>(null);
  const [runs, setRuns] = React.useState<SyncRun[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [range, setRange] = React.useState({ start: "", end: "" });
  const action = useAction();

  const load = React.useCallback(async () => {
    try {
      const st = await getDataStatus();
      setStatus(st);
      if (st.is_admin) setRuns(await getSyncRuns(25));
      setError(null);
    } catch (e) { setError((e as Error).message); }
  }, []);
  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => {                          // poll while a job is running
    if (!status?.running) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [status?.running, load]);

  if (error && !status) return <ErrorBox message={error} onRetry={load} />;
  if (!status) return <Spinner />;
  if (!me?.is_admin && !status.is_admin) {
    return <><PageHeader title="Data Administration" /><Card><p className="text-sm text-ink2">Only administrators can manage data synchronization. Administrators are listed in <code>FLASK_ADMIN_EMAILS</code>.</p></Card></>;
  }

  const start = (req: SyncRequest) => action.run(async () => { await startSync(req); await load(); });
  const c = status.counts;
  const blocked = status.limitations.length > 0;

  return (
    <>
      <PageHeader title="Data Administration" sub="Provider status, data freshness and manual sync controls"
        action={<Button size="sm" onClick={load}><RefreshCw className="h-3.5 w-3.5" />Refresh</Button>} />
      {(error || action.error) && <div className="mb-3"><ErrorBox message={(action.error ?? error)!} /></div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Data provider">
          <ul className="space-y-1.5 text-sm">
            <li className="flex justify-between"><span className="text-ink3">Provider</span><span className="num">{status.provider.provider}</span></li>
            <li className="flex justify-between"><span className="text-ink3">API key</span>
              {status.provider.configured ? <Badge tone="good"><CheckCircle2 className="mr-1 h-3 w-3" />configured</Badge> : <Badge tone="bad"><XCircle className="mr-1 h-3 w-3" />missing</Badge>}</li>
            <li className="flex justify-between"><span className="text-ink3">Pace</span><span className="num">{status.provider.requests_per_minute}/min</span></li>
            {status.provider.daily_quota != null && (
              <li className="flex justify-between"><span className="text-ink3">Requests today</span>
                <span className={`num ${(status.provider.requests_used_today ?? 0) >= status.provider.daily_quota ? "text-bad" : ""}`}>{status.provider.requests_used_today ?? 0} / {status.provider.daily_quota}</span></li>)}
            <li className="flex justify-between"><span className="text-ink3">Season</span><span className="num">{status.season}-{String(status.season + 1).slice(2)}</span></li>
            <li className="flex justify-between"><span className="text-ink3">Data in database</span><span className="num">{status.has_real_data ? status.data_source : "none"}</span></li>
          </ul>
          {status.provider.message && <p className="mt-3 text-xs text-amber">{status.provider.message} Add it to <code>.env</code> as <code>{status.provider.key_variable}=…</code> and restart the backend. The key is never shown here or sent to the browser.</p>}
        </Card>

        <Card title="Data freshness">
          <div className="space-y-3">
            <Stat label="Last successful sync" value={status.last_success ? ago(status.freshness_seconds) : "never"} sub={status.last_success ? `${status.last_success.job} · ${when(status.last_success.finished_at)}` : undefined} />
            <div className="text-sm">
              <div className="text-[11px] uppercase tracking-wider text-ink3">Last attempt</div>
              {status.last_attempt ? <div className="flex items-center gap-2"><Badge tone={TONE[status.last_attempt.status]}>{status.last_attempt.status}</Badge><span className="text-ink2">{status.last_attempt.job} · {when(status.last_attempt.started_at)}</span></div> : <span className="text-ink3">no sync has run yet</span>}
              {status.last_attempt?.error && <p className="mt-1 text-xs text-bad">{status.last_attempt.error}</p>}
            </div>
            {status.running && <Badge tone="blue">A sync is running…</Badge>}
          </div>
        </Card>

        <Card title="Imported data">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="Teams" value={c.teams} /><Stat label="Players" value={c.players} />
            <Stat label="Games" value={c.games} sub={`${c.final_games} final · ${c.upcoming_games} upcoming`} />
            <Stat label="Player box scores" value={c.player_game_stats.toLocaleString()} />
            <Stat label="Fantasy scores" value={c.fantasy_scores.toLocaleString()} />
            <Stat label="Final games w/o stats" value={c.final_games_missing_stats} tone={c.final_games_missing_stats ? "bad" : undefined} />
          </div>
        </Card>
      </div>

      {blocked && (
        <div className="mt-4 rounded-lg border border-amber/40 bg-amber/10 p-4 text-sm" role="note">
          <div className="mb-1 flex items-center gap-2 font-medium text-amber"><CircleAlert className="h-4 w-4" />Provider plan limitation</div>
          {status.limitations.map((l, i) => <p key={i} className="text-ink2">{l}</p>)}
        </div>
      )}
      {status.onboarding && <div className="mt-4"><Card><p className="text-sm text-ink2">{status.onboarding}</p></Card></div>}

      <Card className="mt-4" title="Manual sync">
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {JOBS.map((j) => (
            <div key={j.job} className="rounded-md border border-line bg-panel2 p-3">
              <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{j.label}</span>
                <Button size="sm" variant="primary" disabled={action.busy || status.running || (!status.provider.configured && j.job !== "scores")} onClick={() => start({ job: j.job, season: j.job === "schedule" ? status.season : undefined })}><Play className="h-3 w-3" />Run</Button></div>
              <p className="mt-1 text-xs text-ink3">{j.hint}</p>
            </div>))}
        </div>
        <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); start({ job: "schedule", start: range.start, end: range.end }); }}>
          <label className="text-xs text-ink3">Backfill range - from<Input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} required className="mt-1" /></label>
          <label className="text-xs text-ink3">to<Input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} required className="mt-1" /></label>
          <Button type="submit" disabled={action.busy || status.running || !status.provider.configured}>Sync schedule for range</Button>
          <Button type="button" disabled={action.busy || status.running || !status.provider.configured || !range.start} onClick={() => start({ job: "stats", start: range.start, end: range.end || range.start })}>Re-import box scores for range</Button>
        </form>
        <p className="mt-2 text-xs text-ink3">Jobs run in the background. The free plan allows a limited number of requests per day, so the first import of a season spans a day or two; the page updates by itself. Only one job can run at a time.</p>
      </Card>

      <Card className="mt-4" title="Recent sync runs" pad={false}>
        <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm">
          <thead className="text-[11px] uppercase tracking-wider text-ink3"><tr className="border-b border-line"><th className="p-2 text-left">Started</th><th className="p-2 text-left">Job</th><th className="p-2 text-left">Status</th><th className="p-2 text-right">New</th><th className="p-2 text-right">Updated</th><th className="p-2 text-right">Unchanged</th><th className="p-2 text-right">Requests</th><th className="p-2 text-left">Covered / error</th><th className="p-2 text-left">By</th></tr></thead>
          <tbody>{runs.map((r) => (
            <tr key={r.id} className="border-b border-line/60 align-top">
              <td className="num p-2 text-xs text-ink2">{when(r.started_at)}</td><td className="p-2">{r.job}</td>
              <td className="p-2"><Badge tone={TONE[r.status]}>{r.status}</Badge></td>
              <td className="num p-2 text-right">{r.inserted}</td><td className="num p-2 text-right">{r.updated}</td><td className="num p-2 text-right text-ink3">{r.skipped}</td><td className="num p-2 text-right text-ink3">{r.requests}</td>
              <td className="p-2 text-xs">{r.error ? <span className="text-bad">{r.error}</span> : <span className="text-ink3">{r.marker}</span>}</td>
              <td className="p-2 text-xs text-ink3">{r.triggered_by}</td></tr>))}
          </tbody></table>
          {!runs.length && <p className="p-4 text-sm text-ink3">No sync runs yet.</p>}
        </div>
      </Card>
    </>
  );
}

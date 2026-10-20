"use client";
import * as React from "react";
import { Copy } from "lucide-react";
import { api } from "@/lib/api";
import { useApp, useLeagueData } from "@/lib/league-context";
import { useAction } from "@/lib/use-action";
import { Badge, Button, Card, ErrorBox, Input, PageHeader, Spinner } from "@/components/ui";

 
export default function SettingsPage() {
  const { me, league, reload } = useApp();
  const [name, setName] = React.useState(me?.display_name ?? "");
  const profile = useAction();
  const [saved, setSaved] = React.useState(false);
  return (
    <>
      <PageHeader title="Settings" sub="Profile and league configuration" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Your profile">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); profile.run(async () => { await api("/me", { method: "PATCH", body: { display_name: name } }); await reload(); setSaved(true); }); }}>
            <label className="block text-xs text-ink3">Display name<Input value={name} onChange={(e) => { setName(e.target.value); setSaved(false); }} minLength={2} maxLength={40} className="mt-1" /></label>
            <div className="text-xs text-ink3">Account: <span className="num text-ink2">{me?.email}</span> <Badge>{me?.auth_mode === "demo" ? "Local demo account" : "School sign-in"}</Badge></div>
            {profile.error && <ErrorBox message={profile.error} />}
            <div className="flex items-center gap-3"><Button type="submit" variant="primary" disabled={profile.busy}>Save</Button>{saved && <span className="text-xs text-good">Saved</span>}</div>
            {me?.auth_mode === "sso" && <p className="text-xs text-ink3">Sign-in and sign-out are handled by the school login (OAuth2-Proxy).</p>}
          </form>
        </Card>
        {league ? <LeagueSettings /> : <Card><p className="text-sm text-ink3">Select a league to see its settings.</p></Card>}
      </div>
    </>
  );
}

function LeagueSettings() {
  const { league, reload } = useApp();
  const { data, error, loading, reload: refresh } = useLeagueData<any>("");
  const [rules, setRules] = React.useState<Record<string, number>>({});
  const [teamName, setTeamName] = React.useState("");
  const [leagueName, setLeagueName] = React.useState("");
  const save = useAction();
  React.useEffect(() => { if (data) { setRules(data.scoring_rules); setLeagueName(data.name); setTeamName(data.teams.find((t: any) => t.is_me)?.name ?? ""); } }, [data]);
  if (loading && !data) return <Spinner />;
  if (error) return <ErrorBox message={error} onRetry={refresh} />;
  if (!data || !league) return null;
  const editable = data.is_commissioner && data.status === "pre_draft";
  return (
    <>
      <Card title="League settings">
        <div className="space-y-3 text-sm">
          <label className="block text-xs text-ink3">League name<Input value={leagueName} onChange={(e) => setLeagueName(e.target.value)} disabled={!editable} className="mt-1" /></label>
          <div className="grid grid-cols-2 gap-2 text-ink2"><div>Sport: {data.sport_name}</div><div>Format: Head-to-head points</div><div>Teams: {data.num_teams} ({data.open_seats} open)</div><div>Commissioner: {data.commissioner}</div></div>
          <div className="flex items-center gap-2 rounded-md border border-line bg-panel2 p-2.5"><span className="text-xs text-ink3">Invitation code</span>
            <code className="num flex-1 text-base tracking-widest text-teal">{data.invite_code}</code>
            <Button size="sm" onClick={() => navigator.clipboard?.writeText(data.invite_code)}><Copy className="h-3 w-3" />Copy</Button></div>
          <div><div className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink3">Scoring rules (points per stat)</div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{Object.entries(data.stat_labels).filter(([k]) => k in rules).map(([k, l]) => (
              <label key={k} className="text-xs text-ink3">{l as string}<Input type="number" step="0.1" disabled={!editable} value={rules[k]} onChange={(e) => setRules({ ...rules, [k]: Number(e.target.value) })} className="num mt-1" /></label>))}</div></div>
          <div><div className="mb-1 text-xs font-semibold uppercase tracking-wider text-ink3">Roster</div>
            <div className="flex flex-wrap gap-1">{data.roster_config.map(([s, c]: [string, number]) => <Badge key={s} tone={s === "BN" || s === "IR" ? "neutral" : "teal"}>{c} × {s}</Badge>)}</div></div>
          {save.error && <ErrorBox message={save.error} />}
          {editable ? <Button variant="primary" disabled={save.busy} onClick={() => save.run(async () => { await api(`/leagues/${league.id}`, { method: "PATCH", body: { name: leagueName, scoring_rules: rules } }); await reload(); await refresh(); })}>Save league settings</Button>
            : <p className="text-xs text-ink3">{data.is_commissioner ? "Settings are locked once the draft starts." : "Only the commissioner can change league settings."}</p>}
        </div>
      </Card>
      <Card title="Your team in this league">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); save.run(async () => { await api(`/leagues/${league.id}/team-name`, { method: "PATCH", body: { name: teamName } }); await refresh(); await reload(); }); }}>
          <Input aria-label="Team name" value={teamName} onChange={(e) => setTeamName(e.target.value)} minLength={2} maxLength={40} /><Button type="submit" disabled={save.busy}>Rename</Button>
        </form>
        <h3 className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wider text-ink3">League members</h3>
        <ul className="space-y-1 text-sm">{data.teams.map((t: any) => <li key={t.id} className="flex justify-between"><span className={t.is_me ? "text-teal" : ""}>{t.name}</span><span className="text-ink3">{t.manager}{t.is_bot ? " (computer)" : ""}</span></li>)}</ul>
      </Card>
    </>
  );
}

"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BarChart3, Gavel, LayoutDashboard, LogOut, Menu, Repeat, Settings, Swords, Trophy, Users, UserSquare2, X, Zap, ListOrdered } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApp } from "@/lib/league-context";
import { ErrorBox, Spinner } from "@/components/ui";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/leagues", label: "My Leagues", icon: Trophy },
  { href: "/team", label: "My Team", icon: UserSquare2 },
  { href: "/players", label: "Players", icon: Users },
  { href: "/matchups", label: "Matchups", icon: Swords },
  { href: "/draft", label: "Draft Room", icon: Gavel },
  { href: "/trades", label: "Trades", icon: Repeat },
  { href: "/standings", label: "Standings", icon: ListOrdered },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/activity", label: "League Activity", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NavLinks({ onClick }: { onClick?: () => void }) {
  const path = usePathname();
  return (
    <nav aria-label="Primary" className="flex flex-col gap-0.5 px-2">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href} onClick={onClick} aria-current={active ? "page" : undefined}
            className={cn("flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
              active ? "bg-teal/10 text-teal" : "text-ink2 hover:bg-panel2 hover:text-ink")}>
            <Icon className="h-4 w-4" />{label}
          </Link>
        );
      })}
    </nav>
  );
}

function LeagueSwitcher() {
  const { leagues, league, setLeagueId } = useApp();
  if (!leagues.length) return <Link href="/leagues" className="mx-3 rounded-md border border-dashed border-line px-3 py-2 text-xs text-ink3 hover:text-ink">Create or join a league</Link>;
  return (
    <div className="px-3">
      <label htmlFor="league-switch" className="mb-1 block text-[10px] uppercase tracking-wider text-ink3">League</label>
      <select id="league-switch" value={league?.id ?? ""} onChange={(e) => setLeagueId(Number(e.target.value))}
        className="h-9 w-full rounded-md border border-line bg-panel2 px-2 text-sm focus:border-teal focus:outline-none">
        {leagues.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
      </select>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2 px-5 py-4">
      <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-teal to-blue text-[#04201c]"><Zap className="h-4 w-4" strokeWidth={2.5} /></span>
      <span className="text-lg font-semibold tracking-tight">Fanta<span className="text-teal">Ball</span></span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, league, loading, error, reload } = useApp();
  const [open, setOpen] = React.useState(false);
  const path = usePathname();
  React.useEffect(() => setOpen(false), [path]);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-panel/60 lg:flex">
        <Brand />
        <LeagueSwitcher />
        <div className="mt-4 flex-1 overflow-y-auto"><NavLinks /></div>
        <UserBox me={me} />
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-bg/90 backdrop-blur lg:hidden">
        <Brand />
        <button className="mr-3 rounded p-2 text-ink2 hover:bg-panel2" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>
      {open && (
        <div className="fixed inset-x-0 top-[57px] bottom-0 z-20 overflow-y-auto bg-bg py-3 lg:hidden">
          <LeagueSwitcher /><div className="mt-3"><NavLinks onClick={() => setOpen(false)} /></div><div className="mt-4"><UserBox me={me} /></div>
        </div>
      )}

      <main className="min-w-0 px-4 py-6 lg:px-8">
        <div className="mx-auto max-w-[1280px]">
          {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : <div className="fade-in">{children}</div>}
          {league?.is_demo && <p className="mt-10 text-center text-[11px] text-ink3">All players, schedules and statistics in FantaBall are simulated demo data, not real NBA information.</p>}
        </div>
      </main>
    </div>
  );
}

function UserBox({ me }: { me: ReturnType<typeof useApp>["me"] }) {
  if (!me) return null;
  return (
    <div className="flex items-center gap-2.5 border-t border-line px-4 py-3">
      <div className="grid h-8 w-8 place-items-center rounded-full bg-panel2 text-sm font-semibold text-teal">{me.display_name[0]?.toUpperCase()}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm">{me.display_name}</div>
        <div className="text-[11px] text-ink3">{me.auth_mode === "demo" ? "Demo account" : "Signed in"}</div>
      </div>
      {me.logout_url && <a href={me.logout_url} aria-label="Log out" className="rounded p-1.5 text-ink3 hover:bg-panel2 hover:text-ink"><LogOut className="h-4 w-4" /></a>}
    </div>
  );
}

/** Pages that need a league show this when the user has none selected. */
export function NeedLeague({ children }: { children: React.ReactNode }) {
  const { league } = useApp();
  if (!league) return (
    <div className="rounded-lg border border-dashed border-line p-10 text-center">
      <p className="text-ink2">You are not in a league yet.</p>
      <Link href="/leagues" className="mt-3 inline-block rounded-md bg-teal px-4 py-2 text-sm font-semibold text-[#04201c]">Create or join a league</Link>
    </div>
  );
  return <>{children}</>;
}

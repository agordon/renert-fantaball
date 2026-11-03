"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApiData, useApp } from "@/lib/league-context";
import { useAppearance } from "@/lib/appearance";
import { THEMES, THEME_IDS } from "@/lib/themes";
import type { SportInfo } from "@/lib/api-types";
import { ErrorBox, Spinner } from "@/components/ui";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/team", label: "My Team" },
  { href: "/players", label: "Players" },
  { href: "/matchups", label: "Matchups" },
  { href: "/draft", label: "Draft Room" },
  { href: "/trades", label: "Trades" },
  { href: "/standings", label: "Standings" },
  { href: "/analytics", label: "Analytics" },
  { href: "/activity", label: "Activity" },
  { href: "/leagues", label: "My Leagues" },
  { href: "/settings", label: "Settings" },
];

function NavLinks({ onClick }: { onClick?: () => void }) {
  const path = usePathname();
  const { me } = useApp();
  const items = me?.is_admin ? [...NAV, { href: "/admin", label: "Data Admin" }] : NAV;
  return (
    <nav aria-label="Primary" className="flex flex-col">
      {items.map(({ href, label }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link key={href} href={href} onClick={onClick} aria-current={active ? "page" : undefined}
            className={cn("heading-case border-l-[3px] px-5 py-1.5 font-display text-[16px] font-medium",
              active ? "border-accent bg-panel2 text-ink" : "border-transparent text-ink2 hover:bg-panel2/60 hover:text-ink")}>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function LeagueSwitcher() {
  const { leagues, league, setLeagueId } = useApp();
  if (!leagues.length) return <Link href="/leagues" className="mx-5 block border border-dashed border-line px-3 py-2 text-xs text-ink3 hover:text-ink">Create or join a league</Link>;
  return (
    <div className="px-5">
      <label htmlFor="league-switch" className="mb-1 block text-xs text-ink3">League</label>
      <select id="league-switch" value={league?.id ?? ""} onChange={(e) => setLeagueId(Number(e.target.value))}
        className="h-9 w-full rounded-md border border-line bg-panel2 px-2 text-sm focus:border-accent focus:outline-none">
        {leagues.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
      </select>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="block px-5 py-5 font-display text-[28px] font-bold leading-none tracking-wide">
      FANTA<span className="text-accent">BALL</span>
    </Link>
  );
}

function ThemeSwitcher() {
  const { appearance, update } = useAppearance();
  return (
    <div className="px-5 pb-3">
      <label htmlFor="theme-switch" className="mb-1 block text-xs text-ink3">Theme</label>
      <select id="theme-switch" value={appearance.theme} onChange={(e) => update({ theme: e.target.value as typeof appearance.theme })}
        className="h-8 w-full rounded-md border border-line bg-panel2 px-2 text-sm focus:border-accent focus:outline-none">
        <option value="system">Match my device</option>
        {THEME_IDS.map((id) => <option key={id} value={id}>{THEMES[id].name}</option>)}
      </select>
      <Link href="/settings" className="mt-1 inline-block text-xs text-ink3 hover:text-ink hover:underline">More appearance options</Link>
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const { me, loading, error, reload } = useApp();
  const [open, setOpen] = React.useState(false);
  const path = usePathname();
  React.useEffect(() => setOpen(false), [path]);

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[224px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col border-r border-line bg-panel lg:flex">
        <Brand />
        <LeagueSwitcher />
        <div className="mt-5 flex-1 overflow-y-auto"><NavLinks /></div>
        <ThemeSwitcher />
        <UserBox me={me} />
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-panel lg:hidden">
        <Brand />
        <button className="mr-3 rounded p-2 text-ink2 hover:bg-panel2" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>
      {open && (
        <div className="fixed inset-x-0 bottom-0 top-[68px] z-20 overflow-y-auto bg-panel py-3 lg:hidden">
          <LeagueSwitcher /><div className="mt-4"><NavLinks onClick={() => setOpen(false)} /></div><div className="mt-4"><ThemeSwitcher /><UserBox me={me} /></div>
        </div>
      )}

      <main className="min-w-0 px-4 py-6 lg:px-8">
        <div className="mx-auto max-w-[1280px]">
          {loading ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : children}
        </div>
      </main>
    </div>
  );
}

function UserBox({ me }: { me: ReturnType<typeof useApp>["me"] }) {
  if (!me) return null;
  return (
    <div className="flex items-center gap-2.5 border-t border-line px-5 py-3">
      <div className="grid h-8 w-8 place-items-center bg-ink font-display text-lg font-semibold text-bg">{me.display_name[0]?.toUpperCase()}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{me.display_name}</div>
        <div className="text-xs text-ink3">{me.auth_mode === "local" ? "Local login" : "Signed in"}</div>
      </div>
      {me.logout_url && <a href={me.logout_url} aria-label="Log out" className="rounded p-1.5 text-ink3 hover:bg-panel2 hover:text-ink"><LogOut className="h-4 w-4" /></a>}
    </div>
  );
}

/** Pages that need a league show this when the user has none selected. */
export function NeedLeague({ children }: { children: React.ReactNode }) {
  const { league } = useApp();
  const { data: sports } = useApiData<SportInfo[]>(league ? null : "/sports");
  const noData = !!sports && !sports.some((s) => s.available);
  if (!league) return (
    <div className="border border-dashed border-line p-10 text-center">
      <p className="text-ink2">You are not in a league yet.</p>
      {noData && <p className="mx-auto mt-2 max-w-xl text-sm text-amber">No player data has been imported yet, so a league cannot be created. Set your data-provider API key in <code>.env</code> and run <code>npm run sync</code> (administrators can also use the Data Admin page).</p>}
      <Link href="/leagues" className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-sm font-semibold text-on-accent">Create or join a league</Link>
    </div>
  );
  return <>{children}</>;
}

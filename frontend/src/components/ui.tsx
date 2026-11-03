"use client";
import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useApp } from "@/lib/league-context";

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "outline" | "danger"; size?: "sm" | "md" };
export function Button({ className, variant = "outline", size = "md", ...p }: BtnProps) {
  const v = {
    primary: "bg-accent text-on-accent font-semibold hover:brightness-110",
    ghost: "text-ink2 hover:bg-panel2 hover:text-ink",
    outline: "border border-line bg-panel text-ink hover:border-ink3",
    danger: "border border-bad text-bad hover:bg-bad/10",
  }[variant];
  return <button className={cn("inline-flex items-center justify-center gap-1.5 rounded-md font-medium disabled:pointer-events-none disabled:opacity-40",
    size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-4 text-sm", v, className)} {...p} />;
}

/** A boxed section with a ruled title bar, like a box score in a newspaper. */
export function Card({ className, children, title, action, pad = true }: { className?: string; children: React.ReactNode; title?: React.ReactNode; action?: React.ReactNode; pad?: boolean }) {
  return (
    <section className={cn("rounded-md border border-line bg-panel", className)}>
      {(title || action) && (
        <header className="flex items-baseline justify-between gap-3 border-b border-line px-4 py-2">
          <h2 className="heading-case font-display text-[15px] font-semibold text-ink">{title}</h2>{action}
        </header>
      )}
      <div className={pad ? "px-4 py-3" : ""}>{children}</div>
    </section>
  );
}

export function Badge({ children, tone = "neutral", className, title }: { children: React.ReactNode; tone?: "neutral" | "teal" | "blue" | "amber" | "bad" | "good"; className?: string; title?: string }) {
  const t = { neutral: "border-line text-ink2", teal: "border-accent text-accent", blue: "border-blue text-blue",
    amber: "border-amber text-amber", bad: "border-bad text-bad", good: "border-good text-good" }[tone];
  return <span title={title} className={cn("inline-flex items-center rounded-sm border px-1.5 py-px text-[11px] font-medium leading-4", t, className)}>{children}</span>;
}

export const PosBadge = ({ positions }: { positions: string }) => <span className="num text-[11px] text-ink3">{positions.replace(",", "/")}</span>;
export function InjuryBadge({ status, note }: { status: string; note?: string | null }) {
  if (status === "HEALTHY") return null;
  return <Badge tone={status === "OUT" ? "bad" : "amber"} className="ml-1.5">{status}{note ? ` · ${note}` : ""}</Badge>;
}

/** A big scoreboard-style figure with its label underneath. */
export function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "good" | "bad" }) {
  return (
    <div>
      <div className={cn("big-num text-[40px] font-semibold leading-none", tone === "good" && "text-good", tone === "bad" && "text-bad")}>{value}</div>
      <div className="mt-1 text-xs font-medium text-ink2">{label}</div>
      {sub && <div className="text-xs text-ink3">{sub}</div>}
    </div>
  );
}

export function PageHeader({ title, sub, action }: { title: string; sub?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 border-b-2 border-ink pb-3">
      <div>
        <h1 className="heading-case font-display text-[34px] font-semibold leading-none">{title}</h1>
        {sub && <p className="mt-1.5 text-sm text-ink3">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export const Spinner = ({ label = "Loading" }: { label?: string }) => (
  <div role="status" className="flex items-center gap-2 py-10 text-sm text-ink3"><Loader2 className="h-4 w-4 animate-spin" />{label}…</div>
);

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-bad bg-bad/10 p-3 text-sm text-bad">
      <div className="flex-1">{message}</div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

/** Names where the numbers come from (taken from the league, or passed explicitly). Used sparingly. */
export function DataBadge({ source }: { source?: string | null }) {
  const { league } = useApp();
  if (!(source ?? league?.data_source)) return null;
  return <Badge tone="neutral">Real NBA data</Badge>;
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("h-9 w-full rounded-md border border-line bg-panel2 px-3 text-sm placeholder:text-ink3 focus:border-accent focus:outline-none", className)} {...p} />
));
Input.displayName = "Input";

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-9 rounded-md border border-line bg-panel2 px-2.5 text-sm focus:border-accent focus:outline-none", className)} {...p}>{children}</select>;
}

/** Underlined tabs. */
export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex border-b border-line">
      {options.map((o) => (
        <button key={o.value} aria-pressed={o.value === value} onClick={() => onChange(o.value)}
          className={cn("-mb-px border-b-2 px-3 py-1.5 text-sm", o.value === value ? "border-accent font-semibold text-ink" : "border-transparent text-ink3 hover:text-ink")}>{o.label}</button>
      ))}
    </div>
  );
}

export function Modal({ open, onOpenChange, title, children, wide }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <DialogPrimitive.Content aria-describedby={undefined} className={cn("fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[94vw] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-md border border-line bg-panel p-5", wide ? "max-w-3xl" : "max-w-lg")}>
          <div className="mb-3 flex items-center justify-between border-b border-line pb-2">
            <DialogPrimitive.Title className="font-display text-xl font-semibold">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="rounded p-1 text-ink3 hover:bg-panel2 hover:text-ink" aria-label="Close"><X className="h-4 w-4" /></DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Sparkline({ values, w = 72, h = 22, color = "var(--accent)" }: { values: number[]; w?: number; h?: number; color?: string }) {
  if (values.length < 2) return <span className="text-ink3">-</span>;
  const min = Math.min(...values), max = Math.max(...values), r = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * (w - 4) + 2},${h - 3 - ((v - min) / r) * (h - 6)}`);
  const last = pts[pts.length - 1].split(",");
  return <svg width={w} height={h} role="img" aria-label={`Last ${values.length} games: ${values.map((v) => Math.round(v)).join(", ")}`}>
    <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    <circle cx={last[0]} cy={last[1]} r={2.25} fill={color} />
  </svg>;
}

export const Empty = ({ children }: { children: React.ReactNode }) => <div className="py-8 text-center text-sm text-ink3">{children}</div>;

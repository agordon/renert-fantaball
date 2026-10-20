"use client";
import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Loader2, X, AlertTriangle, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "outline" | "danger"; size?: "sm" | "md" };
export function Button({ className, variant = "outline", size = "md", ...p }: BtnProps) {
  const v = {
    primary: "bg-teal text-[#04201c] hover:bg-[#5eead4] font-semibold",
    ghost: "text-ink2 hover:bg-panel2 hover:text-ink",
    outline: "border border-line bg-panel hover:bg-panel2 text-ink",
    danger: "border border-bad/40 text-bad hover:bg-bad/10",
  }[variant];
  return <button className={cn("inline-flex items-center justify-center gap-1.5 rounded-md transition-colors disabled:opacity-40 disabled:pointer-events-none",
    size === "sm" ? "h-7 px-2.5 text-xs" : "h-9 px-3.5 text-sm", v, className)} {...p} />;
}

export function Card({ className, children, title, action, pad = true }: { className?: string; children: React.ReactNode; title?: React.ReactNode; action?: React.ReactNode; pad?: boolean }) {
  return (
    <section className={cn("rounded-lg border border-line bg-panel", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between px-4 pt-3 pb-2">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink3">{title}</h2>{action}
        </header>
      )}
      <div className={pad ? "px-4 pb-4 pt-1" : ""}>{children}</div>
    </section>
  );
}

export function Badge({ children, tone = "neutral", className, title }: { children: React.ReactNode; tone?: "neutral" | "teal" | "blue" | "amber" | "bad" | "good"; className?: string; title?: string }) {
  const t = { neutral: "bg-panel2 text-ink2 border-line", teal: "bg-teal/10 text-teal border-teal/30", blue: "bg-blue/10 text-blue border-blue/30",
    amber: "bg-amber/10 text-amber border-amber/30", bad: "bg-bad/10 text-bad border-bad/30", good: "bg-good/10 text-good border-good/30" }[tone];
  return <span title={title} className={cn("inline-flex items-center rounded border px-1.5 py-0.5 text-[11px] font-medium leading-none", t, className)}>{children}</span>;
}

export const PosBadge = ({ positions }: { positions: string }) => <span className="num text-[11px] text-ink3">{positions.replace(",", "/")}</span>;
export function InjuryBadge({ status, note }: { status: string; note?: string | null }) {
  if (status === "HEALTHY") return null;
  return <Badge tone={status === "OUT" ? "bad" : "amber"} className="ml-1.5">{status}{note ? ` · ${note}` : ""}</Badge>;
}

export function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "good" | "bad" }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-ink3">{label}</div>
      <div className={cn("num text-2xl font-semibold", tone === "good" && "text-good", tone === "bad" && "text-bad")}>{value}</div>
      {sub && <div className="text-xs text-ink3">{sub}</div>}
    </div>
  );
}

export function PageHeader({ title, sub, action }: { title: string; sub?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold tracking-tight">{title}</h1>{sub && <p className="mt-0.5 text-sm text-ink3">{sub}</p>}</div>
      {action}
    </div>
  );
}

export const Spinner = ({ label = "Loading" }: { label?: string }) => (
  <div role="status" className="flex items-center gap-2 py-10 text-sm text-ink3"><Loader2 className="h-4 w-4 animate-spin" />{label}…</div>
);

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start gap-2 rounded-md border border-bad/40 bg-bad/10 p-3 text-sm text-bad">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /><div className="flex-1">{message}</div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export const SimBadge = ({ text = "Simulated demo data" }: { text?: string }) => (
  <span className="inline-flex items-center gap-1 rounded border border-amber/30 bg-amber/10 px-1.5 py-0.5 text-[11px] text-amber"><FlaskConical className="h-3 w-3" />{text}</span>
);

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn("h-9 w-full rounded-md border border-line bg-panel2 px-3 text-sm placeholder:text-ink3 focus:border-teal focus:outline-none", className)} {...p} />
));
Input.displayName = "Input";

export function Select({ className, children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("h-9 rounded-md border border-line bg-panel2 px-2.5 text-sm focus:border-teal focus:outline-none", className)} {...p}>{children}</select>;
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-line bg-panel p-0.5">
      {options.map((o) => (
        <button key={o.value} aria-pressed={o.value === value} onClick={() => onChange(o.value)}
          className={cn("rounded px-3 py-1 text-xs transition-colors", o.value === value ? "bg-panel2 text-teal" : "text-ink3 hover:text-ink")}>{o.label}</button>
      ))}
    </div>
  );
}

export function Modal({ open, onOpenChange, title, children, wide }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <DialogPrimitive.Content aria-describedby={undefined} className={cn("fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[94vw] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-line bg-panel p-5 fade-in", wide ? "max-w-3xl" : "max-w-lg")}>
          <div className="mb-3 flex items-center justify-between">
            <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close className="rounded p-1 text-ink3 hover:bg-panel2 hover:text-ink" aria-label="Close"><X className="h-4 w-4" /></DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Sparkline({ values, w = 72, h = 22, color = "var(--teal)" }: { values: number[]; w?: number; h?: number; color?: string }) {
  if (values.length < 2) return <span className="text-ink3">-</span>;
  const min = Math.min(...values), max = Math.max(...values), r = max - min || 1;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * (w - 4) + 2},${h - 3 - ((v - min) / r) * (h - 6)}`);
  const last = pts[pts.length - 1].split(",");
  return <svg width={w} height={h} role="img" aria-label={`Last ${values.length} games: ${values.map((v) => Math.round(v)).join(", ")}`}>
    <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
    <circle cx={last[0]} cy={last[1]} r={2.5} fill={color} />
  </svg>;
}

export const Empty = ({ children }: { children: React.ReactNode }) => <div className="py-8 text-center text-sm text-ink3">{children}</div>;

"use client";
import * as React from "react";
import { Check } from "lucide-react";
import { useAppearance } from "@/lib/appearance";
import { THEMES, THEME_IDS, resolveTheme, type Density, type Heading, type Radius, type ThemeId } from "@/lib/themes";
import { cn } from "@/lib/utils";
import { Button, Card, Segmented } from "@/components/ui";

const ACCENTS = ["#e9803d", "#e5484d", "#f5a524", "#c8d84a", "#3ddc84", "#2dd4bf", "#38bdf8", "#5b8def", "#a98bff", "#e879c6", "#f2f2f2"];

function Preview({ id }: { id: ThemeId }) {
  const v = THEMES[id].vars;
  return (
    <span aria-hidden className="block overflow-hidden border" style={{ background: v.bg, borderColor: v.line }}>
      <span className="flex h-3 items-center gap-1 px-1.5" style={{ background: v.panel, borderBottom: `1px solid ${v.line}` }}>
        <span className="h-1 w-5" style={{ background: v.accent }} /><span className="h-1 w-3" style={{ background: v.ink3 }} />
      </span>
      <span className="block space-y-1 p-1.5">
        <span className="block h-1.5 w-3/4" style={{ background: v.ink }} />
        <span className="block h-1 w-1/2" style={{ background: v.ink3 }} />
        <span className="flex gap-1 pt-0.5"><span className="h-2.5 w-6" style={{ background: v.accent }} /><span className="h-2.5 w-5" style={{ background: v.panel2, border: `1px solid ${v.line}` }} /></span>
      </span>
    </span>
  );
}

export function AppearancePanel() {
  const { appearance, update, reset } = useAppearance();
  const active = resolveTheme(appearance);
  return (
    <Card title="Appearance" action={<Button size="sm" variant="ghost" onClick={reset}>Reset to default</Button>}>
      <div className="space-y-5">
        <div>
          <div className="mb-2 text-sm font-medium">Theme</div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
            {THEME_IDS.map((id) => (
              <button key={id} aria-pressed={appearance.theme === id} onClick={() => update({ theme: id })}
                className={cn("space-y-1.5 border p-2 text-left", appearance.theme === id ? "border-accent" : "border-line hover:border-ink3")}>
                <Preview id={id} />
                <span className="flex items-center justify-between text-sm font-medium">{THEMES[id].name}{appearance.theme === id && <Check className="h-3.5 w-3.5 text-accent" />}</span>
                <span className="block text-xs text-ink3">{THEMES[id].note}</span>
              </button>
            ))}
            <button aria-pressed={appearance.theme === "system"} onClick={() => update({ theme: "system" })}
              className={cn("space-y-1.5 border p-2 text-left", appearance.theme === "system" ? "border-accent" : "border-line hover:border-ink3")}>
              <span className="grid grid-cols-2"><Preview id="hardwood" /><Preview id="daylight" /></span>
              <span className="flex items-center justify-between text-sm font-medium">Match my device{appearance.theme === "system" && <Check className="h-3.5 w-3.5 text-accent" />}</span>
              <span className="block text-xs text-ink3">Dark or light, following your system (now: {THEMES[active].name})</span>
            </button>
          </div>
        </div>

        <div>
          <div className="mb-2 text-sm font-medium">Accent colour</div>
          <div className="flex flex-wrap items-center gap-2">
            <button aria-pressed={appearance.accent === null} onClick={() => update({ accent: null })}
              className={cn("h-8 border px-2.5 text-xs", appearance.accent === null ? "border-accent text-ink" : "border-line text-ink3 hover:text-ink")}>Theme default</button>
            {ACCENTS.map((c) => (
              <button key={c} aria-label={`Accent ${c}`} aria-pressed={appearance.accent === c} onClick={() => update({ accent: c })}
                className={cn("h-8 w-8 border-2", appearance.accent === c ? "border-ink" : "border-transparent hover:border-ink3")} style={{ background: c }} />
            ))}
            <label className="ml-1 flex items-center gap-2 text-xs text-ink3">Custom
              <input type="color" aria-label="Custom accent colour" value={appearance.accent ?? THEMES[active].vars.accent} onChange={(e) => update({ accent: e.target.value })} className="h-8 w-10 cursor-pointer border border-line bg-transparent p-0" />
            </label>
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-3">
          <div>
            <div className="mb-1 text-sm font-medium">Corners</div>
            <Segmented<Radius> label="Corner style" value={appearance.radius} onChange={(radius) => update({ radius })}
              options={[{ value: "sharp", label: "Square" }, { value: "standard", label: "Standard" }, { value: "round", label: "Round" }]} />
          </div>
          <div>
            <div className="mb-1 text-sm font-medium">Density</div>
            <Segmented<Density> label="Density" value={appearance.density} onChange={(density) => update({ density })}
              options={[{ value: "comfortable", label: "Comfortable" }, { value: "compact", label: "Compact" }]} />
          </div>
          <div>
            <div className="mb-1 text-sm font-medium">Headings</div>
            <Segmented<Heading> label="Heading font" value={appearance.heading} onChange={(heading) => update({ heading })}
              options={[{ value: "condensed", label: "Condensed" }, { value: "serif", label: "Serif" }, { value: "sans", label: "Plain" }]} />
          </div>
        </div>
        <p className="text-xs text-ink3">Saved in this browser only. Changes apply immediately.</p>
      </div>
    </Card>
  );
}

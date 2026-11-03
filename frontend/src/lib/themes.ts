/**
 * Appearance system: ONE source of truth for every theme and option.
 * Themes are sets of CSS variables applied to <html> (see applyAppearance); the same data feeds the picker previews and
 * the tiny boot script that runs before first paint (so there is no flash of the wrong theme).
 */
export type ThemeId =
  | "hardwood" | "midnight" | "newsprint" | "daylight" | "terminal" | "ocean" | "sunset" | "forest" | "royal" | "contrast";

export interface Theme {
  name: string;
  note: string;
  scheme: "dark" | "light";
  vars: {
    bg: string; panel: string; panel2: string; line: string; ink: string; ink2: string; ink3: string;
    accent: string; onAccent: string; blue: string; amber: string; violet: string; good: string; bad: string;
  };
}

export const THEMES: Record<ThemeId, Theme> = {
  hardwood: {
    name: "Hardwood", note: "Warm charcoal with basketball orange (default)", scheme: "dark",
    vars: { bg: "#15110e", panel: "#1d1814", panel2: "#262019", line: "#3a3027", ink: "#f2e8dc", ink2: "#c4b6a5", ink3: "#8e8071",
            accent: "#e9803d", onAccent: "#1a0f06", blue: "#6aa5e8", amber: "#e3b341", violet: "#b494e6", good: "#7cc47a", bad: "#e8685f" },
  },
  midnight: {
    name: "Midnight", note: "Cool near-black with teal", scheme: "dark",
    vars: { bg: "#0d1014", panel: "#141920", panel2: "#1a2028", line: "#252d38", ink: "#e8edf3", ink2: "#aab4c0", ink3: "#7b8694",
            accent: "#2dd4bf", onAccent: "#04201c", blue: "#4f8cff", amber: "#f59e0b", violet: "#a78bfa", good: "#34d399", bad: "#f87171" },
  },
  newsprint: {
    name: "Newsprint", note: "Cream paper and red ink, like a sports page", scheme: "light",
    vars: { bg: "#f1ebdf", panel: "#faf6ec", panel2: "#ede6d6", line: "#d2c8b2", ink: "#1d1a15", ink2: "#4a443a", ink3: "#7a7262",
            accent: "#b3261e", onAccent: "#ffffff", blue: "#1f5f9e", amber: "#a86a00", violet: "#6b4a9e", good: "#2f7d3a", bad: "#b3261e" },
  },
  daylight: {
    name: "Daylight", note: "Clean light with a blue accent", scheme: "light",
    vars: { bg: "#f3f5f8", panel: "#ffffff", panel2: "#eef1f5", line: "#d9dee5", ink: "#12171d", ink2: "#46505c", ink3: "#78828f",
            accent: "#2457d6", onAccent: "#ffffff", blue: "#2457d6", amber: "#b26a00", violet: "#6d4fc2", good: "#1f8a4c", bad: "#c93a31" },
  },
  terminal: {
    name: "Terminal", note: "Phosphor green on black", scheme: "dark",
    vars: { bg: "#050805", panel: "#0a100a", panel2: "#101a10", line: "#1d3320", ink: "#c8f2c8", ink2: "#8fc58f", ink3: "#5b8a5b",
            accent: "#3df56a", onAccent: "#031505", blue: "#5ad1e6", amber: "#e6c84a", violet: "#b58be6", good: "#3df56a", bad: "#ff6b5e" },
  },
  ocean: {
    name: "Ocean", note: "Deep navy with sky blue", scheme: "dark",
    vars: { bg: "#08131d", panel: "#0d1c2b", panel2: "#132738", line: "#1f3a52", ink: "#e2eff9", ink2: "#a6c0d4", ink3: "#6f8da4",
            accent: "#3ab6f0", onAccent: "#04121c", blue: "#5b9dff", amber: "#f2b640", violet: "#a58bf0", good: "#43d49a", bad: "#f2766b" },
  },
  sunset: {
    name: "Sunset", note: "Plum dusk with coral", scheme: "dark",
    vars: { bg: "#19101f", panel: "#221629", panel2: "#2c1d35", line: "#432c4e", ink: "#f6e8f0", ink2: "#cdb0c4", ink3: "#977e90",
            accent: "#ff7b5c", onAccent: "#240a04", blue: "#7fa6ff", amber: "#ffc15a", violet: "#c79aff", good: "#7ed6a0", bad: "#ff6f7d" },
  },
  forest: {
    name: "Forest", note: "Deep green with moss", scheme: "dark",
    vars: { bg: "#0d1511", panel: "#131e18", panel2: "#1a2820", line: "#29402f", ink: "#e3efe6", ink2: "#a7c0ad", ink3: "#6f8c78",
            accent: "#93d467", onAccent: "#0b1a05", blue: "#69b3e0", amber: "#e3b84a", violet: "#b49be0", good: "#93d467", bad: "#e8776a" },
  },
  royal: {
    name: "Royal", note: "Indigo night with violet", scheme: "dark",
    vars: { bg: "#110e1e", panel: "#191530", panel2: "#211c3d", line: "#342d5c", ink: "#ece9fa", ink2: "#b4aedb", ink3: "#7f78a8",
            accent: "#a98bff", onAccent: "#150a33", blue: "#6f9bff", amber: "#f0b955", violet: "#a98bff", good: "#6fd6a0", bad: "#f27a86" },
  },
  contrast: {
    name: "High contrast", note: "Black, white and yellow - maximum legibility", scheme: "dark",
    vars: { bg: "#000000", panel: "#0b0b0b", panel2: "#161616", line: "#8a8a8a", ink: "#ffffff", ink2: "#e6e6e6", ink3: "#bdbdbd",
            accent: "#ffd400", onAccent: "#000000", blue: "#6db6ff", amber: "#ffb000", violet: "#d0a8ff", good: "#4dff88", bad: "#ff6b6b" },
  },
};

export const THEME_IDS = Object.keys(THEMES) as ThemeId[];
export type Radius = "sharp" | "standard" | "round";
export type Density = "comfortable" | "compact";
export type Heading = "condensed" | "serif" | "sans";

export interface Appearance {
  theme: ThemeId | "system";
  accent: string | null;          // custom accent override (#rrggbb) or null = the theme's own
  radius: Radius;
  density: Density;
  heading: Heading;
}

export const DEFAULT_APPEARANCE: Appearance = { theme: "hardwood", accent: null, radius: "standard", density: "comfortable", heading: "condensed" };
export const STORAGE_KEY = "fb.appearance";
const HEX = /^#[0-9a-fA-F]{6}$/;
const RADII: Record<Radius, string> = { sharp: "0px", standard: "4px", round: "12px" };

/** Black or white text, whichever reads better on `hex`. */
export function readableOn(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? "#111111" : "#ffffff";
}

export function resolveTheme(a: Appearance): ThemeId {
  if (a.theme !== "system") return a.theme;
  const dark = typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  return dark ? "hardwood" : "daylight";
}

/** Sanitise whatever was stored (it is user-editable) before using it. */
export function cleanAppearance(raw: unknown): Appearance {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    theme: o.theme === "system" || (typeof o.theme === "string" && o.theme in THEMES) ? (o.theme as Appearance["theme"]) : DEFAULT_APPEARANCE.theme,
    accent: typeof o.accent === "string" && HEX.test(o.accent) ? o.accent : null,
    radius: o.radius === "sharp" || o.radius === "round" ? o.radius : "standard",
    density: o.density === "compact" ? "compact" : "comfortable",
    heading: o.heading === "serif" || o.heading === "sans" ? o.heading : "condensed",
  };
}

export function applyAppearance(a: Appearance, el: HTMLElement = document.documentElement) {
  const id = resolveTheme(a);
  const t = THEMES[id];
  const v = t.vars;
  const accent = a.accent ?? v.accent;
  const set = (k: string, val: string) => el.style.setProperty(k, val);
  set("--bg", v.bg); set("--panel", v.panel); set("--panel-2", v.panel2); set("--line", v.line);
  set("--ink", v.ink); set("--ink-2", v.ink2); set("--ink-3", v.ink3);
  set("--accent", accent); set("--on-accent", a.accent ? readableOn(a.accent) : v.onAccent);
  set("--blue", v.blue); set("--amber", v.amber); set("--violet", v.violet); set("--good", v.good); set("--bad", v.bad);
  set("--r", RADII[a.radius]);
  el.dataset.theme = id;
  el.dataset.density = a.density;
  el.dataset.heading = a.heading;
  el.style.colorScheme = t.scheme;
}

/** Runs before first paint (inlined in <head>): reads the saved choice and applies it, so the page never flashes the wrong theme. */
export function bootScript(): string {
  return `(function(){try{
var T=${JSON.stringify(Object.fromEntries(THEME_IDS.map((k) => [k, { s: THEMES[k].scheme, v: THEMES[k].vars }])))};
var R=${JSON.stringify(RADII)};
var a=JSON.parse(localStorage.getItem(${JSON.stringify(STORAGE_KEY)})||"{}");
var id=a.theme;
if(id==="system"){id=matchMedia("(prefers-color-scheme: dark)").matches?"hardwood":"daylight"}
if(!T[id])id="hardwood";
var v=T[id].v,e=document.documentElement,s=e.style,ac=/^#[0-9a-fA-F]{6}$/.test(a.accent||"")?a.accent:null;
function lum(h){var c=[1,3,5].map(function(i){var x=parseInt(h.substr(i,2),16)/255;return x<=0.03928?x/12.92:Math.pow((x+0.055)/1.055,2.4)});return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]}
s.setProperty("--bg",v.bg);s.setProperty("--panel",v.panel);s.setProperty("--panel-2",v.panel2);s.setProperty("--line",v.line);
s.setProperty("--ink",v.ink);s.setProperty("--ink-2",v.ink2);s.setProperty("--ink-3",v.ink3);
s.setProperty("--accent",ac||v.accent);s.setProperty("--on-accent",ac?(lum(ac)>0.4?"#111111":"#ffffff"):v.onAccent);
s.setProperty("--blue",v.blue);s.setProperty("--amber",v.amber);s.setProperty("--violet",v.violet);s.setProperty("--good",v.good);s.setProperty("--bad",v.bad);
s.setProperty("--r",R[a.radius]||R.standard);
e.dataset.theme=id;e.dataset.density=a.density==="compact"?"compact":"comfortable";e.dataset.heading=a.heading==="serif"||a.heading==="sans"?a.heading:"condensed";
s.colorScheme=T[id].s;
}catch(x){}})();`;
}

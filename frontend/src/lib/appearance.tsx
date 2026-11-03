"use client";
import * as React from "react";
import { DEFAULT_APPEARANCE, STORAGE_KEY, applyAppearance, cleanAppearance, type Appearance } from "@/lib/themes";

interface Ctx { appearance: Appearance; update: (patch: Partial<Appearance>) => void; reset: () => void }
const C = React.createContext<Ctx>({ appearance: DEFAULT_APPEARANCE, update: () => {}, reset: () => {} });
export const useAppearance = () => React.useContext(C);

/** Keeps the choice in localStorage and re-applies it to <html> (the boot script already did the first paint). */
export function AppearanceProvider({ children }: { children: React.ReactNode }) {
  const [appearance, setAppearance] = React.useState<Appearance>(DEFAULT_APPEARANCE);

  React.useEffect(() => {
    let saved: unknown = {};
    try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch { /* ignore a corrupt value */ }
    setAppearance(cleanAppearance(saved));
  }, []);

  React.useEffect(() => {          // "system" follows the operating system while the app is open
    if (appearance.theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => applyAppearance(appearance);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [appearance]);

  const save = (next: Appearance) => {
    setAppearance(next);
    applyAppearance(next);
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch { /* storage may be blocked */ }
  };
  const update = (patch: Partial<Appearance>) => save(cleanAppearance({ ...appearance, ...patch }));
  const reset = () => save(DEFAULT_APPEARANCE);
  return <C.Provider value={{ appearance, update, reset }}>{children}</C.Provider>;
}

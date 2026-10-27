import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...i: ClassValue[]) => twMerge(clsx(i));
export const fmt = (n: number | null | undefined, d = 1) => (n == null ? "-" : n.toFixed(d));

/** "3 min ago" style age from seconds. */
export function ago(seconds: number | null | undefined): string {
  if (seconds == null) return "never";
  if (seconds < 90) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

export const when = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString() : "-");

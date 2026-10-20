import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...i: ClassValue[]) => twMerge(clsx(i));
export const fmt = (n: number | null | undefined, d = 1) => (n == null ? "-" : n.toFixed(d));

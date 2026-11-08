"use client";
import { useApp } from "@/lib/league-context";

/** Real leagues are scored automatically after each data sync, up to the last day whose box scores are imported. */
export function ScoredThrough() {
  const { league } = useApp();
  if (!league || league.status !== "active") return null;
  return <span className="text-xs text-ink3">Scored through {league.scored_through ?? "the start of the season"} · updates after each data sync</span>;
}

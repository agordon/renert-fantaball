/** Typed API client functions (thin wrappers over `api`). The browser never sees or sends the provider API key. */
import { api } from "@/lib/api";
import type { DataStatus, RuleSetInfo, SportInfo, SyncRun } from "@/lib/api-types";

export type SyncJob = "teams_players" | "schedule" | "stats" | "corrections" | "scores" | "daily";

export const getDataStatus = () => api<DataStatus>("/data/status");
export const getSports = () => api<SportInfo[]>("/sports");
export const getSyncRuns = (limit = 30) => api<SyncRun[]>(`/data/runs?limit=${limit}`);
export const getRuleSets = (sport: string) => api<RuleSetInfo[]>(`/data/rulesets?sport=${encodeURIComponent(sport)}`);

export interface SyncRequest { job: SyncJob; season?: number; start?: string; end?: string; days?: number }
/** Starts a job (the server runs it in the background and answers 202). Poll getDataStatus() for the result. */
export const startSync = (req: SyncRequest) => api<{ accepted: boolean; job: string } | SyncRun>("/admin/sync", { method: "POST", body: req });

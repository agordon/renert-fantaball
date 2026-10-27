/** Typed shapes of the Flask API responses used by the data / admin / player pages. */

export type DataSource = "demo" | "balldontlie" | "mock";

export interface SyncRun {
  id: number;
  provider: string;
  job: string;
  status: "running" | "success" | "partial" | "failed" | "blocked";
  started_at: string | null;
  finished_at: string | null;
  inserted: number;
  updated: number;
  skipped: number;
  requests: number;
  marker: string | null;
  error: string | null;
  triggered_by: string | null;
  steps?: { name: string; status: string; note?: string; error?: string }[] | null;
}

export interface DataStatus {
  provider: { provider: string; configured: boolean; is_mock: boolean; requests_per_minute: number; demo_data: boolean; message: string | null };
  data_source: string;
  season: number;
  season_start: string | null;
  today: string;
  counts: {
    teams: number; players: number; games: number; final_games: number; upcoming_games: number;
    final_games_missing_stats: number; player_game_stats: number; fantasy_scores: number;
  };
  last_success: SyncRun | null;
  last_attempt: SyncRun | null;
  last_by_job: Record<string, SyncRun>;
  failures: SyncRun[];
  freshness_seconds: number | null;
  running: boolean;
  limitations: string[];
  has_real_data: boolean;
  demo_data_enabled: boolean;
  is_admin: boolean;
  onboarding: string | null;
}

export interface SportInfo {
  code: string;
  name: string;
  positions: string[];
  stats: Record<string, string>;
  default_scoring: Record<string, number>;
  roster: [string, number][];
  playable: boolean;
  players: number;
  available: boolean;
  data_source: DataSource | null;
  season: number | null;
}

export interface RuleSetInfo { id: number; name: string; rules: Record<string, number>; is_template?: boolean }

export interface GameLogEntry {
  day: number;
  date: string | null;
  opponent?: string;
  home?: boolean;
  stats: Record<string, number | null>;
  fp: number | null;          // null = a stat the rules need was not reported, so the game cannot be scored
}

export interface UpcomingProGame {
  day: number;
  date: string | null;
  starts_at: string | null;
  status: string;
  home: string;
  away: string;
}

export interface RecentPerformance {
  athlete_id: number;
  name: string;
  team: string;
  positions: string;
  day: number;
  fp: number;
  line: Record<string, number | null>;
}

export interface DataBlock {
  source: DataSource;
  simulated: boolean;
  season: number | null;
  last_sync: string | null;
  stats_as_of: string | null;
  scored_through: string | null;
}

export type Me = { id: number; email: string; display_name: string; auth_mode: "local" | "sso"; logout_url: string | null; is_admin: boolean };
export type LeagueSummary = {
  id: number; name: string; sport: string; sport_name: string; num_teams: number; status: "pre_draft" | "drafting" | "active";
  current_day: number; current_week: number; season_days: number; season_weeks: number; is_commissioner: boolean;
  data_source: string; season: number | null; scored_through: string | null;
  my_team_id: number; record?: { wins: number; losses: number; ties: number; rank: number; pf: number; team_name: string } | null; members?: number;
};
export type Player = {
  id: number; name: string; positions: string; team: string; team_name: string; age: number | null; rank: number; injury: string; injury_note: string | null;
  gp: number; avg: Record<string, number>; total: number; fpg: number | null; last5: number | null; proj: number; owner_team_id: number | null; owner_team: string | null;
  available: boolean; data_source?: string; height?: string | null; weight?: string | null; games_week: number; games_left_week: number; recent: number[]; slot?: string;
};
export type TeamInfo = { id: number; name: string; manager: string; is_bot: boolean; is_me: boolean; draft_slot: number | null };

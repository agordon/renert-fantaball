# FantaBall roadmap

## Done
**Fantasy platform (Phases 1-4 of the first build):** leagues, snake draft with computer managers + strategy assistant, lineups with position
rules, add/drop, trades + impact simulator, matchups, standings/power rankings, Fantasy GM, What-If (lineup swap), Next.js UI for every page.

**Database-driven real data (this milestone)**
- Alembic migrations (baseline 0001 + 0002); legacy databases are stamped and upgraded; `people` table untouched.
- Schema for provider teams/players/games/box scores (typed, nullable stats, unique player+game), scoring rule sets,
  persisted fantasy scores, team period scores, sync runs, roster acquisition history.
- `NBADataProvider` interface; `HighlightlyProvider` (default; free plan with player box scores, quota-aware) and `BallDontLieProvider` (alternative); shared client with timeouts, pacing, backoff, 401/403/429/5xx handling;
  an offline fixture provider used by the automated tests only.
- Idempotent ingestion jobs: teams+players, schedule, box scores (missing only), corrections, score recalculation, daily job, CLI
  commands, scheduler files (systemd timer, cron script, Windows task), one-running-job lock.
- Exact `Decimal` scoring; real leagues advance automatically when a day is final and imported; matchup/team totals recomputed after corrections.
- Pages: Data Admin (status, freshness, plan limitation, manual sync), dashboard (upcoming games, recent performances, data timestamps),
  player database + profile with selectable scoring rules and missing-vs-zero display, onboarding when no data exists.
- **All simulated data removed** (fictional players, generated schedules/stat lines, demo league, NHL demo set, "Sim day" controls,
  demo flags). Migration 0003 deletes them from existing databases; 70 backend tests use an offline fixture provider.

## Hardcoded data audit (result)
Removed: simulated players/schedule/stats (`providers.py`, `seed.py`), demo league and flags, NHL demo dataset, simulation endpoint and buttons,
lenient scoring. Kept (legitimate configuration, not data): sport definitions in `sports.py` (positions, stat keys, default scoring, roster slots),
the draft-room position filter, computer-manager team names. Scoring labels/defaults and stat labels now come from the API.

## Needs your action / not verified
- **Add your Highlightly key** (`HIGHLIGHTLY_API_KEY` in `.env`), then `npm run sync`. No real box score has been fetched yet: the integration
  follows the provider's OpenAPI spec and is tested offline, so expect small adjustments after the first real import.
- Assumptions to confirm with a key: stat names match the documented box-score names; `positionAbbreviation` values map via
  `ingest.POSITION_MAP`; `/matches?season=` numbering (handled by a one-time probe); whether preseason games are listed (set
  `FLASK_NBA_SEASON_START` if so); final scores are not imported (the spec's score arrays are ambiguous) - fantasy points do not need them.
- Playoff games are not distinguished (the API has no flag); injuries are not imported (every player shows healthy).

## Not done
Waiver claim processing (schema only), playoffs, other formats (categories/roto/keeper), NFL, NHL, league chat, League Legacy,
full Draft War Room, historical seasons beyond the current one (one season per database), frontend automated tests, live (in-game) scoring.

## Next steps
1. Add the API key, run `npm run sync`, review Data Admin, fix any provider-shape surprises.  2. Decide on ALL-STAR for box scores.
3. Schedule `nba daily`.  4. Waivers.  5. Playoffs.  6. Injury feed (paid tier) and live stats if the plan allows.

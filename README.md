# FantaBall

Fantasy basketball platform (Flask + SQLAlchemy backend, Next.js frontend). Real NBA data flows
**provider -> database -> scoring engine -> website**. There is no simulated or placeholder data anywhere in the application:
until you import real data the pages show setup instructions.

## Quick start

```
npm run setup      # once: venv, Python packages, .env, frontend packages
npm run dev        # API (5010) + app (3000) with auto-reload  ->  open http://localhost:3000
npm run prod       # build the frontend, run both without debug
npm run test       # backend tests + frontend build
```
(`pnpm dev` etc. work the same.) Always use **http://localhost:3000**; port 5010 is only the API.
The database is migrated automatically on every start (see *Database*).

## Real NBA data (Highlightly, free plan)

Provider facts were read from https://highlightly.net/nba-api/documentation/ (and its OpenAPI spec) on 2026-10-27, and the base URL /
header behaviour was confirmed against the live service (no header -> HTTP 403; invalid key -> HTTP 401).

* **Free plan, no credit card:** 100 requests per day; player stats and box scores are included (highlights and odds are not).
* **Terms** (https://highlightly.net/terms/): storing the data and using it in your own app is allowed; cash-prize fantasy sports and
  betting are excluded (FantaBall has neither); do not circumvent rate limits or resell API access.
* Auth: header `x-rapidapi-key` to `https://nba.highlightly.net`. The response header `x-ratelimit-requests-remaining` is read, and
  the app stops before the quota is gone.
* `/players` lists only id + name, so **players are discovered from box scores** (a player appears once he has played) and their
  position comes from the match lineup. The player pool therefore grows during the season.

**One-time setup**
1. Create a free account at https://highlightly.net/ (dashboard -> API key).
2. Put the key in `.env` (git-ignored): `HIGHLIGHTLY_API_KEY=your_key` (see `.env.development.example`; placeholders only).
3. `npm run dev`, then in another terminal `npm run sync` (teams, whole-season schedule, then box scores of finished games).
   Each game costs about 1-2 requests, so the first import of a season already underway can take **a day or two**: it stops
   cleanly when today's budget is used up, and the next run continues where it stopped (**Data Admin** shows "requests today").
4. **Data Admin** (emails in `FLASK_ADMIN_EMAILS`) shows status, freshness, failures and has buttons for every job.

**Request budget** (daily job, ~10 games/day): ~9 date queries (yesterday to next week) + ~10 box scores + a few lineups +
~10 for the one-day corrections re-check = ~30-40 of the 100. Mondays add ~13 for a full-season refresh. If the provider also lists
preseason games, set `FLASK_NBA_SEASON_START=YYYY-MM-DD` (the Monday of regular-season week 1) before the first sync.

**Alternative provider:** `FLASK_NBA_PROVIDER=balldontlie` (needs `BALLDONTLIE_API_KEY`; its free plan has no player stats).

**Commands** (`npm run nba -- <cmd>` or `python -m flask --app app nba <cmd>`; all are safe to repeat)

| Command | What it does |
|---|---|
| `nba status` | provider config, last runs |
| `nba sync-teams` | teams + current players |
| `nba sync-games --season 2026` / `--start D --end D` | schedule + results (the first full-season run anchors the season calendar) |
| `nba sync-stats [--date D \| --start D --end D]` | box scores: only missing ones, or re-import dates |
| `nba corrections [--days 3]` | re-fetch recent games and apply official corrections |
| `nba recalc` | rebuild every stored fantasy score and league total |
| `nba daily` | the scheduled job: schedule window -> missing box scores -> corrections -> scores -> league scoring |
| `nba bootstrap` | first import (= `npm run sync`) |
| `nba purge-data --yes` | dev only: delete imported NBA rows (only while no league uses them) |

**Scheduling.** Run `nba daily` once or twice a day. Linux: `deploy/fantaball-sync.service` + `.timer` (systemd) or cron
`0 6 * * * /srv/fantaball/scripts/daily-sync.sh`. Windows: `scripts/daily-sync.ps1` (the `schtasks` line is in the file).
No scheduler runs inside the web workers. A partial unique index on `data_sync_runs` allows only **one** running sync per
provider, so duplicate schedulers or several workers can never run the same job twice.

**Request economy.** Games are fetched by date window; box scores only for *final* games whose stats were never imported
(grouped by date, 100 rows/page); corrections re-check only the last few days; retries use exponential backoff with
`Retry-After`; 401/403 are never retried. Every job is recorded in `data_sync_runs` (inserted/updated/skipped/requests/errors).

**Tests.** The automated tests never touch the network or the paid plan: they use an offline fixture provider
(`tests/mock_provider.py`, installed through `NBA_PROVIDER_FACTORY`). The running application cannot use it.

## How real data becomes fantasy points

1. `fantaball/nba/highlightly.py` (or `balldontlie.py`) fetches and parses (pure `parse_*` functions); `http.py` handles timeouts, retries, pacing and the daily budget.
2. `fantaball/nba/ingest.py` upserts teams, players, games, `game_stats` by the provider's ids (idempotent), per-batch commits.
   Unreported stats stay `NULL` - never 0. Players without a known position are stored but not draftable.
3. `fantaball/scoring.py::score_decimal` (exact `Decimal`, weights may be negative/fractional) turns a stat line into points;
   a needed stat that is missing makes the game *unscored* instead of zero.
4. `fantaball/nba/scoring_service.py` stores `player_fantasy_scores` per (stat line, **immutable rule set**). Leagues with the
   same weights share one rule set; changing a league's rules selects another, so history is preserved.
5. `fantaball/nba/league_sync.py` advances real leagues day by day once every game of a day is final **and** imported
   (future/postponed games never count), snapshots each lineup (`daily_scores`) and recomputes matchups + `team_period_scores`
   (`fantaball/league_scoring.py::recompute_week`). Corrections re-run this for finalized weeks too.

Scores are as fresh as the last sync, not live; the UI shows "statistics as of" timestamps.
Day numbering: day 1 = the Monday on/before the season's first game; weeks are Monday-Sunday.
A league drafted mid-season starts scoring the next day.

## Database

SQLite (Flask-SQLAlchemy) with **Alembic migrations** in `migrations/` (`models/fantasy.py` is the schema).
`app.py` runs them on start: a new database gets every migration; an old `create_all()` database is stamped as baseline `0001`
and upgraded; migration `0003` deletes the old simulated demo world (fictional players, schedules, stat lines and the leagues built on them). The read-only `people` table is never touched.
Before upgrading a production server run `./backup-database-before-upgrade.sh` (already part of `update-and-restart-server.sh`).
New migration: edit models, then `FLASK_SKIP_DB_INIT=true python -m flask --app app db migrate -m "what changed"` and review the file.

| Spec entity | Table / model |
|---|---|
| ProfessionalTeam / Player / Game / PlayerGameStat | `pro_teams` / `athletes` / `pro_games` / `game_stats` (provider ids, typed nullable stats, unique player+game) |
| FantasyLeague / FantasyTeam / LeagueMembership | `leagues` / `fantasy_teams` (unique league+manager = membership) |
| RosterEntry | `roster_slots` (unique athlete per league, `acquired_via`) ; history via `player_transactions` |
| FantasyScoringRule | `scoring_rulesets` (immutable weight sets, named templates) + `scoring_configs` (league -> rule set) |
| PlayerFantasyScore | `player_fantasy_scores` |
| FantasyMatchup / TeamPeriodScore | `matchups` / `team_period_scores` |
| DataSyncRun | `data_sync_runs` |
| Draft, trades, waivers (schema), activity | `draft_*`, `trade_*`, `waiver_claims`, `league_activity` |

## Where the algorithms are (for study)

| Topic | File |
|---|---|
| Exact scoring, rule-set hashing | `fantaball/scoring.py`, `fantaball/rulesets.py` |
| Provider interface, Highlightly / BALLDONTLIE clients, retries | `fantaball/nba/provider.py`, `highlightly.py`, `balldontlie.py`, `http.py` |
| Ingestion (upserts, run tracking, daily job) | `fantaball/nba/ingest.py` |
| Fantasy score persistence / league progression | `fantaball/nba/scoring_service.py`, `league_sync.py` |
| Matchup totals / corrections | `fantaball/league_scoring.py` |
| Position eligibility, lineup optimizer | `fantaball/roster.py` |
| Projections (shrinkage + recent form) | `fantaball/stats.py` |
| Snake draft, bot picks (value over replacement), assistant | `fantaball/draft.py`, `draft_assist.py` |
| Trade impact simulator, Fantasy GM, What-If | `fantaball/trade_analysis.py`, `gm.py`, `whatif.py` |
| Schedule / standings / power rankings | `fantaball/leagues.py` |

## Tests

`npm run test`, or `python -m pytest tests -q` (89 tests, temp database, **no network**: the real provider is exercised with a
fake HTTP opener, the pipeline with the offline fixture provider) and `cd frontend && npx tsc --noEmit && npx eslint src && npx next build`.
Covered: provider parsing, pagination, retries/401/403/429/5xx, upserts, duplicate prevention, failure recovery, plan limits,
corrections, exact scoring, rule changes, ownership, authorization, lineup/matchup/team totals, migrations of a legacy database.
The live provider has been verified only up to the unauthenticated request (HTTP 403/401 as documented); real box scores have not been fetched yet.

## Adding NHL / NFL

Add the sport to `fantaball/sports.py` (positions, stat keys, default scoring, roster slots), write a provider returning the same
records, add it to `PLAYABLE_SPORTS`. Scoring, drafting, trades and the UI read these definitions.

## Troubleshooting

* *Port in use*: the launcher stops and names the port; close the old server.
* *"Application Control policy has blocked" `_util_cy` on Windows*: delete `.venv/Lib/site-packages/sqlalchemy/*/*_cy.*.pyd`;
  SQLAlchemy then uses its pure-Python code.
* *Auth*: uses the school JWT/OAuth2-Proxy manager (`flask_jwt_auth_manager.py`, not modified; it does not verify signatures,
  so keep `FLASK_JWT_AUTH_DUMMY_USER_IF_NO_PROXY=false` in production and run only behind the proxy).

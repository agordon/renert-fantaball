# FantaBall

Fantasy basketball platform (Flask + SQLAlchemy backend, Next.js frontend). Real NBA data flows
**provider -> database -> scoring engine -> website**. A clearly labelled *simulated demo world* is available as an explicit option.

## Quick start

```
npm run setup      # once: venv, Python packages, .env, frontend packages
npm run dev        # API (5010) + app (3000) with auto-reload  ->  open http://localhost:3000
npm run prod       # build the frontend, run both without debug
npm run test       # backend tests + frontend build
```
(`pnpm dev` etc. work the same.) Always use **http://localhost:3000**; port 5010 is only the API.
The database is migrated automatically on every start (see *Database*).

## Real NBA data (BALLDONTLIE)

Provider facts below were checked against https://docs.balldontlie.io/ and the OpenAPI spec on 2026-10-27.

| | Free | ALL-STAR ($9.99/mo) | GOAT ($39.99/mo) |
|---|---|---|---|
| Teams, players, games (schedule + scores) | yes | yes | yes |
| **Game player stats (box scores)** | **no (HTTP 401)** | yes | yes |
| Season averages, box scores v2, standings, odds ... | no | no | yes |
| Rate limit | 5 requests/min | 60/min | 600/min |

Auth is the `Authorization` header; pagination is cursor-based (`per_page` max 100). History goes back to 1946.
**Fantasy points from real box scores need at least the ALL-STAR plan.** On the free plan, teams/players/schedules import
fine and the app says clearly that statistics are unavailable; nothing is invented. No subscription is bought by this project.

**One-time setup**
1. Create an account at https://www.balldontlie.io/ and copy your key.
2. Put it in `.env` (git-ignored): `BALLDONTLIE_API_KEY=your_key` (`.env.development.example` shows the settings; placeholders only).
3. Restart the backend, then import: `npm run sync` (teams + players, full-season schedule, every available box score).
   The free rate limit (5/min) makes the first import take several minutes.
4. Open **Data Admin** (listed in `FLASK_ADMIN_EMAILS`) to see status, freshness, failures and to run jobs by hand.

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
| `nba purge-data --yes` | dev only: delete imported NBA rows (when switching provider) |
| `nba demo-seed` | create the simulated demo world |

**Scheduling.** Run `nba daily` once or twice a day. Linux: `deploy/fantaball-sync.service` + `.timer` (systemd) or cron
`0 6 * * * /srv/fantaball/scripts/daily-sync.sh`. Windows: `scripts/daily-sync.ps1` (the `schtasks` line is in the file).
No scheduler runs inside the web workers. A partial unique index on `data_sync_runs` allows only **one** running sync per
provider, so duplicate schedulers or several workers can never run the same job twice.

**Request economy.** Games are fetched by date window; box scores only for *final* games whose stats were never imported
(grouped by date, 100 rows/page); corrections re-check only the last few days; retries use exponential backoff with
`Retry-After`; 401/403 are never retried. Every job is recorded in `data_sync_runs` (inserted/updated/skipped/requests/errors).

**Offline development.** `FLASK_NBA_PROVIDER=mock` uses `fantaball/nba/mock.py` (invented data, labelled MOCK in the UI).
It is only used when selected explicitly - never as a fallback for a failed real request. Automated tests use it.

## How real data becomes fantasy points

1. `fantaball/nba/balldontlie.py` fetches and parses (pure `parse_*` functions); `http.py` handles timeouts/retries/rate limit.
2. `fantaball/nba/ingest.py` upserts teams, players, games, `game_stats` by the provider's ids (idempotent), per-batch commits.
   Unreported stats stay `NULL` - never 0. Players without a known position are stored but not draftable.
3. `fantaball/scoring.py::score_decimal` (exact `Decimal`, weights may be negative/fractional) turns a stat line into points;
   a needed stat that is missing makes the game *unscored* instead of zero.
4. `fantaball/nba/scoring_service.py` stores `player_fantasy_scores` per (stat line, **immutable rule set**). Leagues with the
   same weights share one rule set; changing a league's rules selects another, so history is preserved.
5. `fantaball/nba/league_sync.py` advances real leagues day by day once every game of a day is final **and** imported
   (future/postponed games never count), snapshots each lineup (`daily_scores`) and recomputes matchups + `team_period_scores`
   (`fantaball/simulation.py::recompute_week`). Corrections re-run this for finalized weeks too.

Scores are as fresh as the last sync, not live; the UI shows "statistics as of" timestamps.
Day numbering: day 1 = the Monday on/before the season's first game; weeks are Monday-Sunday.
A league drafted mid-season starts scoring the next day.

## Database

SQLite (Flask-SQLAlchemy) with **Alembic migrations** in `migrations/` (`models/fantasy.py` is the schema).
`app.py` runs them on start: a new database gets every migration; an old `create_all()` database is stamped as baseline `0001`
and upgraded to `0002` (the old simulated `nba` data is relabelled `nba_demo`). The read-only `people` table is never touched.
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

## Demo mode (simulated)

`FLASK_DEMO_DATA=true` (default in the *development* example) creates fictional players and a pre-played 12-team league on
start (`nba_demo` / `nhl` sports). Everything in it is labelled "Simulated demo data". Set it to `false` for real data only.
With no data at all, pages show onboarding instructions instead of fake content.

## Where the algorithms are (for study)

| Topic | File |
|---|---|
| Exact scoring, rule-set hashing | `fantaball/scoring.py`, `fantaball/rulesets.py` |
| Provider interface, BALLDONTLIE client, retries | `fantaball/nba/provider.py`, `balldontlie.py`, `http.py` |
| Ingestion (upserts, run tracking, daily job) | `fantaball/nba/ingest.py` |
| Fantasy score persistence / league progression | `fantaball/nba/scoring_service.py`, `league_sync.py` |
| Matchup totals / corrections | `fantaball/simulation.py` |
| Position eligibility, lineup optimizer | `fantaball/roster.py` |
| Projections (shrinkage + recent form) | `fantaball/stats.py` |
| Snake draft, bot picks (value over replacement), assistant | `fantaball/draft.py`, `draft_assist.py` |
| Trade impact simulator, Fantasy GM, What-If | `fantaball/trade_analysis.py`, `gm.py`, `whatif.py` |
| Schedule / standings / power rankings | `fantaball/leagues.py` |
| Demo world generator | `fantaball/providers.py`, `seed.py` |

## Tests

`npm run test`, or `python -m pytest tests -q` (71 tests, temp database, **no network**: the real provider is exercised with a
fake HTTP opener and the mock provider) and `cd frontend && npx tsc --noEmit && npx eslint src && npx next build`.
Covered: provider parsing, pagination, retries/401/403/429/5xx, upserts, duplicate prevention, failure recovery, plan limits,
corrections, exact scoring, rule changes, ownership, authorization, lineup/matchup/team totals, migrations of a legacy database.
The real provider itself has been verified only up to the unauthenticated request (the live API answers HTTP 401 without a key).

## Adding NHL / NFL

Add the sport to `fantaball/sports.py`, write a provider returning the same records, add it to `PLAYABLE_SPORTS`.
Scoring, drafting, trades and the UI read these definitions. NHL demo data and scoring already exist.

## Troubleshooting

* *Port in use*: the launcher stops and names the port; close the old server.
* *"Application Control policy has blocked" `_util_cy` on Windows*: delete `.venv/Lib/site-packages/sqlalchemy/*/*_cy.*.pyd`;
  SQLAlchemy then uses its pure-Python code.
* *Auth*: uses the school JWT/OAuth2-Proxy manager (`flask_jwt_auth_manager.py`, not modified; it does not verify signatures,
  so keep `FLASK_JWT_AUTH_DUMMY_USER_IF_NO_PROXY=false` in production and run only behind the proxy).

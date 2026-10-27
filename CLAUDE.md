# FantaBall - project notes

Flask + Flask-SQLAlchemy backend (existing school project) + Next.js/React/TypeScript/Tailwind frontend in `frontend/`.
Real NBA data (BALLDONTLIE) -> `fantaball/nba/*` ingestion -> database -> `fantaball/scoring.py` -> API -> website.

## Commands
- `npm run setup` once; `npm run dev` (API :5010 + app :3000, open http://localhost:3000); `npm run prod`; `npm run test`
- Data: `npm run sync` (first import), `npm run sync:daily`, `npm run sync:status`, any command: `npm run nba -- <cmd>` (see README table)
- Backend tests: `python -m pytest tests -q` (temp DB, no network, uses the MOCK provider). Frontend: `cd frontend && npx tsc --noEmit && npx eslint src && npx next build`
- Migrations: Alembic in `migrations/`, applied automatically on start. New one: edit `models/fantasy.py`, then
  `FLASK_SKIP_DB_INIT=true python -m flask --app app db migrate -m "msg"` and review/name constraints (SQLite batch mode).

## Rules
- DO NOT modify `flask_jwt_auth_manager.py` or `models/people.py`; Alembic ignores the `people` table. Identity = JWT email -> `managers`.
- Business logic lives in `fantaball/` (no Flask request code); `views/api*.py` only parse input, call services, serialize.
  Authorization: `leagues.membership()` / `require_commissioner()` / `views.api_common.require_admin()` (FLASK_ADMIN_EMAILS).
- Never trust the client: ownership, eligibility, turn order, roster size are validated server-side. Services raise `ApiError`.
- Real vs demo data: sport `nba` = real provider data; `nba_demo`/`nhl` = SIMULATED (`Sport.data_source`). Never mix them, never fall
  back silently to fictional/mock data. Demo world only with `FLASK_DEMO_DATA=true`. MOCK provider only when selected explicitly.
- Missing provider stats are NULL, never 0. Real scoring uses `score_decimal` (None if a needed stat is missing); the lenient
  `score_stat_line` is for the demo world only. Scoring rule sets are immutable (new weights = new `scoring_rulesets` row).
- Provider calls go through `fantaball/nba/http.py` (timeout, rate limit, backoff; 401/403 never retried). The API key lives only in
  the environment (`BALLDONTLIE_API_KEY`), never in code, responses or logs. Do not buy plans / make paid calls without approval.
- Ingestion must stay idempotent (upsert by provider id) and tracked in `data_sync_runs` (one running job per provider).
- Tests: tests that touch the real-data sport use the `world` fixture (wipes `nba` rows) and `FLASK_FAKE_TODAY`; test clients push a
  fresh app context per request (see `tests/conftest.py`).
- Next.js is v16 (see `frontend/AGENTS.md`); client-rendered, Cache Components off. Typed API shapes: `src/lib/api-types.ts`, `client.ts`.
- Windows: SQLAlchemy's compiled `.pyd` files may be blocked by Application Control - delete them (README troubleshooting).
- Never push to GitHub without the user's approval (origin is the teacher's repo, `agordon/renert-fantaball`).

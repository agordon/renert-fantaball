# FantaBall - project notes

Flask + Flask-SQLAlchemy backend (existing school project) + Next.js/React/TypeScript/Tailwind frontend in `frontend/`.
Real NBA data (Highlightly; BALLDONTLIE alternative) -> `fantaball/nba/*` ingestion -> database -> `fantaball/scoring.py` -> API -> website.

## Commands
- `npm run setup` once; `npm run dev` (API :5010 + app :3000, open http://localhost:3000); `npm run prod`; `npm run test`
- Data: `npm run sync` (first import), `npm run sync:daily`, `npm run sync:status`, any command: `npm run nba -- <cmd>` (see README table)
- Backend tests: `python -m pytest tests -q` (temp DB, no network, offline fixture provider in `tests/mock_provider.py`). Frontend: `cd frontend && npx tsc --noEmit && npx eslint src && npx next build`
- Migrations: Alembic in `migrations/`, applied automatically on start. New one: edit `models/fantasy.py`, then
  `FLASK_SKIP_DB_INIT=true python -m flask --app app db migrate -m "msg"` and review/name constraints (SQLite batch mode).

## Rules
- DO NOT modify `flask_jwt_auth_manager.py` or `models/people.py`; Alembic ignores the `people` table. Identity = JWT email -> `managers`.
- Business logic lives in `fantaball/` (no Flask request code); `views/api*.py` only parse input, call services, serialize.
  Authorization: `leagues.membership()` / `require_commissioner()` / `views.api_common.require_admin()` (FLASK_ADMIN_EMAILS).
- Never trust the client: ownership, eligibility, turn order, roster size are validated server-side. Services raise `ApiError`.
- There is NO simulated / placeholder data in the application (it was removed on purpose; migration 0003 deletes old rows). Never
  add fictional players, fake stats or a silent fallback: with no data the UI shows onboarding instructions. The offline fixture
  provider lives in `tests/` only and is injected through `app.config["NBA_PROVIDER_FACTORY"]`.
- Missing provider stats are NULL, never 0. Scoring uses `score_decimal` (None if a needed stat is missing). Scoring rule sets are
  immutable (new weights = new `scoring_rulesets` row).
- Provider calls go through `fantaball/nba/http.py` (timeout, rate limit, backoff; 401/403 never retried). The API key lives only in
  the environment (`HIGHLIGHTLY_API_KEY`), never in code, responses or logs. Do not buy plans / make paid calls without approval.
- Highlightly specifics: players come from box scores (no roster endpoint), positions from lineups, one request per game, free quota
  100/day (the client stops at the budget / `x-ratelimit-requests-remaining`). Provider capabilities live as attributes on `NBADataProvider`.
- Ingestion must stay idempotent (upsert by provider id) and tracked in `data_sync_runs` (one running job per provider).
- Tests: use the `world` / `nba_data` fixtures (they wipe and refill the `nba` rows) and `FLASK_FAKE_TODAY`; helpers in
  `tests/helpers.py`; test clients push a fresh app context per request (see `tests/conftest.py`).
- Next.js is v16 (see `frontend/AGENTS.md`); client-rendered, Cache Components off. Typed API shapes: `src/lib/api-types.ts`, `client.ts`.
- Windows: SQLAlchemy's compiled `.pyd` files may be blocked by Application Control - delete them (README troubleshooting).
- Never push to GitHub without the user's approval (origin is the teacher's repo, `agordon/renert-fantaball`).

# FantaBall - project notes

Flask + Flask-SQLAlchemy backend (existing school project) + Next.js/React/TypeScript/Tailwind frontend in `frontend/`.

## Commands
- Backend (from repo root, Python venv in `.venv`): `pip install -r requirements.txt -r requirements-dev.txt`, copy `.env.development.example` to `.env`, then `python -m flask --app app run --port 5010`
- Frontend: `cd frontend && npm install && npm run dev` (http://localhost:3000; API URL via `NEXT_PUBLIC_API_URL`, default http://127.0.0.1:5010)
- Tests: `python -m pytest tests -q` (uses a temp DB; first run seeds the demo world, ~10 s). Frontend checks: `npx tsc --noEmit`, `npx eslint src`, `npx next build`
- Reset demo data: stop Flask, delete `instance/database.db`, restart.

## Rules
- DO NOT modify `flask_jwt_auth_manager.py` or `models/people.py` (marked read-only). Identity = JWT email (dummy user in dev) -> `managers` table.
- All business rules live in `fantaball/` (no Flask code); `views/api*.py` only parse input, call services, serialize. Authorization = `leagues.membership()` / `require_commissioner()`.
- Never trust the client: ownership, eligibility, turn order, roster size are re-validated server-side. Services raise `ApiError` (status + safe message).
- Sport differences live ONLY in `fantaball/sports.py` (+ a `DataProvider` in `providers.py`).
- All data is simulated (`DemoProvider`); label it as such in the UI.
- Next.js here is v16 (see `frontend/AGENTS.md`); the app is client-rendered, Cache Components is off.
- Never push to GitHub without the user's approval (origin is the teacher's repo, `agordon/renert-fantaball`).

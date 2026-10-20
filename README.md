# FantaBall

Fantasy sports platform prototype (NBA head-to-head points first). Flask API + Next.js UI.
**All players, schedules and stats are simulated demo data** - nothing is real NBA data.

## Run locally
```
python -m venv .venv && .venv\Scripts\activate        # Windows (use source .venv/bin/activate on Linux/macOS)
pip install -r requirements.txt
copy .env.development.example .env                      # (cp on Linux/macOS)
python -m flask --app app run --port 5010               # first start seeds the demo world + a 12-team league (~10 s)

cd frontend && npm install && npm run dev               # http://localhost:3000
```
Open http://localhost:3000. You are logged in as the local demo user (John Doe) and own "Demo Dynasty" in a pre-played demo league (week 5). Use **Sim day / Sim week** to advance the season.

## Tests
`pip install -r requirements-dev.txt && python -m pytest tests -q`  ·  frontend: `cd frontend && npx tsc --noEmit && npx next build`

## Where the algorithms are (for study)
| Topic | File |
|---|---|
| Scoring formula (configurable) | `fantaball/scoring.py` |
| Position eligibility, lineup optimizer | `fantaball/roster.py` |
| Projections (shrinkage + recent form) | `fantaball/stats.py` |
| Snake order, bot drafting (value over replacement) | `fantaball/draft.py` |
| Draft strategy assistant | `fantaball/draft_assist.py` |
| Trade impact simulator | `fantaball/trade_analysis.py` |
| Fantasy GM suggestions | `fantaball/gm.py` |
| Round-robin schedule, standings, power rankings | `fantaball/leagues.py` |
| Day simulation | `fantaball/simulation.py` |
| What-If | `fantaball/whatif.py` |
| Seed data / data-provider abstraction | `fantaball/seed.py`, `fantaball/providers.py` |

## Adding NHL / NFL
Add the sport to `fantaball/sports.py` (positions, stat keys, default scoring, roster slots), supply a `DataProvider`, and add it to `PLAYABLE_SPORTS`. NHL data and scoring already exist; NFL needs a new entry and provider. Scoring, drafting, trades and the UI read these definitions rather than hard-coding basketball.

## Notes
- Auth uses the existing JWT/OAuth2-Proxy manager (see `PROJECT_ROADMAP.md` security notes). Production: set `FLASK_ENVIRONMENT=production`; the demo league is then not created.
- Existing files `flask_jwt_auth_manager.py` and `models/people.py` are untouched.

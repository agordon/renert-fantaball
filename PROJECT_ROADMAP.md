# FantaBall roadmap

## Done (Phases 1-4 core, tested)
- Models for sports, pro teams, athletes, game logs, leagues, scoring configs, teams, rosters (unique ownership per league), drafts, matchups, daily scores, transactions, trades, waiver claims (schema only), activity.
- Scoring engine (configurable per league), roster eligibility + lineup optimizer, auto/manual lineups, add/drop.
- Snake draft (timer, queue, computer managers, auto-pick, strategy assistant), schedule + standings + power rankings.
- Day/week simulator, matchup center, trades (propose/accept/decline, atomic) + Trade Impact Simulator, Fantasy GM (rule-based), What-If lineup swap.
- REST API (`/api/...`), Next.js UI for every nav page, 12-team seeded demo league, 21 backend tests.

## Not done / simulated
- Waiver claims (table only), playoffs, categories/roto/keeper/dynasty formats, NFL, NHL leagues (NHL data + scoring exist; league creation disabled).
- Real login/register/logout: auth is the school OAuth2-Proxy JWT (local dev uses a dummy user); no passwords stored.
- League chat, League Legacy, advanced What-If (draft/trade variants), full Draft War Room (other managers' needs).
- Real sports data: only simulated provider (fictional players).
- Frontend automated tests (manually verified with Playwright; add e2e later).

## Security notes
- `flask_jwt_auth_manager.py` does NOT verify JWT signatures - only safe behind NGINX + OAuth2-Proxy that blocks direct access. Keep `FLASK_JWT_AUTH_DUMMY_USER_IF_NO_PROXY=false` in production.
- Mutating API calls require JSON content type and an allowed Origin.

## Next steps
1. Waiver claims processing; 2. NHL leagues; 3. Playoff bracket; 4. Draft War Room (opponent needs); 5. League chat + Legacy; 6. Deployment (build `frontend`, serve behind nginx next to Flask).

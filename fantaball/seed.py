"""Seed the simulated world (athletes, schedule, stat lines) and a complete 12-team NBA demo league.

Everything is created through the same services the app uses (draft engine, transactions, simulator), so the
demo data is internally consistent: rosters come from a real snake draft, standings from real simulated weeks.
Safe to run repeatedly: it only inserts what is missing.
"""
from root import app, db
from models.fantasy import Athlete, GameStat, League, Manager, ProGame, ProTeam, Sport
from fantaball import draft as draft_svc
from fantaball import leagues as league_svc
from fantaball import stats as stats_svc
from fantaball import transactions as tx
from fantaball.lineups import team_slots
from fantaball.providers import DataProvider, DemoProvider
from fantaball.simulation import advance_day
from fantaball.sports import SPORTS

DEMO_LEAGUE_NAME = "FantaBall Demo League (simulated)"
DEMO_DAYS = 31          # four full weeks + 3 days into week 5


def load_world(provider: DataProvider):
    """Insert one sport's teams, athletes, schedule and game logs (skipped if the sport already exists)."""
    code = provider.sport_code
    if db.session.scalar(db.select(Sport).where(Sport.code == code)):
        return
    sport = Sport(code=code, name=SPORTS[code]["name"])
    db.session.add(sport)
    db.session.flush()
    teams = {}
    for t in provider.pro_teams():
        pt = ProTeam(sport_id=sport.id, **t)
        db.session.add(pt)
        teams[t["abbr"]] = pt
    db.session.flush()

    raw_athletes = provider.athletes()
    athletes = []
    for a in raw_athletes:
        ath = Athlete(sport_id=sport.id, pro_team_id=teams[a["team"]].id, name=a["name"], positions=a["positions"], age=a["age"],
                      rank=a["rank"], injury_start=a["injury_start"], injury_end=a["injury_end"], injury_note=a["injury_note"])
        db.session.add(ath)
        athletes.append(ath)
    schedule = provider.schedule()
    games = []
    for g in schedule:
        pg = ProGame(sport_id=sport.id, day=g["day"], home_team_id=teams[g["home"]].id, away_team_id=teams[g["away"]].id)
        db.session.add(pg)
        games.append(pg)
    db.session.flush()
    rows = [dict(athlete_id=athletes[r["athlete_index"]].id, pro_game_id=games[r["game_index"]].id, day=r["day"], stats=r["stats"])
            for r in provider.game_stats(raw_athletes, schedule)]
    db.session.execute(db.insert(GameStat), rows)
    db.session.commit()
    stats_svc.clear_cache()
    app.logger.info(f"seed: loaded {code} world ({len(athletes)} athletes, {len(games)} games, {len(rows)} stat lines)")


def get_or_create_manager(email: str, display_name: str) -> Manager:
    m = db.session.scalar(db.select(Manager).where(Manager.email == email))
    if not m:
        m = Manager(email=email, display_name=display_name)
        db.session.add(m)
        db.session.commit()
    return m


def seed_demo_league(demo_email: str, demo_name: str):
    """12-team NBA points league: real snake draft -> 31 simulated days -> a few trades/pending offers."""
    if db.session.scalar(db.select(League.id).where(League.is_demo.is_(True))):
        return
    me = get_or_create_manager(demo_email, demo_name)
    league = league_svc.create_league(me, DEMO_LEAGUE_NAME, "nba", 12, team_name="Demo Dynasty", is_demo=True)
    session = draft_svc.start_draft(league, pick_seconds=45)
    draft_svc.sim_until_human(league, session, to_end=True)      # computer managers draft for everybody

    teams = league_svc.teams_of(league.id)
    mine = next(t for t in teams if t.manager_id == me.id)
    bots = [t for t in teams if t.is_bot]
    trade_done = False
    for _ in range(DEMO_DAYS):
        advance_day(league)
        if league.current_day == 12 and not trade_done:        # one completed bot-vs-bot trade for the history
            trade_done = _bot_trade(league, bots[0], bots[1])
    _pending_offers(league, mine, bots[2:4])
    mine.auto_lineup = False
    db.session.commit()
    app.logger.info(f"seed: demo league '{league.name}' ready at day {league.current_day}")


def _best_by_proj(league, team, rank_from_top):
    summ = stats_svc.summaries(league.sport_id, league.scoring.rules, league.current_day)
    slots = sorted(team_slots(team.id), key=lambda s: -summ[s.athlete_id]["proj"])
    return slots[min(rank_from_top, len(slots) - 1)].athlete_id


def _bot_trade(league, a, b) -> bool:
    try:
        offer = tx.propose_trade(league, a, b.id, [_best_by_proj(league, a, 4)], [_best_by_proj(league, b, 4)], "Simulated bot trade")
        tx.accept_trade(league, offer, b, "Deal")
        return True
    except Exception as exc:        # a seed trade must never block start-up
        db.session.rollback()
        app.logger.warning(f"seed: skipped bot trade: {exc}")
        return False


def _pending_offers(league, mine, bots):
    """Offers from computer managers to the demo user so the Trades page has something to evaluate."""
    for i, bot in enumerate(bots):
        try:
            tx.propose_trade(league, bot, mine.id, [_best_by_proj(league, bot, 3 + i)], [_best_by_proj(league, mine, 3 + i)],
                             "Simulated offer from a computer manager")
        except Exception as exc:
            db.session.rollback()
            app.logger.warning(f"seed: skipped pending offer: {exc}")


def seed_all(demo_email: str, demo_name: str):
    load_world(DemoProvider("nba"))
    load_world(DemoProvider("nhl"))
    seed_demo_league(demo_email, demo_name)

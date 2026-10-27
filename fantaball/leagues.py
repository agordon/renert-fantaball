"""League creation / membership / settings, the weekly schedule, standings and power rankings."""
import re
import secrets

from root import db
from models.fantasy import Activity, Athlete, FantasyTeam, League, Manager, Matchup, ScoringConfig, Sport
from fantaball.pool import pool_filter
from fantaball.rulesets import get_or_create_ruleset
from fantaball.errors import bad_request, conflict, forbidden, not_found
from fantaball.scoring import default_rules, validate_rules
from fantaball.sports import PLAYABLE_SPORTS, SPORTS

BOT_TEAM_NAMES = [
    "Court Jesters", "Hardwood Heroes", "Pick & Roll Pirates", "Fast Break Falcons", "Glass Cleaners",
    "Triple-Double Trouble", "Zone Defenders", "Buzzer Beaters", "Alley-Oop Army", "Swish Syndicate",
    "Paint Patrol", "Backdoor Cuts", "Corner Threes", "Sixth Man Society", "Full Court Press", "Rim Protectors",
]
VALID_SLOTS = {"PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "BN", "IR"}


def new_invite_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not db.session.scalar(db.select(League.id).where(League.invite_code == code)):
            return code


def get_or_create_bot_manager(n: int) -> Manager:
    email = f"bot{n}@fantaball.demo"
    m = db.session.scalar(db.select(Manager).where(Manager.email == email))
    if not m:
        m = Manager(email=email, display_name=f"AI Manager {n}", is_demo_bot=True)
        db.session.add(m)
        db.session.flush()
    return m


def add_bot_team(league: League, index: int) -> FantasyTeam:
    mgr = get_or_create_bot_manager(index)
    team = FantasyTeam(league_id=league.id, manager_id=mgr.id, is_bot=True, auto_lineup=True,
                       name=BOT_TEAM_NAMES[index % len(BOT_TEAM_NAMES)])
    db.session.add(team)
    db.session.flush()
    return team


def teams_of(league_id: int) -> list[FantasyTeam]:
    return list(db.session.scalars(db.select(FantasyTeam).where(FantasyTeam.league_id == league_id).order_by(FantasyTeam.id)))


def fill_with_bots(league: League):
    teams = teams_of(league.id)
    used = {t.manager_id for t in teams}
    n = 0
    while len(teams) < league.num_teams:
        n += 1
        if get_or_create_bot_manager(n).id in used:
            continue
        teams.append(add_bot_team(league, n))
        used.add(teams[-1].manager_id)


def clean_roster_config(sport_code: str, cfg) -> list:
    if cfg is None:
        return [list(x) for x in SPORTS[sport_code]["roster"]]
    if not isinstance(cfg, list) or not cfg:
        raise bad_request("roster_config must be a list of [slot, count]")
    out, seen = [], set()
    for item in cfg:
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            raise bad_request("roster_config entries must be [slot, count]")
        slot, count = item
        valid = set(SPORTS[sport_code]["slot_positions"]) | {"UTIL", "BN", "IR"}
        if slot not in valid or slot in seen:
            raise bad_request(f"Invalid or duplicate roster slot '{slot}'")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 8:
            raise bad_request(f"Slot count for {slot} must be a whole number from 0 to 8")
        seen.add(slot)
        if count:
            out.append([slot, count])
    starters = sum(c for s, c in out if s not in ("BN", "IR"))
    if starters < 3:
        raise bad_request("A league needs at least 3 starting slots")
    return out


def create_league(manager: Manager, name: str, sport_code: str, num_teams: int = 12, scoring_rules=None,
                  roster_config=None, team_name: str | None = None, fill_bots: bool = True, is_demo: bool = False) -> League:
    name = (name or "").strip()
    if not 3 <= len(name) <= 50:
        raise bad_request("League name must be 3-50 characters")
    if sport_code not in PLAYABLE_SPORTS:
        raise bad_request(f"Leagues for '{sport_code}' are not available yet")
    if isinstance(num_teams, bool) or not isinstance(num_teams, int) or not 4 <= num_teams <= 14 or num_teams % 2:
        raise bad_request("Number of teams must be an even number from 4 to 14")
    sport = db.session.scalar(db.select(Sport).where(Sport.code == sport_code))
    if not sport or not db.session.scalar(db.select(db.func.count(Athlete.id)).where(*pool_filter(sport.id))):
        if sport_code == "nba":
            raise conflict("No real NBA data has been imported yet. An administrator must run the data import first (see Data Administration).")
        raise bad_request("Data for that sport is not loaded")
    try:
        rules = validate_rules(sport_code, scoring_rules) if scoring_rules is not None else default_rules(sport_code)
    except ValueError as e:
        raise bad_request(str(e))
    cfg = clean_roster_config(sport_code, roster_config)

    league = League(name=name, sport_id=sport.id, commissioner_id=manager.id, invite_code=new_invite_code(),
                    num_teams=num_teams, roster_config=cfg, is_demo=is_demo, season=sport.season)
    db.session.add(league)
    db.session.flush()
    db.session.add(ScoringConfig(league_id=league.id, rules=rules, ruleset_id=get_or_create_ruleset(sport.id, rules).id))
    tname = clean_team_name(team_name or f"{manager.display_name}'s Team")
    db.session.add(FantasyTeam(league_id=league.id, manager_id=manager.id, name=tname))
    db.session.flush()
    if fill_bots:
        fill_with_bots(league)
    db.session.add(Activity(league_id=league.id, kind="league", message=f"{manager.display_name} created the league"))
    db.session.commit()
    return league


def clean_team_name(name: str) -> str:
    name = re.sub(r"\s+", " ", (name or "").strip())
    if not 2 <= len(name) <= 40:
        raise bad_request("Team name must be 2-40 characters")
    return name


def join_league(manager: Manager, code: str, team_name: str | None = None) -> League:
    league = db.session.scalar(db.select(League).where(League.invite_code == (code or "").strip().upper()))
    if not league:
        raise not_found("No league with that invitation code")
    teams = teams_of(league.id)
    if any(t.manager_id == manager.id for t in teams):
        raise conflict("You are already in this league")
    if league.status != "pre_draft":
        raise conflict("This league has already started its draft")
    tname = clean_team_name(team_name or f"{manager.display_name}'s Team")
    bot_team = next((t for t in teams if t.is_bot), None)
    if len(teams) < league.num_teams:
        db.session.add(FantasyTeam(league_id=league.id, manager_id=manager.id, name=tname))
    elif bot_team:      # a human takes over a computer-controlled slot
        bot_team.manager_id, bot_team.is_bot, bot_team.auto_lineup, bot_team.name = manager.id, False, False, tname
    else:
        raise conflict("This league is full")
    db.session.add(Activity(league_id=league.id, kind="league", message=f"{manager.display_name} joined the league"))
    db.session.commit()
    return league


def membership(manager: Manager, league_id: int) -> tuple[League, FantasyTeam]:
    """League + the manager's team in it, or 404/403. Use for every league-scoped endpoint."""
    league = db.session.get(League, league_id)
    if not league:
        raise not_found("League not found")
    team = db.session.scalar(db.select(FantasyTeam).where(FantasyTeam.league_id == league_id, FantasyTeam.manager_id == manager.id))
    if not team:
        raise forbidden("You are not a member of this league")
    return league, team


def require_commissioner(manager: Manager, league: League):
    if league.commissioner_id != manager.id:
        raise forbidden("Only the commissioner can do that")


def update_settings(manager: Manager, league: League, data: dict) -> League:
    require_commissioner(manager, league)
    if league.status != "pre_draft":
        raise conflict("Settings are locked once the draft has started")
    if "name" in data:
        name = (data["name"] or "").strip()
        if not 3 <= len(name) <= 50:
            raise bad_request("League name must be 3-50 characters")
        league.name = name
    if "scoring_rules" in data:
        try:
            rules = validate_rules(league.sport.code, data["scoring_rules"])
        except ValueError as e:
            raise bad_request(str(e))
        # a new rule set is selected (old ones are never edited), so previously stored fantasy scores stay valid
        league.scoring.rules = rules
        league.scoring.ruleset_id = get_or_create_ruleset(league.sport_id, rules).id
    if "roster_config" in data:
        league.roster_config = clean_roster_config(league.sport.code, data["roster_config"])
    if "num_teams" in data:
        n = data["num_teams"]
        if isinstance(n, bool) or not isinstance(n, int) or not 4 <= n <= 14 or n % 2:
            raise bad_request("Number of teams must be an even number from 4 to 14")
        if n < len(teams_of(league.id)):
            raise bad_request("Cannot have fewer teams than current members")
        league.num_teams = n
    db.session.commit()
    return league


# ---------------------------------------------------------------------------------------------
# Schedule, standings, power rankings
# ---------------------------------------------------------------------------------------------
def round_robin(team_ids: list[int]) -> list[list[tuple[int, int]]]:
    """Circle-method round robin. Returns weeks -> [(home, away)]. Needs an even number of teams."""
    ids = list(team_ids)
    n = len(ids)
    weeks = []
    for r in range(n - 1):
        pairs = [(ids[i], ids[n - 1 - i]) for i in range(n // 2)]
        if r % 2:
            pairs = [(b, a) for a, b in pairs]
        weeks.append(pairs)
        ids = [ids[0]] + [ids[-1]] + ids[1:-1]      # rotate everyone but the first team
    return weeks


def generate_schedule(league: League, first_week: int = 1):
    """One matchup per team per week from `first_week` to the end of the season; the round robin repeats if the season is longer."""
    if db.session.scalar(db.select(Matchup.id).where(Matchup.league_id == league.id)):
        return
    season_weeks = SPORTS[league.sport.code]["season_days"] // SPORTS[league.sport.code]["days_per_week"]
    rounds = round_robin([t.id for t in teams_of(league.id)])
    if first_week == 1:
        rounds = rounds[:season_weeks] if len(rounds) > season_weeks else rounds
    for w in range(first_week, season_weeks + 1):
        for home, away in rounds[(w - first_week) % len(rounds)]:
            db.session.add(Matchup(league_id=league.id, week=w, home_team_id=home, away_team_id=away))
    league.first_week = first_week


def standings(league: League) -> list[dict]:
    teams = {t.id: t for t in teams_of(league.id)}
    rec = {tid: dict(team_id=tid, team=t.name, manager=t.manager.display_name, is_bot=t.is_bot, w=0, l=0, t=0, pf=0.0, pa=0.0, results=[])
           for tid, t in teams.items()}
    for m in db.session.scalars(db.select(Matchup).where(Matchup.league_id == league.id, Matchup.final.is_(True)).order_by(Matchup.week)):
        for tid, mine, theirs in ((m.home_team_id, m.home_score, m.away_score), (m.away_team_id, m.away_score, m.home_score)):
            r = rec[tid]
            r["pf"] += mine
            r["pa"] += theirs
            res = "W" if mine > theirs else "L" if mine < theirs else "T"
            r[res.lower()] += 1
            r["results"].append(res)
    rows = sorted(rec.values(), key=lambda r: (-(r["w"] + 0.5 * r["t"]), -r["pf"]))
    cutoff = 6 if len(rows) >= 8 else 4
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
        r["pf"], r["pa"] = round(r["pf"], 1), round(r["pa"], 1)
        r["last5"] = "".join(r["results"][-5:])
        r["streak"] = _streak(r["results"])
        r["playoff"] = i <= cutoff
        del r["results"]
    return rows


def _streak(results: list[str]) -> str:
    if not results:
        return "-"
    n = 1
    while n < len(results) and results[-1 - n] == results[-1]:
        n += 1
    return f"{results[-1]}{n}"


def power_rankings(league: League) -> list[dict]:
    """POWER SCORE (0-100) = 50 * win% + 30 * (avg points / best avg points) + 20 * (last-3 avg / best last-3 avg).

    Wins matter most, but scoring volume and current form separate teams with equal records.
    """
    teams = teams_of(league.id)
    finals = list(db.session.scalars(db.select(Matchup).where(Matchup.league_id == league.id, Matchup.final.is_(True)).order_by(Matchup.week)))
    scores = {t.id: [] for t in teams}
    wins = {t.id: 0.0 for t in teams}
    for m in finals:
        scores[m.home_team_id].append(m.home_score)
        scores[m.away_team_id].append(m.away_score)
        if m.home_score != m.away_score:
            wins[m.home_team_id if m.home_score > m.away_score else m.away_team_id] += 1
        else:
            wins[m.home_team_id] += 0.5
            wins[m.away_team_id] += 0.5
    avg = {tid: (sum(s) / len(s) if s else 0.0) for tid, s in scores.items()}
    last3 = {tid: (sum(s[-3:]) / len(s[-3:]) if s else 0.0) for tid, s in scores.items()}
    best_avg, best_l3 = max(avg.values() or [1]) or 1, max(last3.values() or [1]) or 1
    rows = []
    for t in teams:
        gp = len(scores[t.id])
        wp = wins[t.id] / gp if gp else 0.5
        power = 50 * wp + 30 * (avg[t.id] / best_avg) + 20 * (last3[t.id] / best_l3)
        rows.append(dict(team_id=t.id, team=t.name, power=round(power, 1), win_pct=round(wp, 3), avg_points=round(avg[t.id], 1), last3=round(last3[t.id], 1)))
    rows.sort(key=lambda r: -r["power"])
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def log_activity(league_id: int, kind: str, message: str, day: int = 0):
    db.session.add(Activity(league_id=league_id, kind=kind, message=message, day=day))

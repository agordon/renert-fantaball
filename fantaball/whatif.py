"""What-If Machine (foundation): re-score a past day with a different lineup choice. Read-only - league history is never modified."""
from root import db
from models.fantasy import Athlete, DailyScore, FantasyTeam, League
from fantaball import stats as stats_svc
from fantaball.errors import bad_request, conflict
from fantaball.roster import eligible
from fantaball.scoring import score_stat_line


def lineup_swap(league: League, team: FantasyTeam, day: int, in_id: int, out_id: int) -> dict:
    """What if `in_id` had started in the slot where `out_id` actually started on `day`?"""
    if not 1 <= day <= league.current_day:
        raise bad_request("Choose a day that has already been simulated")
    out_row = db.session.scalar(db.select(DailyScore).where(
        DailyScore.league_id == league.id, DailyScore.team_id == team.id, DailyScore.athlete_id == out_id, DailyScore.day == day, DailyScore.counted.is_(True)))
    if out_row is None:
        raise conflict("That player did not play for your team in a starting slot on that day")
    a_in = db.session.get(Athlete, in_id)
    a_out = db.session.get(Athlete, out_id)
    if not a_in or a_in.sport_id != league.sport_id:
        raise bad_request("Unknown player")
    if not eligible(league.sport.code, out_row.slot, a_in.position_list, a_in.injury_status(day)):
        raise conflict(f"{a_in.name} was not eligible for the {out_row.slot} slot")
    rules = league.scoring.rules
    stats_in = next((s for d, s in stats_svc.game_log(league.sport_id).get(in_id, []) if d == day), None)
    fp_in = score_stat_line(stats_in, rules) if stats_in else 0.0
    delta = round(fp_in - out_row.points, 1)
    when = "played no game" if stats_in is None else f"scored {fp_in:.1f}"
    verdict = "would have gained" if delta > 0 else "would have lost" if delta < 0 else "would have broken even by"
    return dict(day=day, slot=out_row.slot, actual_points=out_row.points, alternative_points=fp_in, delta=delta,
                explanation=f"On day {day}, {a_out.name} scored {out_row.points:.1f} in your {out_row.slot} slot. {a_in.name} {when}. "
                            f"You {verdict} {abs(delta):.1f} points (history unchanged - this is only a simulation).")

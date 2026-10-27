"""Persist fantasy points for imported box scores.

One PlayerFantasyScore row = one (game stat line, scoring rule set). Because rows point at an immutable rule set,
  * leagues with identical rules share the rows (no duplicates),
  * changing a league's rules just selects another rule set (old results stay valid for history),
  * re-running is idempotent: existing rows are only touched when the computed points actually changed.
Only FINAL games are scored - scheduled / in-progress / postponed games never contribute.
"""
from dataclasses import dataclass

from root import db
from models.fantasy import Athlete, GameStat, League, PlayerFantasyScore, ProGame, ScoringConfig, ScoringRuleSet, Sport, utcnow
from fantaball.scoring import score_decimal

BATCH = 1500


@dataclass
class ScoreCounts:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


def rulesets_in_use(sport_id: int) -> list[ScoringRuleSet]:
    """Rule sets used by this sport's leagues, plus its stored templates (so the player pages can show points for them)."""
    used = db.select(ScoringConfig.ruleset_id).join(League, League.id == ScoringConfig.league_id).where(League.sport_id == sport_id, ScoringConfig.ruleset_id.is_not(None))
    return list(db.session.scalars(db.select(ScoringRuleSet).where(
        ScoringRuleSet.sport_id == sport_id, db.or_(ScoringRuleSet.id.in_(used), ScoringRuleSet.is_template.is_(True)))))


def recalculate(sport: Sport, *, stat_ids: set[int] | None = None, rulesets: list[ScoringRuleSet] | None = None) -> ScoreCounts:
    rulesets = rulesets if rulesets is not None else rulesets_in_use(sport.id)
    counts = ScoreCounts()
    q = (db.select(GameStat.id, GameStat.athlete_id, GameStat.pro_game_id, GameStat.day, GameStat.stats)
         .join(Athlete, Athlete.id == GameStat.athlete_id).join(ProGame, ProGame.id == GameStat.pro_game_id)
         .where(Athlete.sport_id == sport.id, ProGame.status == "final").order_by(GameStat.id))
    if stat_ids is not None:
        if not stat_ids:
            return counts
        ids = sorted(stat_ids)
        batches = [q.where(GameStat.id.in_(ids[i:i + BATCH])) for i in range(0, len(ids), BATCH)]
    else:
        batches = [q]
    now = utcnow()
    for bq in batches:
        rows = db.session.execute(bq).all()
        if not rows:
            continue
        for chunk_start in range(0, len(rows), BATCH):
            chunk = rows[chunk_start:chunk_start + BATCH]
            ids = [r.id for r in chunk]
            for rs in rulesets:
                existing = {p.game_stat_id: p for p in db.session.scalars(
                    db.select(PlayerFantasyScore).where(PlayerFantasyScore.ruleset_id == rs.id, PlayerFantasyScore.game_stat_id.in_(ids)))}
                for r in chunk:
                    points = score_decimal(r.stats, rs.rules)
                    row = existing.get(r.id)
                    if row is None:
                        db.session.add(PlayerFantasyScore(game_stat_id=r.id, athlete_id=r.athlete_id, pro_game_id=r.pro_game_id, day=r.day,
                                                          ruleset_id=rs.id, points=points, calculated_at=now))
                        counts.inserted += 1
                    elif row.points != points or row.day != r.day:
                        row.points, row.day, row.calculated_at = points, r.day, now
                        counts.updated += 1
                    else:
                        counts.skipped += 1
            db.session.commit()
    return counts


def points_for_day(ruleset_id: int, day: int) -> dict[int, float]:
    """{athlete_id: fantasy points} for one day under a rule set (stat lines that could not be scored are omitted)."""
    rows = db.session.execute(db.select(PlayerFantasyScore.athlete_id, PlayerFantasyScore.points).where(
        PlayerFantasyScore.ruleset_id == ruleset_id, PlayerFantasyScore.day == day, PlayerFantasyScore.points.is_not(None))).all()
    return {aid: float(p) for aid, p in rows}

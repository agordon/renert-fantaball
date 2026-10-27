"""Stored, versioned scoring rule sets (see models.fantasy.ScoringRuleSet)."""
from root import db
from models.fantasy import ScoringRuleSet, Sport
from fantaball.scoring import default_rules, rules_hash


def get_or_create_ruleset(sport_id: int, rules: dict, name: str | None = None, template: bool = False) -> ScoringRuleSet:
    """The rule set for exactly these weights (created on first use). Never modifies an existing rule set."""
    h = rules_hash(rules)
    rs = db.session.scalar(db.select(ScoringRuleSet).where(ScoringRuleSet.sport_id == sport_id, ScoringRuleSet.rules_hash == h))
    if rs is None:
        rs = ScoringRuleSet(sport_id=sport_id, rules_hash=h, rules=dict(rules), name=name, is_template=template)
        db.session.add(rs)
        db.session.flush()
    elif template and not rs.is_template:
        rs.is_template, rs.name = True, name or rs.name
    return rs


def ensure_default_template(sport: Sport) -> ScoringRuleSet:
    """Every sport gets a stored 'Standard points' template, so scoring choices are database data, not code."""
    return get_or_create_ruleset(sport.id, default_rules(_scoring_code(sport)), name="Standard points league", template=True)


def _scoring_code(sport: Sport) -> str:
    return sport.code

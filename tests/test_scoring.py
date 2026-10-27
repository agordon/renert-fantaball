import pytest
from decimal import Decimal

from fantaball.scoring import default_rules, rules_hash, score_decimal, score_float, validate_rules


def test_default_nba_scoring_formula():
    line = dict(pts=30, reb=10, ast=8, stl=2, blk=1, tov=4, fg3m=3)
    # 30*1 + 10*1.2 + 8*1.5 + 2*3 + 1*3 - 4*1 + 3*0.5
    assert score_decimal(line, default_rules("nba")) == Decimal("60.50")
    assert score_float(line, default_rules("nba")) == 60.5


def test_custom_rules_change_the_score():
    line = dict(pts=20, reb=10, ast=5)
    assert score_decimal(line, {"pts": 1, "reb": 1, "ast": 1}) == 35
    assert score_decimal(line, {"pts": 2, "reb": 0, "ast": 0}) == 40


def test_any_stat_names_work_so_other_sports_fit_the_same_engine():
    assert score_decimal(dict(g=1, a=2, sog=4), {"g": 6, "a": 4, "sog": 0.9}) == Decimal("17.60")


def test_validate_rules_rejects_bad_input():
    with pytest.raises(ValueError):
        validate_rules("nba", {"touchdowns": 6})
    with pytest.raises(ValueError):
        validate_rules("nba", {"pts": "lots"})
    with pytest.raises(ValueError):
        validate_rules("nba", {"pts": 500})
    with pytest.raises(ValueError):
        validate_rules("nba", {})
    assert validate_rules("nba", {"pts": 2, "reb": 1}) == {"pts": 2.0, "reb": 1.0}


# ------------------------------------------------------------------ strict / exact scoring used for real data


def test_score_decimal_is_exact_and_supports_negative_and_fractional_weights():
    rules = {"pts": 1, "reb": 1.2, "ast": 1.5, "stl": 3, "blk": 3, "tov": -1, "fg3m": 0.5}
    line = dict(pts=30, reb=10, ast=8, stl=2, blk=1, tov=4, fg3m=3)
    assert score_decimal(line, rules) == Decimal("60.50")
    assert score_decimal(dict(pts=7, reb=3, ast=0, stl=0, blk=0, tov=0, fg3m=0), rules) == Decimal("10.60")   # 7 + 3*1.2, no float noise
    assert score_decimal(dict(pts=0, tov=5), {"pts": 1, "tov": -2}) == Decimal("-10.00")


def test_score_decimal_rounds_half_up_to_cents():
    assert score_decimal({"pts": 1}, {"pts": 0.005}) == Decimal("0.01")
    assert score_decimal({"pts": 1}, {"pts": 0.004}) == Decimal("0.00")
    assert score_decimal({"pts": 3}, {"pts": 0.335}) == Decimal("1.01")


def test_score_decimal_missing_stat_is_not_scored_but_zero_is():
    rules = {"pts": 1, "blk": 3}
    assert score_decimal({"pts": 10, "blk": None}, rules) is None          # provider did not report blocks
    assert score_decimal({"pts": 10}, rules) is None
    assert score_decimal({"pts": 10, "blk": 0}, rules) == Decimal("10.00")   # a reported zero is a real zero
    assert score_decimal({"pts": 10}, {"pts": 1, "blk": 0}) == Decimal("10.00")   # a stat with weight 0 is irrelevant


def test_rules_hash_identifies_identical_weights():
    a = rules_hash({"pts": 1, "reb": 1.2})
    assert a == rules_hash({"reb": 1.2, "pts": 1.0})                         # order / int-vs-float do not matter
    assert a != rules_hash({"pts": 1, "reb": 1.3})

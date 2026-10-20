import pytest

from fantaball.scoring import default_rules, score_stat_line, validate_rules


def test_default_nba_scoring_formula():
    line = dict(pts=30, reb=10, ast=8, stl=2, blk=1, tov=4, fg3m=3)
    # 30*1 + 10*1.2 + 8*1.5 + 2*3 + 1*3 - 4*1 + 3*0.5
    assert score_stat_line(line, default_rules("nba")) == 30 + 12 + 12 + 6 + 3 - 4 + 1.5


def test_custom_rules_change_the_score():
    line = dict(pts=20, reb=10, ast=5)
    assert score_stat_line(line, {"pts": 1, "reb": 1, "ast": 1}) == 35
    assert score_stat_line(line, {"pts": 2, "reb": 0, "ast": 0}) == 40


def test_missing_stats_count_as_zero():
    assert score_stat_line({"pts": 10}, {"pts": 1, "reb": 5}) == 10


def test_nhl_uses_same_engine():
    assert score_stat_line(dict(g=1, a=2, sog=4), default_rules("nhl")) == 6 + 8 + 3.6


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

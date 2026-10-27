import pytest

from fantaball.draft import snake_team_slot
from tests.helpers import SMALL_ROSTER


def test_snake_order_12_teams():
    order = [snake_team_slot(o, 12) for o in range(1, 37)]
    assert order[:12] == list(range(1, 13))
    assert order[12:24] == list(range(12, 0, -1))      # round 2 reverses
    assert order[24:36] == list(range(1, 13))
    # every team picks exactly once per round
    for r in range(3):
        assert sorted(order[r * 12:(r + 1) * 12]) == list(range(1, 13))


def test_create_league_validation(nba_data, alice):
    post = lambda **kw: alice.post("/api/leagues", {"sport": "nba", "roster_config": SMALL_ROSTER, **kw})
    assert post(name="x")[0] == 400
    assert post(name="Valid name", num_teams=7)[0] == 400
    assert alice.post("/api/leagues", {"name": "Valid name", "sport": "nhl"})[0] == 400      # no such data set
    assert post(name="Valid name", scoring_rules={"bogus": 1})[0] == 400
    assert alice.post("/api/leagues", {"sport": "nba", "name": "Valid name", "roster_config": [["PG", 99]]})[0] == 400
    s, lg = post(name="Alice League", num_teams=8, scoring_rules={"pts": 1, "reb": 2})
    assert s == 201 and lg["is_commissioner"] and lg["status"] == "pre_draft" and lg["data_source"] == "mock"
    s, detail = alice.get(f"/api/leagues/{lg['id']}")
    assert detail["scoring_rules"] == {"pts": 1.0, "reb": 2.0}
    assert len(detail["teams"]) == 8 and len(detail["invite_code"]) == 8


def test_join_league_by_code_and_access_control(nba_data, alice, bob):
    _, lg = alice.post("/api/leagues", {"sport": "nba", "name": "Join Me", "num_teams": 4, "roster_config": SMALL_ROSTER})
    lid = lg["id"]
    assert bob.get(f"/api/leagues/{lid}")[0] == 403                      # non-member cannot read
    assert bob.post("/api/leagues/join", {"code": "NOSUCH00"})[0] == 404
    _, detail = alice.get(f"/api/leagues/{lid}")
    s, joined = bob.post("/api/leagues/join", {"code": detail["invite_code"], "team_name": "Bob's Bombers"})
    assert s == 200
    assert bob.post("/api/leagues/join", {"code": detail["invite_code"]})[0] == 409   # already a member
    assert bob.get(f"/api/leagues/{lid}")[0] == 200
    # only the commissioner may change settings / start the draft
    assert bob.patch(f"/api/leagues/{lid}", {"name": "Hijacked"})[0] == 403
    assert bob.post(f"/api/leagues/{lid}/draft/start", {})[0] == 403
    assert alice.patch(f"/api/leagues/{lid}", {"name": "Renamed league"})[0] == 200


def test_full_draft_enforces_turn_order_and_uniqueness(nba_data, alice):
    _, lg = alice.post("/api/leagues", {"sport": "nba", "name": "Draft Test", "num_teams": 6, "roster_config": SMALL_ROSTER})
    lid = lg["id"]
    s, st = alice.post(f"/api/leagues/{lid}/draft/start", {"pick_seconds": 60})
    assert s == 200 and st["session"]["status"] == "live"
    me = st["my_team_id"]
    # Make sure it's alice's turn (let computer managers pick first if needed) - she must not be able to pick out of turn
    if st["session"]["on_clock_team_id"] != me:
        pool_id = st["pool"][0]["id"]
        assert alice.post(f"/api/leagues/{lid}/draft/pick", {"athlete_id": pool_id})[0] == 403
        while True:
            s, st = alice.post(f"/api/leagues/{lid}/draft/advance", {})
            if st["session"]["on_clock_team_id"] == me:
                break
    s, st = alice.get(f"/api/leagues/{lid}/draft")
    first = st["pool"][0]["id"]
    assert alice.post(f"/api/leagues/{lid}/draft/pick", {"athlete_id": first})[0] == 200
    # advance computer picks until alice's next turn, then try to take the same player again
    while True:
        s, st = alice.post(f"/api/leagues/{lid}/draft/advance", {})
        if st["session"]["on_clock_team_id"] == me:
            break
    assert alice.post(f"/api/leagues/{lid}/draft/pick", {"athlete_id": first})[0] == 409     # already drafted
    # assistant works while live
    s, assist = alice.get(f"/api/leagues/{lid}/draft/assistant")
    assert s == 200 and assist["best_available"]
    # finish the draft
    s, st = alice.post(f"/api/leagues/{lid}/draft/sim", {"to_end": True})
    assert st["session"]["status"] == "complete"
    picks = st["picks"]
    assert len(picks) == 6 * st["session"]["rounds"]
    assert len({p["athlete"]["id"] for p in picks}) == len(picks)                            # nobody drafted twice
    assert [p["overall"] for p in picks] == list(range(1, len(picks) + 1))
    # rosters were created, league is active, schedule exists
    s, team = alice.get(f"/api/leagues/{lid}/team")
    assert team["league"]["status"] == "active"
    assert len(team["players"]) == st["session"]["rounds"]
    assert alice.get(f"/api/leagues/{lid}/matchup")[0] == 200
    s, st2 = alice.get(f"/api/leagues/{lid}/draft")
    assert st2["session"]["status"] == "complete"

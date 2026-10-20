"""Roster edits, add/drop, trades, matchup scoring and persistence on a freshly drafted 4-team league."""
import pytest

from fantaball.scoring import score_stat_line


def make_active_league(client, name="Active League", teams=4):
    _, lg = client.post("/api/leagues", {"name": name, "num_teams": teams})
    lid = lg["id"]
    client.post(f"/api/leagues/{lid}/draft/start", {})
    client.post(f"/api/leagues/{lid}/draft/sim", {"to_end": True})
    return lid


@pytest.fixture()
def league(alice):
    return make_active_league(alice)


def team(client, lid, team_id=None):
    s, t = client.get(f"/api/leagues/{lid}/team" + (f"?team_id={team_id}" if team_id else ""))
    assert s == 200
    return t


def test_lineup_edit_validates_and_persists(alice, league):
    t = team(alice, league)
    assignment = {p["id"]: p["slot"] for p in t["players"]}
    starters = [p for p in t["players"] if p["slot"] not in ("BN", "IR")]
    bench = [p for p in t["players"] if p["slot"] == "BN"]
    # illegal: unknown slot
    bad = dict(assignment)
    bad[bench[0]["id"]] = "XX"
    assert alice.put(f"/api/leagues/{league}/lineup", {"assignment": {str(k): v for k, v in bad.items()}})[0] == 400
    # illegal: missing players
    partial = dict(list(assignment.items())[:3])
    assert alice.put(f"/api/leagues/{league}/lineup", {"assignment": {str(k): v for k, v in partial.items()}})[0] == 400
    # legal: swap a UTIL starter with a healthy bench player (UTIL / BN accept anyone)
    util = next(p for p in starters if p["slot"] == "UTIL")
    ok_bench = next(p for p in bench if p["injury"] == "HEALTHY")
    new = dict(assignment)
    new[util["id"]], new[ok_bench["id"]] = "BN", "UTIL"
    s, res = alice.put(f"/api/leagues/{league}/lineup", {"assignment": {str(k): v for k, v in new.items()}})
    assert s == 200
    # persistence: a brand-new request reads the saved lineup
    again = {p["id"]: p["slot"] for p in team(alice, league)["players"]}
    assert again[ok_bench["id"]] == "UTIL" and again[util["id"]] == "BN"


def test_position_eligibility_enforced_on_server(alice, league):
    t = team(alice, league)
    assignment = {p["id"]: p["slot"] for p in t["players"]}
    # put a player who cannot play C into the C slot
    c_holder = next(p for p in t["players"] if p["slot"] == "C")
    wrong = next(p for p in t["players"] if p["slot"] == "BN" and "C" not in p["positions"].split(","))
    bad = dict(assignment)
    bad[wrong["id"]], bad[c_holder["id"]] = "C", "BN"
    s, res = alice.put(f"/api/leagues/{league}/lineup", {"assignment": {str(k): v for k, v in bad.items()}})
    assert s == 400 and "not eligible" in res["error"]


def test_cannot_edit_other_teams_or_leagues(alice, bob, league):
    assert bob.put(f"/api/leagues/{league}/lineup", {"assignment": {}})[0] == 403
    assert bob.post(f"/api/leagues/{league}/add-drop", {"add_id": 1})[0] == 403
    assert bob.post(f"/api/leagues/{league}/simulate", {"days": 1})[0] == 403


def test_add_drop_ownership_rules(alice, league):
    t = team(alice, league)
    _, pool = alice.get(f"/api/leagues/{league}/players?status=available&limit=5&sort=proj")
    fa = pool["players"][0]
    _, others = alice.get(f"/api/leagues/{league}/players?status=owned&limit=200")
    owned_elsewhere = next(p for p in others["players"] if p["owner_team_id"] != t["team"]["id"])
    mine = t["players"][-1]
    # the draft leaves the 14th (IR) spot open, so one add without a drop is legal...
    extra = pool["players"][1]
    assert alice.post(f"/api/leagues/{league}/add-drop", {"add_id": extra["id"]})[0] == 200
    # ...after that the roster is full: adding without a drop is rejected
    assert alice.post(f"/api/leagues/{league}/add-drop", {"add_id": fa["id"]})[0] == 409
    t = team(alice, league)
    mine = t["players"][-1]
    # cannot add a player another team owns
    assert alice.post(f"/api/leagues/{league}/add-drop", {"add_id": owned_elsewhere["id"], "drop_id": mine["id"]})[0] == 409
    # cannot drop a player you do not own
    assert alice.post(f"/api/leagues/{league}/add-drop", {"add_id": fa["id"], "drop_id": owned_elsewhere["id"]})[0] == 403
    # valid swap
    s, res = alice.post(f"/api/leagues/{league}/add-drop", {"add_id": fa["id"], "drop_id": mine["id"]})
    assert s == 200
    ids = {p["id"] for p in res["players"]}
    assert fa["id"] in ids and mine["id"] not in ids and len(ids) == len(t["players"])
    # the dropped player is a free agent again; the added one is owned
    _, now_free = alice.get(f"/api/leagues/{league}/players?status=available&limit=200&search={mine['name'].split()[1]}")
    assert any(p["id"] == mine["id"] for p in now_free["players"])
    _, still_free = alice.get(f"/api/leagues/{league}/players?status=available&limit=200")
    assert all(p["id"] != fa["id"] for p in still_free["players"])


def test_trade_preview_and_authorization(alice, bob, league):
    me = team(alice, league)
    _, detail = alice.get(f"/api/leagues/{league}")
    bot = next(t for t in detail["teams"] if t["is_bot"])
    theirs = team(alice, league, bot["id"])
    give, get = [me["players"][2]["id"]], [theirs["players"][2]["id"]]
    s, a = alice.post(f"/api/leagues/{league}/trades/analyze", {"to_team_id": bot["id"], "give_ids": give, "get_ids": get})
    assert s == 200 and "weekly_change" in a["team_a"] and a["disclaimer"]
    # cannot offer a player you do not own / trade with yourself
    assert alice.post(f"/api/leagues/{league}/trades/analyze", {"to_team_id": bot["id"], "give_ids": get, "get_ids": give})[0] in (403, 409)
    assert alice.post(f"/api/leagues/{league}/trades/analyze", {"to_team_id": me["team"]["id"], "give_ids": give, "get_ids": get})[0] == 400
    # an outsider cannot touch the league's trades
    assert bob.post(f"/api/leagues/{league}/trades/analyze", {"to_team_id": bot["id"], "give_ids": give, "get_ids": get})[0] == 403


def test_trade_is_atomic_and_only_recipient_can_accept(alice, bob):
    # two humans in one league: alice (commissioner) + bob joined into a bot seat
    _, lg = alice.post("/api/leagues", {"name": "Two Humans", "num_teams": 4})
    lid = lg["id"]
    _, d = alice.get(f"/api/leagues/{lid}")
    assert bob.post("/api/leagues/join", {"code": d["invite_code"]})[0] == 200
    alice.post(f"/api/leagues/{lid}/draft/start", {})
    alice.post(f"/api/leagues/{lid}/draft/sim", {"to_end": True})
    a_team, b_team = team(alice, lid), team(bob, lid)
    give, get = [a_team["players"][1]["id"]], [b_team["players"][1]["id"]]
    s, res = alice.post(f"/api/leagues/{lid}/trades", {"to_team_id": b_team["team"]["id"], "give_ids": give, "get_ids": get})
    assert s == 201
    oid = res["offer"]["id"]
    assert alice.post(f"/api/leagues/{lid}/trades/{oid}/accept")[0] == 403          # proposer cannot accept own offer
    # alice drops the offered player; accepting the now-invalid offer must fail and change nothing
    _, pool = alice.get(f"/api/leagues/{lid}/players?status=available&limit=1")
    assert alice.post(f"/api/leagues/{lid}/add-drop", {"add_id": pool["players"][0]["id"], "drop_id": give[0]})[0] == 200
    s, _ = bob.post(f"/api/leagues/{lid}/trades/{oid}/accept")
    assert s in (403, 409)
    assert {p["id"] for p in team(bob, lid)["players"]} == {p["id"] for p in b_team["players"]}
    # a fresh valid offer: accept swaps both rosters consistently and keeps sizes
    a_now, b_now = team(alice, lid), team(bob, lid)
    give2, get2 = [a_now["players"][2]["id"]], [b_now["players"][2]["id"]]
    _, res = alice.post(f"/api/leagues/{lid}/trades", {"to_team_id": b_now["team"]["id"], "give_ids": give2, "get_ids": get2})
    oid2 = res["offer"]["id"]
    assert bob.post(f"/api/leagues/{lid}/trades/{oid2}/accept")[0] == 200
    a_after, b_after = team(alice, lid), team(bob, lid)
    assert get2[0] in {p["id"] for p in a_after["players"]} and give2[0] in {p["id"] for p in b_after["players"]}
    assert len(a_after["players"]) == len(a_now["players"]) and len(b_after["players"]) == len(b_now["players"])
    all_ids = [p["id"] for p in a_after["players"]] + [p["id"] for p in b_after["players"]]
    assert len(all_ids) == len(set(all_ids))
    assert bob.post(f"/api/leagues/{lid}/trades/{oid2}/accept")[0] == 409           # cannot accept twice
    _, trades = alice.get(f"/api/leagues/{lid}/trades")
    assert any(o["id"] == oid2 for o in trades["completed"])


def test_simulation_scores_use_league_rules_and_persist(alice):
    lid = make_active_league(alice, "Sim League")
    assert alice.post(f"/api/leagues/{lid}/simulate", {"days": 3})[0] == 200
    _, m = alice.get(f"/api/leagues/{lid}/matchup")
    side = m["matchup"]["home"] if m["matchup"]["home"]["team_id"] == m["my_team_id"] else m["matchup"]["away"]
    assert side["points"] == round(sum(p["points"] for p in side["players"]), 1)
    assert side["points"] > 0
    # recompute one starter's points from his raw game log with the league's scoring rules
    _, detail = alice.get(f"/api/leagues/{lid}")
    rules = detail["scoring_rules"]
    starter = next(p for p in side["players"] if p["slot"] not in ("BN", "IR") and p["points"] > 0)
    _, prof = alice.get(f"/api/leagues/{lid}/players/{starter['athlete_id']}")
    days = {int(d) for d in starter["daily"]}
    expected = sum(score_stat_line(g["stats"], rules) for g in prof["game_log"] if g["day"] in days)
    assert round(expected, 1) == starter["points"]
    assert alice.get(f"/api/leagues/{lid}")[1]["current_day"] == 3


def test_origin_and_content_type_checks(flask_app, demo):
    c = flask_app.test_client()
    r = c.patch("/api/me", json={"display_name": "Evil"}, headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    r = c.patch("/api/me", data="display_name=x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415
    r = c.patch("/api/me", json={"display_name": "Demo Coach"}, headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert demo.patch("/api/me", {"display_name": "<>"})[0] == 400

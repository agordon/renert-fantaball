"""Trade API: propose / analyze / accept / decline, pending and completed offers. Computer managers answer immediately."""
from root import db
from models.fantasy import FantasyTeam, TradeOffer
from fantaball import leagues as league_svc
from fantaball import transactions as tx
from fantaball.errors import forbidden, not_found
from fantaball.trade_analysis import analyze_trade
from views.api_common import api, body, int_list, need_int


def _offer_json(o: TradeOffer, names: dict, my_team_id: int) -> dict:
    return dict(id=o.id, status=o.status, from_team_id=o.from_team_id, to_team_id=o.to_team_id, from_team=names[o.from_team_id],
                to_team=names[o.to_team_id], note=o.note, response_note=o.response_note, created_at=o.created_at.isoformat(),
                resolved_at=o.resolved_at.isoformat() if o.resolved_at else None, incoming=o.to_team_id == my_team_id,
                outgoing=o.from_team_id == my_team_id,
                sends=[dict(id=i.athlete_id, name=i.athlete.name, positions=i.athlete.positions, team=i.athlete.pro_team.abbr)
                       for i in o.items if i.from_team_id == o.from_team_id],
                receives=[dict(id=i.athlete_id, name=i.athlete.name, positions=i.athlete.positions, team=i.athlete.pro_team.abbr)
                          for i in o.items if i.from_team_id == o.to_team_id])


def _offer(lg, offer_id) -> TradeOffer:
    o = db.session.get(TradeOffer, offer_id)
    if not o or o.league_id != lg.id:
        raise not_found("Offer not found")
    return o


@api("/leagues/<int:league_id>/trades")
def list_trades(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    names = {t.id: t.name for t in league_svc.teams_of(lg.id)}
    offers = db.session.scalars(db.select(TradeOffer).where(TradeOffer.league_id == lg.id).order_by(TradeOffer.id.desc()))
    rows = [_offer_json(o, names, team.id) for o in offers]
    return dict(pending=[r for r in rows if r["status"] == "pending" and (r["incoming"] or r["outgoing"])],
                completed=[r for r in rows if r["status"] == "accepted"], other=[r for r in rows if r["status"] in ("declined", "cancelled")][:20])


def _partner_and_terms(lg, team):
    d = body()
    partner = db.session.get(FantasyTeam, need_int(d, "to_team_id"))
    if not partner or partner.league_id != lg.id:
        raise not_found("Trade partner not found")
    give, get = int_list(d, "give_ids"), int_list(d, "get_ids")
    tx.validate_trade_terms(lg, team, partner, give, get)
    return partner, give, get, d


@api("/leagues/<int:league_id>/trades/analyze", methods=("POST",))
def trade_analyze(me, league_id):
    """Preview only - nothing is saved."""
    lg, team = league_svc.membership(me, league_id)
    partner, give, get, _ = _partner_and_terms(lg, team)
    return analyze_trade(lg, team, partner, give, get)


@api("/leagues/<int:league_id>/trades", methods=("POST",))
def trade_propose(me, league_id):
    lg, team = league_svc.membership(me, league_id)
    partner, give, get, d = _partner_and_terms(lg, team)
    offer = tx.propose_trade(lg, team, partner.id, give, get, d.get("note") if isinstance(d.get("note"), str) else None)
    ai = None
    if partner.is_bot:      # a computer manager decides right away, using the same analysis the user sees
        analysis = analyze_trade(lg, team, partner, give, get)
        if analysis["ai_would_accept"]:
            tx.accept_trade(lg, offer, partner, "Accepted by computer manager")
        else:
            tx.decline_or_cancel(lg, offer, partner, analysis["ai_reason"])
        ai = dict(accepted=offer.status == "accepted", reason=analysis["ai_reason"])
    names = {t.id: t.name for t in league_svc.teams_of(lg.id)}
    return dict(offer=_offer_json(offer, names, team.id), ai_response=ai), 201


@api("/leagues/<int:league_id>/trades/<int:offer_id>/accept", methods=("POST",))
def trade_accept(me, league_id, offer_id):
    lg, team = league_svc.membership(me, league_id)
    offer = tx.accept_trade(lg, _offer(lg, offer_id), team)
    return _offer_json(offer, {t.id: t.name for t in league_svc.teams_of(lg.id)}, team.id)


@api("/leagues/<int:league_id>/trades/<int:offer_id>/decline", methods=("POST",))
def trade_decline(me, league_id, offer_id):
    lg, team = league_svc.membership(me, league_id)
    offer = tx.decline_or_cancel(lg, _offer(lg, offer_id), team)
    return _offer_json(offer, {t.id: t.name for t in league_svc.teams_of(lg.id)}, team.id)

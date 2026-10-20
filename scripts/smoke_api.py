import json, app
c = app.app.test_client()
def g(url, **kw):
    r = c.get(url, **kw)
    print(r.status_code, url, (r.get_data(as_text=True)[:150] if r.status_code!=200 else ""))
    return r.get_json()
me = g("/api/me"); print(me)
ls = g("/api/leagues"); print(json.dumps(ls)[:300])
L = ls[0]["id"]
for p in ["", "/dashboard", "/team", "/players?limit=3", "/players/5", "/compare?ids=1,2", "/matchup", "/matchups", "/standings", "/activity", "/transactions", "/trades", "/draft"]:
    d = g(f"/api/leagues/{L}{p}")
dash = g(f"/api/leagues/{L}/dashboard"); print(json.dumps(dash["matchup"]), dash["record"]); print(dash["gm"]["summary"]); print(dash["gm"]["suggestions"][:2])
tr = g(f"/api/leagues/{L}/trades"); print(len(tr["pending"]), len(tr["completed"]))

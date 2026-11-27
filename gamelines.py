"""Game lines: calls on each game's total (over/under) and point spread (v2, Nov 27 2026).

Each game gets a predicted score from team power ratings (ratings.py: offense and defense for every
team, adjusted for opponents and home field). That prediction becomes a chance against the Vegas
number, and is blended with Vegas' own chance (bookmaker's cut removed):

    chance = w * our model + (1 - w) * Vegas      (w per league and market, refit every Monday)

The call is the same edge rule as the props (calib.decide): green PLAY when the better side beats
what its odds need by 3+ points, yellow LEAN 0-3, red PASS when neither side does. STRONG at +6.

Scores come from ESPN team schedules (regular season, current season).
"""
import concurrent.futures as cf
import datetime as dt
import json

from build_board import ESPN_SPORT, get, implied, num
import calib
import ratings

def team_log(league, tid):
    """Completed regular-season games, newest first: event, pf (points for), pa (points against)."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT[league]}/{league}/teams/{tid}/schedule"
    try:
        d = json.loads(get(url))
    except Exception:
        return None
    out = []
    for e in d.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        if not ((c.get("status") or {}).get("type") or {}).get("completed"):
            continue
        me = next((x for x in c.get("competitors", []) if str(x["team"]["id"]) == str(tid)), None)
        op = next((x for x in c.get("competitors", []) if str(x["team"]["id"]) != str(tid)), None)
        if not me or not op:
            continue
        pf, pa = num(str((me.get("score") or {}).get("value", ""))), num(str((op.get("score") or {}).get("value", "")))
        if pf is None or pa is None:
            continue
        out.append({"event": str(e["id"]), "date": e.get("date"), "pf": pf, "pa": pa})
    out.sort(key=lambda g: g["date"] or "", reverse=True)
    return out


def _line(v):
    v = str(v or "").strip().lower().lstrip("ou")
    if v in ("pk", "pick", "even"):
        return 0.0
    return num(v.replace("+", ""))


def build(games, league, season=None):
    """Adds g["lines"] = {"total": {...}, "spread": {...}} to each game of this league."""
    lg = league.lower()
    todo = [g for g in games if g.get("league") == league and g.get("espnAway") and g.get("espnHome")]
    if not todo:
        return
    season = season if season is not None else ratings.season_games(lg)
    R = ratings.Ratings(lg, season)
    W = calib.model()["games"]
    for g in todo:
        a, h = g["teams"].get("away") or {}, g["teams"].get("home") or {}
        aw, hm = str(g["espnAway"]), str(g["espnHome"])
        out = {}
        # ---- total
        tot, totu = (a.get("total") or {}), (h.get("total") or {})
        line = _line(tot.get("v"))
        if line:
            c = ratings.chances(R, hm, aw, line, None)
            vg, vgu = implied(tot.get("odds")), implied(totu.get("odds"))
            mk = calib.no_vig(vg, vgu)
            if c and mk is not None:
                w = W.get(f"{league}|Total", 0.25)
                p = round(w * c["over"] + (1 - w) * mk, 1)
                d = calib.decide(p, tot.get("odds"), totu.get("odds"))
                out["total"] = {"line": line, "overOdds": tot.get("odds"), "underOdds": totu.get("odds"),
                                "vegas": vg, "vegasU": vgu, "market": round(mk, 1), "model": round(c["over"], 1),
                                "w": w, "proj": round(p), **d,
                                "expected": c["total"], "score": [c["away"], c["home"]]}
        # ---- spread (from the away side's number: +2.5 means away gets 2.5 points)
        sp, sph = (a.get("spread") or {}), (h.get("spread") or {})
        s = _line(sp.get("v"))
        if s is not None and sp.get("v"):
            c = ratings.chances(R, hm, aw, None, s)
            vg, vgh = implied(sp.get("odds")), implied(sph.get("odds"))
            mk = calib.no_vig(vg, vgh)
            if c and mk is not None:
                w = W.get(f"{league}|Spread", 0.25)
                p = round(w * c["awayCover"] + (1 - w) * mk, 1)       # chance the away side covers
                d = calib.decide(p, sp.get("odds"), sph.get("odds"))  # "over" = away, "under" = home
                side = "away" if d["side"] == "over" else "home"
                team = a if side == "away" else h
                num_ = s if side == "away" else -s
                # our own line: the predicted margin, from the away side's view
                ours = -c["margin"]
                out["spread"] = {"line": s, "awayOdds": sp.get("odds"), "homeOdds": sph.get("odds"),
                                 "vegas": vg, "vegasH": vgh, "market": round(mk, 1), "model": round(c["awayCover"], 1),
                                 "w": w, "proj": round(p), "side": side, "chance": d["chance"], "edge": d["edge"],
                                 "call": d["call"], "strong": d["strong"],
                                 "team": team.get("name"),
                                 "pick": f"{team.get('name')} {'+' if num_ > 0 else ''}{num_:g}" if num_ else f"{team.get('name')} PK",
                                 "ourLine": round(ours, 1), "score": [c["away"], c["home"]]}
        if out:
            g["lines"] = out


def refit_weights(data_dir, today, season_by_league, days=42, min_n=40):
    """Grid-search each market's model weight (0 to 0.6) on the last 6 weeks of graded game calls:
    the weight whose blended chance would have scored best. Fewer than 40 graded: keep the old one."""
    import glob
    import os
    since = (today - dt.timedelta(days=days)).isoformat()
    rows = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "gamepicks", "*.json"))):
        if os.path.basename(path)[:-5] < since:
            continue
        for p in json.load(open(path))["picks"].values():
            if p.get("r") not in ("over", "under", "home", "away"):
                continue
            rows.setdefault(f"{p['lg']}|{p['s']}", []).append(p)
    weights, note, cache = {}, {}, {}
    for key, ps in rows.items():
        lg = key.split("|")[0].lower()
        season = season_by_league.get(lg) or []
        by_ev = {g["event"]: g for g in season}
        pts = []
        for p in ps:
            g = by_ev.get(str(p["ev"]))
            if not g:
                continue
            day = g["date"][:10]
            if (lg, day) not in cache:
                cache[(lg, day)] = ratings.Ratings(lg, [q for q in season if q["date"] < g["date"]])
            R = cache[(lg, day)]
            if p["s"] == "Total":
                c = ratings.chances(R, g["home"], g["away"], p["line"], None, g["neutral"])
                model, y = c and c["over"], p["r"] == "over"
                mk = p.get("mk")
                if mk is None and p.get("vg") is not None:  # older picks saved only their own side's price
                    mk = p["vg"] / 1.045 if p.get("side") == "over" else 100 - p["vg"] / 1.045
            else:
                c = ratings.chances(R, g["home"], g["away"], None, p["line"], g["neutral"])
                model, y = c and c["awayCover"], p["r"] == "away"
                mk = p.get("mk")
                if mk is None and p.get("vg") is not None:
                    mk = p["vg"] / 1.045 if p.get("side") == "away" else 100 - p["vg"] / 1.045
            if model is None or mk is None:
                continue
            pts.append((model, mk, 1.0 if y else 0.0))
        if len(pts) < min_n:
            note[key] = {"n": len(pts), "kept": True}
            continue
        best = None
        for i in range(0, 13):
            w = i * 0.05
            b = sum(((w * m + (1 - w) * k) / 100 - y) ** 2 for m, k, y in pts) / len(pts)
            if best is None or b < best[1] - 1e-6:
                best = (w, b)
        vegas = sum((k / 100 - y) ** 2 for m, k, y in pts) / len(pts)
        weights[key] = round(best[0], 2)
        note[key] = {"n": len(pts), "w": round(best[0], 2), "blend": round(best[1], 4), "vegas": round(vegas, 4)}
    return {"weights": weights, "note": note}


def final_score(league, event, home_tid, cache):
    """(away points, home points) once the game is final, else None."""
    if home_tid not in cache:
        cache[home_tid] = team_log(league.lower(), home_tid)
    for x in cache[home_tid] or []:
        if x["event"] == str(event):
            return x["pa"], x["pf"]
    return None

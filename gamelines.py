"""Game lines: calls on each game's total (over/under) and point spread, same idea as the props.

Total:  for each team, how often its games this season (and its last 5) went over today's total.
        Form % = 60% season + 40% last 5, averaged over the two teams; Projected % = 75% Form +
        25% the Vegas % of the over. Green OVER / yellow LEAN / red UNDER, as for props.
Spread: how often the away team would have covered today's number (its own margins), and how
        often the home team would have failed to cover its side; same 60/40 and Vegas blend. The
        call names the likelier side: green at 58%+, yellow below that. STRONG at 70%+.

Scores come from ESPN team schedules (regular season, current season).
"""
import concurrent.futures as cf
import datetime as dt
import json

from build_board import ESPN_SPORT, get, implied, num
import calib

MIN_GAMES = 3


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


def _rate(xs, test):
    xs = list(xs)
    return (sum(1 for x in xs if test(x)) / len(xs)) if xs else None


def _form(log, test):
    """60% season rate + 40% last-5 rate (leaning on the last 5 with few games), as a %."""
    if not log or len(log) < MIN_GAMES:
        return None
    s, l5 = _rate(log, test), _rate(log[:5], test)
    w = 0.6 if len(log) >= 5 else 0.6 * len(log) / 5
    return 100 * (w * s + (1 - w) * l5)


def _line(v):
    v = str(v or "").strip().lower().lstrip("ou")
    if v in ("pk", "pick", "even"):
        return 0.0
    return num(v.replace("+", ""))


def build(games, league):
    """Adds g["lines"] = {"total": {...}, "spread": {...}} to each game of this league."""
    lg = league.lower()
    todo = [g for g in games if g.get("league") == league and g.get("espnAway") and g.get("espnHome")]
    tids = sorted({t for g in todo for t in (g["espnAway"], g["espnHome"])})
    with cf.ThreadPoolExecutor(8) as ex:
        logs = dict(zip(tids, ex.map(lambda t: team_log(lg, t), tids)))
    for g in todo:
        a, h = g["teams"].get("away") or {}, g["teams"].get("home") or {}
        la, lh = logs.get(g["espnAway"]), logs.get(g["espnHome"])
        out = {}
        # ---- total
        tot = (a.get("total") or {})
        line = _line(tot.get("v"))
        if line and la and lh:
            fa = _form(la, lambda x: x["pf"] + x["pa"] > line)
            fh = _form(lh, lambda x: x["pf"] + x["pa"] > line)
            if fa is not None and fh is not None:
                form = round((fa + fh) / 2)
                vg = implied(tot.get("odds"))
                vgu = implied((h.get("total") or {}).get("odds"))
                proj = calib.project(form, vg)
                c = calib.call(proj)
                avg = lambda log: sum(x["pf"] for x in log) / len(log)
                allow = lambda log: sum(x["pa"] for x in log) / len(log)
                exp = ((avg(la) + allow(lh)) / 2) + ((avg(lh) + allow(la)) / 2)
                out["total"] = {"line": line, "overOdds": tot.get("odds"), "underOdds": (h.get("total") or {}).get("odds"),
                                "vegas": vg, "vegasU": vgu, "form": form, "proj": proj, "call": c,
                                "strong": calib.strong(proj), "expected": round(exp, 1),
                                "awayAvg": round(sum(x["pf"] + x["pa"] for x in la) / len(la), 1),
                                "homeAvg": round(sum(x["pf"] + x["pa"] for x in lh) / len(lh), 1)}
        # ---- spread (from the away side's number: +2.5 means away gets 2.5 points)
        sp = (a.get("spread") or {})
        s = _line(sp.get("v"))
        if s is not None and sp.get("v") and la and lh:
            fa = _form(la, lambda x: x["pf"] - x["pa"] + s > 0)      # away team would cover +s
            fh = _form(lh, lambda x: x["pf"] - x["pa"] - s < 0)      # home team would fail to cover -s
            if fa is not None and fh is not None:
                form = round((fa + fh) / 2)
                vg = implied(sp.get("odds"))
                proj = calib.project(form, vg)            # chance the away side covers
                side = "away" if proj >= 50 else "home"
                chance = proj if side == "away" else 100 - proj
                team = a if side == "away" else h
                num_ = s if side == "away" else -s
                out["spread"] = {"line": s, "awayOdds": sp.get("odds"), "homeOdds": (h.get("spread") or {}).get("odds"),
                                 "vegas": vg, "form": form, "proj": proj, "side": side,
                                 "team": team.get("name"), "pick": f"{team.get('name')} {'+' if num_ > 0 else ''}{num_:g}" if num_ else f"{team.get('name')} PK",
                                 "chance": chance, "call": "hit" if chance >= calib.GREEN else "lean",
                                 "strong": chance >= calib.STRONG_OVER,
                                 "awayCover": round(fa), "homeFail": round(fh)}
        if out:
            g["lines"] = out


def final_score(league, event, home_tid, cache):
    """(away points, home points) once the game is final, else None."""
    if home_tid not in cache:
        cache[home_tid] = team_log(league.lower(), home_tid)
    for x in cache[home_tid] or []:
        if x["event"] == str(event):
            return x["pa"], x["pf"]
    return None

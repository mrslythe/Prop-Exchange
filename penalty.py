"""Penny Blocks: five parlays per league built from the board's highest projected props.

Each parlay takes one stat, picks the props with the highest Projected % for it (one leg per
player, green calls only, no injured players, same-game legs allowed), and prices the parlay from
each leg's best available over odds.
"""

# (stat label, legs) per league. Same-game legs are allowed.
PARLAYS = {
    "NFL": [("Anytime TD", 4), ("Rec Yds", 3), ("Rush Yds", 3), ("Receptions", 3), ("Pass Yds", 3)],
    "NBA": [("Points", 3), ("Rebounds", 3), ("Assists", 3), ("3PM", 3), ("Pts+Reb+Ast", 3)],
}
MIN_LEGS = 2  # a parlay with fewer green legs than this is skipped for the day


def decimal_odds(american):
    a = str(american or "").strip().lower()
    if a in ("even", "ev", "+100", "100"):
        return 2.0
    try:
        v = float(a.replace("+", ""))
    except ValueError:
        return None
    if v == 0:
        return None
    return 1 + (v / 100 if v > 0 else 100 / -v)


def american_odds(dec):
    if not dec or dec <= 1:
        return None
    return f"+{round((dec - 1) * 100)}" if dec >= 2 else f"{round(-100 / (dec - 1))}"


def build(games):
    out = []
    for league, specs in PARLAYS.items():
        for stat, n_legs in specs:
            cands = []
            for g in games:
                if g.get("league") != league:
                    continue
                a, h = (g.get("teams") or {}).get("away", {}), (g.get("teams") or {}).get("home", {})
                label = f"{a.get('name', '')} @ {h.get('name', '')}"
                for pl in g.get("players", []):
                    if pl.get("injury"):  # skip anyone on the injury report, questionable included
                        continue
                    for x in pl.get("props", []):
                        if x["stat"] != stat or x.get("call") != "hit" or not x.get("over"):
                            continue
                        dec = decimal_odds(x["over"].get("odds"))
                        if not dec:
                            continue
                        se = x.get("season") or {}
                        edge = ((se.get("avg") or x["avg"]) - x["line"]) / max(x["line"], 0.5)
                        cands.append({
                            "name": pl["name"], "team": pl.get("team"), "pid": pl.get("pid"),
                            "game": label, "gameId": g["id"], "event": g.get("espnEvent"), "start": g.get("start"),
                            "line": x["line"], "overLine": x["over"]["line"], "odds": x["over"]["odds"],
                            "dec": dec, "proj": x["proj"], "vegas": x.get("vegas"),
                            "season": se, "l5": x["hits"], "_rank": (x["proj"], se.get("n") or 0, edge),
                        })
            cands.sort(key=lambda c: c["_rank"], reverse=True)
            legs, seen = [], set()
            for c in cands:
                if c["name"] in seen:
                    continue
                seen.add(c["name"])
                legs.append({k: v for k, v in c.items() if k != "_rank"})
                if len(legs) == n_legs:
                    break
            if len(legs) < MIN_LEGS:
                out.append({"id": f"{league}-{stat}", "league": league, "stat": stat, "legs": [],
                            "note": f"Not enough green {stat} props on the board right now."})
                continue
            dec, chance = 1.0, 1.0
            for l in legs:
                dec *= l["dec"]
                chance *= l["proj"] / 100
            out.append({
                "id": f"{league}-{stat}", "league": league, "stat": stat, "legs": legs,
                "dec": round(dec, 2), "american": american_odds(dec),
                "proj": round(100 * chance, 1), "implied": round(100 / dec, 1),
            })
    return out

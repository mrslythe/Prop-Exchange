"""Penny Blocks: five parlays per league built from the board's highest projected overs.

Each parlay takes one stat and picks the props with the highest Projected % for it: green OVER
calls first, then yellow leans (one leg per player, no injured players, same-game legs allowed).
It is priced from each leg's best available over odds. Anytime TD is priced from Vegas alone, so
its parlay is the likeliest scorers, marked low confidence.
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
                        if x["stat"] != stat:
                            continue
                        c = x.get("call")
                        if x.get("low") and x.get("over"):
                            c = "hit"  # Anytime TD: the likeliest scorers, whatever their color
                        side = "over" if c in ("hit", "lean") else None
                        if not side or not x.get(side):
                            continue
                        dec = decimal_odds(x[side].get("odds"))
                        if not dec:
                            continue
                        chance = x["proj"] if side == "over" else 100 - x["proj"]
                        se = x.get("season") or {}
                        cands.append({
                            "name": pl["name"], "team": pl.get("team"), "pid": pl.get("pid"),
                            "game": label, "gameId": g["id"], "event": g.get("espnEvent"), "start": g.get("start"),
                            "side": side, "line": x["line"], "sideLine": x[side]["line"], "odds": x[side]["odds"],
                            "dec": dec, "proj": chance, "vegas": x.get("vegas" if side == "over" else "vegasU"),
                            "strong": x.get("strong", False), "low": x.get("low", False),
                            "season": se, "l5": x["hits"],
                            # best value first: how far the chance beats the book's price, then the chance
                            "_rank": (chance, se.get("n") or 0),
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
                            "note": f"Not enough {stat} calls on the board right now."})
                continue
            dec, chance = 1.0, 1.0
            for l in legs:
                dec *= l["dec"]
                chance *= l["proj"] / 100
            out.append({
                "id": f"{league}-{stat}", "league": league, "stat": stat, "legs": legs,
                "dec": round(dec, 2), "american": american_odds(dec),
                "proj": round(100 * chance, 1), "implied": round(100 / dec, 1),
                "low": any(l.get("low") for l in legs),
            })
    return out

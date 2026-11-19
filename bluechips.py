"""Blue Chips: big-line players who went over in their last game.

A player qualifies for a stat when:
  - today's line is at least the stat's minimum (NBA: 12.5 points, 4.5 rebounds, 4.5 assists,
    20.5 Pts+Reb+Ast; NFL: 224.5 passing yards, 59.5 rushing yards, 54.5 receiving yards,
    4.5 receptions), and
  - in his most recent game he beat BOTH the line he had that night (from the tracker's saved
    picks) and today's line.

No projections are involved. Every qualifier is listed, sorted by how far his last game cleared
today's line, and each card is also priced as a parlay of every qualifier on it.
"""
import glob
import json
import os

from penalty import american_odds, decimal_odds

RULES = {
    "NBA": [("Points", 12.5), ("Rebounds", 4.5), ("Assists", 4.5), ("Pts+Reb+Ast", 20.5)],
    "NFL": [("Pass Yds", 224.5), ("Rush Yds", 59.5), ("Rec Yds", 54.5), ("Receptions", 4.5)],
}


def _past_lines(data_dir, days=45):
    """(league, ESPN event, ESPN player id, stat) -> the line saved for that game."""
    out = {}
    for path in sorted(glob.glob(os.path.join(data_dir, "picks", "*.json")))[-days:]:
        try:
            with open(path) as f:
                picks = json.load(f)["picks"]
        except (OSError, ValueError, KeyError):
            continue
        for p in picks.values():
            if p.get("ev") and p.get("pid") and p.get("line") is not None:
                out[(p["lg"], str(p["ev"]), str(p["pid"]), p["s"])] = p["line"]
    return out


def build(games, data_dir):
    lines = _past_lines(data_dir)
    out = []
    for league, rules in RULES.items():
        for stat, minimum in rules:
            legs = []
            for g in games:
                if g.get("league") != league:
                    continue
                a, h = (g.get("teams") or {}).get("away", {}), (g.get("teams") or {}).get("home", {})
                for pl in g.get("players", []):
                    if (pl.get("injury") or {}).get("status") in ("Out", "Injured Reserve", "Doubtful", "Suspension"):
                        continue
                    x = next((x for x in pl.get("props", []) if x["stat"] == stat), None)
                    if not x or x["line"] < minimum or not x.get("over") or not pl.get("gl") or not x.get("v"):
                        continue
                    last, val = pl["gl"][0], x["v"][0]
                    if val is None or len(last) < 6 or not last[5]:
                        continue
                    prev_line = lines.get((league, str(last[5]), str(pl.get("pid")), stat))
                    if prev_line is None or not (val > prev_line and val > x["line"]):
                        continue
                    dec = decimal_odds(x["over"].get("odds"))
                    if not dec:
                        continue
                    legs.append({
                        "name": pl["name"], "team": pl.get("team"), "pid": pl.get("pid"),
                        "game": f"{a.get('name', '')} @ {h.get('name', '')}", "gameId": g["id"],
                        "event": g.get("espnEvent"), "start": g.get("start"),
                        "line": x["line"], "odds": x["over"]["odds"], "dec": dec, "proj": x.get("proj"),
                        "last": {"v": val, "line": prev_line, "opp": last[1], "date": last[0], "home": last[2]},
                        "margin": round(val - x["line"], 1),
                    })
            legs.sort(key=lambda l: (-l["margin"], -l["line"]))
            card = {"id": f"BC-{league}-{stat}", "league": league, "stat": stat, "min": minimum, "legs": legs}
            if len(legs) >= 2:
                dec = 1.0
                for l in legs:
                    dec *= l["dec"]
                card.update(dec=round(dec, 2), american=american_odds(dec))
            out.append(card)
    return out

"""Daily Sheet: a one-page summary of the board (data/sheet.json), like the sheets Vegas books hand
out. Used by the Daily Sheet tab and the daily email: each game's total and spread calls and its green
plays, over and under (biggest edge first)."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def build(board, path, now, days=1):
    today = now.astimezone(ET).date()
    out = []
    for g in sorted(board.get("games", []), key=lambda g: g.get("start") or ""):
        if not g.get("start"):
            continue
        start = dt.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
        if start <= now or (start.astimezone(ET).date() - today).days >= days:
            continue  # only games still to start, today (ET)
        a, h = (g.get("teams") or {}).get("away", {}), (g.get("teams") or {}).get("home", {})
        overs, unders = [], []
        for pl in g.get("players", []):
            for x in pl.get("props", []):
                if x.get("call") != "play" or x.get("low"):
                    continue
                side = x.get("side")
                row = {"n": pl["name"], "t": pl.get("team"), "s": x["stat"], "line": x["line"], "proj": x["proj"],
                       "ch": x.get("chance"), "edge": x.get("edge"), "strong": x.get("strong", False),
                       "odds": (x.get(side) or {}).get("odds")}
                (overs if side == "over" else unders).append(row)
        overs.sort(key=lambda r: -(r["edge"] or 0))
        unders.sort(key=lambda r: -(r["edge"] or 0))
        out.append({"lg": g["league"], "game": f"{a.get('name', '')} @ {h.get('name', '')}", "start": g["start"],
                    "lines": g.get("lines") or {}, "overs": overs, "unders": unders})
    sheet = {"date": today.isoformat(), "updatedAt": now.isoformat(timespec="seconds"),
             "site": "https://mrslythe.github.io/Prop-Exchange/#daily-sheet", "games": out,
             "parlays": [{k: p.get(k) for k in ("league", "stat", "american", "proj")} | {"legs": [l["name"] for l in p["legs"]]}
                         for p in board.get("parlays", []) if p.get("legs")]}
    with open(path, "w") as f:
        json.dump(sheet, f, separators=(",", ":"))
    return sheet

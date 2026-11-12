"""Daily Sheet: a one-page summary of the board (data/sheet.json), like the sheets Vegas books hand
out. Used by the Daily Sheet tab and the daily email: each game's total and spread calls, its green
OVER calls, and its STRONG UNDER calls (strongest first)."""
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
                row = {"n": pl["name"], "t": pl.get("team"), "s": x["stat"], "line": x["line"], "proj": x["proj"],
                       "strong": x.get("strong", False), "odds": (x.get("over") or {}).get("odds")}
                if x.get("call") == "hit" and not x.get("low"):
                    overs.append(row)
                elif x.get("call") == "miss" and x.get("strong") and x.get("under") and not x.get("low"):
                    unders.append({**row, "odds": x["under"].get("odds")})
        overs.sort(key=lambda r: -r["proj"])
        unders.sort(key=lambda r: r["proj"])
        out.append({"lg": g["league"], "game": f"{a.get('name', '')} @ {h.get('name', '')}", "start": g["start"],
                    "lines": g.get("lines") or {}, "overs": overs, "unders": unders})
    sheet = {"date": today.isoformat(), "updatedAt": now.isoformat(timespec="seconds"),
             "site": "https://mrslythe.github.io/Prop-Exchange/#daily-sheet", "games": out,
             "parlays": [{k: p.get(k) for k in ("league", "stat", "american", "proj")} | {"legs": [l["name"] for l in p["legs"]]}
                         for p in board.get("parlays", []) if p.get("legs")]}
    with open(path, "w") as f:
        json.dump(sheet, f, separators=(",", ":"))
    return sheet

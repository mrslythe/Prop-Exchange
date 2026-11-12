"""Line movement: remembers the first line seen for each prop today and shows how far it has moved.

data/lines/<game date>.json keeps, per prop, the first line and prices the board saw. Each run
adds "open" (that first line) and "move" (current line minus opening line) to every prop. A line
that rises usually means money came in on the over; one that falls, on the under.
"""
import datetime as dt
import glob
import json
import os
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
KEEP_DAYS = 4


def apply(board, data_dir, now):
    d = os.path.join(data_dir, "lines")
    os.makedirs(d, exist_ok=True)
    files = {}
    for g in board.get("games", []):
        if not g.get("start"):
            continue
        start = dt.datetime.fromisoformat(g["start"].replace("Z", "+00:00"))
        path = os.path.join(d, start.astimezone(ET).date().isoformat() + ".json")
        if path not in files:
            try:
                with open(path) as f:
                    files[path] = json.load(f)
            except (OSError, ValueError):
                files[path] = {}
        seen = files[path]
        for pl in g.get("players", []):
            for x in pl.get("props", []):
                key = f"{g['league']}|{g['id']}|{pl['name']}|{x['stat']}"
                o = seen.get(key)
                if o is None:
                    o = seen[key] = {"l": x["line"], "o": (x.get("over") or {}).get("odds"),
                                     "u": (x.get("under") or {}).get("odds"),
                                     "t": now.isoformat(timespec="minutes")}
                x["open"] = {"line": o["l"], "over": o["o"], "under": o["u"], "t": o["t"]}
                x["move"] = round(x["line"] - o["l"], 1)
    for path, seen in files.items():
        with open(path, "w") as f:
            json.dump(seen, f, separators=(",", ":"), sort_keys=True)
    cutoff = (now.astimezone(ET).date() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for path in glob.glob(os.path.join(d, "*.json")):
        if os.path.basename(path)[:-5] < cutoff:
            os.remove(path)

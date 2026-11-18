"""NBA box scores for the season: defense vs position and teammate in/out splits.

Every finished regular-season game's ESPN box score is cached in data/nba_box/<event>.json
(minutes, points, rebounds, assists, steals, blocks, 3s and position for every player, and who
did not play), so later runs download only new games.

- Defense vs position: what each defense allows per game to guards, forwards and centers for a
  stat, ranked 1 (allows the least: toughest) to 30. Nudges Projected % like the NFL version.
- Teammate in/out: a player's numbers in this season's games his OUT teammate missed vs played.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os

from build_board import get, num

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
FIELD = {"points": "pts", "totalRebounds": "reb", "assists": "ast", "steals": "stl", "blocks": "blk",
         "threePointFieldGoalsMade": "fg3"}
TIERS = 8
NUDGE_PER = 25
NUDGE_CAP = 8


def _group(ab):
    ab = (ab or "").upper()
    if ab == "C":
        return "C"
    if ab.endswith("G"):
        return "G"
    if ab.endswith("F"):
        return "F"
    return None


def _box(event_id, date):
    d = json.loads(get(f"{SITE}/summary?event={event_id}"))
    sides = d.get("boxscore", {}).get("players", [])
    teams = [str(t["team"]["id"]) for t in sides]
    if len(teams) != 2:
        return None
    comp = ((d.get("header") or {}).get("competitions") or [{}])[0]
    home = next((str(c["team"]["id"]) for c in comp.get("competitors", []) if c.get("homeAway") == "home"), None)
    players = []
    for t in sides:
        tid = str(t["team"]["id"])
        for cat in t.get("statistics", [])[:1]:
            keys = cat.get("keys") or []
            for a in cat.get("athletes", []):
                st = dict(zip(keys, a.get("stats", [])))
                m = num(st.get("minutes"))
                fg3 = (st.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted") or "").split("-")[0]
                players.append({
                    "id": str(a["athlete"]["id"]), "team": tid,
                    "pos": _group((a["athlete"].get("position") or {}).get("abbreviation")),
                    "min": m or 0, "dnp": bool(a.get("didNotPlay")) or not m,
                    "pts": num(st.get("points")) or 0, "reb": num(st.get("rebounds")) or 0,
                    "ast": num(st.get("assists")) or 0, "stl": num(st.get("steals")) or 0,
                    "blk": num(st.get("blocks")) or 0, "fg3": num(fg3) or 0,
                })
    return {"event": str(event_id), "date": date, "home": home,
            "teams": {teams[0]: teams[1], teams[1]: teams[0]}, "players": players}


def _finished_games(now, box_dir):
    """(event id, date) of every finished regular-season game this season. Days already checked
    and complete are remembered in nba_box/_days.json so each run asks ESPN only about new days."""
    try:
        d = json.loads(get(f"{SITE}/scoreboard"))
        start = ((d.get("leagues") or [{}])[0].get("season") or {}).get("startDate", "")[:10]
    except Exception:
        return []
    if not start:
        return []
    path = os.path.join(box_dir, "_days.json")
    try:
        with open(path) as f:
            known = json.load(f)
    except (OSError, ValueError):
        known = {}
    day, last = dt.date.fromisoformat(start), (now - dt.timedelta(days=1)).date()
    days = []
    while day <= last:
        days.append(day.strftime("%Y%m%d"))
        day += dt.timedelta(days=1)

    def fetch(ds):
        try:
            d = json.loads(get(f"{SITE}/scoreboard?dates={ds}"))
        except Exception:
            return ds, None
        evs, done = [], True
        for e in d.get("events", []):
            if (e.get("season") or {}).get("type") != 2:
                continue
            if ((e.get("status") or {}).get("type") or {}).get("completed"):
                evs.append([str(e["id"]), (e.get("date") or "")[:10]])
            else:
                done = False
        return ds, (evs, done)
    with cf.ThreadPoolExecutor(8) as ex:
        for ds, res in ex.map(fetch, [x for x in days if x not in known]):
            if res and res[1]:
                known[ds] = res[0]
            elif res:
                known.pop(ds, None)
                known["_partial_" + ds] = res[0]
    with open(path, "w") as f:
        json.dump({k: v for k, v in known.items() if not k.startswith("_partial_")}, f, separators=(",", ":"))
    return [tuple(e) for k, v in known.items() for e in v]


def load(data_dir, now):
    box_dir = os.path.join(data_dir, "nba_box")
    os.makedirs(box_dir, exist_ok=True)
    games = _finished_games(now, box_dir)
    todo = [(e, d) for e, d in games if not os.path.exists(os.path.join(box_dir, f"{e}.json"))]

    def fetch(ed):
        try:
            return ed[0], _box(*ed)
        except Exception:
            return ed[0], None
    with cf.ThreadPoolExecutor(8) as ex:
        for e, b in ex.map(fetch, todo):
            if b:
                with open(os.path.join(box_dir, f"{e}.json"), "w") as f:
                    json.dump(b, f, separators=(",", ":"))
    boxes = []
    for e, _ in games:
        try:
            with open(os.path.join(box_dir, f"{e}.json")) as f:
                boxes.append(json.load(f))
        except (OSError, ValueError):
            pass
    return Nba(boxes) if boxes else None


class Nba:
    def __init__(self, boxes):
        self.boxes = sorted(boxes, key=lambda b: b["date"], reverse=True)
        self.games = {}     # defense team -> games
        self.allowed = {}   # (defense, group, field) -> total
        self.pos = {}       # player -> group (latest)
        self.team = {}      # player -> team (latest)
        self.by_team = {}   # team -> boxes, newest first
        for b in self.boxes:
            for tid, opp in b["teams"].items():
                self.games[opp] = self.games.get(opp, 0) + 1
                self.by_team.setdefault(tid, []).append(b)
            for p in b["players"]:
                self.pos.setdefault(p["id"], p["pos"])
                self.team.setdefault(p["id"], p["team"])
                if p["dnp"] or not p["pos"]:
                    continue
                d = b["teams"][p["team"]]
                for fld in FIELD.values():
                    k = (d, p["pos"], fld)
                    self.allowed[k] = self.allowed.get(k, 0) + p[fld]

    def position(self, pid):
        return self.pos.get(str(pid))

    def matchup(self, defense, group, keys):
        flds = [FIELD.get(k) for k in keys]
        if not defense or not group or None in flds or defense not in self.games:
            return None
        per = {d: sum(self.allowed.get((d, group, f), 0) for f in flds) / n for d, n in self.games.items() if n}
        if defense not in per or len(per) < 25:
            return None
        avg = sum(per.values()) / len(per)
        order = sorted(per, key=lambda d: per[d])
        rank = order.index(defense) + 1
        ratio = per[defense] / avg if avg else 1
        nudge = max(-NUDGE_CAP, min(NUDGE_CAP, round((ratio - 1) * NUDGE_PER)))
        tier = "tough" if rank <= TIERS else "easy" if rank > len(per) - TIERS else "neutral"
        return {"pos": group, "rank": rank, "of": len(per), "allowed": round(per[defense], 1),
                "avg": round(avg, 1), "games": self.games[defense], "nudge": nudge, "tier": tier}

    def role(self, pid, team):
        """(games played, minutes per game) for a player this season with this team."""
        played = [p for b in self.by_team.get(team, []) for p in b["players"] if p["id"] == str(pid) and not p["dnp"]]
        return len(played), (sum(p["min"] for p in played) / len(played) if played else 0)

    def without(self, pid, team, mate):
        """This season's games of `pid` split by whether teammate `mate` played.
        Returns {"wo": [player rows], "w": [player rows]} (rows are box-score lines of pid)."""
        out = {"wo": [], "w": []}
        for b in self.by_team.get(team, []):
            me = next((p for p in b["players"] if p["id"] == str(pid)), None)
            if not me or me["dnp"]:
                continue
            m = next((p for p in b["players"] if p["id"] == str(mate)), None)
            out["w" if m and not m["dnp"] else "wo"].append(me)
        return out

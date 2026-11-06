"""NFL defense vs. position.

For every finished regular-season game this season, reads ESPN's box score and credits each
player's passing, rushing and receiving numbers to his position (QB, RB, WR, TE) and to the
defense he faced. Each defense then gets a per-game average of what it allows to each position,
and a rank from 1 (allows the least: toughest) to 32 (allows the most: easiest).

Box scores of finished games are cached in data/nfl_box/ so later runs download only new games.
"""
import concurrent.futures as cf
import json
import os

from build_board import get, num

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
POSITIONS = ("QB", "RB", "WR", "TE")
# ESPN game-log stat names (what the props use) -> box score fields
FIELD = {
    "passingYards": "pass_yds", "passingTouchdowns": "pass_td", "completions": "comp",
    "passingAttempts": "att", "interceptions": "int", "rushingAttempts": "rush_att",
    "rushingYards": "rush_yds", "rushingTouchdowns": "rush_td", "receptions": "rec",
    "receivingYards": "rec_yds", "receivingTouchdowns": "rec_td",
}
TIERS = 8          # the 8 toughest are "Tough", the 8 easiest "Easy"
NUDGE_PER = 25     # points of Projected % per 100% above or below the league average
NUDGE_CAP = 8      # the matchup can move a projection at most this many points


def _box(event_id):
    """Trimmed box score: {event, teams: {teamId: oppId}, players: [{id, team, fields...}]}."""
    d = json.loads(get(f"{SITE}/summary?event={event_id}"))
    teams = [str(t["team"]["id"]) for t in d.get("boxscore", {}).get("players", [])]
    if len(teams) != 2:
        return None
    opp = {teams[0]: teams[1], teams[1]: teams[0]}
    rows = {}
    for t in d["boxscore"]["players"]:
        tid = str(t["team"]["id"])
        for cat in t.get("statistics", []):
            labels = cat.get("labels") or []
            for a in cat.get("athletes", []):
                pid = str(a["athlete"]["id"])
                r = rows.setdefault(pid, {"id": pid, "team": tid, "name": a["athlete"].get("displayName", "")})
                st = dict(zip(labels, a.get("stats", [])))
                if cat["name"] == "passing":
                    c, _, at = (st.get("C/ATT") or "0/0").partition("/")
                    r.update(comp=num(c) or 0, att=num(at) or 0, pass_yds=num(st.get("YDS")) or 0,
                             pass_td=num(st.get("TD")) or 0, int=num(st.get("INT")) or 0)
                elif cat["name"] == "rushing":
                    r.update(rush_att=num(st.get("CAR")) or 0, rush_yds=num(st.get("YDS")) or 0,
                             rush_td=num(st.get("TD")) or 0)
                elif cat["name"] == "receiving":
                    r.update(rec=num(st.get("REC")) or 0, rec_yds=num(st.get("YDS")) or 0,
                             rec_td=num(st.get("TD")) or 0)
    players = [r for r in rows.values() if len(r) > 3]
    return {"event": str(event_id), "teams": opp, "players": players}


def _finished_games(season_year):
    """Event ids of every finished regular-season game this season."""
    ids = []
    for week in range(1, 19):
        try:
            d = json.loads(get(f"{SITE}/scoreboard?seasontype=2&week={week}&dates={season_year}"))
        except Exception:
            continue
        evs = d.get("events", [])
        if not evs:
            break
        ids += [e["id"] for e in evs if e.get("status", {}).get("type", {}).get("completed")]
    return ids


def _positions(data_dir, need):
    """ESPN athlete id -> position for the given ids, from rosters plus a cached lookup."""
    path = f"{data_dir}/nfl_positions.json"
    try:
        with open(path) as f:
            pos = json.load(f)
    except (OSError, ValueError):
        pos = {}
    for tid in range(1, 35):  # current rosters (ids 1-34 cover all 32 teams)
        try:
            d = json.loads(get(f"{SITE}/teams/{tid}/roster"))
        except Exception:
            continue
        for grp in d.get("athletes", []):
            for a in grp.get("items", []):
                ab = (a.get("position") or {}).get("abbreviation")
                if ab:
                    pos[str(a["id"])] = ab
    missing = [p for p in need if p not in pos]

    def look(pid):
        try:
            a = json.loads(get(f"{CORE}/athletes/{pid}"))
            return pid, (a.get("position") or {}).get("abbreviation")
        except Exception:
            return pid, None
    with cf.ThreadPoolExecutor(8) as ex:
        for pid, ab in ex.map(look, missing):
            if ab:
                pos[pid] = ab
    with open(path, "w") as f:
        json.dump(pos, f, separators=(",", ":"), sort_keys=True)
    return pos


def _group(ab):
    if ab in ("QB",):
        return "QB"
    if ab in ("RB", "FB", "HB"):
        return "RB"
    if ab in ("WR",):
        return "WR"
    if ab in ("TE",):
        return "TE"
    return None


def load(data_dir, season_year):
    """Build the defense-vs-position table. Returns a Dvp object (or None if nothing loads)."""
    box_dir = f"{data_dir}/nfl_box"
    os.makedirs(box_dir, exist_ok=True)
    ids = _finished_games(season_year)
    todo = [e for e in ids if not os.path.exists(f"{box_dir}/{e}.json")]

    def fetch(e):
        try:
            return e, _box(e)
        except Exception:
            return e, None
    with cf.ThreadPoolExecutor(8) as ex:
        for e, b in ex.map(fetch, todo):
            if b:
                with open(f"{box_dir}/{e}.json", "w") as f:
                    json.dump(b, f, separators=(",", ":"))
    boxes = []
    for e in ids:
        try:
            with open(f"{box_dir}/{e}.json") as f:
                boxes.append(json.load(f))
        except (OSError, ValueError):
            pass
    if not boxes:
        return None
    pos = _positions(data_dir, {p["id"] for b in boxes for p in b["players"]})
    return Dvp(boxes, pos)


class Dvp:
    def __init__(self, boxes, pos):
        self.pos = pos
        self.games = {}   # defense team id -> games played
        self.allowed = {}  # (defense team id, group, field) -> total
        for b in boxes:
            for tid, opp in b["teams"].items():
                self.games[opp] = self.games.get(opp, 0) + 1
            for p in b["players"]:
                g = _group(pos.get(p["id"]))
                if not g:
                    continue
                defense = b["teams"].get(p["team"])
                for fld in FIELD.values():
                    if fld in p:
                        k = (defense, g, fld)
                        self.allowed[k] = self.allowed.get(k, 0) + p[fld]

    def position(self, pid):
        return _group(self.pos.get(str(pid)))

    def matchup(self, defense, group, keys):
        """Per-game amount of this stat the defense allows to this position, its rank (1 = toughest),
        the league average, and the Projected % nudge."""
        flds = [FIELD.get(k) for k in keys]
        if not defense or not group or None in flds or defense not in self.games:
            return None
        per = {}
        for d, n in self.games.items():
            if n:
                per[d] = sum(self.allowed.get((d, group, f), 0) for f in flds) / n
        if defense not in per or len(per) < 20:
            return None
        avg = sum(per.values()) / len(per)
        order = sorted(per, key=lambda d: per[d])  # least allowed first = toughest
        rank = order.index(defense) + 1
        ratio = per[defense] / avg if avg else 1
        nudge = max(-NUDGE_CAP, min(NUDGE_CAP, round((ratio - 1) * NUDGE_PER)))
        tier = "tough" if rank <= TIERS else "easy" if rank > len(per) - TIERS else "neutral"
        return {"pos": group, "rank": rank, "of": len(per), "allowed": round(per[defense], 1),
                "avg": round(avg, 1), "games": self.games[defense], "nudge": nudge, "tier": tier}

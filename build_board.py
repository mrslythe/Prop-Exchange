#!/usr/bin/env python3
"""Build the Prop Board slate for NFL and NBA.

Vegas lines come from scoresandodds.com (game lines + player props).
Each player's last 5 games come from ESPN's public game logs.

Usage: python3 build_board.py [data/board.json]
Writes one JSON file with every game, player and prop for the website.
"""
import concurrent.futures as cf
import datetime as dt
import html
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
from zoneinfo import ZoneInfo

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
SAO = "https://www.scoresandodds.com"

# prop slug on scoresandodds -> (label, ESPN gamelog stat names summed)
PROPS = {
    "nfl": {
        "passing-yards": ("Pass Yds", ["passingYards"]),
        "passing-tds": ("Pass TDs", ["passingTouchdowns"]),
        "completions": ("Completions", ["completions"]),
        "pass-attempts": ("Pass Att", ["passingAttempts"]),
        "interceptions": ("INTs", ["interceptions"]),
        "rushing-yards": ("Rush Yds", ["rushingYards"]),
        "rush-attempts": ("Rush Att", ["rushingAttempts"]),
        "receiving-yards": ("Rec Yds", ["receivingYards"]),
        "receptions": ("Receptions", ["receptions"]),
        "touchdowns": ("Anytime TD", ["rushingTouchdowns", "receivingTouchdowns"]),
        "rushing-&-receiving-yards": ("Rush+Rec Yds", ["rushingYards", "receivingYards"]),
        "passing-&-rushing-yards": ("Pass+Rush Yds", ["passingYards", "rushingYards"]),
    },
    "nba": {
        "points": ("Points", ["points"]),
        "rebounds": ("Rebounds", ["totalRebounds"]),
        "assists": ("Assists", ["assists"]),
        "3-pointers": ("3PM", ["threePointFieldGoalsMade"]),
        "points,-rebounds,-&-assists": ("Pts+Reb+Ast", ["points", "totalRebounds", "assists"]),
        "points-&-rebounds": ("Pts+Reb", ["points", "totalRebounds"]),
        "points-&-assists": ("Pts+Ast", ["points", "assists"]),
        "rebounds-&-assists": ("Reb+Ast", ["totalRebounds", "assists"]),
        "steals": ("Steals", ["steals"]),
        "blocks": ("Blocks", ["blocks"]),
    },
}
ESPN_SPORT = {"nfl": "football", "nba": "basketball"}
# Stats where a missing column counts as 0 (a QB's log has no receiving TDs, a WR's may have no rushing TDs).
PARTIAL_OK = {"Anytime TD"}


def stat_value(stats, keys, label=""):
    """The prop's number for one game, or None if the game has no such stat."""
    vals = [stats.get(k) for k in keys]
    if all(v is None for v in vals) or (label not in PARTIAL_OK and any(v is None for v in vals)):
        return None
    return round(sum(v or 0 for v in vals), 1)


def get(url, tries=3):
    for i in range(tries):
        r = subprocess.run(["curl", "-sS", "-L", "--max-time", "30", "-A", UA, url],
                           capture_output=True)
        if r.returncode == 0 and r.stdout:
            return r.stdout.decode("utf-8", "replace")
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url}")


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ---------------- scoresandodds: games ----------------
def parse_games(league):
    page = get(f"{SAO}/{league}")
    games = {}
    for m in re.finditer(r'<div id="%s\.(\d+)" class="event-card"' % league, page):
        gid = m.group(1)
        end = page.find('<div id="%s.' % league, m.end())
        card = page[m.start(): end if end > 0 else m.start() + 60000]
        tm = re.search(r'data-role="localtime" data-value="([^"]+)"', card)
        rows = re.findall(r'<tr class="event-card-row[^"]*" data-side="(away|home)">(.*?)</tr>', card, re.S)
        g = {"id": gid, "start": tm.group(1) if tm else None, "teams": {}}
        for side, row in rows:
            name = re.search(r'<span class="team-name">\s*<a[^>]*>\s*<span>([^<]+)</span>', row)
            logo = re.search(r'teamlogos/%s/\d+/([a-z0-9]+)\.png' % league, row)
            rec = re.search(r'class="team-record"[^>]*>\s*<span>([^<]+)</span>', row)

            def field(f):
                c = re.search(r'data-field="%s"[^>]*>(.*?)</td>' % f, row, re.S)
                if not c:
                    return None
                v = re.search(r'class="data-value">\s*([^<]+?)\s*<', c.group(1))
                o = re.search(r'class="data-odds[^"]*">\s*([^<]+?)\s*<', c.group(1))
                return {"v": v.group(1) if v else None, "odds": o.group(1) if o else None}

            g["teams"][side] = {
                "name": name.group(1).strip() if name else side.title(),
                "abbr": logo.group(1).upper() if logo else None,
                "record": rec.group(1).strip() if rec else None,
                "spread": field("current-spread"),
                "total": field("current-total"),
                "ml": field("current-moneyline"),
            }
        games[gid] = g
    return games


# ---------------- scoresandodds: props ----------------
def parse_props(league, slug):
    page = get(f"{SAO}/{league}/props/{urllib.parse.quote(slug, safe='&,-')}")
    out = []
    for li in re.findall(r'<li class="border"(.*?)</li>', page, re.S):
        state = re.search(r'data-state="([^"]*)"', li)
        if state and state.group(1) != "Pregame":
            continue
        ev = re.search(r'data-event="%s/(\d+)"' % league, li)
        name = re.search(r'<div class="props-name">\s*<a [^>]*>([^<]+)</a>', li)
        match = re.search(r'small gray">([^<]+)<', li)
        lines = re.findall(r'data-moneyline">\s*([ou])([\d.]+)\s*</span>\s*<small class="data-odds[^"]*">\s*([^<]+?)\s*<', li)
        if not lines and slug == "touchdowns":
            # anytime TD has no over/under, just a "yes" price: treat it as over 0.5 at that price
            yes = re.search(r'data-moneyline">\s*([+-]\d+|even)\s*<', li)
            lines = [("o", "0.5", yes.group(1))] if yes else []
        if not (ev and name and lines):
            continue
        over = next(((float(l), o) for s, l, o in lines if s == "o"), None)
        under = next(((float(l), o) for s, l, o in lines if s == "u"), None)
        if not over and not under:
            continue
        # consensus line: midpoint of the best over and best under lines, snapped to 0.5
        if over and under:
            line = round((over[0] + under[0]) / 2 * 2) / 2
        else:
            line = (over or under)[0]
        mt = match.group(1).strip() if match else ""
        team = re.split(r"\s+(?:@|vs)\s+", mt)[0] if mt else None
        out.append({
            "event": ev.group(1), "player": html.unescape(name.group(1)).strip(), "team": team,
            "matchup": mt, "slug": slug, "line": line,
            "over": {"line": over[0], "odds": over[1]} if over else None,
            "under": {"line": under[0], "odds": under[1]} if under else None,
        })
    return out


# ---------------- ESPN ----------------
def espn_find(league, name):
    url = ("https://site.web.api.espn.com/apis/common/v3/search?type=player&limit=5&query="
           + urllib.parse.quote(name))
    try:
        d = json.loads(get(url))
    except Exception:
        return None
    for it in d.get("items", []):
        if it.get("league") == league:
            return it.get("id")
    return None


def espn_games(league, pid):
    """Every regular-season and playoff game of a player's career, newest first.

    Returns (games, current_season). Each game: {date, season, cur, post, opp, oppId, oppName,
    teamId, atVs, res, stats{name: value}}.
    """
    base = f"https://site.web.api.espn.com/apis/common/v3/sports/{ESPN_SPORT[league]}/{league}/athletes/{pid}/gamelog"
    games, seen = [], set()

    def parse(d, season, cur):
        names = d.get("names") or []
        evmeta = d.get("events") or {}
        for st in d.get("seasonTypes", []):
            label = st.get("displayName", "")
            if "Regular" not in label and "Postseason" not in label:
                continue
            for cat in st.get("categories", []):
                if cat.get("type") not in (None, "event"):
                    continue
                for e in cat.get("events", []):
                    eid = e.get("eventId")
                    if eid in seen or eid not in evmeta:
                        continue
                    seen.add(eid)
                    vals = {}
                    for n, v in zip(names, e.get("stats", [])):
                        if "-" in n and isinstance(v, str) and "-" in v[1:]:
                            # "made-attempted" pairs, e.g. 3PM: "5-10"
                            a, b = n.split("-", 1)
                            x, y = v.split("-", 1)
                            vals[a], vals[b] = num(x), num(y)
                        else:
                            vals.setdefault(n, num(v))
                    m = evmeta[eid]
                    opp = m.get("opponent") or {}
                    games.append({
                        "date": m.get("gameDate", "")[:10],
                        "season": season, "cur": cur, "post": "Postseason" in label,
                        "opp": opp.get("abbreviation", ""), "oppId": str(opp.get("id", "")),
                        "oppName": opp.get("displayName", ""),
                        "teamId": str((m.get("team") or {}).get("id", "")),
                        "atVs": m.get("atVs", ""),
                        "res": " ".join(x for x in (m.get("gameResult", ""), m.get("score", "")) if x),
                        "stats": vals,
                    })

    try:
        d0 = json.loads(get(base))
    except Exception:
        return [], None
    flt = next((f for f in d0.get("filters", []) if f.get("name") == "season"), {})
    seasons = [str(o.get("value")) for o in flt.get("options", []) if o.get("value")]
    cur = str(flt.get("value") or (seasons[0] if seasons else ""))
    parse(d0, int(cur) if cur.isdigit() else 0, True)
    for s in seasons:  # the rest of the career, one season at a time
        if s == cur or not s.isdigit():
            continue
        try:
            parse(json.loads(get(f"{base}?season={s}")), int(s), False)
        except Exception:
            continue
    games.sort(key=lambda g: g["date"], reverse=True)
    return games, (int(cur) if cur.isdigit() else None)


def implied(odds):
    """Vegas' implied chance of the over from American odds (vig included), e.g. -110 -> 52."""
    o = str(odds or "").strip().lower()
    if o in ("even", "ev", "+100", "100"):
        return 50
    v = num(o.replace("+", ""))
    if v is None or v == 0:
        return None
    return round(100 * (-v / (-v + 100) if v < 0 else 100 / (v + 100)))


# ---------------- special games: birthday, revenge, hometown ----------------
ET = ZoneInfo("America/New_York")
HOME_MILES = 35  # birthplace within this distance of the arena counts as a hometown game
# Birthplaces ESPN lists as neighborhoods or boroughs that are not Census places.
PLACE_ALIASES = {
    ("NY", "brooklyn"): ("NY", "new york"), ("NY", "bronx"): ("NY", "new york"),
    ("NY", "the bronx"): ("NY", "new york"), ("NY", "queens"): ("NY", "new york"),
    ("NY", "manhattan"): ("NY", "new york"), ("NY", "harlem"): ("NY", "new york"),
    ("NY", "staten island"): ("NY", "new york"), ("NY", "new york city"): ("NY", "new york"),
    ("CA", "hollywood"): ("CA", "los angeles"), ("CA", "north hollywood"): ("CA", "los angeles"),
    ("CA", "van nuys"): ("CA", "los angeles"), ("CA", "san pedro"): ("CA", "los angeles"),
    ("CA", "watts"): ("CA", "los angeles"), ("CA", "sherman oaks"): ("CA", "los angeles"),
    ("CA", "encino"): ("CA", "los angeles"), ("CA", "panorama city"): ("CA", "los angeles"),
    ("CA", "south central los angeles"): ("CA", "los angeles"),
}
# Canadian cities for Toronto (Raptors) and other games in Canada.
CANADA = {
    "toronto": (43.653, -79.383), "scarborough": (43.777, -79.231), "etobicoke": (43.620, -79.513),
    "north york": (43.761, -79.411), "mississauga": (43.589, -79.644), "brampton": (43.732, -79.762),
    "markham": (43.857, -79.337), "vaughan": (43.837, -79.508), "richmond hill": (43.882, -79.440),
    "oakville": (43.468, -79.687), "pickering": (43.838, -79.086), "ajax": (43.851, -79.020),
    "hamilton": (43.256, -79.869), "montreal": (45.502, -73.567), "vancouver": (49.283, -123.121),
}
CA_PROVINCES = {"ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE"}
_PLACES = None


def places():
    global _PLACES
    if _PLACES is None:
        _PLACES = {}
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "us_places.tsv")
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("#"):
                        continue
                    st, name, lat, lon = line.rstrip("\n").split("\t")
                    _PLACES[(st, name.lower())] = (float(lat), float(lon))
        except OSError:
            pass
    return _PLACES


def locate(city, state, country):
    city = (city or "").strip().lower().replace("st. ", "saint ")
    if not city:
        return None
    if (country or "").lower() == "canada" or state in CA_PROVINCES:
        return CANADA.get(city)
    key = PLACE_ALIASES.get((state, city), (state, city))
    pl = places()
    return pl.get(key) or pl.get((key[0], key[1].replace("saint ", "st. ")))


def miles(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def current_season(league):
    t = dt.date.today()
    if league == "nba":  # ESPN names NBA seasons by end year: 2026-27 is 2027
        return t.year + 1 if t.month >= 8 else t.year
    return t.year if t.month >= 6 else t.year - 1


def espn_teams(league):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT[league]}/{league}/teams"
    try:
        d = json.loads(get(url))
        return {t["team"]["id"]: t["team"] for t in d["sports"][0]["leagues"][0]["teams"]}
    except Exception:
        return {}


def team_id(teams, nickname):
    n = (nickname or "").lower()
    for tid, t in teams.items():
        if t.get("name", "").lower() == n or t.get("displayName", "").lower().endswith(" " + n):
            return tid
    return None


def espn_venues(league, dates):
    """(away team id, home team id) -> {city, state, country, name} for games on the given ET dates."""
    out = {}
    for d in sorted(dates):
        url = (f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT[league]}/{league}/scoreboard"
               f"?dates={d.replace('-', '')}")
        try:
            data = json.loads(get(url))
        except Exception:
            continue
        for e in data.get("events", []):
            c = (e.get("competitions") or [{}])[0]
            side = {t.get("homeAway"): t["team"]["id"] for t in c.get("competitors", [])}
            v = c.get("venue") or {}
            a = v.get("address") or {}
            st = a.get("state", "")
            country = a.get("country") or ("Canada" if st in CA_PROVINCES else ("USA" if st else ""))
            if "away" in side and "home" in side:
                out[(side["away"], side["home"])] = {"city": a.get("city", ""), "state": st,
                                                     "country": country, "name": v.get("fullName", ""),
                                                     "event": str(e.get("id", ""))}
    return out


def espn_person(league, pid):
    """Birth date, birthplace, current team id, and last season's team ids for one player."""
    info = {"dob": None, "born": {}, "team": None, "lastTeams": set()}
    try:
        a = json.loads(get(f"https://sports.core.api.espn.com/v2/sports/{ESPN_SPORT[league]}/leagues/{league}/athletes/{pid}"))
        info["dob"] = (a.get("dateOfBirth") or "")[:10] or None
        info["born"] = a.get("birthPlace") or {}
        m = re.search(r"/teams/(\d+)", (a.get("team") or {}).get("$ref", ""))
        info["team"] = m.group(1) if m else None
    except Exception:
        pass
    return info


def badges(person, game, teams, venue):
    """Return the special-game markers for one player in one game."""
    out = []
    if not person:
        return out
    start = game.get("start")
    local = dt.datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(ET).date() if start else None
    # Birthday
    if person["dob"] and local:
        b = dt.date.fromisoformat(person["dob"])
        if (b.month, b.day) == (local.month, local.day):
            out.append({"icon": "🎂", "kind": "birthday", "text": f"Turns {local.year - b.year} today"})
    # Revenge: today's opponent is a team he played for last season (and not his team now)
    away, home = game.get("espnAway"), game.get("espnHome")
    me = person["team"]
    if me in (away, home):
        opp = home if me == away else away
        if opp in person["lastTeams"]:
            name = (teams.get(opp) or {}).get("displayName", "this team")
            out.append({"icon": "😤", "kind": "revenge", "text": f"Played for the {name} last season"})
    # Hometown
    born = person["born"] or {}
    if venue and born.get("city"):
        bc, bs, bco = born.get("city"), born.get("state", ""), born.get("country", "")
        where = ", ".join(x for x in (bc, bs or bco) if x)
        here = locate(venue["city"], venue["state"], venue["country"])
        there = locate(bc, bs, bco)
        same_city = bc.lower() == venue["city"].lower() and (bs or bco) in (venue["state"], venue["country"])
        dist = miles(here, there) if here and there else None
        if same_city or (dist is not None and dist <= HOME_MILES):
            near = "" if same_city or dist is None or dist < 3 else f", {round(dist)} miles from the arena"
            out.append({"icon": "🏠", "kind": "hometown", "text": f"Hometown game: born in {where}{near}"})
        elif bs and bs == venue["state"] and venue["country"] in ("USA", ""):
            out.append({"icon": "📍", "kind": "homestate", "text": f"Home-state game: born in {where}"})
        elif not bs and bco and bco != "USA" and bco == venue["country"]:
            out.append({"icon": "📍", "kind": "homestate", "text": f"Home-country game: born in {where}"})
    return out


OUT_STATUSES = {"Out", "Injured Reserve", "Doubtful", "Suspension"}


def espn_injuries(league):
    """ESPN athlete id -> {status, type, note, returns} for everyone on the league injury report."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT[league]}/{league}/injuries"
    out = {}
    try:
        d = json.loads(get(url))
    except Exception:
        return out
    for t in d.get("injuries", []):
        for i in t.get("injuries", []):
            status = i.get("status") or ""
            if not status or status == "Active":
                continue
            a = i.get("athlete") or {}
            m = re.search(r"/id/(\d+)", " ".join(l.get("href", "") for l in a.get("links", [])))
            if not m:
                continue
            det = i.get("details") or {}
            out[m.group(1)] = {"status": status, "type": det.get("type") or "",
                               "note": i.get("shortComment") or "", "returns": det.get("returnDate") or ""}
    return out


def versus(career, person, game, teams):
    """Career games against today's opponent (newest first), or None if the matchup is unknown."""
    if not person or person.get("team") not in (game.get("espnAway"), game.get("espnHome")):
        return None
    opp = game["espnHome"] if person["team"] == game["espnAway"] else game["espnAway"]
    vg = [g for g in career if g["oppId"] == opp]
    return {
        "opp": (teams.get(opp) or {}).get("displayName", ""),
        "n": len(vg),
        "games": [{"d": g["date"], "p": g["post"], "a": g["atVs"], "o": g["opp"], "r": g["res"]} for g in vg],
        "_games": vg,  # used while building props, dropped before writing
    }


def build(league):
    import calib
    games = parse_games(league)
    props = []
    with cf.ThreadPoolExecutor(6) as ex:
        for res in ex.map(lambda s: parse_props(league, s), PROPS[league]):
            props.extend(res)
    props = [p for p in props if p["event"] in games]
    names = sorted({p["player"] for p in props})

    with cf.ThreadPoolExecutor(8) as ex:
        ids = dict(zip(names, ex.map(lambda n: espn_find(league, n), names)))
    with cf.ThreadPoolExecutor(12) as ex:
        careers = dict(zip(names, ex.map(lambda n: espn_games(league, ids[n]) if ids[n] else ([], None), names)))
    logs = {n: c[0] for n, c in careers.items()}
    with cf.ThreadPoolExecutor(8) as ex:
        people = dict(zip(names, ex.map(lambda n: espn_person(league, ids[n]) if ids[n] else None, names)))
    for n, (career, cur) in careers.items():
        if people.get(n) and cur:
            people[n]["lastTeams"] = {g["teamId"] for g in career if g["season"] == cur - 1 and g["teamId"]}

    teams = espn_teams(league)
    for g in games.values():
        g["espnAway"] = team_id(teams, (g["teams"].get("away") or {}).get("name"))
        g["espnHome"] = team_id(teams, (g["teams"].get("home") or {}).get("name"))
    dates = {dt.datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(ET).date().isoformat()
             for g in games.values() if g.get("start")}
    venues = espn_venues(league, dates)
    injuries = espn_injuries(league)
    defense = None
    if league == "nfl":
        try:
            import dvp
            defense = dvp.load(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
                               current_season("nfl"))
        except Exception as e:
            print("defense vs position unavailable:", e, file=sys.stderr)

    board = {}
    skipped = 0
    for p in props:
        label, keys = PROPS[league][p["slug"]]
        played = []  # every game with this stat, newest first
        for g in logs.get(p["player"], []):
            v = stat_value(g["stats"], keys, label)
            if v is None:
                continue
            played.append({"v": v, "date": g["date"], "opp": g["opp"],
                           "atVs": g["atVs"], "cur": g.get("cur", True)})
        last = [{k: x[k] for k in ("v", "date", "opp", "atVs")} for x in played[:5]]
        if len(last) < 5:
            skipped += 1
            continue
        line = p["line"]
        if label in calib.DROP_HALF and line == 0.5:
            skipped += 1  # 0.5 steals/blocks: almost always an under at a steep price, taken off the board
            continue
        hits = sum(1 for x in last if x["v"] > line)
        avg = round(sum(x["v"] for x in last) / 5, 1)
        season = [x for x in played if x["cur"]]
        s_n = len(season)
        s_hits = sum(1 for x in season if x["v"] > line)
        s_pct = round(100 * s_hits / s_n) if s_n else None
        s_avg = round(sum(x["v"] for x in season) / s_n, 1) if s_n else None
        l5_pct = hits * 20
        # Projected %: the season hit rate carries 60%, the last 5 carry 40% (recent form).
        # With fewer than 5 games this season, lean on the last 5, which reach into last season.
        if s_n >= 5:
            proj = round(0.6 * s_pct + 0.4 * l5_pct)
        elif s_n:
            w = 0.6 * s_n / 5
            proj = round(w * s_pct + (1 - w) * l5_pct)
        else:
            proj = l5_pct
        gid = p["event"]
        # NFL matchup: nudge the projection by how much the opponent allows this stat to this position
        matchup, proj_base = None, proj
        person = people.get(p["player"])
        if defense and person and person.get("team"):
            g0 = games[gid]
            if person["team"] in (g0.get("espnAway"), g0.get("espnHome")):
                opp = g0["espnHome"] if person["team"] == g0["espnAway"] else g0["espnAway"]
                matchup = defense.matchup(opp, defense.position(ids.get(p["player"])), keys)
                if matchup:
                    matchup["opp"] = (teams.get(opp) or {}).get("displayName", "")
                    proj = max(1, min(99, proj + matchup["nudge"]))
        gb = board.setdefault(gid, {"players": {}})
        if p["player"] not in gb["players"]:
            g = games[gid]
            venue = venues.get((g.get("espnAway"), g.get("espnHome")))
            g["venue"] = venue
            g["espnEvent"] = (venue or {}).get("event")
            person = people.get(p["player"])
            gb["players"][p["player"]] = {"name": p["player"], "team": p["team"], "props": [],
                                          "pid": ids.get(p["player"]),
                                          "injury": injuries.get(str(ids.get(p["player"]))),
                                          "badges": badges(person, g, teams, venue),
                                          "vs": versus(logs.get(p["player"], []), person, g, teams)}
        pl = gb["players"][p["player"]]
        vs_games = pl["vs"]["_games"] if pl["vs"] else []
        vv = []
        for vg in vs_games:
            vv.append(stat_value(vg["stats"], keys, label))
        got = [x for x in vv if x is not None]
        vs_hits = sum(1 for x in got if x > line)
        # "form" is the last-5 + season blend (with the NFL matchup nudge). "proj" mixes in a little
        # of the Vegas price (calib.py).
        vg = implied(p["over"]["odds"]) if p["over"] else None
        vgu = implied(p["under"]["odds"]) if p["under"] else None
        form = proj
        low = label in calib.LOW_CONF
        proj = calib.td_chance(vg) if low else calib.project(form, vg)
        c = "out" if (pl["injury"] or {}).get("status") in OUT_STATUSES else calib.call(proj)
        pl["props"].append({
            "stat": label, "line": line, "over": p["over"], "under": p["under"],
            "last5": last, "hits": hits, "pct": l5_pct, "avg": avg,
            "season": {"n": s_n, "hits": s_hits, "pct": s_pct, "avg": s_avg},
            "vegas": vg, "vegasU": vgu,
            "proj": proj, "form": form, "projBase": proj_base, "matchup": matchup,
            "call": c, "strong": c != "out" and not low and calib.strong(proj), "low": low,
            "keys": keys,
            # career vs today's opponent: shown in the player's dropdown, not used in "proj"
            "vs": {"n": len(got), "hits": vs_hits, "avg": round(sum(got) / len(got), 1) if got else None,
                   "v": vv, "hot": len(got) >= 3 and vs_hits / len(got) >= 0.6},
        })

    out_games = []
    for gid, g in games.items():
        if gid not in board:
            continue
        players = list(board[gid]["players"].values())
        for pl in players:
            if pl["vs"]:
                pl["vs"].pop("_games", None)
        for pl in players:
            pl["props"].sort(key=lambda x: -x["proj"])
            # the line under the name: the player's main stat for his position, else any prop with a matchup
            main = {"QB": "Pass Yds", "RB": "Rush Yds", "WR": "Rec Yds", "TE": "Rec Yds"}
            ms = [x for x in pl["props"] if x.get("matchup")]
            pick = next((x for x in ms if x["stat"] == main.get(x["matchup"]["pos"])), ms[0] if ms else None)
            pl["matchup"] = {**pick["matchup"], "stat": pick["stat"]} if pick else None
            for x in pl["props"]:  # keep each prop's copy small; the full details live on the player
                if x.get("matchup"):
                    x["matchup"] = {k: x["matchup"][k] for k in ("rank", "allowed", "avg", "nudge", "tier")}
        players.sort(key=lambda pl: ((pl["injury"] or {}).get("status") in OUT_STATUSES,
                                     -max(x["proj"] for x in pl["props"]), pl["name"]))
        out_games.append({**g, "players": players})
    out_games.sort(key=lambda g: g["start"] or "")
    return {
        "league": league.upper(),
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": f"Lines: scoresandodds.com/{league}/props and /{league}. Last 5 games, season and career stats: ESPN game logs.",
        "rule": "Form % = 60% season hit rate + 40% last-5 hit rate against the consensus line. Projected % = 75% Form % + 25% Vegas %. Green OVER 65%+, yellow LEAN 50-64%, red UNDER below 50%.",
        "propsSeen": len(props), "propsSkipped": skipped,
        "games": out_games,
    }


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import track
    out = sys.argv[1] if len(sys.argv) > 1 else "data/board.json"
    data_dir = os.path.dirname(out) or "."
    now = dt.datetime.now(dt.timezone.utc)
    board = {"run": now.strftime("r%Y%m%dT%H%M%S"), "createdAt": now.isoformat(timespec="seconds"),
             "leagues": {}, "games": []}
    errors = 0
    import lines
    for lg in ("nfl", "nba"):
        try:
            data = build(lg)
        except Exception as e:  # keep the other league going
            data = {"league": lg.upper(), "error": str(e), "games": []}
        errors += bool(data.get("error"))
        n = sum(len(pl["props"]) for g in data["games"] for pl in g["players"])
        board["leagues"][lg.upper()] = {"games": len(data["games"]), "props": n,
                                        "skipped": data.get("propsSkipped"), "error": data.get("error")}
        board["games"] += [{"league": lg.upper(), **g} for g in data["games"]]
        print(f"{lg}: {len(data['games'])} games, {n} props, skipped {data.get('propsSkipped')}",
              data.get("error") or "")
    lines.apply(board, data_dir, now)
    import penalty
    board["parlays"] = penalty.build(board["games"])
    os.makedirs(data_dir, exist_ok=True)
    if board["games"]:
        with open(out, "w") as f:
            json.dump(board, f, separators=(",", ":"))
        print(f"Wrote {out} ({os.path.getsize(out)//1024} KB)")
    else:
        # nothing usable: keep the previous board instead of blanking the site
        print("No games found in either league; board left unchanged.", file=sys.stderr)

    # results tracker: save today's calls, grade finished games, rebuild the track record
    saved = track.record_picks(board, data_dir, now)
    track.record_parlays(board, data_dir, now)
    graded = track.grade(data_dir, now)
    rec = track.summarize(data_dir, now)
    t = rec["total"]
    print(f"Tracker: {saved} picks saved, {graded} graded, {rec['pending']} pending; "
          f"green {t['gHit']}/{t['gN']}, red {t['rHit']}/{t['rN']}")
    if errors == 2:
        sys.exit(1)  # both leagues failed: make the workflow run show red

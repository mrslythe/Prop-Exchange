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
import re
import subprocess
import sys
import time
import urllib.parse

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
    """Return played regular-season games, most recent first: [{date, opp, atVs, stats{name:value}}]."""
    base = f"https://site.web.api.espn.com/apis/common/v3/sports/{ESPN_SPORT[league]}/{league}/athletes/{pid}/gamelog"
    games = []
    seen = set()
    d = {}
    for attempt in range(2):
        url = base
        if attempt == 1:
            if len(games) >= 5:
                break
            # not enough games this season: reach back one season
            # (ESPN names NBA seasons by end year, so 2026-27 is 2027 and last season is 2026)
            season = d.get("requestedSeason", {}).get("year") if isinstance(d, dict) else None
            today = dt.date.today()
            cur = int(season) if season else (today.year + (1 if league == "nba" and today.month >= 8 else 0))
            url = f"{base}?season={cur - 1}"
        try:
            d = json.loads(get(url))
        except Exception:
            d = {}
            continue
        names = d.get("names") or []
        evmeta = d.get("events") or {}
        for st in d.get("seasonTypes", []):
            if "Regular" not in st.get("displayName", "") and "Postseason" not in st.get("displayName", ""):
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
                    games.append({
                        "date": m.get("gameDate", "")[:10],
                        "opp": (m.get("opponent") or {}).get("abbreviation", ""),
                        "atVs": m.get("atVs", ""),
                        "cur": attempt == 0,  # False = reached back into last season
                        "stats": vals,
                    })
    games.sort(key=lambda g: g["date"], reverse=True)
    return games


def implied(odds):
    """Vegas' implied chance of the over from American odds (vig included), e.g. -110 -> 52."""
    o = str(odds or "").strip().lower()
    if o in ("even", "ev", "+100", "100"):
        return 50
    v = num(o.replace("+", ""))
    if v is None or v == 0:
        return None
    return round(100 * (-v / (-v + 100) if v < 0 else 100 / (v + 100)))


def build(league):
    games = parse_games(league)
    props = []
    with cf.ThreadPoolExecutor(6) as ex:
        for res in ex.map(lambda s: parse_props(league, s), PROPS[league]):
            props.extend(res)
    props = [p for p in props if p["event"] in games]
    names = sorted({p["player"] for p in props})

    with cf.ThreadPoolExecutor(8) as ex:
        ids = dict(zip(names, ex.map(lambda n: espn_find(league, n), names)))
    with cf.ThreadPoolExecutor(8) as ex:
        logs = dict(zip(names, ex.map(lambda n: espn_games(league, ids[n]) if ids[n] else [], names)))

    board = {}
    skipped = 0
    for p in props:
        label, keys = PROPS[league][p["slug"]]
        played = []  # every game with this stat, newest first
        for g in logs.get(p["player"], []):
            vs = [g["stats"].get(k) for k in keys]
            if any(v is None for v in vs):
                continue
            played.append({"v": round(sum(vs), 1), "date": g["date"], "opp": g["opp"],
                           "atVs": g["atVs"], "cur": g.get("cur", True)})
        last = [{k: x[k] for k in ("v", "date", "opp", "atVs")} for x in played[:5]]
        if len(last) < 5:
            skipped += 1
            continue
        line = p["line"]
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
        gb = board.setdefault(gid, {"players": {}})
        pl = gb["players"].setdefault(p["player"], {"name": p["player"], "team": p["team"], "props": []})
        pl["props"].append({
            "stat": label, "line": line, "over": p["over"], "under": p["under"],
            "last5": last, "hits": hits, "pct": l5_pct, "avg": avg,
            "season": {"n": s_n, "hits": s_hits, "pct": s_pct, "avg": s_avg},
            "vegas": implied(p["over"]["odds"]) if p["over"] else None,
            "proj": proj,
            "call": "hit" if proj >= 55 else "miss",
        })

    out_games = []
    for gid, g in games.items():
        if gid not in board:
            continue
        players = list(board[gid]["players"].values())
        for pl in players:
            pl["props"].sort(key=lambda x: -x["proj"])
        players.sort(key=lambda pl: (-max(x["proj"] for x in pl["props"]), pl["name"]))
        out_games.append({**g, "players": players})
    out_games.sort(key=lambda g: g["start"] or "")
    return {
        "league": league.upper(),
        "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": f"Lines: scoresandodds.com/{league}/props and /{league}. Last 5 games and season stats: ESPN game logs.",
        "rule": "Projected % = 60% season hit rate + 40% last-5 hit rate against the consensus line (midpoint of best over and best under). Green = 55% or higher.",
        "propsSeen": len(props), "propsSkipped": skipped,
        "games": out_games,
    }


if __name__ == "__main__":
    import os
    out = sys.argv[1] if len(sys.argv) > 1 else "data/board.json"
    now = dt.datetime.now(dt.timezone.utc)
    board = {"run": now.strftime("r%Y%m%dT%H%M%S"), "createdAt": now.isoformat(timespec="seconds"),
             "leagues": {}, "games": []}
    for lg in ("nfl", "nba"):
        try:
            data = build(lg)
        except Exception as e:  # keep the other league going
            data = {"league": lg.upper(), "error": str(e), "games": []}
        n = sum(len(pl["props"]) for g in data["games"] for pl in g["players"])
        board["leagues"][lg.upper()] = {"games": len(data["games"]), "props": n,
                                        "skipped": data.get("propsSkipped"), "error": data.get("error")}
        board["games"] += [{"league": lg.upper(), **g} for g in data["games"]]
        print(f"{lg}: {len(data['games'])} games, {n} props, skipped {data.get('propsSkipped')}",
              data.get("error") or "")
    if not board["games"]:
        # nothing usable: keep yesterday's board instead of blanking the site
        print("No games found in either league; board left unchanged.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as f:
        json.dump(board, f, separators=(",", ":"))
    print(f"Wrote {out} ({os.path.getsize(out)//1024} KB)")

"""Results tracker for the Prop Exchange board.

Every run:
  1. record_picks: saves each prop's call (line, projected %, green or red) for games that have
     not started, in data/picks/<game date>.json. Later runs overwrite a game's picks until it
     starts, so the last call before kickoff or tip-off is the one that gets graded.
  2. grade: once a game is over, looks up each player's real stat in his ESPN game log and marks
     the pick: over (went over the line), under, push (exactly the line), or dnp (did not play).
  3. summarize: writes data/record.json, the track record the site shows.
"""
import datetime as dt
import glob
import json
import os
from zoneinfo import ZoneInfo

from build_board import ESPN_SPORT, get, num, stat_value

ET = ZoneInfo("America/New_York")
GRADE_AFTER = dt.timedelta(hours=4)   # a game is treated as finished this long after its start
GIVE_UP_AFTER = dt.timedelta(days=3)  # no stat line by then: the player did not play
OUT_STATUSES = {"Out", "Injured Reserve", "Doubtful", "Suspension"}


def _start(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else None


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"picks": {}}


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)


def record_picks(board, data_dir, now):
    """Save the current call for every prop in a game that has not started yet."""
    os.makedirs(f"{data_dir}/picks", exist_ok=True)
    files = {}
    for g in board.get("games", []):
        start = _start(g.get("start"))
        if not start or start <= now or not g.get("espnEvent"):
            continue
        day = start.astimezone(ET).date().isoformat()
        a, h = (g.get("teams") or {}).get("away", {}), (g.get("teams") or {}).get("home", {})
        label = f"{a.get('name', '')} @ {h.get('name', '')}"
        path = f"{data_dir}/picks/{day}.json"
        data = files.setdefault(path, _load(path))
        for pl in g.get("players", []):
            if not pl.get("pid"):
                continue
            inj = (pl.get("injury") or {}).get("status")
            for x in pl.get("props", []):
                key = f"{g['league']}|{g['espnEvent']}|{pl['pid']}|{x['stat']}"
                old = data["picks"].get(key)
                if old and old.get("r"):
                    continue  # already graded
                data["picks"][key] = {
                    "lg": g["league"], "ev": g["espnEvent"], "gl": label, "st": g["start"],
                    "n": pl["name"], "pid": pl["pid"], "s": x["stat"], "k": x.get("keys", []),
                    "line": x["line"], "proj": x["proj"], "call": x["call"], "vg": x.get("vegas"),
                    "inj": inj, "r": None, "a": None,
                }
    for path, data in files.items():
        _save(path, data)
    return sum(len(d["picks"]) for d in files.values())


def record_parlays(board, data_dir, now):
    """Save each Penalty Stocks parlay under the date of its first leg, until that leg starts."""
    os.makedirs(f"{data_dir}/parlays", exist_ok=True)
    saved = 0
    for par in board.get("parlays", []):
        legs = par.get("legs") or []
        starts = [_start(l.get("start")) for l in legs]
        if not legs or any(s is None for s in starts) or not all(l.get("event") and l.get("pid") for l in legs):
            continue
        first = min(starts)
        if first <= now:
            continue  # already under way: keep the version saved before it started
        day = first.astimezone(ET).date().isoformat()
        path = f"{data_dir}/parlays/{day}.json"
        data = _load(path)
        data.setdefault("parlays", {})
        data["parlays"][par["id"]] = {
            "id": par["id"], "lg": par["league"], "s": par["stat"], "first": first.isoformat(),
            "american": par.get("american"), "proj": par.get("proj"), "implied": par.get("implied"),
            "legs": [{"key": f"{par['league']}|{l['event']}|{l['pid']}|{par['stat']}", "n": l["name"],
                      "line": l["line"], "odds": l["odds"], "proj": l["proj"]} for l in legs],
        }
        _save(path, {"picks": data.get("picks", {}), "parlays": data["parlays"]})
        saved += 1
    return saved


def _parlay_results(data_dir):
    """Grade saved parlays from their legs' pick results. A push or did-not-play leg drops out,
    as sportsbooks do; the parlay wins if every remaining leg went over."""
    results = {}
    for path in sorted(glob.glob(f"{data_dir}/picks/*.json")):
        for key, p in _load(path)["picks"].items():
            results[key] = p
    out = []
    for path in sorted(glob.glob(f"{data_dir}/parlays/*.json")):
        day = os.path.basename(path)[:-5]
        for par in (_load(path).get("parlays") or {}).values():
            legs = [results.get(l["key"]) for l in par["legs"]]
            rs = [(p or {}).get("r") for p in legs]
            if any(r == "under" for r in rs):
                res = "lost"
            elif any(r is None for r in rs):
                res = "pending"
            else:
                live = [r for r in rs if r == "over"]
                res = "won" if live else "void"
            out.append({"d": day, "id": par["id"], "lg": par["lg"], "s": par["s"], "american": par.get("american"),
                        "proj": par.get("proj"), "res": res,
                        "legs": [{"n": l["n"], "line": l["line"], "r": r, "a": (p or {}).get("a")}
                                 for l, p, r in zip(par["legs"], legs, rs)]})
    return out


def _season_log(league, pid):
    """eventId -> stats for a player's current season (regular season and playoffs)."""
    url = (f"https://site.web.api.espn.com/apis/common/v3/sports/{ESPN_SPORT[league]}/{league}"
           f"/athletes/{pid}/gamelog")
    try:
        d = json.loads(get(url))
    except Exception:
        return None
    names = d.get("names") or []
    out = {}
    for st in d.get("seasonTypes", []):
        label = st.get("displayName", "")
        if "Regular" not in label and "Postseason" not in label:
            continue
        for cat in st.get("categories", []):
            for e in cat.get("events", []):
                vals = {}
                for n, v in zip(names, e.get("stats", [])):
                    if "-" in n and isinstance(v, str) and "-" in v[1:]:
                        a, b = n.split("-", 1)
                        x, y = v.split("-", 1)
                        vals[a], vals[b] = num(x), num(y)
                    else:
                        vals.setdefault(n, num(v))
                out[str(e.get("eventId"))] = vals
    return out


def grade(data_dir, now, days_back=14):
    """Fill in results for finished games from the last couple of weeks."""
    import concurrent.futures as cf
    todo = {}
    for path in sorted(glob.glob(f"{data_dir}/picks/*.json"))[-days_back:]:
        data = _load(path)
        for key, p in data["picks"].items():
            start = _start(p.get("st"))
            if p.get("r") or not start or now - start < GRADE_AFTER:
                continue
            todo.setdefault((p["lg"].lower(), p["pid"]), []).append((path, key))
    if not todo:
        return 0
    with cf.ThreadPoolExecutor(8) as ex:
        logs = dict(zip(todo, ex.map(lambda k: _season_log(*k), todo)))
    files, graded = {}, 0
    for who, items in todo.items():
        log = logs.get(who)
        if log is None:
            continue  # ESPN did not answer: try again next run
        for path, key in items:
            data = files.setdefault(path, _load(path))
            p = data["picks"][key]
            stats = log.get(str(p["ev"]))
            if stats is None:
                if now - _start(p["st"]) > GIVE_UP_AFTER:
                    p["r"] = "dnp"
                    graded += 1
                continue
            val = stat_value(stats, p.get("k") or [], p.get("s", ""))
            if val is None:
                p["r"] = "dnp"
            else:
                p["a"] = val
                p["r"] = "over" if p["a"] > p["line"] else ("push" if p["a"] == p["line"] else "under")
            graded += 1
    for path, data in files.items():
        _save(path, data)
    return graded


def summarize(data_dir, now):
    """Build data/record.json from every graded pick."""
    def blank():
        return {"gN": 0, "gHit": 0, "rN": 0, "rHit": 0}

    def add(b, p):
        if p["call"] == "hit":
            b["gN"] += 1
            b["gHit"] += p["r"] == "over"
        elif p["call"] == "miss":
            b["rN"] += 1
            b["rHit"] += p["r"] == "under"

    total, by_league, by_stat, days = blank(), {}, {}, []
    buckets = {k: {"n": 0, "over": 0} for k in ("0-34", "35-54", "55-64", "65-74", "75-100")}
    week = blank()
    week_start = (now.astimezone(ET).date() - dt.timedelta(days=6)).isoformat()
    latest = None
    pending = 0
    for path in sorted(glob.glob(f"{data_dir}/picks/*.json")):
        day = os.path.basename(path)[:-5]
        dayb = blank()
        graded_today = []
        for p in _load(path)["picks"].values():
            if not p.get("r"):
                pending += 1
                continue
            if p["r"] in ("dnp", "push") or p.get("inj") in OUT_STATUSES or p["call"] == "out":
                continue  # no action: not counted either way
            for b in (total, dayb, by_league.setdefault(p["lg"], blank()), by_stat.setdefault(f"{p['lg']} {p['s']}", blank())):
                add(b, p)
            if day >= week_start:
                add(week, p)
            pr = p["proj"]
            bk = "0-34" if pr < 35 else "35-54" if pr < 55 else "55-64" if pr < 65 else "65-74" if pr < 75 else "75-100"
            buckets[bk]["n"] += 1
            buckets[bk]["over"] += p["r"] == "over"
            graded_today.append(p)
        if dayb["gN"] or dayb["rN"]:
            days.append({"d": day, **dayb})
            latest = (day, graded_today)
    rec = {
        "updatedAt": now.isoformat(timespec="seconds"),
        "total": total, "week": week, "pending": pending,
        "byLeague": by_league,
        "byStat": dict(sorted(by_stat.items(), key=lambda kv: -kv[1]["gN"])),
        "buckets": buckets,
        "days": days[-30:],
        "latest": None,
    }
    if latest:
        day, picks = latest
        greens = sorted((p for p in picks if p["call"] == "hit"), key=lambda p: -p["proj"])
        rec["latest"] = {"d": day, "picks": [
            {"n": p["n"], "lg": p["lg"], "gl": p["gl"], "s": p["s"], "line": p["line"],
             "a": p["a"], "proj": p["proj"], "r": p["r"]} for p in greens]}
    pars = _parlay_results(data_dir)
    done = [p for p in pars if p["res"] in ("won", "lost")]
    rec["parlays"] = {
        "n": len(done), "won": sum(p["res"] == "won" for p in done),
        "pending": sum(p["res"] == "pending" for p in pars),
        "recent": [p for p in pars if p["res"] != "pending"][-15:][::-1],
    }
    with open(f"{data_dir}/record.json", "w") as f:
        json.dump(rec, f, separators=(",", ":"))
    return rec

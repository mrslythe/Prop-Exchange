"""Projected % and the call (v4, Nov 27 2026).

Projected % is the chance of the over, from a model refit every Monday on the last 14 days of
graded props (data/calib.json):

    chance of over = logistic( a + b * Vegas + c * Form )      (fit separately for NBA and NFL)

    Vegas = the chance of the over from the over and under prices with the bookmaker's cut removed
    Form  = 60% season hit rate + 40% last-5 hit rate, plus the nudges (matchup, home/away,
            minutes, back-to-back, teammate out)

Each weight is whatever the last two weeks of results say it is worth (Form can't go below zero).
If Form starts predicting better, it automatically gets more weight the next Monday.

The call compares that chance to what each side's odds require (at -110 you need 52.4%):

    edge = our chance of the side - the chance its odds need to break even

    Green  PLAY   the better side's edge is +3 points or more (over or under)
    Yellow LEAN   edge between 0 and +3: close to the price
    Red    PASS   neither side beats its price
    STRONG        edge of +6 or more

Game totals and spreads use the same edge rule (gamelines.py), with the power-rating model blended
into the Vegas chance by a weight that is also refit every Monday.
"""
import datetime as dt
import glob
import json
import math
import os

PLAY, STRONG_EDGE = 3.0, 6.0
LOW_CONF = {"Anytime TD"}          # priced from Vegas alone, marked low confidence
DROP_HALF = {"Steals", "Blocks"}   # 0.5 lines on these are taken off the board
WINDOW_DAYS = 14
MIN_ROWS = 1500                    # fewer graded props than this: keep last week's fit

# Starting weights (fit on Nov 13-26 2026). Replaced by data/calib.json once it exists.
DEFAULT = {
    "props": {"NBA": {"a": -0.05, "vegas": 1.3, "form": 0.0}, "NFL": {"a": -0.2, "vegas": 0.85, "form": 0.0}},
    # weight of our power-rating model vs the Vegas chance, per league and market
    "games": {"NBA|Total": 0.0, "NFL|Total": 0.15, "NBA|Spread": 0.40, "NFL|Spread": 0.10},
}
_model = None
_path = None


def load(data_dir):
    """Read data/calib.json (call once per run, after refit)."""
    global _model, _path
    _path = os.path.join(data_dir, "calib.json")
    try:
        with open(_path) as f:
            _model = json.load(f)
    except (OSError, ValueError):
        _model = {"props": dict(DEFAULT["props"]), "games": dict(DEFAULT["games"]), "fitted": None}
    return _model


def model():
    return _model or {"props": DEFAULT["props"], "games": DEFAULT["games"]}


def logit(p):
    p = min(99.0, max(1.0, p)) / 100
    return math.log(p / (1 - p))


def sig(z):
    return 1 / (1 + math.exp(-z))


def no_vig(vg, vu):
    """Vegas' chance of the over with the bookmaker's cut taken out (both prices as implied %)."""
    if vg is not None and vu:
        return 100 * vg / (vg + vu)
    if vg is not None:
        return vg / 1.045  # over price only: take out a typical 4.5% cut
    if vu:
        return 100 - vu / 1.045  # under price only
    return None


def project(form, vg, vu=None, league="NBA"):
    """Chance of the over (1-99)."""
    w = model()["props"].get(league) or DEFAULT["props"][league]
    nv = no_vig(vg, vu)
    z = w["a"]
    if nv is not None:
        z += w["vegas"] * logit(nv)
    if form is not None:
        z += w["form"] * logit(form)
    return max(1, min(99, round(100 * sig(z))))


def td_chance(vg):
    """Anytime TD: Vegas' yes price with its built-in margin taken out (graded TDs ran ~10% under it)."""
    return max(1, min(99, round((vg or 0) * 0.9)))


def breakeven(odds):
    """The chance (%) a bet at these American odds must win to break even, e.g. -110 -> 52.4."""
    o = str(odds or "").strip().lower()
    if o in ("even", "ev", "+100", "100"):
        return 50.0
    try:
        v = float(o.replace("+", ""))
    except ValueError:
        return None
    if v == 0:
        return None
    return 100 * (-v / (-v + 100) if v < 0 else 100 / (v + 100))


def decide(p_over, over_odds, under_odds, low=False):
    """The better side and its edge. Returns {side, chance, edge, call, strong}."""
    opts = []
    for side, chance, odds in (("over", p_over, over_odds), ("under", 100 - p_over, under_odds)):
        be = breakeven(odds)
        if be is not None:
            opts.append((round(chance - be, 1), side, chance))
    if not opts:
        side = "over" if p_over >= 50 else "under"
        return {"side": side, "chance": round(max(p_over, 100 - p_over)), "edge": None, "call": "pass", "strong": False}
    edge, side, chance = max(opts)
    call = "play" if edge >= PLAY else "lean" if edge >= 0 else "pass"
    if low:
        call = "pass" if edge < 0 else call
    return {"side": side, "chance": round(chance), "edge": edge, "call": call,
            "strong": (not low) and edge >= STRONG_EDGE}


# ---------------- weekly refit ----------------
def _fit_logistic(X, y, l2=1.0, nonneg=()):
    """Newton's method with a small ridge penalty; columns in `nonneg` are kept at or above zero."""
    k = len(X[0])
    w = [0.0] * k
    free = list(range(k))
    for _ in range(3):  # refit with any negative non-negative weights pinned at zero
        for _it in range(50):
            g = [0.0] * k
            H = [[0.0] * k for _ in range(k)]
            for xi, yi in zip(X, y):
                z = sum(w[j] * xi[j] for j in free)
                p = sig(z)
                r, s = p - yi, p * (1 - p)
                for a in free:
                    g[a] += r * xi[a]
                    for b in free:
                        H[a][b] += s * xi[a] * xi[b]
            for a in free:
                if a:
                    g[a] += l2 * w[a]
                    H[a][a] += l2
            sub = [[H[a][b] for b in free] for a in free]
            step = _solve(sub, [g[a] for a in free])
            for i, a in enumerate(free):
                w[a] -= step[i]
            if max(abs(s) for s in step) < 1e-7:
                break
        neg = [j for j in nonneg if j in free and w[j] < 0]
        if not neg:
            break
        for j in neg:
            w[j] = 0.0
            free.remove(j)
    return w


def _solve(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-12:
            continue
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] if abs(M[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _prop_rows(data_dir, start, end):
    rows = []
    for path in sorted(glob.glob(os.path.join(data_dir, "picks", "*.json"))):
        day = os.path.basename(path)[:-5]
        if not (start <= day <= end):
            continue
        try:
            picks = json.load(open(path))["picks"]
        except (OSError, ValueError, KeyError):
            continue
        for p in picks.values():
            if p.get("r") not in ("over", "under") or p.get("s") in LOW_CONF:
                continue
            if p.get("vg") is None or p.get("form") is None:
                continue
            nv = no_vig(p["vg"], p.get("vu"))
            rows.append((day, p["lg"], [1.0, logit(nv), logit(p["form"])], 1.0 if p["r"] == "over" else 0.0, nv))
    return rows


def _brier(rows, w):
    return sum((sig(sum(a * b for a, b in zip(w[r[1]], r[2]))) - r[3]) ** 2 for r in rows) / len(rows)


def _fit_leagues(rows):
    w = {}
    for lg in ("NBA", "NFL"):
        rs = [r for r in rows if r[1] == lg]
        if len(rs) < 300:
            d = DEFAULT["props"][lg]
            w[lg] = [d["a"], d["vegas"], d["form"]]
            continue
        w[lg] = _fit_logistic([r[2] for r in rs], [r[3] for r in rs], nonneg=(2,))
    return w


def refit(data_dir, now, games_fn=None):
    """Refit the prop weights on the last 14 days of graded props (and, through games_fn, the
    game-line blend weights) and write data/calib.json. Runs once a week (Mondays)."""
    load(data_dir)
    today = now.date() if isinstance(now, dt.datetime) else now
    end = (today - dt.timedelta(days=1)).isoformat()
    start = (today - dt.timedelta(days=WINDOW_DAYS)).isoformat()
    rows = _prop_rows(data_dir, start, end)
    out = dict(_model or {})
    out.setdefault("props", dict(DEFAULT["props"]))
    out.setdefault("games", dict(DEFAULT["games"]))
    note = {}
    if len(rows) >= MIN_ROWS:
        # honesty check first: fit on the older 7 days, score on the newer 7
        mid = (today - dt.timedelta(days=WINDOW_DAYS // 2)).isoformat()
        old, new = [r for r in rows if r[0] < mid], [r for r in rows if r[0] >= mid]
        if len(old) > 600 and len(new) > 300:
            w_old = _fit_leagues(old)
            base = sum(r[3] for r in old) / len(old)
            note["test"] = {
                "n": len(new),
                "model": round(_brier(new, w_old), 4),
                "vegas": round(sum((r[4] / 100 - r[3]) ** 2 for r in new) / len(new), 4),
                "coinflip": round(sum((base - r[3]) ** 2 for r in new) / len(new), 4),
            }
        w = _fit_leagues(rows)
        out["props"] = {lg: {"a": round(v[0], 4), "vegas": round(v[1], 4), "form": round(v[2], 4)} for lg, v in w.items()}
        note["n"] = len(rows)
        note["over"] = round(100 * sum(r[3] for r in rows) / len(rows), 1)
    else:
        note["n"] = len(rows)
        note["kept"] = "not enough graded props; kept the previous weights"
    if games_fn:
        try:
            g = games_fn(data_dir, today)
            if g:
                out["games"].update(g.get("weights", {}))
                note["games"] = g.get("note")
        except Exception as e:  # game-line refit is extra: never block the props
            note["games"] = f"skipped: {e}"
    out["fitted"] = today.isoformat()
    out["window"] = [start, end]
    out["props_note"] = note
    with open(os.path.join(data_dir, "calib.json"), "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    load(data_dir)
    return out


def due(data_dir, now):
    """True when the last refit is older than this week's Monday (Eastern date)."""
    m = load(data_dir)
    today = now.date() if isinstance(now, dt.datetime) else now
    monday = (today - dt.timedelta(days=today.weekday())).isoformat()
    return not m.get("fitted") or m["fitted"] < monday

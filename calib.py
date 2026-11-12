"""Calibrated projection: turns a prop's form (last 5 + season hit rates) and its Vegas price into
an honest chance of the over.

    chance of over = logistic(a + b * logit(Vegas % of the over) + c * (form - 50) / 50)

a, b and c are fitted per league from the tracker's own graded picks (the last 30 days), once a
week, and saved in data/calibration.json. So if the board says 60%, about 60% of those props
should really go over. Until there are enough graded picks, the defaults below are used (fitted on
the first week of results, Nov 6-12 2026).
"""
import datetime as dt
import glob
import json
import math
import os

REFIT_EVERY = dt.timedelta(days=7)
FIT_DAYS = 30
MIN_PICKS = 300
DEFAULT = {"NBA": [-0.214, 0.638, 0.014], "NFL": [-0.182, 0.866, 0.253]}
OVER, UNDER = 55, 45      # call the over at 55%+, the under at 45% or less (and only at a fair price)
LOW_CONF = {"Anytime TD"}  # priced from Vegas alone, low confidence: never called
DROP_HALF = {"Steals", "Blocks"}  # 0.5 lines on these are taken off the board


def _logit(p):
    p = min(max(p, 0.02), 0.98)
    return math.log(p / (1 - p))


def _feats(vg, form):
    return [1.0, _logit(vg / 100), (form - 50) / 50]


def chance(coef, vg, form):
    """Chance of the over, 1-99. vg: Vegas % of the over (vig included); form: form % (0-100)."""
    if vg is None:
        vg = 50
    z = sum(a * b for a, b in zip(coef, _feats(vg, form)))
    return max(1, min(99, round(100 / (1 + math.exp(-z)))))


def td_chance(vg):
    """Anytime TD: Vegas' price with its built-in margin taken out (graded TDs ran ~10% under it)."""
    return max(1, min(99, round((vg or 0) * 0.9)))


def call(p_over, stat, vg, vgu):
    """Over or under only when the chance is 55%+ for that side AND beats the price the book
    charges for it (its implied %, vig included). Otherwise pass, even a likely side at a bad price."""
    if p_over >= OVER and (vg is None or p_over >= vg) and stat not in LOW_CONF:
        return "hit"
    if 100 - p_over >= 100 - UNDER and vgu is not None and 100 - p_over >= vgu and stat not in LOW_CONF:
        return "miss"
    return "pass"


def strong(p_over, c, vg, vgu):
    """60%+ on the side called and at least 3 points better than the book's price."""
    if c == "hit":
        return p_over >= OVER + 5 and p_over - (vg or 0) >= 3
    if c == "miss":
        return p_over <= UNDER - 5 and (100 - p_over) - (vgu or 100) >= 3
    return False


def _fit(rows, iters=25, ridge=1.0):
    """Logistic regression by Newton's method (3 coefficients, light ridge on the slopes)."""
    k = 3
    w = [0.0] * k
    for _ in range(iters):
        g = [0.0] * k
        H = [[0.0] * k for _ in range(k)]
        for x, y in rows:
            q = 1 / (1 + math.exp(-sum(a * b for a, b in zip(w, x))))
            for i in range(k):
                g[i] += (q - y) * x[i]
                for j in range(k):
                    H[i][j] += q * (1 - q) * x[i] * x[j]
        for i in range(1, k):
            g[i] += ridge * w[i]
            H[i][i] += ridge
        A = [H[i] + [g[i]] for i in range(k)]
        for i in range(k):
            piv = A[i][i]
            for j in range(i, k + 1):
                A[i][j] /= piv
            for r in range(k):
                if r != i:
                    f = A[r][i]
                    for j in range(i, k + 1):
                        A[r][j] -= f * A[i][j]
        w = [w[i] - A[i][k] for i in range(k)]
    w[2] = max(0.0, w[2])  # form never counts against the over
    return [round(v, 4) for v in w]


def load(data_dir, now):
    """Coefficients per league; refits from graded picks once a week."""
    path = os.path.join(data_dir, "calibration.json")
    try:
        with open(path) as f:
            cal = json.load(f)
        if now - dt.datetime.fromisoformat(cal["fitted"]) < REFIT_EVERY:
            return {lg: cal.get(lg, {}).get("coef", DEFAULT[lg]) for lg in DEFAULT}
    except (OSError, ValueError, KeyError):
        pass
    since = (now - dt.timedelta(days=FIT_DAYS)).date().isoformat()
    rows = {lg: [] for lg in DEFAULT}
    for p_ in sorted(glob.glob(os.path.join(data_dir, "picks", "*.json"))):
        if os.path.basename(p_)[:-5] < since:
            continue
        try:
            with open(p_) as f:
                picks = json.load(f)["picks"].values()
        except (OSError, ValueError, KeyError):
            continue
        for p in picks:
            if p.get("r") not in ("over", "under") or not p.get("vg") or p["lg"] not in rows:
                continue
            if p["s"] in LOW_CONF or (p["s"] in DROP_HALF and p["line"] == 0.5):
                continue
            form = p.get("form", p["proj"])  # picks before Nov 12 stored the form % as "proj"
            rows[p["lg"]].append((_feats(p["vg"], form), p["r"] == "over"))
    cal = {"fitted": now.isoformat(timespec="seconds"), "days": FIT_DAYS}
    for lg, rs in rows.items():
        if len(rs) >= MIN_PICKS:
            cal[lg] = {"coef": _fit(rs), "n": len(rs)}
        else:
            cal[lg] = {"coef": DEFAULT[lg], "n": len(rs), "default": True}
    with open(path, "w") as f:
        json.dump(cal, f, indent=1)
    return {lg: cal[lg]["coef"] for lg in DEFAULT}

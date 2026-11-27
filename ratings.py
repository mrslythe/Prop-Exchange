"""Team power ratings for game totals and spreads.

Every team gets an offense and a defense rating, in points, fit to every game this season with
ridge regression (recent games count more, and ratings are pulled toward average until a team has
played enough to earn them):

    points scored by A vs B  =  league average + offense(A) - defense(B) + home edge (if A is home)

From those, each game gets a predicted score, a predicted total and a predicted margin. Those are
turned into chances against the Vegas number with a normal curve (spread of results measured from
this season's misses), then blended with Vegas' own chance (bookmaker's cut removed), because the
market is usually right. See gamelines.py for how the blend becomes a call.
"""
import concurrent.futures as cf
import json
import math

from build_board import ESPN_SPORT, espn_teams, get, num

# How fast old games fade (a game this many games ago counts half) and how hard ratings are pulled
# to average (in games' worth of evidence).
HALF_LIFE = {"nfl": 8, "nba": 20}
RIDGE = {"nfl": 4.0, "nba": 6.0}
# Floors for the spread of results around our predictions (points).
MIN_SD = {"nfl": {"total": 12.0, "margin": 12.0}, "nba": {"total": 15.0, "margin": 11.0}}


def season_games(league):
    """Every completed regular-season game: event, date, home, away, home/away points, neutral."""
    teams = espn_teams(league)

    def sched(tid):
        url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_SPORT[league]}/{league}/teams/{tid}/schedule"
        try:
            return json.loads(get(url)).get("events", [])
        except Exception:
            return []

    with cf.ThreadPoolExecutor(8) as ex:
        evs = [e for es in ex.map(sched, list(teams)) for e in es]
    games = {}
    for e in evs:
        c = (e.get("competitions") or [{}])[0]
        if not ((c.get("status") or {}).get("type") or {}).get("completed"):
            continue
        cs = {x.get("homeAway"): x for x in c.get("competitors", [])}
        h, a = cs.get("home"), cs.get("away")
        if not h or not a:
            continue
        hp = num(str((h.get("score") or {}).get("value", "")))
        ap = num(str((a.get("score") or {}).get("value", "")))
        if hp is None or ap is None:
            continue
        games[str(e["id"])] = {"event": str(e["id"]), "date": e.get("date") or "", "home": str(h["team"]["id"]),
                               "away": str(a["team"]["id"]), "hp": hp, "ap": ap,
                               "neutral": bool(c.get("neutralSite"))}
    return sorted(games.values(), key=lambda g: g["date"])


def _solve(A, b):
    """Gaussian elimination for a small dense system (no numpy needed in the workflow)."""
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


class Ratings:
    def __init__(self, league, games):
        """Fits ratings to `games` (already limited to the games before the one being predicted)."""
        self.league = league
        teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
        self.idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        self.n_games = {t: 0 for t in teams}
        for g in games:
            self.n_games[g["home"]] += 1
            self.n_games[g["away"]] += 1
        # parameters: [mu, home, off_0..off_n-1, def_0..def_n-1]
        P = 2 + 2 * n
        A = [[0.0] * P for _ in range(P)]
        b = [0.0] * P
        hl = HALF_LIFE[league]
        # recency in games: rank games by date, newest = 0, counting a team's schedule pace
        per_week = 1.0 if league == "nfl" else 3.5
        last = games[-1]["date"][:10] if games else ""
        for g in games:
            age_days = _days(g["date"][:10], last)
            age_games = age_days / 7.0 * per_week
            w = 0.5 ** (age_games / hl)
            for team, opp, pts, home in ((g["home"], g["away"], g["hp"], 0 if g["neutral"] else 1),
                                         (g["away"], g["home"], g["ap"], 0)):
                x = {0: 1.0, 2 + self.idx[team]: 1.0, 2 + n + self.idx[opp]: -1.0}
                if home:
                    x[1] = 1.0
                for i, xi in x.items():
                    b[i] += w * xi * pts
                    for j, xj in x.items():
                        A[i][j] += w * xi * xj
        lam = RIDGE[league]
        for i in range(2, P):
            A[i][i] += lam
        sol = _solve(A, b) if games else [0.0] * P
        self.mu, self.hfa = sol[0], sol[1]
        self.off = {t: sol[2 + i] for t, i in self.idx.items()}
        self.dfn = {t: sol[2 + n + i] for t, i in self.idx.items()}
        # spread of results around the fit, for turning points into chances
        rt, rm, wt = 0.0, 0.0, 0.0
        for g in games:
            ph, pa = self.predict(g["home"], g["away"], g["neutral"])
            if ph is None:
                continue
            rt += ((g["hp"] + g["ap"]) - (ph + pa)) ** 2
            rm += ((g["hp"] - g["ap"]) - (ph - pa)) ** 2
            wt += 1
        fl = MIN_SD[league]
        # in-sample misses run small, so scale up a little
        self.sd_total = max(fl["total"], 1.1 * math.sqrt(rt / wt)) if wt else fl["total"]
        self.sd_margin = max(fl["margin"], 1.1 * math.sqrt(rm / wt)) if wt else fl["margin"]

    def predict(self, home, away, neutral=False):
        """Predicted (home points, away points), or (None, None) if either team is unknown."""
        if home not in self.idx or away not in self.idx:
            return None, None
        h = self.mu + self.off[home] - self.dfn[away] + (0 if neutral else self.hfa)
        a = self.mu + self.off[away] - self.dfn[home]
        return h, a


def _days(a, b):
    import datetime as dt
    try:
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
    except ValueError:
        return 0


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def chances(r, home, away, total_line, away_spread, neutral=False):
    """Model chances (0-100) of the over and of the away side covering, plus the predicted score."""
    ph, pa = r.predict(home, away, neutral)
    if ph is None:
        return None
    out = {"home": round(ph, 1), "away": round(pa, 1), "total": round(ph + pa, 1), "margin": round(pa - ph, 1)}
    if total_line is not None:
        out["over"] = 100 * phi((ph + pa - total_line) / r.sd_total)
    if away_spread is not None:
        out["awayCover"] = 100 * phi((pa - ph + away_spread) / r.sd_margin)
    return out

# Prop Exchange

**Live board:** https://mrslythe.github.io/Prop-Exchange/

A daily board of NFL and NBA player props. For every game it lists the players with props, each player's last 5 games and full-season numbers, and whether the board calls the **over** (green), a **lean** (yellow) or the **under** (red).

## How it works

- **Lines** come from [scoresandodds.com](https://www.scoresandodds.com) (game lines from `/nfl` and `/nba`, player props from `/nfl/props/*` and `/nba/props/*`). The line used is the midpoint of the best over and best under, which sits close to the consensus.
- **Last 5 games and season stats** come from ESPN's public game logs (every game the player has played this season).
- **Form %** (`form`) = 60% × season hit rate + 40% × last-5 hit rate, both against the same line. With fewer than 5 games this season it leans on the last 5, which reach back into last season.
- **Projected %** (`proj`, `calib.py`) = 75% × Form % + 25% × the Vegas % of the over (a light blend).
- **The call**: green **OVER** at 58%+, yellow **LEAN** at 46–57%, red **UNDER** at 45% or less. **STRONG** = 70%+ over or 30% or less under.
- **Anytime TD** is priced from Vegas alone (yes price × 0.9), marked low confidence and never tagged strong. **0.5 lines on steals and blocks** are left off the board.
- **Line movement** (`lines.py`): the first line and prices seen for each prop are kept in `data/lines/<game date>.json`; each prop carries `open` and `move` (current line − opening line).
- **NFL matchup** (`dvp.py`): every finished game's ESPN box score is credited to each player's position (QB, RB, WR, TE) and to the defense he faced (cached in `data/nfl_box/`). Each defense's per-game average allowed for the prop's stat is ranked 1 (toughest) to 32. Form % is nudged by 25 points per 100% above or below the league average, capped at ±8; the pre-matchup value is kept as `projBase`.
- **Vegas %** is the chance implied by the sportsbook's over price, shown for comparison.
- **Career vs today's opponent**: tap a player's name to open every regular-season and playoff game of his career against that day's opponent, measured against today's lines (games, how many went over, average, each game's number). 🔥 marks a prop he has cleared in at least 60% of 3+ games against that team. Reference only: it does not change the projection.
- **Injuries** (ESPN injury report): ⚠️ questionable or day-to-day; players listed out, doubtful, suspended or on injured reserve are greyed out and get no call.
- **Track record**: every call is saved just before its game starts (`data/picks/<date>.json`) and graded after the game against ESPN's final stats (`track.py`). `data/record.json` holds the running totals the site shows: how often green Over calls went over and red Under calls went under (plus Strong calls), by league, stat and projection range. Yellow leans are counted separately. **Profit tracker**: each call is also scored as a $10 bet at the best price saved with it (`oo`/`uo` odds, else the Vegas %), so the record shows dollars won or lost, not just hit rate; Penny Blocks shows the same for $10 on each parlay. Red anytime-TD calls are not counted as Under picks (there is no "no TD" price). Picks from earlier versions (Nov 6–12) are reported separately as `v1`. Pushes and players who did not play are not counted.
- **Penny Blocks** (`penalty.py`, the second tab): five parlays per sport, each built from the highest Projected % overs for one stat, green first, then yellow (anytime TD takes the likeliest scorers) (NFL: anytime TD, receiving yards, rushing yards, receptions, passing yards; NBA: points, rebounds, assists, 3-pointers, points+rebounds+assists). One leg per player, no injured players, same-game legs allowed. Each card shows the payout from the best over odds, the combined chance (legs multiplied, assuming independence) and the sportsbook's implied chance, with buttons that open Hard Rock or PrizePicks and copy the picks. Parlays are saved before their first leg starts (`data/parlays/`) and graded from their legs.
- **Blue Chips** (third tab): people sign in with an emailed link (Supabase Auth, project `prop-exchange`), save the players they usually bet on (with the ☆ next to any name on the board, the only way to add one), and see each player's props today plus the board's results on him over the last 30 days (`data/players.json`, written by `track.py`). Saved players live in the Supabase table `blue_chips`; row-level security lets each person read, add and remove only their own (50 max).
- **Badges** (from ESPN player records): 🎂 the game is on the player's birthday · 😤 revenge game, the opponent is a team he played for last season · 🏠 hometown game, the arena is within 35 miles of his birthplace · 📍 home-state (or home-country) game. Distances use the US Census place list in `data/us_places.tsv`.
- Props for players with fewer than 5 games this season are left out.

Five games is a small sample and ignores injuries, matchups and minutes. Treat it as one input.

## Files

| File | What it does |
| --- | --- |
| `index.html` | The board. Loads `data/board.json`. |
| `build_board.py` | Pulls the lines, game logs and injury report and writes `data/board.json`, then runs the tracker. Python 3 standard library plus `curl`. |
| `dvp.py` | NFL defense vs. position: box scores, rankings, and the matchup nudge. |
| `penalty.py` | Builds the Penny Blocks parlays from the board. |
| `calib.py` | Projected % (form + light Vegas blend) and the green/yellow/red call. |
| `lines.py` | Line movement: first line seen per prop (`data/lines/`). |
| `track.py` | Saves each call before its game and grades it afterward; writes `data/picks/` and `data/record.json`. |
| `.github/workflows/update-board.yml` | Runs the builder and commits the new data. Started hourly 10 AM–8 PM Eastern by a cron-job.org timer (workflow_dispatch); GitHub's own 14:44 and 21:44 UTC schedules are a backup. Can also be run by hand from the Actions tab. |

## Run it yourself

```sh
python3 build_board.py data/board.json
python3 -m http.server 8000   # then open http://localhost:8000
```

## Hosting

GitHub Pages serves the site from the `main` branch root: Settings → Pages → Build and deployment → Source: **Deploy from a branch**, Branch: **main** / **(root)**.

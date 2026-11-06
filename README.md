# Prop Exchange

**Live board:** https://mrslythe.github.io/Prop-Exchange/

A daily board of NFL and NBA player props. For every game it lists the players with props, each player's last 5 games and full-season numbers, and whether that player is projected to **hit** (green) or **miss** (red) the Vegas line.

## How it works

- **Lines** come from [scoresandodds.com](https://www.scoresandodds.com) (game lines from `/nfl` and `/nba`, player props from `/nfl/props/*` and `/nba/props/*`). The line used is the midpoint of the best over and best under, which sits close to the consensus.
- **Last 5 games and season stats** come from ESPN's public game logs (every game the player has played this season).
- **Projected %** = 60% × season hit rate + 40% × last-5 hit rate, both against the same line. With fewer than 5 games this season it leans on the last 5, which reach back into last season. 55% or higher is green; otherwise red.
- **Vegas %** is the chance implied by the sportsbook's over price, shown for comparison.
- **Career vs today's opponent**: tap a player's name to open every regular-season and playoff game of his career against that day's opponent, measured against today's lines (games, how many went over, average, each game's number). 🔥 marks a prop he has cleared in at least 60% of 3+ games against that team. Reference only: it does not change the Projected %.
- **Injuries** (ESPN injury report): ⚠️ questionable or day-to-day; players listed out, doubtful, suspended or on injured reserve are greyed out and get no call.
- **Track record**: every call is saved just before its game starts (`data/picks/<date>.json`) and graded after the game against ESPN's final stats (`track.py`). `data/record.json` holds the running totals the site shows: how often green calls went over, how often red calls went under, by league, stat and projection range. Pushes and players who did not play are not counted.
- **Penalty Stocks** (`penalty.py`, the second tab): five parlays per sport, each built from the highest Projected % green calls for one stat (NFL: anytime TD, receiving yards, rushing yards, receptions, passing yards; NBA: points, rebounds, assists, 3-pointers, points+rebounds+assists). One leg per player, no injured players, same-game legs allowed. Each card shows the payout from the best over odds, the combined chance (legs multiplied, assuming independence) and the sportsbook's implied chance, with buttons that open Hard Rock or PrizePicks and copy the picks. Parlays are saved before their first leg starts (`data/parlays/`) and graded from their legs.
- **Badges** (from ESPN player records): 🎂 the game is on the player's birthday · 😤 revenge game, the opponent is a team he played for last season · 🏠 hometown game, the arena is within 35 miles of his birthplace · 📍 home-state (or home-country) game. Distances use the US Census place list in `data/us_places.tsv`.
- Props for players with fewer than 5 games this season are left out.

Five games is a small sample and ignores injuries, matchups and minutes. Treat it as one input.

## Files

| File | What it does |
| --- | --- |
| `index.html` | The board. Loads `data/board.json`. |
| `build_board.py` | Pulls the lines, game logs and injury report and writes `data/board.json`, then runs the tracker. Python 3 standard library plus `curl`. |
| `penalty.py` | Builds the Penalty Stocks parlays from the board. |
| `track.py` | Saves each call before its game and grades it afterward; writes `data/picks/` and `data/record.json`. |
| `.github/workflows/update-board.yml` | Runs the builder twice a day (14:44 and 21:44 UTC) and commits the new data. Can also be run by hand from the Actions tab. |

## Run it yourself

```sh
python3 build_board.py data/board.json
python3 -m http.server 8000   # then open http://localhost:8000
```

## Hosting

GitHub Pages serves the site from the `main` branch root: Settings → Pages → Build and deployment → Source: **Deploy from a branch**, Branch: **main** / **(root)**.

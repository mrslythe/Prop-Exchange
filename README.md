# Prop Exchange

**Live board:** https://mrslythe.github.io/Prop-Exchange/

A daily board of NFL and NBA player props. For every game it lists the players with props, each player's last 5 games and full-season numbers, and whether that player is projected to **hit** (green) or **miss** (red) the Vegas line.

## How it works

- **Lines** come from [scoresandodds.com](https://www.scoresandodds.com) (game lines from `/nfl` and `/nba`, player props from `/nfl/props/*` and `/nba/props/*`). The line used is the midpoint of the best over and best under, which sits close to the consensus.
- **Last 5 games and season stats** come from ESPN's public game logs (every game the player has played this season).
- **Projected %** = 60% × season hit rate + 40% × last-5 hit rate, both against the same line. With fewer than 5 games this season it leans on the last 5, which reach back into last season. 55% or higher is green; otherwise red.
- **Vegas %** is the chance implied by the sportsbook's over price, shown for comparison.
- **Career vs today's opponent**: tap a player's name to open every regular-season and playoff game of his career against that day's opponent, measured against today's lines (games, how many went over, average, each game's number). 🔥 marks a prop he has cleared in at least 60% of 3+ games against that team. Reference only: it does not change the Projected %.
- **Badges** (from ESPN player records): 🎂 the game is on the player's birthday · 😤 revenge game, the opponent is a team he played for last season · 🏠 hometown game, the arena is within 35 miles of his birthplace · 📍 home-state (or home-country) game. Distances use the US Census place list in `data/us_places.tsv`.
- Props for players with fewer than 5 games this season are left out.

Five games is a small sample and ignores injuries, matchups and minutes. Treat it as one input.

## Files

| File | What it does |
| --- | --- |
| `index.html` | The board. Loads `data/board.json`. |
| `build_board.py` | Pulls the lines and game logs and writes `data/board.json`. Python 3 standard library plus `curl`. |
| `.github/workflows/update-board.yml` | Runs the builder every day at 18:14 UTC and commits the new data. Can also be run by hand from the Actions tab. |

## Run it yourself

```sh
python3 build_board.py data/board.json
python3 -m http.server 8000   # then open http://localhost:8000
```

## Hosting

GitHub Pages serves the site from the `main` branch root: Settings → Pages → Build and deployment → Source: **Deploy from a branch**, Branch: **main** / **(root)**.

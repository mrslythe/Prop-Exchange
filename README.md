# Prop Exchange

A daily board of NFL and NBA player props. For every game it lists the players with props, each player's last 5 games, and whether that player trends to **hit** (green) or **miss** (red) the Vegas line.

## How it works

- **Lines** come from [scoresandodds.com](https://www.scoresandodds.com) (game lines from `/nfl` and `/nba`, player props from `/nfl/props/*` and `/nba/props/*`). The line used is the midpoint of the best over and best under, which sits close to the consensus.
- **Last 5 games** come from ESPN's public game logs.
- **Hit %** is the share of the last 5 games that went over the line. 3 or more of 5 is green; otherwise red.
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

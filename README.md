# Prop Exchange

**Live board:** https://mrslythe.github.io/Prop-Exchange/

A daily board of NFL and NBA player props. For every game it lists the players with props, each player's last 5 games and full-season numbers, and whether the board calls the **over** (green), a **lean** (yellow) or the **under** (red).

## How it works

- **Lines** come from [scoresandodds.com](https://www.scoresandodds.com) (game lines from `/nfl` and `/nba`, player props from `/nfl/props/*` and `/nba/props/*`). The line used is the midpoint of the best over and best under, which sits close to the consensus.
- **Last 5 games and season stats** come from ESPN's public game logs (every game the player has played this season).
- **Form %** (`form`) = 60% × season hit rate + 40% × last-5 hit rate, both against the same line. With fewer than 5 games this season it leans on the last 5, which reach back into last season.
- **Projected %** (`proj`, `calib.py`, v4 since Nov 27 2026) = the chance of the over from a logistic model, fit separately for NBA and NFL: `logistic(a + b × logit(Vegas no-vig %) + c × logit(Form %))`. Vegas no-vig % comes from both prices with the bookmaker's cut removed; Form % includes the nudges. The weights are refit every Monday on the last 14 days of graded props (`calib.refit`, stored in `data/calib.json` with an honesty check: fit on the older 7 days, scored on the newer 7, against Vegas alone and a coin flip). Form's weight can't go below zero. The first fit (Nov 13–26, 12,050 props) gave Form a weight of 0: the old form-based percentages were far too confident (a 73% over went over about 52% of the time).
- **The call** (`calib.decide`): the chance of each side minus what its odds need to break even (52.4% at −110) is the **edge**. Green **PLAY** on the better side (▲ over or ▼ under) at +3 or more, yellow **LEAN** 0 to +3, red **PASS** when neither side beats its price. **STRONG** = +6 or more. Props save `side`, `chance`, `edge`.
- **Anytime TD** is priced from Vegas alone (yes price × 0.9), marked low confidence and never tagged strong. **0.5 lines on steals and blocks** are left off the board.
- **Game lines** (`gamelines.py`, `ratings.py`, v2 since Nov 27 2026): every team gets offense and defense power ratings from all its regular-season games (ridge regression, opponent- and home-adjusted, recent games weighted more). They predict each game's score, which becomes a chance against the total and the spread (normal curve, spread of results measured from the fit). That is blended with Vegas' no-vig chance: `w × model + (1 − w) × Vegas`, with `w` per league and market refit every Monday (`gamelines.refit_weights`: grid search 0–0.6 on the last 6 weeks of graded calls, 40+ needed; first fit NBA spread 0.4, NBA total 0, NFL spread 0.1, NFL total 0.15). Same PLAY / LEAN / PASS edge rule as props. Saved in `data/gamepicks/` (v2 saves `edge`, `mk` = Vegas, `md` = model) and graded from final scores; the track record shows them with $10 profit, the old hit-rate version kept apart.
- **Blue Chips** (`bluechips.py`, third tab): players whose line today is at least 12.5 points, 4.5 rebounds, 4.5 assists or 20.5 PRA (NFL: 224.5 passing, 59.5 rushing, 54.5 receiving yards, 4.5 receptions) and who, in their last game, beat both that night's line (from `data/picks/`) and today's line. Every qualifier is listed by margin; the card is priced as a parlay of all of them. Saved in `data/bluechips/` and graded from the picks: each qualifier as a $10 bet, plus each day's full parlay per stat.
- **Daily Sheet** (`sheet.py`, fourth tab): `data/sheet.json` lists, for today's games still to start, the game-line calls, the green OVER calls and the strong UNDER calls, plus Penny Blocks. Printable, and emailed daily by a scheduled agent.
- **Nudges** (`build_board.py`): the base % (60% season + 40% last 5) is adjusted by: matchup (defense vs the player's position; NFL via `dvp.py`, NBA via `nba.py`; ±8), home/away (this season's hit rate at today's venue vs overall, ±4), NBA minutes trend (last 5 vs season minutes, ±5), NBA back-to-back (−2), and NBA teammate out (the player's hit rate in games his biggest OUT teammate missed, 3+ games needed, ±8). Total capped at ±12; each prop carries `nudges`.
- **NBA box scores** (`nba.py`): every finished regular-season game is cached in `data/nba_box/` (one small file per game, plus `_days.json`) for NBA defense vs position (G/F/C, ranked 1–30) and teammate in/out splits.
- **Prop detail** (tap a stat): bar chart of the last 5/10/20/season games vs the line, alt-line hit rates, home/away split, teammate-out split and the projection breakdown. Players carry `gl` (last 20 games: date, opponent, home, minutes, this season) and each prop `v` (its stat in those games).
- **Line movement** (`lines.py`): the first line and prices seen for each prop are kept in `data/lines/<game date>.json`; each prop carries `open` and `move` (current line − opening line).
- **NFL matchup** (`dvp.py`): every finished game's ESPN box score is credited to each player's position (QB, RB, WR, TE) and to the defense he faced (cached in `data/nfl_box/`). Each defense's per-game average allowed for the prop's stat is ranked 1 (toughest) to 32. Form % is nudged by 25 points per 100% above or below the league average, capped at ±8; the pre-matchup value is kept as `projBase`.
- **Vegas %** is the chance implied by the sportsbook's over price, shown for comparison.
- **Career vs today's opponent**: tap a player's name to open every regular-season and playoff game of his career against that day's opponent, measured against today's lines (games, how many went over, average, each game's number). 🔥 marks a prop he has cleared in at least 60% of 3+ games against that team. Reference only: it does not change the projection.
- **Injuries** (ESPN injury report): ⚠️ questionable or day-to-day; players listed out, doubtful, suspended or on injured reserve are greyed out and get no call.
- **Track record**: every call is saved just before its game starts (`data/picks/<date>.json`) and graded after the game against ESPN's final stats (`track.py`). `data/record.json` holds the running totals the site shows: how often green Over calls went over and red Under calls went under (plus Strong calls), by league, stat and projection range. Yellow leans are counted separately. **Weekly view**: the record's headline is the current week (Monday to Sunday by the game's Eastern date, starting fresh each Monday), with a week-by-week table (`weeks`) and all-time totals kept underneath; Penny Blocks and game lines also show this week. **Profit tracker**: each call is also scored as a $10 bet at the best price saved with it (`oo`/`uo` odds, else the Vegas %), so the record shows dollars won or lost, not just hit rate; Penny Blocks shows the same for $10 on each parlay. Red anytime-TD calls are not counted as Under picks (there is no "no TD" price). Picks from earlier versions (Nov 6–12) are reported separately as `v1`. Pushes and players who did not play are not counted.
- **Penny Blocks** (`penalty.py`, the second tab): five parlays per sport, each built from the overs for one stat: green plays first, then yellow leans, then the likeliest of the rest (anytime TD takes the likeliest scorers) (NFL: anytime TD, receiving yards, rushing yards, receptions, passing yards; NBA: points, rebounds, assists, 3-pointers, points+rebounds+assists). One leg per player, no injured players, same-game legs allowed. Each card shows the payout from the best over odds, the combined chance (legs multiplied, assuming independence) and the sportsbook's implied chance, with buttons that open Hard Rock or PrizePicks and copy the picks. Parlays are saved before their first leg starts (`data/parlays/`) and graded from their legs.
- **Badges** (from ESPN player records): 🎂 the game is on the player's birthday · 😤 revenge game, the opponent is a team he played for last season · 🏠 hometown game, the arena is within 35 miles of his birthplace · 📍 home-state (or home-country) game. Distances use the US Census place list in `data/us_places.tsv`.
- Props for players with fewer than 5 games this season are left out.

Five games is a small sample and ignores injuries, matchups and minutes. Treat it as one input.

## Files

| File | What it does |
| --- | --- |
| `index.html` | The board's page and styles. Has a Content Security Policy: only the site's own script (`app.js`), Google Fonts and its own `data/` files may load. |
| `og.png` | Share-preview image (1200×630) shown when the link is posted in texts, Slack or social apps. |
| `app.js` | The page's script (kept out of `index.html` so the security policy can block every inline script). Bump `?v=` in `index.html` after changing it. |
| `build_board.py` | Pulls the lines, game logs and injury report and writes `data/board.json`, then runs the tracker. Python 3 standard library plus `curl`. |
| `dvp.py` | NFL defense vs. position: box scores, rankings, and the matchup nudge. |
| `nba.py` | NBA box scores: defense vs. position and teammate in/out splits. |
| `penalty.py` | Builds the Penny Blocks parlays from the board. |
| `calib.py` | Projected % (weekly-refit model on Vegas no-vig + Form), the edge-based PLAY/LEAN/PASS call, and the Monday refit. |
| `ratings.py` | Team power ratings (offense/defense, opponent-adjusted) for game totals and spreads. |
| `lines.py` | Line movement: first line seen per prop (`data/lines/`). |
| `gamelines.py` | Game total and spread calls, and final scores for grading them. |
| `bluechips.py` | Builds the Blue Chips cards (big lines that went over last game). |
| `sheet.py` | Writes `data/sheet.json` for the Daily Sheet tab and email. |
| `track.py` | Saves each call before its game and grades it afterward; writes `data/picks/` and `data/record.json`. |
| `.github/workflows/update-board.yml` | Runs the builder and commits the new data. Started hourly 10 AM–8 PM Eastern by a cron-job.org timer (workflow_dispatch); GitHub's own 14:44 and 21:44 UTC schedules are a backup. Can also be run by hand from the Actions tab. |

## Run it yourself

```sh
python3 build_board.py data/board.json
python3 -m http.server 8000   # then open http://localhost:8000
```

## Hosting

GitHub Pages serves the site from the `main` branch root: Settings → Pages → Build and deployment → Source: **Deploy from a branch**, Branch: **main** / **(root)**.

# nhl-props

Tracking spine for NHL player-prop betting: projected lineups and starting goalies before the game,
actual production and deployment after it. Runs on GitHub Actions; all data is committed to `data/`
as small text files, so the repo *is* the database.

## What runs when (all times Eastern)

| Job | Schedule | What it does |
|---|---|---|
| `morning` | 9:00am | Pulls today's + tomorrow's schedule, a first lineup snapshot for every team playing, the starting-goalies board, and any boxscores from the last two days that were missed. |
| `evening` | every 30 min, 4:00pm–11:30pm | Refreshes the goalie board, and re-pulls Daily Faceoff lines for any team whose game starts within 3 hours (until ~15 min after puck drop). A lineup snapshot is only saved when something changed. |
| `overnight` | 4:00am | Pulls boxscores and shift charts for finished games, derives actual linemates from shift overlap. |

Any job can be run by hand from the **Actions** tab (`Run workflow`), optionally for a specific date.

## Data layout

```
data/schedule/YYYY-MM-DD.json          games for the day (id, start time, teams, state)
data/lineups/YYYY-MM-DD/TEAM/<utc>.json   Daily Faceoff lines/pairs/goalies/PP/PK/injuries — one file per change
data/goalies/YYYY-MM-DD.csv            starting-goalie board, one row per goalie per run (Confirmed/Unconfirmed)
data/boxscores/<game_id>.csv           per-player G/A/P/SOG/TOI/PP TOI etc. from the NHL API
data/shifts/<game_id>.csv              raw shift chart
data/lines_actual/<game_id>.csv        per-skater shift TOI and most-common linemates (who actually played together)
data/games/<game_id>.json              final score / OT / SO
data/debug/                            raw HTML saved only when a Daily Faceoff parse fails
```

## Local use

```
pip install -r requirements.txt
PYTHONPATH=src python -m nhl_props.run morning            # or evening / overnight
PYTHONPATH=src python -m nhl_props.run backfill --days 14  # boxscores + shifts for the last 14 days
PYTHONPATH=src python -m nhl_props.build_db               # -> nhl_props.sqlite (games, player_games, shifts,
                                                          #    lines_actual, lineup_slots, latest_lineup, goalie_starts, injuries)
```

## Next layers (not built yet)

1. Odds snapshots (The Odds API: DK/FD/MGM points, assists, goals, alternates) 2–3×/day + closing lines.
2. Bet365 feed.
3. Bet log + auto-grading against `player_games`.
4. Modeling: point/goal/assist distributions conditioned on deployment, goalie, opponent; SGP correlation.

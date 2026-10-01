# nhl-props

Tracking spine for NHL player-prop betting: projected lineups and starting goalies before the game,
actual production and deployment after it. Runs on GitHub Actions; all data is committed to `data/`
as small text files, so the repo *is* the database.

**Daily one-pager:** https://jjurgill14.github.io/nhl-props/ — regenerated after every run
(tonight's slate with goalies/lines/PP1/injuries and lineup changes, hot list, last night's results and
projection check, data health).

## What runs when (all times Eastern)

| Job | Schedule | What it does |
|---|---|---|
| `morning` | 9:00am | Pulls today's + tomorrow's schedule, a first lineup snapshot for every team playing, the starting-goalies board, and any boxscores from the last two days that were missed. |
| `evening` | starts 4:00pm, then every 15 min until 11:45pm | One long-running job that loops: refreshes the goalie board and re-pulls Daily Faceoff lines for any team whose game starts within 3 hours (until ~15 min after puck drop), committing each cycle. A lineup snapshot is only saved when something changed. Backup starts at 6pm and 8pm cover a late GitHub scheduler. |
| `overnight` | 4:00am | Pulls boxscores and shift charts for finished games, derives actual linemates from shift overlap. |
| `backfill` | manual only | Re-pulls boxscores/shifts for the last N days (`force` re-pulls games that already have files). |

Any job can be run by hand from the **Actions** tab (`Run workflow`), optionally for a specific date.
GitHub's cron is often late (hours, on quiet repos) — that's why the evening job is a loop rather than 30-min crons.

## Data layout

```
data/schedule/YYYY-MM-DD.json          games for the day (id, start time, teams, state)
data/lineups/YYYY-MM-DD/TEAM/<utc>.json   Daily Faceoff lines/pairs/goalies/PP/PK/injuries — one file per change
data/goalies/YYYY-MM-DD.csv            starting-goalie board, one row per goalie per run (Confirmed/Unconfirmed)
data/boxscores/<game_id>.csv           per-player G/A/P/SOG/TOI/PP TOI etc. from the NHL API
data/shifts/<game_id>.csv              raw shift chart
data/lines_actual/<game_id>.csv        per-skater shift TOI and most-common linemates (who actually played together)
data/games/<game_id>.json              final score / OT / SO
data/debug/                            raw HTML saved only when a Daily Faceoff parse fails (pruned after 2 days)
data/runs.jsonl                        one line per job run
docs/index.html                        the one-pager (GitHub Pages)
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

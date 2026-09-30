"""Job entry points. Usage: python -m nhl_props.run {morning|evening|overnight|backfill} [--date YYYY-MM-DD]"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from . import goalies, lineups, results, schedule
from .common import ET, log, now_utc, today_et

WINDOW_HOURS = 3.0


def _dates_back(n: int, anchor: str) -> list[str]:
    d0 = datetime.strptime(anchor, "%Y-%m-%d")
    return [(d0 - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def ingest_finished(dates: list[str]) -> None:
    for d in dates:
        games = schedule.load_day(d) or schedule.save_day(d)
        for g in games:
            if g["game_type"] == 1:  # skip preseason
                continue
            box = results.BOX_DIR / f"{g['game_id']}.csv"
            shifts = results.SHIFT_DIR / f"{g['game_id']}.csv"
            if box.exists() and shifts.exists():
                continue
            try:
                st = results.ingest_game(g["game_id"], force=box.exists() and not shifts.exists())
                log.info("ingest %s %s@%s: %s", g["game_id"], g["away"], g["home"], st)
            except Exception as e:
                log.error("ingest %s failed: %s", g["game_id"], e)


def morning(date: str) -> None:
    games = schedule.save_day(date)
    schedule.save_day((datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"))
    teams = [t for g in games for t in (g["away"], g["home"])]
    if teams:
        lineups.snapshot_teams(teams, date)
        goalies.snapshot(date)
    ingest_finished(_dates_back(3, date)[1:])  # yesterday and the day before, in case overnight missed


def evening(date: str) -> None:
    games = schedule.save_day(date)
    soon = schedule.games_starting_within(games, WINDOW_HOURS)
    log.info("%d games today, %d within %.0fh window", len(games), len(soon), WINDOW_HOURS)
    if not games:
        return
    goalies.snapshot(date)
    teams = [t for g in soon for t in (g["away"], g["home"])]
    if teams:
        res = lineups.snapshot_teams(teams, date)
        log.info("lineups: %s", res)


def overnight(date: str) -> None:
    # runs ~4am ET: finalize yesterday's games (and catch stragglers from earlier)
    ingest_finished(_dates_back(4, date))


def prune_debug(max_age_days: int = 2) -> None:
    """Debug HTML captures are only useful for a day or two; keep the repo small."""
    from .lineups import DEBUG_DIR
    if not DEBUG_DIR.exists():
        return
    cutoff = now_utc().timestamp() - max_age_days * 86400
    for f in DEBUG_DIR.glob("*.html"):
        # Actions checkouts reset mtimes, so read the UTC stamp from the file name instead
        try:
            ts = datetime.strptime(f.stem.rsplit("_", 1)[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
        if ts < cutoff:
            f.unlink()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["morning", "evening", "overnight", "backfill"])
    ap.add_argument("--date", default=None, help="ET game date, default today")
    ap.add_argument("--days", type=int, default=7, help="backfill: how many days back")
    a = ap.parse_args()
    date = a.date or today_et()
    log.info("job=%s date=%s now_et=%s", a.job, date, now_utc().astimezone(ET).strftime("%H:%M"))
    prune_debug()
    if a.job == "morning":
        morning(date)
    elif a.job == "evening":
        evening(date)
    elif a.job == "overnight":
        overnight(date)
    elif a.job == "backfill":
        ingest_finished(_dates_back(a.days, date))


if __name__ == "__main__":
    main()

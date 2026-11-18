"""Job entry points. Usage: python -m nhl_props.run {morning|evening|overnight|backfill} [--date YYYY-MM-DD]"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from . import alerts, goalies, lineups, report, results, roster, schedule
from .common import DATA, ET, log, now_utc, parse_utc, today_et

WINDOW_HOURS = 3.0


def _dates_back(n: int, anchor: str) -> list[str]:
    d0 = datetime.strptime(anchor, "%Y-%m-%d")
    return [(d0 - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def ingest_finished(dates: list[str], *, force: bool = False) -> None:
    for d in dates:
        games = schedule.load_day(d) or schedule.save_day(d)
        for g in games:
            if g["game_type"] == 1:  # skip preseason
                continue
            box = results.BOX_DIR / f"{g['game_id']}.csv"
            shifts = results.SHIFT_DIR / f"{g['game_id']}.csv"
            if box.exists() and shifts.exists() and not force:
                continue
            try:
                st = results.ingest_game(g["game_id"], force=force or (box.exists() and not shifts.exists()))
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
    try:
        from . import assets
        assets.logos()
        assets.headshots()
        from . import badges
        badges.build()
    except Exception as e:  # assets are nice-to-have, never block data
        log.error("assets failed: %s", e)


def evening(date: str) -> None:
    games = schedule.save_day(date)
    soon = schedule.games_starting_within(games, WINDOW_HOURS)
    log.info("%d games today, %d within %.0fh window", len(games), len(soon), WINDOW_HOURS)
    if not games:
        return
    goalies.snapshot(date)
    new_alerts: list[dict] = []
    for g in soon:
        for side in ("away", "home"):
            t, o = g[side], g["home" if side == "away" else "away"]
            prev = lineups.latest(t, date)
            try:
                status, changed = lineups.snapshot_team(t, date)
            except Exception as e:
                log.error("DFO %s failed: %s", t, e)
                continue
            items = alerts.diff_goalies(date, t)
            if changed:
                cur = lineups.latest(t, date)
                items += alerts.diff_snapshots(prev, cur)
            new_alerts += alerts.record(date, t, o, g.get("start_utc", ""), items, (lineups.latest(t, date) or {}).get("updated_dfo"))
    try:  # B: measure when the league publishes the dressed roster (never blocks the loop)
        cutoff = now_utc() - timedelta(minutes=30)
        upcoming = [g for g in schedule.games_starting_within(games, WINDOW_HOURS, include_started=True) if parse_utc(g["start_utc"]) >= cutoff]
        roster.probe(upcoming, date)
    except Exception as e:
        log.warning("roster probe: %s", e)
    hot = schedule.games_starting_within(games, 1.0)
    (DATA / "next_sleep").write_text("300" if hot else "900")
    alerts.publish(date)
    try:  # one card per game about an hour out, whether or not anything changed
        alerts.pregame(date, games)
    except Exception as e:
        log.error("pregame card failed: %s", e)
    if new_alerts:
        log.info("late changes: %s", [a["text"] for a in new_alerts])
        alerts.notify(date, new_alerts)


def overnight(date: str) -> None:
    results.fill_team_stats()  # PP opportunities for any game that lacks them (idempotent)
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
    ap.add_argument("--force", action="store_true", help="backfill: re-pull games that already have files")
    a = ap.parse_args()
    date = a.date or today_et()
    log.info("job=%s date=%s now_et=%s", a.job, date, now_utc().astimezone(ET).strftime("%H:%M"))
    prune_debug()
    try:
        if a.job == "morning":
            morning(date)
        elif a.job == "evening":
            evening(date)
        elif a.job == "overnight":
            overnight(date)
        elif a.job == "backfill":
            ingest_finished(_dates_back(a.days, date), force=a.force)
    finally:
        # always leave a fresh one-pager, even if a source failed mid-run
        report.log_run(a.job, date=date)
        try:
            report.build(today_et())
        except Exception as e:  # the page must never break data collection
            log.error("report failed: %s", e)
        try:
            from . import debrief
            debrief.build(today_et())
        except Exception as e:
            log.error("debrief failed: %s", e)
        try:
            from . import board
            board.build(today_et())
        except Exception as e:
            log.error("board failed: %s", e)


if __name__ == "__main__":
    main()

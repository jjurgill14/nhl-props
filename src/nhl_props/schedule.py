"""Daily schedule from the NHL API. Stored at data/schedule/YYYY-MM-DD.json (one file per game day)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from .common import DATA, NHL_WEB, get_json, log, now_utc, parse_utc, write_json, read_json

SCHED_DIR = DATA / "schedule"


def fetch_day(date: str) -> list[dict]:
    """Fetch the games for one ET date. The API returns a week; we keep the requested day."""
    payload = get_json(f"{NHL_WEB}/schedule/{date}")
    games: list[dict] = []
    for day in payload.get("gameWeek", []):
        if day.get("date") != date:
            continue
        for g in day.get("games", []):
            games.append({
                "game_id": g["id"],
                "date": date,
                "season": g.get("season"),
                "game_type": g.get("gameType"),  # 1 pre, 2 regular, 3 playoffs
                "start_utc": g.get("startTimeUTC"),
                "venue": (g.get("venue") or {}).get("default") if isinstance(g.get("venue"), dict) else g.get("venue"),
                "away": g["awayTeam"]["abbrev"],
                "away_id": g["awayTeam"]["id"],
                "home": g["homeTeam"]["abbrev"],
                "home_id": g["homeTeam"]["id"],
                "state": g.get("gameState"),
                "schedule_state": g.get("gameScheduleState"),
            })
    return games


def save_day(date: str) -> list[dict]:
    games = fetch_day(date)
    path = SCHED_DIR / f"{date}.json"
    prev = read_json(path, {})
    write_json(path, {"date": date, "fetched_utc": now_utc().isoformat(), "games": games})
    log.info("schedule %s: %d games (%s)", date, len(games), "updated" if prev else "new")
    return games


def load_day(date: str) -> list[dict]:
    d = read_json(SCHED_DIR / f"{date}.json")
    return d["games"] if d else []


def games_starting_within(games: list[dict], hours: float, *, include_started: bool = False) -> list[dict]:
    now = now_utc()
    horizon = now + timedelta(hours=hours)
    out = []
    for g in games:
        st = parse_utc(g["start_utc"])
        if include_started:
            if st <= horizon:
                out.append(g)
        elif now - timedelta(minutes=15) <= st <= horizon:
            # keep pulling until ~15 min after puck drop so the last snapshot is the true pregame lineup
            out.append(g)
    return out


def all_schedule_files() -> list[Path]:
    return sorted(SCHED_DIR.glob("*.json"))

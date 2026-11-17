"""NHL pre-game roster probe (official dressed lineup from the league's own API).

Instrumentation first: every evening poll asks api-web for each upcoming game's roster and records
the first time it appears relative to puck drop. Once we know how early it lands, it becomes the
authority inside the final hour. Rosters are saved so the lead-time data is checkable later.

data/roster_probe.jsonl        one line per (game, poll): seen?, minutes to puck drop, counts
data/rosters/<date>/<game_id>.json   first roster seen (player ids + names + positions per side)
"""
from __future__ import annotations

import json

from .common import DATA, NHL_WEB, get, log, now_utc, parse_utc, read_json, write_json

PROBE = DATA / "roster_probe.jsonl"
ROSTER_DIR = DATA / "rosters"


def fetch_roster(game_id: int) -> dict | None:
    """Return {'away': [...], 'home': [...]} from play-by-play rosterSpots, or None if not published."""
    r = get(f"{NHL_WEB}/gamecenter/{game_id}/play-by-play")
    if r.status_code != 200:
        return None
    d = r.json()
    spots = d.get("rosterSpots") or []
    if not spots:
        return None
    away_id, home_id = d["awayTeam"]["id"], d["homeTeam"]["id"]
    out = {"away": [], "home": [], "game_state": d.get("gameState")}
    for s in spots:
        side = "away" if s["teamId"] == away_id else "home"
        out[side].append({"id": s["playerId"], "name": f"{s['firstName']['default']} {s['lastName']['default']}",
                          "pos": s.get("positionCode"), "sweater": s.get("sweaterNumber")})
    return out


def probe(games: list[dict], date: str) -> list[dict]:
    """Probe every game in the list; log and persist. Returns rosters seen this poll."""
    now = now_utc()
    seen = []
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    for g in games:
        gid = g["game_id"]
        mins = round((parse_utc(g["start_utc"]) - now).total_seconds() / 60)
        path = ROSTER_DIR / date / f"{gid}.json"
        first = not path.exists()
        try:
            ros = fetch_roster(gid)
        except Exception as e:
            log.warning("roster %s: %s", gid, e)
            ros = None
        rec = {"at": now.isoformat(), "date": date, "game_id": gid, "away": g["away"], "home": g["home"],
               "mins_to_puck": mins, "seen": ros is not None,
               "n_away": len(ros["away"]) if ros else 0, "n_home": len(ros["home"]) if ros else 0,
               "state": ros.get("game_state") if ros else None, "first": bool(ros) and first}
        with open(PROBE, "a") as f:
            f.write(json.dumps(rec) + "\n")
        if ros:
            if first:
                write_json(path, {**rec, **ros})
                log.info("roster %s %s@%s published %d min before puck drop (%d/%d)", gid, g["away"], g["home"], mins, rec["n_away"], rec["n_home"])
            seen.append({**rec, **ros})
    return seen


def lead_times() -> list[dict]:
    """For the punch list: per game, how many minutes before puck drop the roster first appeared."""
    if not PROBE.exists():
        return []
    rows = [json.loads(l) for l in PROBE.read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get("first")]

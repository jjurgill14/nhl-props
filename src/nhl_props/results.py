"""Post-game truth from the NHL API: boxscore player stats and shift charts.

Files:
  data/boxscores/<game_id>.csv     one row per player who dressed (skaters + goalies)
  data/shifts/<game_id>.csv        raw shift chart rows
  data/lines_actual/<game_id>.csv  per-skater actual deployment derived from shift overlap
                                   (most-common linemates, EV/PP TOI)
"""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations

from .common import DATA, NHL_STATS, NHL_WEB, get_json, log, write_csv, write_json

BOX_DIR = DATA / "boxscores"
SHIFT_DIR = DATA / "shifts"
LINES_DIR = DATA / "lines_actual"
GAMEINFO_DIR = DATA / "games"

SKATER_FIELDS = ["game_id", "date", "team", "opp", "home", "player_id", "player", "full_name", "sweater", "pos",
                 "goals", "assists", "points", "plus_minus", "pim", "hits", "pp_goals", "sog",
                 "faceoff_pct", "toi", "toi_s", "ev_toi_s", "pp_toi_s", "sh_toi_s", "blocked", "shifts",
                 "giveaways", "takeaways",
                 "starter", "decision", "shots_against", "saves", "save_pct", "goals_against"]


def _toi_secs(s: str | None) -> int:
    if not s or ":" not in s:
        return 0
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def fetch_boxscore(game_id: int) -> dict:
    return get_json(f"{NHL_WEB}/gamecenter/{game_id}/boxscore")


def boxscore_rows(box: dict) -> list[dict]:
    rows = []
    date = box.get("gameDate")
    teams = {"awayTeam": box["awayTeam"]["abbrev"], "homeTeam": box["homeTeam"]["abbrev"]}
    pbgs = box.get("playerByGameStats") or {}
    for side, abbrev in teams.items():
        opp = teams["homeTeam"] if side == "awayTeam" else teams["awayTeam"]
        for group in ("forwards", "defense", "defensemen", "goalies"):
            for p in (pbgs.get(side) or {}).get(group, []):
                sa = p.get("saveShotsAgainst")  # "27/29" style for goalies
                saves = shots = None
                if isinstance(sa, str) and "/" in sa:
                    saves, shots = (int(x) for x in sa.split("/"))
                rows.append({
                    "game_id": box["id"], "date": date, "team": abbrev, "opp": opp,
                    "home": int(side == "homeTeam"),
                    "player_id": p.get("playerId"), "player": (p.get("name") or {}).get("default"),
                    "sweater": p.get("sweaterNumber"), "pos": p.get("position"),
                    "goals": p.get("goals"), "assists": p.get("assists"), "points": p.get("points"),
                    "plus_minus": p.get("plusMinus"), "pim": p.get("pim"), "hits": p.get("hits"),
                    "pp_goals": p.get("powerPlayGoals"), "sog": p.get("sog"),
                    "faceoff_pct": p.get("faceoffWinningPctg"),
                    "toi": p.get("toi"), "pp_toi": p.get("powerPlayToi"), "sh_toi": p.get("shorthandedToi"),
                    "blocked": p.get("blockedShots"), "shifts": p.get("shifts"),
                    "giveaways": p.get("giveaways"), "takeaways": p.get("takeaways"),
                    "starter": p.get("starter"), "decision": p.get("decision"),
                    "shots_against": shots, "saves": saves, "save_pct": p.get("savePctg"),
                    "goals_against": p.get("goalsAgainst"),
                })
    return rows


def fetch_toi(game_id: int) -> dict[int, dict]:
    """EV/PP/SH time on ice in seconds per skater, from the NHL stats REST API (not in the boxscore)."""
    payload = get_json(f"{NHL_STATS}/skater/timeonice?cayenneExp=gameId={game_id}&limit=-1")
    out = {}
    for r in payload.get("data", []):
        out[r["playerId"]] = {
            "full_name": r.get("skaterFullName"), "toi_s": r.get("timeOnIce"), "ev_toi_s": r.get("evTimeOnIce"),
            "pp_toi_s": r.get("ppTimeOnIce"), "sh_toi_s": r.get("shTimeOnIce"),
        }
    return out


def fetch_shifts(game_id: int) -> list[dict]:
    payload = get_json(f"{NHL_STATS}/shiftcharts?cayenneExp=gameId={game_id}")
    out = []
    for s in payload.get("data", []):
        if s.get("typeCode") != 517:  # 517 = shift; other codes are goal/penalty markers
            continue
        out.append({
            "game_id": game_id, "player_id": s["playerId"], "team": s.get("teamAbbrev"),
            "player": f"{s.get('firstName','')} {s.get('lastName','')}".strip(),
            "period": s["period"], "shift_no": s.get("shiftNumber"),
            "start": s["startTime"], "end": s["endTime"], "duration": s.get("duration"),
            "start_s": (s["period"] - 1) * 1200 + _toi_secs(s["startTime"]),
            "end_s": (s["period"] - 1) * 1200 + _toi_secs(s["endTime"]),
        })
    return out


def derive_lines(shifts: list[dict], box_rows: list[dict]) -> list[dict]:
    """For each skater: total shift TOI and the teammates they shared the most ice with."""
    pos = {r["player_id"]: r["pos"] for r in box_rows}
    by_team: dict[str, dict[int, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    names: dict[int, str] = {}
    for s in shifts:
        if pos.get(s["player_id"]) == "G":
            continue
        by_team[s["team"]][s["player_id"]].append((s["start_s"], s["end_s"]))
        names[s["player_id"]] = s["player"]

    out = []
    for team, players in by_team.items():
        overlap: dict[tuple[int, int], int] = defaultdict(int)
        for a, b in combinations(players, 2):
            tot = 0
            for s1, e1 in players[a]:
                for s2, e2 in players[b]:
                    tot += max(0, min(e1, e2) - max(s1, s2))
            overlap[(a, b)] = overlap[(b, a)] = tot
        for pid, shs in players.items():
            toi = sum(e - s for s, e in shs)
            mates = sorted(((overlap[(pid, o)], o) for o in players if o != pid), reverse=True)
            fw = [(t, o) for t, o in mates if pos.get(o) != "D"]
            dm = [(t, o) for t, o in mates if pos.get(o) == "D"]
            top_f = fw[:2] if pos.get(pid) != "D" else fw[:3]
            top_d = dm[:1] if pos.get(pid) == "D" else dm[:2]
            out.append({
                "game_id": shifts[0]["game_id"] if shifts else None, "team": team,
                "player_id": pid, "player": names.get(pid), "pos": pos.get(pid),
                "shift_toi_s": toi, "n_shifts": len(shs),
                "linemates_f": "; ".join(f"{names.get(o)} ({t}s)" for t, o in top_f),
                "linemates_d": "; ".join(f"{names.get(o)} ({t}s)" for t, o in top_d),
            })
    return out


def ingest_game(game_id: int, *, force: bool = False) -> str:
    box_path = BOX_DIR / f"{game_id}.csv"
    if box_path.exists() and not force:
        return "exists"
    box = fetch_boxscore(game_id)
    state = box.get("gameState")
    if state not in ("OFF", "FINAL"):
        return f"not_final:{state}"
    rows = boxscore_rows(box)
    if not rows:
        return "no_player_stats"
    try:
        toi = fetch_toi(game_id)
        for r in rows:
            r.update(toi.get(r["player_id"], {}))
            if not r.get("toi_s"):
                r["toi_s"] = _toi_secs(r.get("toi"))
    except Exception as e:
        log.warning("timeonice for %s failed (%s) — continuing without PP/SH TOI", game_id, e)
    write_csv(box_path, rows, SKATER_FIELDS)
    write_json(GAMEINFO_DIR / f"{game_id}.json", {
        "game_id": box["id"], "date": box.get("gameDate"), "state": state, "start_utc": box.get("startTimeUTC"),
        "away": box["awayTeam"]["abbrev"], "home": box["homeTeam"]["abbrev"],
        "away_score": box["awayTeam"].get("score"), "home_score": box["homeTeam"].get("score"),
        "periods": (box.get("periodDescriptor") or {}).get("number"),
        "last_period_type": (box.get("gameOutcome") or {}).get("lastPeriodType"),
    })
    try:
        shifts = fetch_shifts(game_id)
        write_csv(SHIFT_DIR / f"{game_id}.csv", shifts)
        write_csv(LINES_DIR / f"{game_id}.csv", derive_lines(shifts, rows))
    except Exception as e:  # shifts sometimes lag the boxscore by a while
        log.warning("shifts for %s failed (%s) — boxscore kept, will retry via --force later", game_id, e)
        return "boxscore_only"
    log.info("game %s: %d player rows, %d shifts", game_id, len(rows), len(shifts))
    return "written"

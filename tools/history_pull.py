"""Pull prior seasons' skater game logs (points, shots, even-strength and power-play ice time) for studies.

    PYTHONPATH=src python tools/history_pull.py 20252026 20242025 ...

Writes data/history/skaters_<season>.csv.gz — one row per skater per regular-season game. This is study data
only (line-vs-defense, travel, rest); nothing on the board reads it.

Primary source: the NHL stats REST API's per-game skater reports (two reports, paged 100 rows at a time).
Fallback if that report shape isn't available: one boxscore + one time-on-ice call per game (the same calls
the nightly job makes), threaded.
"""
from __future__ import annotations

import csv
import gzip
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nhl_props.common import NHL_STATS, get_json, log  # noqa: E402
from nhl_props import results  # noqa: E402

OUT = ROOT / "data" / "history"
FIELDS = ["game_id", "date", "team", "opp", "home", "player_id", "player", "pos", "goals", "assists", "points",
          "ev_points", "pp_points", "sog", "toi_s", "ev_toi_s", "pp_toi_s"]
PAGE = 100
SORT = json.dumps([{"property": "gameId", "direction": "ASC"}, {"property": "playerId", "direction": "ASC"}])


def _page(report: str, season: str, start: int) -> dict:
    url = (f"{NHL_STATS}/skater/{report}?isAggregate=false&isGame=true&start={start}&limit={PAGE}"
           f"&sort={SORT}&cayenneExp=gameTypeId=2 and seasonId={season}")
    return get_json(url)


def _report(report: str, season: str) -> list[dict]:
    first = _page(report, season, 0)
    rows, total = list(first.get("data", [])), int(first.get("total") or 0)
    if not rows or "gameId" not in rows[0]:
        raise RuntimeError(f"{report}: no per-game rows (keys: {sorted(rows[0])[:12] if rows else 'none'})")
    starts = list(range(PAGE, total, PAGE))
    with ThreadPoolExecutor(6) as ex:
        for part in ex.map(lambda s: _page(report, season, s).get("data", []), starts):
            rows.extend(part)
    log.info("%s %s: %d rows (API total %d)", report, season, len(rows), total)
    return rows


def bulk(season: str) -> list[dict]:
    summ, toi = _report("summary", season), _report("timeonice", season)
    t = {(r["gameId"], r["playerId"]): r for r in toi}
    out = []
    for r in summ:
        x = t.get((r["gameId"], r["playerId"]), {})
        out.append({
            "game_id": r["gameId"], "date": r.get("gameDate"), "team": r.get("teamAbbrev"), "opp": r.get("opponentTeamAbbrev"),
            "home": int(r.get("homeRoad") == "H"), "player_id": r["playerId"], "player": r.get("skaterFullName"),
            "pos": r.get("positionCode"), "goals": r.get("goals"), "assists": r.get("assists"), "points": r.get("points"),
            "ev_points": r.get("evPoints"), "pp_points": r.get("ppPoints"), "sog": r.get("shots"),
            "toi_s": round(x.get("timeOnIce") or r.get("timeOnIcePerGame") or 0),
            "ev_toi_s": round(x["evTimeOnIce"]) if x.get("evTimeOnIce") is not None else None,
            "pp_toi_s": round(x["ppTimeOnIce"]) if x.get("ppTimeOnIce") is not None else None,
        })
    return out


def _one_game(gid: int) -> list[dict]:
    try:
        rows = [r for r in results.boxscore_rows(results.fetch_boxscore(gid)) if r["pos"] != "G"]
        toi = results.fetch_toi(gid)
    except Exception as e:  # a missing game number or a transient failure: skip, report the count at the end
        log.warning("game %s: %s", gid, e)
        return []
    out = []
    for r in rows:
        x = toi.get(r["player_id"], {})
        out.append({"game_id": gid, "date": r["date"], "team": r["team"], "opp": r["opp"], "home": r["home"],
                    "player_id": r["player_id"], "player": x.get("full_name") or r["player"], "pos": r["pos"],
                    "goals": r["goals"], "assists": r["assists"], "points": r["points"], "ev_points": None,
                    "pp_points": None, "sog": r["sog"], "toi_s": x.get("toi_s") or results._toi_secs(r.get("toi")),
                    "ev_toi_s": x.get("ev_toi_s"), "pp_toi_s": x.get("pp_toi_s")})
    return out


def per_game(season: str) -> list[dict]:
    year = season[:4]
    ids = [int(f"{year}02{n:04d}") for n in range(1, 1313)]
    out = []
    with ThreadPoolExecutor(8) as ex:
        for part in ex.map(_one_game, ids):
            out.extend(part)
    return out


def main(seasons: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for season in seasons:
        t0 = time.time()
        try:
            rows, how = bulk(season), "bulk reports"
        except Exception as e:
            log.warning("%s: bulk pull failed (%s) — falling back to per-game calls", season, e)
            rows, how = per_game(season), "per-game calls"
        if not rows:
            log.error("%s: nothing pulled", season)
            continue
        rows.sort(key=lambda r: (r["game_id"], r["team"], r["player_id"]))
        path = OUT / f"skaters_{season}.csv.gz"
        with gzip.open(path, "wt", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        games = len({r["game_id"] for r in rows})
        log.info("%s: %d skater-games, %d games via %s in %.0fs -> %s", season, len(rows), games, how, time.time() - t0, path.name)
        print(f"{season}: {len(rows)} skater-games, {games} games, {how}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["20252026"])

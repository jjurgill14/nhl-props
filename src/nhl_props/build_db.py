"""Compile the committed CSV/JSON files into one SQLite database for analysis.

    python -m nhl_props.build_db            -> writes nhl_props.sqlite in the repo root (git-ignored)

Tables: games, player_games, shifts, lines_actual, lineup_snapshots, lineup_slots, injuries, goalie_starts
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .common import DATA, ROOT, log

DB = ROOT / "nhl_props.sqlite"


def _load_csvs(con: sqlite3.Connection, table: str, folder: Path) -> int:
    files = sorted(folder.glob("*.csv"))
    n = 0
    for f in files:
        with f.open(newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            continue
        cols = list(rows[0].keys())
        con.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(cols)})")
        con.executemany(f"INSERT INTO {table} VALUES ({', '.join('?' * len(cols))})",
                        [[r.get(c) for c in cols] for r in rows])
        n += len(rows)
    return n


def build() -> Path:
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE games (game_id, date, season, game_type, start_utc, away, home, state, away_score, home_score)")
    for f in sorted((DATA / "schedule").glob("*.json")):
        for g in json.loads(f.read_text())["games"]:
            info = DATA / "games" / f"{g['game_id']}.json"
            sc = json.loads(info.read_text()) if info.exists() else {}
            con.execute("INSERT INTO games VALUES (?,?,?,?,?,?,?,?,?,?)", (
                g["game_id"], g["date"], g["season"], g["game_type"], g["start_utc"], g["away"], g["home"],
                sc.get("state", g["state"]), sc.get("away_score"), sc.get("home_score")))

    n_pg = _load_csvs(con, "player_games", DATA / "boxscores")
    n_sh = _load_csvs(con, "shifts", DATA / "shifts")
    n_la = _load_csvs(con, "lines_actual", DATA / "lines_actual")
    n_gs = _load_csvs(con, "goalie_starts", DATA / "goalies")

    con.execute("CREATE TABLE lineup_snapshots (snapshot_id, team, date, captured_utc, updated_dfo, hash)")
    con.execute("CREATE TABLE lineup_slots (snapshot_id, team, date, section, unit, unit_no, slot, pos, player, dfo_id)")
    con.execute("CREATE TABLE injuries (snapshot_id, team, date, player, dfo_id, status)")
    n_snap = 0
    for f in sorted((DATA / "lineups").glob("*/*/*.json")):
        s = json.loads(f.read_text())
        sid = f"{s['date']}_{s['team']}_{f.stem}"
        con.execute("INSERT INTO lineup_snapshots VALUES (?,?,?,?,?,?)",
                    (sid, s["team"], s["date"], s["captured_utc"], s.get("updated_dfo"), s["hash"]))
        con.executemany("INSERT INTO lineup_slots VALUES (?,?,?,?,?,?,?,?,?,?)", [
            (sid, s["team"], s["date"], r["section"], r["unit"], r["unit_no"], r["slot"], r["pos"], r["player"], r["dfo_id"])
            for r in s["lines"]])
        con.executemany("INSERT INTO injuries VALUES (?,?,?,?,?,?)", [
            (sid, s["team"], s["date"], r["player"], r["dfo_id"], r["status"]) for r in s["injuries"]])
        n_snap += 1

    con.execute("""CREATE VIEW latest_lineup AS
        SELECT ls.* FROM lineup_slots ls
        JOIN (SELECT team, date, MAX(captured_utc) AS mx FROM lineup_snapshots GROUP BY team, date) m
          ON m.team = ls.team AND m.date = ls.date
        JOIN lineup_snapshots s ON s.snapshot_id = ls.snapshot_id AND s.captured_utc = m.mx""")
    con.commit()
    con.close()
    log.info("built %s: %d player-games, %d shifts, %d line rows, %d goalie rows, %d lineup snapshots",
             DB.name, n_pg, n_sh, n_la, n_gs, n_snap)
    return DB


if __name__ == "__main__":
    build()

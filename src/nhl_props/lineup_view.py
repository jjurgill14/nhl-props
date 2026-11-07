"""Lineup view data for ICEBOARD's Lines & Lineups screen.

For a game: both teams' latest DFO snapshot shaped as a grid (F1–F4 as LW/C/RW, D1–D3 as
L/R, G1/G2, PP1/PP2, PK1/PK2), with jersey numbers, NHL player ids (for headshots), season
stat lines, movement vs the team's previous game day, injuries, and goalie W-L-OTL / sv%.
"""
from __future__ import annotations

import csv
import glob
from collections import defaultdict

from . import analysis, report, results


def goalie_records() -> dict[tuple[str, str], dict]:
    """(team, norm name) -> W-L-OTL, sv% from this season's boxscores."""
    out: dict[tuple[str, str], dict] = defaultdict(lambda: {"w": 0, "l": 0, "otl": 0, "sa": 0, "sv": 0, "gs": 0})
    for f in glob.glob(str(results.DATA / "boxscores" / "*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r.get("pos") != "G":
                continue
            k = (r["team"], analysis.norm(r.get("full_name") or r["player"]))
            d = out[k]
            dec = (r.get("decision") or "").upper()
            if dec == "W":
                d["w"] += 1
            elif dec == "L":
                d["l"] += 1
            elif dec in ("O", "OTL"):
                d["otl"] += 1
            d["sa"] += analysis._i(r.get("shots_against"))
            d["sv"] += analysis._i(r.get("saves"))
            if r.get("starter") in ("True", "true", "1"):
                d["gs"] += 1
    return {k: {**v, "record": f"{v['w']}-{v['l']}-{v['otl']}", "sv_pct": (f"{v['sv']/v['sa']:.3f}" if v["sa"] else None)}
            for k, v in out.items()}


def player_ids() -> dict[tuple[str, str], dict]:
    """(team, norm name) -> {'id': NHL player id, 'sweater': number from the most recent boxscore}."""
    ids: dict[tuple[str, str], dict] = {}
    for f in sorted(glob.glob(str(results.DATA / "boxscores" / "*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            n = r.get("full_name") or r["player"]
            if r.get("player_id"):
                ids[(r["team"], analysis.norm(n))] = {"id": int(r["player_id"]), "sweater": analysis._i(r.get("sweater")) or None}
    return ids


_POS_ORDER = {"LW": 0, "C": 1, "RW": 2, "LD": 0, "RD": 1, "G": 0}


def team_lineup(team: str, date: str, logs, ids, grec) -> dict | None:
    snaps = report.team_snapshots(team, date)
    cur = snaps[-1] if snaps else analysis.latest_snapshot_before(team, date)
    if not cur:
        return None
    prev = analysis.latest_snapshot_before(team, date)
    mv = analysis.movement(cur, prev) if prev else {}
    jer = report.jersey_of(cur)
    pp = report.pp_units(cur)
    stats = {p["player"]: p for p in cur.get("players", [])}
    pk: dict[str, int] = {}
    for r in cur.get("lines", []):
        if r["section"] == "PK" and r.get("unit_no") in (1, 2):
            pk[r["player"]] = min(pk.get(r["player"], 9), r["unit_no"])

    def entry(r: dict) -> dict:
        n = r["player"]
        s = stats.get(n, {})
        rows = logs.get((team, analysis.norm(n)), [])
        k5 = sum(1 for x in rows[-5:] if analysis._i(x.get("points")) > 0)
        m = mv.get(n) or {}
        nhl = ids.get((team, analysis.norm(n))) or {}
        e = {
            "name": n, "jersey": nhl.get("sweater") or jer.get(n), "pos": r.get("pos"), "slot": r.get("slot"),
            "player_id": nhl.get("id"), "dfo_id": r.get("dfo_id"),
            "gtd": bool(r.get("gtd")), "injury": r.get("injury_status"),
            "pp": pp.get(n), "pk": pk.get(n), "bias": analysis.bias(rows) if rows else None,
            "season": s.get("season"), "last5": s.get("last5"), "l5_point_games": k5, "gp": len(rows),
            "move": {"ev": m.get("ev", 0), "pp": m.get("pp", 0), "new": bool(m.get("new"))},
        }
        if r["section"] == "G":
            g = grec.get((team, analysis.norm(n)))
            e["record"] = g["record"] if g else None
            e["sv_pct"] = g["sv_pct"] if g else None
            e["starts"] = g["gs"] if g else 0
        return e

    units: dict[str, dict[int, list[dict]]] = {"F": defaultdict(list), "D": defaultdict(list), "G": defaultdict(list),
                                               "PP": defaultdict(list), "PK": defaultdict(list)}
    for r in cur.get("lines", []):
        sec, no = r["section"], r.get("unit_no")
        if sec in units and no:
            units[sec][no].append(entry(r))
    for sec in ("F", "D", "G"):
        for no, ps in units[sec].items():
            ps.sort(key=lambda e: (_POS_ORDER.get(e["pos"] or "", 9), e["slot"] or 0))
    return {
        "team": team, "as_of": cur.get("captured_utc"), "stale": not snaps,
        "source": cur.get("source_name") or "Daily Faceoff", "updated_dfo": cur.get("updated_dfo"),
        "forwards": [units["F"][i] for i in (1, 2, 3, 4)],
        "defense": [units["D"][i] for i in (1, 2, 3)],
        "goalies": [units["G"][i] for i in (1, 2)],
        "pp": [units["PP"][i] for i in (1, 2)],
        "pk": [units["PK"][i] for i in (1, 2)],
        "injuries": [{"player": i["player"], "status": i.get("status"), "news": i.get("news")} for i in cur.get("injuries", [])],
        "unit_ratings": cur.get("unit_ratings"),
    }


def game_lineups(away: str, home: str, date: str, logs=None, ids=None, grec=None) -> dict:
    logs = logs if logs is not None else analysis.player_logs(analysis.all_boxscores())
    ids = ids if ids is not None else player_ids()
    grec = grec if grec is not None else goalie_records()
    return {"away": team_lineup(away, date, logs, ids, grec), "home": team_lineup(home, date, logs, ids, grec)}

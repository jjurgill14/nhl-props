"""Season-to-date analytics used by the one-pager: team rates, player G/A bias, line movement,
linemate correlation, and the "best bets" scorer. Everything is THIS season only, from our own
boxscores and lineup snapshots.
"""
from __future__ import annotations

import csv
import unicodedata
from collections import defaultdict
from pathlib import Path

from . import lineups, results, schedule
from .common import read_json


def norm(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").replace(".", "").split())


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _i(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


# ----------------------------------------------------------------------------- game logs
def all_boxscores() -> dict[int, list[dict]]:
    out = {}
    if results.BOX_DIR.exists():
        for f in sorted(results.BOX_DIR.glob("*.csv")):
            rows = read_csv(f)
            if rows:
                out[int(f.stem)] = rows
    return out


def player_logs(boxes: dict[int, list[dict]]) -> dict[tuple[str, str], list[dict]]:
    """(team, norm full name) -> game rows oldest first (skaters only)."""
    logs: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for gid in sorted(boxes):
        for r in boxes[gid]:
            if r.get("pos") == "G":
                continue
            logs[(r["team"], norm(r.get("full_name") or r["player"]))].append(r)
    for rows in logs.values():
        rows.sort(key=lambda r: (r.get("date") or "", r.get("game_id") or ""))
    return logs


def rolling(rows: list[dict], n: int) -> dict:
    last = rows[-n:]
    gp = len(last)
    if not gp:
        return {}
    tot = lambda k: sum(_i(r.get(k)) for r in last)  # noqa: E731
    return {"gp": gp, "p": tot("points"), "g": tot("goals"), "a": tot("assists"), "sog": tot("sog"),
            "ppg": tot("points") / gp, "gpg": tot("goals") / gp, "spg": tot("sog") / gp, "apg": tot("assists") / gp,
            "pt_games": sum(1 for r in last if _i(r.get("points")) > 0),
            "toi": sum(_i(r.get("toi_s")) for r in last) / gp / 60,
            "pp_toi": sum(_i(r.get("pp_toi_s")) for r in last) / gp / 60}


def bias(rows: list[dict], n: int = 10) -> str | None:
    """'G' if goals dominate points over the window, 'A' if assists do, else None. Needs 3+ points."""
    w = rolling(rows, n)
    if not w or w["p"] < 3:
        return None
    share = w["g"] / w["p"]
    if share >= 0.6:
        return "G"
    if share <= 0.35:
        return "A"
    return None


# ----------------------------------------------------------------------------- team rates
def team_rates(boxes: dict[int, list[dict]], last_n: int | None = None) -> dict[str, dict]:
    """Per team: GF, SF, GA, SA per game (season or last N games)."""
    per_game: dict[str, list[dict]] = defaultdict(list)
    for gid in sorted(boxes):
        rows = boxes[gid]
        teams = sorted({r["team"] for r in rows})
        if len(teams) != 2:
            continue
        agg = {t: {"g": 0, "s": 0} for t in teams}
        for r in rows:
            if r.get("pos") == "G":
                continue
            agg[r["team"]]["g"] += _i(r.get("goals"))
            agg[r["team"]]["s"] += _i(r.get("sog"))
        date = rows[0].get("date")
        for t in teams:
            o = teams[1] if t == teams[0] else teams[0]
            per_game[t].append({"date": date, "gf": agg[t]["g"], "sf": agg[t]["s"], "ga": agg[o]["g"], "sa": agg[o]["s"]})
    out = {}
    for t, gs in per_game.items():
        gs = gs[-last_n:] if last_n else gs
        n = len(gs)
        out[t] = {"gp": n, "gf": sum(g["gf"] for g in gs) / n, "sf": sum(g["sf"] for g in gs) / n,
                  "ga": sum(g["ga"] for g in gs) / n, "sa": sum(g["sa"] for g in gs) / n}
    # ranks: 1 = most (gf/sf) and 1 = most allowed (ga/sa) -- i.e. rank 1 on ga = weakest defense
    for key in ("gf", "sf", "ga", "sa"):
        for i, t in enumerate(sorted(out, key=lambda x: out[x][key], reverse=True), 1):
            out[t][key + "_rk"] = i
    return out


# ----------------------------------------------------------------------------- line movement
def latest_snapshot_before(team: str, date: str) -> dict | None:
    """Last snapshot for the team on the most recent date before `date` (their previous game day)."""
    root = lineups.LINEUP_DIR
    if not root.exists():
        return None
    for d in sorted((p.name for p in root.iterdir() if p.is_dir()), reverse=True):
        if d >= date:
            continue
        files = sorted((root / d / team).glob("*.json")) if (root / d / team).exists() else []
        if files:
            return read_json(files[-1])
    return None


def slots(snap: dict | None) -> dict[str, dict]:
    """player -> {'ev': 1..4 (F) or 1..3 (D), 'pp': 1/2/None}"""
    out: dict[str, dict] = defaultdict(lambda: {"ev": None, "pp": None})
    for r in (snap or {}).get("lines", []):
        if r["section"] in ("F", "D") and r.get("unit_no"):
            out[r["player"]]["ev"] = r["unit_no"]
        elif r["section"] == "PP" and r.get("unit_no") in (1, 2):
            cur = out[r["player"]]["pp"]
            out[r["player"]]["pp"] = min(cur, r["unit_no"]) if cur else r["unit_no"]
    return out


def movement(cur: dict | None, prev: dict | None) -> dict[str, dict]:
    """player -> {'ev': +1 promoted / -1 demoted / 0, 'pp': +1/-1/0, 'new': True if not in prev lineup}"""
    if not cur or not prev:
        return {}
    a, b = slots(prev), slots(cur)
    out = {}
    for p, nb in b.items():
        if p not in a:
            out[p] = {"ev": 0, "pp": 0, "new": True}
            continue
        na = a[p]
        ev = 0
        if na["ev"] and nb["ev"]:
            ev = 1 if nb["ev"] < na["ev"] else (-1 if nb["ev"] > na["ev"] else 0)
        pa, pb = na["pp"] or 3, nb["pp"] or 3  # 3 = no PP time
        pp = 1 if pb < pa else (-1 if pb > pa else 0)
        if ev or pp:
            out[p] = {"ev": ev, "pp": pp, "new": False}
    return out


# ----------------------------------------------------------------------------- linemate correlation
def pair_stats(boxes: dict[int, list[dict]]) -> dict[tuple[str, str, str], dict]:
    """(team, nameA, nameB) sorted -> games actually together (from shift overlap), both-point games, etc.
    'Together' = each is among the other's top linemates in lines_actual for that game."""
    stats: dict[tuple[str, str, str], dict] = defaultdict(lambda: {"n": 0, "both": 0, "a": 0, "b": 0, "either": 0})
    for gid, rows in boxes.items():
        la = read_csv(results.LINES_DIR / f"{gid}.csv")
        if not la:
            continue
        pts = {(r["team"], norm(r.get("full_name") or r["player"])): _i(r.get("points")) for r in rows}
        mates: dict[tuple[str, str], set[str]] = {}
        for r in la:
            me = (r["team"], norm(r["player"]))
            names = set()
            for col in ("linemates_f", "linemates_d"):
                for part in (r.get(col) or "").split(";"):
                    part = part.strip()
                    if part and "(" in part:
                        names.add(norm(part[: part.rfind("(")].strip()))
            mates[me] = names
        seen = set()
        for (team, a), ms in mates.items():
            for b in ms:
                if (team, b) not in mates or a not in mates[(team, b)]:
                    continue  # require mutual
                key = (team,) + tuple(sorted((a, b)))
                if key in seen:
                    continue
                seen.add(key)
                pa, pb = pts.get((team, key[1]), 0) > 0, pts.get((team, key[2]), 0) > 0
                s = stats[key]
                s["n"] += 1
                s["both"] += pa and pb
                s["a"] += pa
                s["b"] += pb
                s["either"] += pa or pb
    return stats


# ----------------------------------------------------------------------------- best bets
def best_bets(games: list[dict], date: str, logs, rates_season, rates_l5, pairs) -> list[dict]:
    """Score every skater on tonight's slate. Higher = more interesting.
    Ingredients: L5 points/game (this season), PP1, same-line+same-PP stack partner, opponent weakness
    (GA and SA allowed rank), and G/A bias. Early season this is thin — GP is shown so you can discount."""
    out = []
    n_teams = max(len(rates_season), 1)
    for g in games:
        for side, opp_side in (("away", "home"), ("home", "away")):
            team, opp = g[side], g[opp_side]
            snaps = [read_json(p) for p in sorted((lineups.LINEUP_DIR / date / team).glob("*.json"))] if (lineups.LINEUP_DIR / date / team).exists() else []
            if not snaps:
                continue
            cur = snaps[-1]
            sl = slots(cur)
            ev_members: dict[tuple[str, int], list[str]] = defaultdict(list)
            for r in cur.get("lines", []):
                if r["section"] in ("F", "D") and r.get("unit_no"):
                    ev_members[(r["section"], r["unit_no"])].append(r["player"])
            opp_r = rates_season.get(opp) or {}
            opp_weak = 0.0
            if opp_r:
                # 1.0 = weakest defense in the league, 0 = stiffest
                opp_weak = ((n_teams - opp_r["ga_rk"]) / max(n_teams - 1, 1) + (n_teams - opp_r["sa_rk"]) / max(n_teams - 1, 1)) / 2
                opp_weak = 1 - opp_weak  # ga_rk 1 = most goals allowed -> weak -> want high score
            for p in cur.get("players", []):
                name = p["player"]
                if (p.get("pos") or "") in ("G", ""):
                    continue
                rows = logs.get((team, norm(name)), [])
                l5 = rolling(rows, 5)
                if not l5:
                    continue
                s = sl.get(name, {"ev": None, "pp": None})
                # stack partner: same EV line AND same PP unit
                partners = []
                for (sec, no), members in ev_members.items():
                    if name in members:
                        for m in members:
                            if m != name and s.get("pp") and sl.get(m, {}).get("pp") == s["pp"]:
                                partners.append(m)
                pair_lines = []
                for m in partners:
                    key = (team,) + tuple(sorted((norm(name), norm(m))))
                    ps = pairs.get(key)
                    if ps and ps["n"]:
                        pair_lines.append(f"{m}: both scored {ps['both']}/{ps['n']} together")
                    else:
                        pair_lines.append(f"{m}: no games together yet")
                score = (l5["ppg"] * 2.0 + l5["spg"] * 0.15 + (0.6 if s.get("pp") == 1 else 0.25 if s.get("pp") == 2 else 0)
                         + (0.5 if partners else 0) + opp_weak * 1.0 + (0.2 if s.get("ev") == 1 else 0))
                out.append({
                    "team": team, "opp": opp, "player": name, "jersey": p.get("jersey"), "pos": p.get("pos"),
                    "ev": s.get("ev"), "pp": s.get("pp"), "bias": bias(rows), "l5": l5, "partners": partners,
                    "pair_lines": pair_lines, "opp_ga_rk": opp_r.get("ga_rk"), "opp_sa_rk": opp_r.get("sa_rk"),
                    "opp_ga": opp_r.get("ga"), "opp_sa": opp_r.get("sa"), "score": score,
                })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out

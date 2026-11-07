"""Point-prop model (v1): P(player records a point / 2+ points) for every top-9 forward
on today's slate, with fair and minimum prices, pair stats, and why-bullets.

This season only. Shrinks each player's observed hit rate toward a role prior,
then adjusts for opponent, home/road, and back-to-back.  Output is plain dicts so
report code / JSON can render it without re-deriving anything.
"""
from __future__ import annotations

import collections
import math
from datetime import datetime, timedelta, timezone

from . import analysis, report, schedule

PRIOR_N = 8           # pseudo-games of role prior
EDGE = 1.06           # min price = odds at P × EDGE
OPP_NUDGE = 0.16      # ±8% by opponent GA rank (rank 1 = leakiest)
B2B_POINT = 0.86      # second leg of a back-to-back, measured n=57 (team goals −14%)
B2B_TWO = 0.78        # same, for 2+ points
ROLE_PRIOR = {"pp1": 0.54, "top6": 0.34, "other": 0.25}
ROLE_PRIOR_2 = {"pp1": 0.20, "top6": 0.08, "other": 0.04}


def american(p: float) -> str:
    p = min(max(p, 0.02), 0.97)
    return f"+{round(100 * (1 - p) / p)}" if p < 0.5 else f"-{round(100 * p / (1 - p))}"


def _role(pp_unit: int | None, line_no: int) -> str:
    return "pp1" if pp_unit == 1 else ("top6" if line_no <= 2 else "other")


def _hits(rows, key="points", n=None, thresh=1):
    r = rows[-n:] if n else rows
    return sum(1 for x in r if analysis._i(x.get(key)) >= thresh), len(r)


def _played_yesterday(team: str, date: str) -> bool:
    y = (datetime.fromisoformat(date) - timedelta(days=1)).strftime("%Y-%m-%d")
    return any(team in (g["away"], g["home"]) for g in schedule.load_day(y))


def _shrink(k: int, n: int, prior: float) -> float:
    return (k + prior * PRIOR_N) / (n + PRIOR_N)


def _pp_goals_allowed(boxes):
    ppga = collections.defaultdict(float)
    gpn = collections.defaultdict(int)
    for rows in boxes.values():
        teams = sorted({r["team"] for r in rows})
        if len(teams) != 2:
            continue
        for t in teams:
            gpn[t] += 1
        for r in rows:
            if r.get("pos") != "G":
                o = teams[0] if r["team"] == teams[1] else teams[1]
                ppga[o] += analysis._i(r.get("pp_goals"))
    per = {t: ppga[t] / gpn[t] for t in gpn}
    rank = {t: i for i, t in enumerate(sorted(per, key=lambda x: per[x], reverse=True), 1)}
    return per, rank


def build_slate(date: str) -> dict:
    games = sorted(schedule.load_day(date), key=lambda g: g["start_utc"])
    boxes = analysis.all_boxscores()
    logs = analysis.player_logs(boxes)
    pairs = analysis.pair_stats(boxes)
    season = analysis.team_rates(boxes)
    l5 = analysis.team_rates(boxes, 5)
    pk, pk_rk = _pp_goals_allowed(boxes)
    gb = report.goalie_board(date)

    out_games = []
    for g in games:
        teams = {}
        for side in ("away", "home"):
            t = g[side]
            o = g["home" if side == "away" else "away"]
            snaps = report.team_snapshots(t, date)
            cur = snaps[-1] if snaps else analysis.latest_snapshot_before(t, date)
            stale = not snaps
            prev = analysis.latest_snapshot_before(t, date)
            mv = analysis.movement(cur, prev) if cur else {}
            pp = report.pp_units(cur) if cur else {}
            jer = report.jersey_of(cur) if cur else {}
            gl = gb["latest"].get(t, {})
            r = season.get(t, {})
            r5 = l5.get(t, {})
            orr = season.get(o, {})
            b2b = _played_yesterday(t, date)
            ev = collections.defaultdict(list)
            if cur:
                for row in cur.get("lines", []):
                    if row["section"] == "F" and row.get("unit_no"):
                        ev[row["unit_no"]].append(row["player"])
            players = []
            if cur:
                for row in cur.get("lines", []):
                    if row["section"] != "F" or row.get("unit_no") not in (1, 2, 3):
                        continue
                    n = row["player"]
                    rows = logs.get((t, analysis.norm(n)), [])
                    gp = len(rows)
                    k, _ = _hits(rows)
                    k5, n5 = _hits(rows, n=5)
                    ka, _ = _hits(rows, "assists")
                    kg, _ = _hits(rows, "goals")
                    k2, _ = _hits(rows, thresh=2)
                    hk, hn = _hits([x for x in rows if x.get("home") == "1"])
                    ak, an = _hits([x for x in rows if x.get("home") != "1"])
                    role = _role(pp.get(n), row["unit_no"])
                    p = _shrink(k, gp, ROLE_PRIOR[role])
                    p2 = _shrink(k2, gp, ROLE_PRIOR_2[role])
                    adj = []
                    if orr:
                        f = 1 + OPP_NUDGE * ((16.5 - orr.get("ga_rk", 16.5)) / 15.5)
                        p *= f; p2 *= f
                        adj.append(("opp", f))
                    # home/road: only when lopsided and both halves have 4+ games
                    sp_k, sp_n = (hk, hn) if side == "home" else (ak, an)
                    if hn >= 4 and an >= 4 and gp >= 8:
                        side_rate = sp_k / sp_n
                        all_rate = k / gp
                        if abs(side_rate - all_rate) >= 0.20:
                            f = 1 + 0.5 * (side_rate - all_rate) / max(all_rate, 0.2)
                            f = min(max(f, 0.8), 1.2)
                            p *= f; p2 *= f
                            adj.append(("venue", f))
                    if b2b:
                        p *= B2B_POINT; p2 *= B2B_TWO
                        adj.append(("b2b", B2B_POINT))
                    p = min(0.92, p); p2 = min(0.70, p2)
                    avg_pp = sum(analysis._i(x.get("pp_toi_s")) for x in rows[-5:]) / max(1, len(rows[-5:])) / 60
                    avg_toi = sum(analysis._i(x.get("toi_s")) for x in rows[-5:]) / max(1, len(rows[-5:])) / 60
                    partners = []
                    for m in [m for m in ev[row["unit_no"]] if m != n]:
                        q = pairs.get((t,) + tuple(sorted((analysis.norm(n), analysis.norm(m)))))
                        partners.append({
                            "name": m, "jersey": jer.get(m), "pp": pp.get(m),
                            "n": q["n"] if q else 0, "both": q["both"] if q else 0,
                            "either": q["either"] if q else 0,
                        })
                    m = mv.get(n) or {}
                    players.append({
                        "name": n, "jersey": jer.get(n), "team": t, "opp": o,
                        "home": side == "home", "line": row["unit_no"], "pp": pp.get(n),
                        "pos": row.get("pos"), "gtd": row.get("gtd"), "role": role,
                        "bias": analysis.bias(rows),
                        "gp": gp, "pt_games": k, "l5": [k5, n5], "ast_games": ka, "goal_games": kg,
                        "two_games": k2, "home_split": [hk, hn], "away_split": [ak, an],
                        "pp_toi": round(avg_pp, 1), "toi": round(avg_toi, 1),
                        "p": round(p, 3), "fair": american(p), "min": american(min(0.95, p * EDGE)),
                        "p2": round(p2, 3), "fair2": american(p2), "min2": american(min(0.9, p2 * EDGE)),
                        "adj": adj, "move": {"ev": m.get("ev", 0), "pp": m.get("pp", 0), "new": m.get("new", False)},
                        "partners": partners,
                    })
            players.sort(key=lambda x: -x["p"])
            teams[side] = {
                "team": t, "opp": o, "home": side == "home", "b2b": b2b,
                "goalie": gl.get("goalie"), "goalie_status": gl.get("status"),
                "goalie_news": gl.get("news"), "goalie_source": gl.get("source"),
                "sv": gl.get("season_sv_pct"), "gaa": gl.get("season_gaa"),
                "ml": gl.get("moneyline"),
                "gp": r.get("gp"), "gf": r.get("gf"), "gf_rk": r.get("gf_rk"),
                "ga": r.get("ga"), "ga_rk": r.get("ga_rk"), "sa": r.get("sa"), "sa_rk": r.get("sa_rk"),
                "ppga": pk.get(t), "ppga_rk": pk_rk.get(t),
                "l5_gf": r5.get("gf"), "l5_ga": r5.get("ga"),
                "lineup_as_of": cur.get("captured_utc") if cur else None, "lineup_stale": stale,
                "out": [{"player": i["player"], "status": i.get("status"), "news": i.get("news")}
                        for i in (cur.get("injuries", []) if cur else [])],
                "lines": {str(no): ev[no] for no in sorted(ev)},
                "pp1": [p_ for p_, u in pp.items() if u == 1], "pp2": [p_ for p_, u in pp.items() if u == 2],
                "players": players,
            }
        out_games.append({
            "game_id": g["game_id"], "start_utc": g["start_utc"], "start_et": report.et(g["start_utc"]),
            "away": g["away"], "home": g["home"], "state": g.get("state"), "venue": g.get("venue"),
            "teams": teams,
        })
    return {"date": date, "generated_utc": datetime.now(timezone.utc).isoformat(), "games": out_games}


def why(p: dict, team: dict, opp_team: dict) -> list[str]:
    """2–4 short bullets in JJ's register."""
    b = []
    k, gp = p["pt_games"], p["gp"]
    l5k, l5n = p["l5"]
    b.append(f"Point in {k} of {gp} this season, {l5k} of last {l5n}.")
    if p["pp"] == 1:
        b.append(f"PP1, {p['pp_toi']} PP min/game over L5.")
    elif p["pp"] == 2:
        b.append(f"PP2 ({p['pp_toi']} PP min/game).")
    mv = p["move"]
    if mv.get("new"):
        b.append("NEW to the lineup vs. last game.")
    elif mv.get("ev", 0) < 0 or mv.get("pp", 0) < 0:
        b.append("Moved UP " + ("a line" if mv.get("ev", 0) < 0 else "a PP unit") + " since last game.")
    elif mv.get("ev", 0) > 0 or mv.get("pp", 0) > 0:
        b.append("Moved DOWN since last game.")
    rk = opp_team.get("ga_rk")
    if rk:
        b.append(f"{p['opp']} allows {opp_team['ga']:.2f} goals/game (#{rk} of 32)"
                 + (f", PK #{opp_team['ppga_rk']} by PP goals allowed." if p["pp"] and opp_team.get("ppga_rk") else "."))
    best = max((q for q in p["partners"] if q["n"] >= 3), key=lambda q: q["both"] / q["n"], default=None)
    if best:
        b.append(f"With {best['name'].split()[-1]}: both scored {best['both']} of {best['n']} games together.")
    if team.get("b2b"):
        b.append("Second leg of a back-to-back — haircut applied (−14% team goals).")
    for name, f in p["adj"]:
        if name == "venue":
            hs, as_ = p["home_split"], p["away_split"]
            b.append(f"Lopsided split: home {hs[0]}/{hs[1]}, road {as_[0]}/{as_[1]}.")
    return b[:5]

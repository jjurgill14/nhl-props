"""Process review: re-derive v3 smash flags from each day's odds file and grade them against finals.

Usage: PYTHONPATH=src python3 tools/review.py [--md out.md]
Prints the tables; with --md also writes a markdown report with every game listed.
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

from nhl_props import market

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

SMASH_BAR, SOFT_BAR = 7, 6          # total goals for an "actual" all-around smash (hard / soft)
SIDE_BAR, SIDE_SOFT = 4, 3          # flagged team's goals for a one-sided hit (hard / soft)


def finals() -> dict[tuple[str, str, str], dict]:
    out = {}
    for f in glob.glob(str(DATA / "games" / "*.json")):
        g = json.load(open(f))
        if g.get("state") not in ("OFF", "FINAL") or g.get("home_score") is None:
            continue
        out[(g["date"], g["away"], g["home"])] = g
    return out


def rows() -> list[dict]:
    fin = finals()
    out = []
    for f in sorted(glob.glob(str(DATA / "odds_manual" / "*.json"))):
        d = json.load(open(f))
        date = Path(f).stem
        for b in d["games"]:
            key = (date, b["away"], b["home"])
            g = fin.get(key)
            m = market.analyze(b)
            s = market.smash(m, b["away"], b["home"])
            if not g or s["flag"] is None:
                continue
            tot = g["away_score"] + g["home_score"]
            r = {
                "date": date, "away": b["away"], "home": b["home"], "line": b["total"],
                "p_over": m["p_over"], "implied": m["implied_total"], "xg_away": m["xg_away"], "xg_home": m["xg_home"],
                "kind": s["kind"], "side": s["side"],
                "sa": g["away_score"], "sh": g["home_score"], "total": tot, "end": g.get("last_period_type", "REG"),
                "sog_a": g.get("away_sog"), "sog_h": g.get("home_sog"),
            }
            r["over"] = tot > b["total"]
            r["ge7"], r["ge6"] = tot >= SMASH_BAR, tot >= SOFT_BAR
            if s["kind"] == "side":
                fs, os_ = (r["sa"], r["sh"]) if s["side"] == b["away"] else (r["sh"], r["sa"])
                r["side_goals"], r["opp_goals"] = fs, os_
                r["side_hit"] = fs >= SIDE_BAR
                r["side_soft"] = fs >= SIDE_SOFT
                r["side_won"] = fs > os_
                r["side_outscored"] = fs > os_  # same as won by score; kept for clarity in tables
            out.append(r)
    return out


def pct(k, n):
    return f"{k}/{n} ({100*k/n:.0f}%)" if n else "0/0"


def team_rows(rs: list[dict]) -> list[dict]:
    out = []
    for r in rs:
        for side, opp in (("away", "home"), ("home", "away")):
            t = r[side]
            xg = r[f"xg_{side}"]
            act = r["sa"] if side == "away" else r["sh"]
            allowed = r["sh"] if side == "away" else r["sa"]
            xga = r[f"xg_{opp}"]
            out.append({"team": t, "date": r["date"], "venue": side, "xg": xg, "act": act, "xga": xga, "allowed": allowed,
                        "opp": r[opp], "flag": r["kind"], "flag_side": r["side"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    a = ap.parse_args()
    rs = rows()
    n = len(rs)
    allr = [r for r in rs if r["kind"] == "all"]
    side = [r for r in rs if r["kind"] == "side"]
    passed = [r for r in rs if r["kind"] is None]
    flagged = allr + side
    L = []
    P = L.append

    P(f"# Process review — smash v3 graded on {n} priced games ({rs[0]['date']} → {rs[-1]['date']})\n")
    P("Inputs frozen: flags re-derived from each day's `data/odds_manual/<date>.json` with the v3 rules "
      "(all-around: implied ≥ 6.35 & both xG ≥ 3.0; one-sided: team ≥ 3.2 & opp < 3.0). Finals from `data/games/`. "
      "Goals = regulation + OT; a shootout win counts one goal (book convention). SO games marked.\n")
    so = sum(1 for r in rs if r["end"] == "SO")
    P(f"Flagged {len(flagged)} of {n} ({100*len(flagged)/n:.0f}%): {len(allr)} all-around, {len(side)} one-sided. Passed on {len(passed)}. {so} games went to a shootout.\n")

    # Q1
    P("## 1. Were the smashes actual smashes?\n")
    P("| Group | N | ≥7 goals | ≥6 goals | Over the book total | Mean total | Mean implied |")
    P("|---|---|---|---|---|---|---|")
    for name, grp in (("All-around flags", allr), ("One-sided flags", side), ("Any flag", flagged), ("Passed (unflagged)", passed), ("Every game", rs)):
        if not grp:
            continue
        P(f"| {name} | {len(grp)} | {pct(sum(r['ge7'] for r in grp), len(grp))} | {pct(sum(r['ge6'] for r in grp), len(grp))} | "
          f"{pct(sum(r['over'] for r in grp), len(grp))} | {st.mean(r['total'] for r in grp):.2f} | {st.mean(r['implied'] for r in grp):.2f} |")
    mkt_over = st.mean(r["p_over"] for r in flagged) if flagged else 0
    P(f"\nMarket's own P(over) averaged across flagged games: {100*mkt_over:.0f}%. "
      f"The flag beats its price only if the 'Over the book total' column for flags clears that.\n")

    # Q2
    P("## 2. One-sided flags — right direction?\n")
    if side:
        P(f"| Metric | Count |\n|---|---|")
        P(f"| Flagged team scored ≥{SIDE_BAR} | {pct(sum(r['side_hit'] for r in side), len(side))} |")
        P(f"| Flagged team scored ≥{SIDE_SOFT} | {pct(sum(r['side_soft'] for r in side), len(side))} |")
        P(f"| Flagged team outscored opponent | {pct(sum(r['side_won'] for r in side), len(side))} |")
        P(f"| Opponent (the 'quiet' side, xG < 3.0) scored ≥{SIDE_BAR} | {pct(sum(r['opp_goals'] >= SIDE_BAR for r in side), len(side))} |")
        P(f"| Opponent scored ≥{SIDE_SOFT} | {pct(sum(r['opp_goals'] >= SIDE_SOFT for r in side), len(side))} |")
        fx = st.mean((r['xg_away'] if r['side'] == r['away'] else r['xg_home']) for r in side)
        ox = st.mean((r['xg_home'] if r['side'] == r['away'] else r['xg_away']) for r in side)
        P(f"| Flagged side: mean xG → mean actual | {fx:.2f} → {st.mean(r['side_goals'] for r in side):.2f} |")
        P(f"| Quiet side: mean xG → mean actual | {ox:.2f} → {st.mean(r['opp_goals'] for r in side):.2f} |")
        hi = [r for r in side if max(r['xg_away'], r['xg_home']) >= 4.0]
        P(f"\n'≥4.0 xG' one-sided flags: {len(hi)} — flagged team ≥{SIDE_BAR}: {pct(sum(r['side_hit'] for r in hi), len(hi))}, "
          f"outscored opp: {pct(sum(r['side_won'] for r in hi), len(hi))}.")
        lo = [r for r in side if r['line'] <= 5.5]
        P(f"One-sided flags on 5.5 totals: {len(lo)} — flagged team ≥{SIDE_BAR}: {pct(sum(r['side_hit'] for r in lo), len(lo))}, ≥{SIDE_SOFT}: {pct(sum(r['side_soft'] for r in lo), len(lo))}.\n")

    # Q3
    P("## 3. The passes — should we have passed?\n")
    P("| Why it didn't flag | N | ≥7 | ≥6 | A team scored ≥4 | Over |")
    P("|---|---|---|---|---|---|")
    buckets = defaultdict(list)
    for r in passed:
        xa, xh, t = r["xg_away"], r["xg_home"], r["implied"]
        if r["line"] <= 5.5:
            b = "5.5 total"
        elif t >= 6.35 and (2.8 <= min(xa, xh) < 3.0):
            b = "6.35+ total, one side just under 3.0 (2.8–3.0)"
        elif t >= 6.35:
            b = "6.35+ total, one side well under 3.0"
        elif 6.2 <= t < 6.35 and min(xa, xh) >= 3.0:
            b = "both ≥3.0 but total 6.2–6.35"
        elif max(xa, xh) >= 3.0:
            b = "6.5 line, total < 6.35, neither side ≥3.2 with opp <3.0"
        else:
            b = "other"
        buckets[b].append(r)
    for b, grp in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        P(f"| {b} | {len(grp)} | {pct(sum(r['ge7'] for r in grp), len(grp))} | {pct(sum(r['ge6'] for r in grp), len(grp))} | "
          f"{pct(sum(max(r['sa'], r['sh']) >= 4 for r in grp), len(grp))} | {pct(sum(r['over'] for r in grp), len(grp))} |")
    P("")

    # Q4
    P("## 4. Which teams are we most wrong about?\n")
    tr = team_rows(rs)
    by = defaultdict(list)
    for t in tr:
        by[t["team"]].append(t)
    P("Per team, every priced game: actual goals minus xG (for) and goals allowed minus opponent xG (against). Positive = we under-rated them. N shown; under 4 is noise.\n")
    P("| Team | N | xG for → actual | Δ for (avg) | xGA → allowed | Δ against (avg) | Flagged for them | Hit ≥4 when flagged |")
    P("|---|---|---|---|---|---|---|---|")
    tab = []
    for team, g in by.items():
        d_for = st.mean(x["act"] - x["xg"] for x in g)
        d_ag = st.mean(x["allowed"] - x["xga"] for x in g)
        fl = [x for x in g if x["flag_side"] == team]
        tab.append((team, len(g), st.mean(x["xg"] for x in g), st.mean(x["act"] for x in g), d_for,
                    st.mean(x["xga"] for x in g), st.mean(x["allowed"] for x in g), d_ag, len(fl), sum(x["act"] >= 4 for x in fl)))
    tab.sort(key=lambda x: -x[4])
    for team, N, xg, act, df, xga, al, da, nf, hf in tab:
        P(f"| {team} | {N} | {xg:.2f} → {act:.2f} | {df:+.2f} | {xga:.2f} → {al:.2f} | {da:+.2f} | {nf} | {hf}/{nf} |")
    P("")

    # calibration
    P("## 5. Is the xG split itself honest? (calibration)\n")
    P("| Team xG bucket | N team-games | Mean xG | Mean actual goals | Scored ≥4 | Scored ≥3 |")
    P("|---|---|---|---|---|---|")
    bk = [("< 2.8", lambda x: x < 2.8), ("2.8–3.2", lambda x: 2.8 <= x < 3.2), ("3.2–3.6", lambda x: 3.2 <= x < 3.6), ("3.6–4.0", lambda x: 3.6 <= x < 4.0), ("≥ 4.0", lambda x: x >= 4.0)]
    for name, fn in bk:
        g = [t for t in tr if fn(t["xg"])]
        if g:
            P(f"| {name} | {len(g)} | {st.mean(t['xg'] for t in g):.2f} | {st.mean(t['act'] for t in g):.2f} | {pct(sum(t['act']>=4 for t in g), len(g))} | {pct(sum(t['act']>=3 for t in g), len(g))} |")
    P("\n| Implied total bucket | N games | Mean implied | Mean actual total | ≥7 | ≥6 | Over |")
    P("|---|---|---|---|---|---|---|")
    tb = [("≤ 5.8", lambda x: x <= 5.8), ("5.8–6.2", lambda x: 5.8 < x < 6.2), ("6.2–6.35", lambda x: 6.2 <= x < 6.35), ("6.35–6.6", lambda x: 6.35 <= x < 6.6), ("≥ 6.6", lambda x: x >= 6.6)]
    for name, fn in tb:
        g = [r for r in rs if fn(r["implied"])]
        if g:
            P(f"| {name} | {len(g)} | {st.mean(r['implied'] for r in g):.2f} | {st.mean(r['total'] for r in g):.2f} | {pct(sum(r['ge7'] for r in g), len(g))} | {pct(sum(r['ge6'] for r in g), len(g))} | {pct(sum(r['over'] for r in g), len(g))} |")
    P("")

    # venue / situational
    P("## 6. Situational splits (team-games)\n")
    P("| Split | N | Mean xG | Mean actual | Δ |")
    P("|---|---|---|---|---|")
    for name, g in (("Home", [t for t in tr if t["venue"] == "home"]), ("Away", [t for t in tr if t["venue"] == "away"]),
                    ("Flagged side (one-sided)", [t for t in tr if t["flag_side"] == t["team"]]),
                    ("Quiet side (one-sided)", [t for t in tr if t["flag"] == "side" and t["flag_side"] != t["team"]]),
                    ("All-around flag", [t for t in tr if t["flag"] == "all"]), ("Unflagged", [t for t in tr if t["flag"] is None])):
        if g:
            P(f"| {name} | {len(g)} | {st.mean(t['xg'] for t in g):.2f} | {st.mean(t['act'] for t in g):.2f} | {st.mean(t['act']-t['xg'] for t in g):+.2f} |")
    P("")

    # every game
    P("## 7. Every game (audit)\n")
    P("| Date | Game | Line | Implied | xG A / H | Flag | Final | Total | End | Verdict |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for r in rs:
        if r["kind"] == "all":
            flag, v = "ALL", ("✅ ≥7" if r["ge7"] else "🟡 6" if r["ge6"] else "❌")
        elif r["kind"] == "side":
            flag = f"SIDE {r['side']}"
            v = ("✅ " if r["side_hit"] else "🟡 " if r["side_soft"] else "❌ ") + f"{r['side']} {r['side_goals']}" + (" W" if r["side_won"] else " L")
        else:
            flag, v = "pass", ("missed ≥7" if r["ge7"] else "missed 6" if r["ge6"] else "✅ pass")
        P(f"| {r['date'][5:]} | {r['away']}@{r['home']} | {r['line']} | {r['implied']:.2f} | {r['xg_away']:.2f} / {r['xg_home']:.2f} | {flag} | "
          f"{r['sa']}–{r['sh']} | {r['total']} | {r['end']} | {v} |")
    text = "\n".join(L)
    print(text)
    if a.md:
        Path(a.md).write_text(text)


if __name__ == "__main__":
    main()

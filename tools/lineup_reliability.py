"""Lineup reliability study: how well does Daily Faceoff's chart (morning / pregame / final) predict
what actually happened on the ice?

    PYTHONPATH=src python tools/lineup_reliability.py            # writes data/analysis/lineup_reliability.csv + prints tables
    PYTHONPATH=src python tools/lineup_reliability.py --md out.md

Three DFO reads per team-game, each = the latest *consistent* snapshot whose DFO stamp (updated_dfo) is <= cutoff:
    morning  noon ET on game day
    pregame  puck drop - 90 min
    final    puck drop
Ground truth: data/lines_actual (shift overlap), data/boxscores (who dressed, PP TOI, starting goalie).

Scores per read (all 0..1, higher = DFO was right):
    f_strict   share of projected forwards whose BOTH projected linemates were his top-2 5v5 forward linemates
    f_loose    ... at least one of the two
    top6_pair  share of the 6 projected same-line pairs on lines 1-2 that were mutual top-2 linemates
    d_pair     share of projected D whose projected partner was his top D partner
    dress_miss count of projected skaters (F+D) who did not play
    pp1        overlap of projected PP1 with the team's top-5 PP TOI (only when the team had >= 2 PP chances)
    goalie     projected starter (chart G1) == boxscore starter
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nhl_props.alerts import consistent  # noqa: E402
from nhl_props.analysis import norm  # noqa: E402

DATA = ROOT / "data"
ET = ZoneInfo("America/New_York")
READS = ("morning", "pregame", "final")
CAPTURE_GRACE = timedelta(minutes=20)  # evening loop keeps pulling ~15 min past puck drop


def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def read_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(newline="") as f:
        return list(csv.DictReader(f))


# ----------------------------------------------------------------------------- inputs
def load_games() -> list[dict]:
    games = []
    for f in sorted((DATA / "schedule").glob("*.json")):
        for g in json.loads(f.read_text())["games"]:
            if g.get("game_type") == 2 and (DATA / "lines_actual" / f"{g['game_id']}.csv").exists():
                games.append(g)
    return games


def load_timelines() -> dict[str, list[dict]]:
    """team -> every snapshot we hold, sorted by (DFO stamp, capture time)."""
    tl: dict[str, list[dict]] = defaultdict(list)
    for f in (DATA / "lineups").glob("*/*/*.json"):
        s = json.loads(f.read_text())
        s["_cap"] = ts(s["captured_utc"])
        s["_upd"] = ts(s.get("updated_dfo")) or s["_cap"]
        s["_file"] = str(f.relative_to(DATA))
        s["_ok"] = consistent(s)
        tl[f.parent.name].append(s)
    for v in tl.values():
        v.sort(key=lambda s: (s["_upd"], s["_cap"]))
    return tl


def pick(timeline: list[dict], cutoff: datetime, puck: datetime) -> dict | None:
    best = None
    for s in timeline:
        if s["_upd"] <= cutoff and s["_cap"] <= puck + CAPTURE_GRACE and s["_ok"]:
            best = s
    return best


# ----------------------------------------------------------------------------- name resolution
class Names:
    """DFO / shift-chart / boxscore names -> NHL player_id for one team-game."""

    def __init__(self, box: list[dict], la: list[dict]):
        self.exact: dict[str, str] = {}
        for r in box:
            self.exact[norm(r.get("full_name") or r["player"])] = r["player_id"]
        for r in la:
            self.exact.setdefault(norm(r["player"]), r["player_id"])
        self.by_last: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for n, pid in self.exact.items():
            self.by_last[n.split()[-1]].append((n, pid))

    def pid(self, name: str) -> str | None:
        n = norm(name)
        if n in self.exact:
            return self.exact[n]
        cands = self.by_last.get(n.split()[-1], []) if n else []
        same_init = {pid for c, pid in cands if c[0] == n[0]}
        if len(same_init) == 1:
            return same_init.pop()
        if len({pid for _, pid in cands}) == 1:
            return cands[0][1]
        return None


def split_mates(s: str) -> list[str]:
    return [re.sub(r"\s*\(\d+s\)\s*$", "", x).strip() for x in (s or "").split(";") if x.strip()]


# ----------------------------------------------------------------------------- scoring
def chart(snap: dict) -> dict:
    f, d, pp1, g1 = defaultdict(list), defaultdict(list), [], None
    for r in snap["lines"]:
        if r["section"] == "F" and r.get("unit_no"):
            f[r["unit_no"]].append(r["player"])
        elif r["section"] == "D" and r.get("unit_no"):
            d[r["unit_no"]].append(r["player"])
        elif r["section"] == "PP" and r.get("unit_no") == 1:
            pp1.append(r["player"])
        elif r["section"] == "G" and r.get("unit_no") == 1:
            g1 = r["player"]
    return {"f": dict(f), "d": dict(d), "pp1": pp1, "g1": g1}


def f_key(c: dict) -> frozenset:
    return frozenset(frozenset(norm(p) for p in line) for line in c["f"].values())


def full_key(c: dict) -> tuple:
    return (f_key(c), frozenset(frozenset(norm(p) for p in pr) for pr in c["d"].values()),
            frozenset(norm(p) for p in c["pp1"]))


def score(snap: dict, box: list[dict], la: list[dict], pp_opps: int | None) -> dict:
    nm, c = Names(box, la), chart(snap)
    dressed = {r["player_id"] for r in box if int(r.get("toi_s") or 0) > 0}
    top_f = {r["player_id"]: [nm.pid(x) for x in split_mates(r["linemates_f"])][:2] for r in la if r["pos"] != "D"}
    top_d = {r["player_id"]: [nm.pid(x) for x in split_mates(r["linemates_d"])][:1] for r in la if r["pos"] == "D"}

    n_f = strict = loose = 0
    pairs = pairs_hit = 0
    trio = {}
    for ln, players in sorted(c["f"].items()):
        ids = [nm.pid(p) for p in players]
        line_ok = len(ids) == 3
        for i, pid in enumerate(ids):
            mates = [x for j, x in enumerate(ids) if j != i]
            act = top_f.get(pid, []) if pid else []
            hits = sum(1 for m in mates if m and m in act)
            n_f += 1
            strict += int(bool(mates) and hits == len(mates))
            loose += int(hits >= 1)
            line_ok = line_ok and hits == len(mates)
        trio[ln] = line_ok
        if ln in (1, 2):
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    a, b = ids[i], ids[j]
                    pairs += 1
                    pairs_hit += int(bool(a and b) and b in top_f.get(a, []) and a in top_f.get(b, []))

    n_d = d_hit = 0
    for players in c["d"].values():
        ids = [nm.pid(p) for p in players]
        for i, pid in enumerate(ids):
            mates = [x for j, x in enumerate(ids) if j != i]
            n_d += 1
            d_hit += int(bool(pid) and bool(mates) and mates[0] in top_d.get(pid, []))

    proj = [p for ps in list(c["f"].values()) + list(c["d"].values()) for p in ps]
    missed = [p for p in proj if nm.pid(p) not in dressed]
    unresolved = [p for p in proj if nm.pid(p) is None]

    pp1 = None
    if pp_opps is not None and pp_opps >= 2 and c["pp1"]:
        sk = sorted((r for r in box if r["pos"] != "G"), key=lambda r: -int(r.get("pp_toi_s") or 0))[:5]
        act = {r["player_id"] for r in sk if int(r.get("pp_toi_s") or 0) > 0}
        pp1 = sum(1 for p in c["pp1"] if nm.pid(p) in act) / len(c["pp1"])

    starter = next((r["player_id"] for r in box if r["pos"] == "G" and r.get("starter") == "True"), None)
    goalie = None if not (c["g1"] and starter) else int(nm.pid(c["g1"]) == starter)

    return {"n_f": n_f, "f_strict": strict / n_f if n_f else None, "f_loose": loose / n_f if n_f else None,
            "top6_pair": pairs_hit / pairs if pairs else None,
            "l1_intact": int(trio.get(1, False)), "l2_intact": int(trio.get(2, False)),
            "d_pair": d_hit / n_d if n_d else None, "dress_miss": len(missed), "missed": "; ".join(missed),
            "unresolved": "; ".join(unresolved), "pp1": pp1, "goalie": goalie}


# ----------------------------------------------------------------------------- build
def build() -> list[dict]:
    games, tl = load_games(), load_timelines()
    played = defaultdict(set)
    for f in (DATA / "schedule").glob("*.json"):
        for g in json.loads(f.read_text())["games"]:
            played[g["date"]] |= {g["away"], g["home"]}
    rows = []
    for g in games:
        gid, date, puck = g["game_id"], g["date"], ts(g["start_utc"])
        box_all, la_all = read_csv(DATA / "boxscores" / f"{gid}.csv"), read_csv(DATA / "lines_actual" / f"{gid}.csv")
        info = json.loads((DATA / "games" / f"{gid}.json").read_text()) if (DATA / "games" / f"{gid}.json").exists() else {}
        noon = datetime.fromisoformat(date + "T12:00:00").replace(tzinfo=ET).astimezone(timezone.utc)
        day0 = datetime.fromisoformat(date + "T00:00:00").replace(tzinfo=ET).astimezone(timezone.utc)
        prev = (datetime.fromisoformat(date) - timedelta(days=1)).strftime("%Y-%m-%d")
        for side in ("away", "home"):
            team = g[side]
            box = [r for r in box_all if r["team"] == team]
            la = [r for r in la_all if r["team"] == team]
            if not box or not la or team not in tl:
                continue
            cut = {"morning": min(noon, puck - timedelta(minutes=90)), "pregame": puck - timedelta(minutes=90), "final": puck}
            snaps = {k: pick(tl[team], v, puck) for k, v in cut.items()}
            if not snaps["final"]:
                continue
            charts = {k: chart(s) if s else None for k, s in snaps.items()}
            n_day = sum(1 for s in tl[team] if day0 <= s["_cap"] <= puck + CAPTURE_GRACE)
            base = {"game_id": gid, "date": date, "team": team, "opp": g["home" if side == "away" else "away"],
                    "home": int(side == "home"), "b2b": int(team in played.get(prev, set())),
                    "puck_et": puck.astimezone(ET).strftime("%H:%M"), "n_snaps_day": n_day,
                    "pp_opps": info.get(f"{side}_pp_opps"),
                    "m_eq_p_f": None if not (charts["morning"] and charts["pregame"]) else int(f_key(charts["morning"]) == f_key(charts["pregame"])),
                    "m_eq_p_full": None if not (charts["morning"] and charts["pregame"]) else int(full_key(charts["morning"]) == full_key(charts["pregame"])),
                    "p_eq_f_f": None if not charts["pregame"] else int(f_key(charts["pregame"]) == f_key(charts["final"])),
                    "p_eq_f_full": None if not charts["pregame"] else int(full_key(charts["pregame"]) == full_key(charts["final"])),
                    "m_eq_f_full": None if not charts["morning"] else int(full_key(charts["morning"]) == full_key(charts["final"]))}
            # "warm-up chart": DFO re-stamped the chart inside the last 45 min (beat writers at warmups)
            base["warm"] = int((puck - snaps["final"]["_upd"]) <= timedelta(minutes=45))
            for k in READS:
                s = snaps[k]
                if not s:
                    continue
                rows.append({**base, "read": k, "snap": s["_file"],
                             "dfo_updated_et": s["_upd"].astimezone(ET).strftime("%m-%d %H:%M"),
                             "stale": int(s["_upd"] < day0),  # chart last touched before game day
                             "mins_before_puck": round((puck - s["_upd"]).total_seconds() / 60),
                             **score(s, box, la, info.get(f"{side}_pp_opps"))})
    return rows


# ----------------------------------------------------------------------------- report
def mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs), len(xs)) if xs else (None, 0)


def pct(x, nd=0):
    return "—" if x is None else f"{100 * x:.{nd}f}%"


def table(head: list[str], body: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in body]
    return "\n".join(out)


METRICS = ("f_strict", "f_loose", "top6_pair", "d_pair", "pp1", "goalie")


def summary_row(label, rows):
    cells = [label, len(rows)]
    for m in METRICS:
        cells.append(pct(mean([r[m] for r in rows])[0]))
    cells.append(f"{mean([r['dress_miss'] for r in rows])[0]:.2f}" if rows else "—")
    cells.append(pct(mean([int(r['dress_miss'] == 0) for r in rows])[0]))
    return cells


HEAD = ["", "N", "F strict", "F loose", "Top-6 pairs", "D pair", "PP1", "Goalie", "Dress misses/gm", "All 18 dressed"]


def report(rows: list[dict]) -> str:
    by = lambda k: [r for r in rows if r["read"] == k]  # noqa: E731
    out = []
    out.append("## League, by read\n\n" + table(HEAD, [summary_row(k, by(k)) for k in READS]))
    late = [r for r in rows if r["date"] >= "2026-11-17"]
    out.append("## League, by read — 11/17 on (tight evening loop)\n\n"
               + table(HEAD, [summary_row(k, [r for r in late if r["read"] == k]) for k in READS]))

    # per team
    teams = sorted({r["team"] for r in rows})
    lg = {k: mean([r["f_strict"] for r in by(k)])[0] for k in READS}
    body = []
    for t in teams:
        tr = {k: [r for r in by(k) if r["team"] == t] for k in READS}
        fin = tr["final"]
        body.append([t, len(fin)] + [pct(mean([r["f_strict"] for r in tr[k]])[0]) for k in READS]
                    + [pct(mean([r["top6_pair"] for r in tr[k]])[0]) for k in READS]
                    + [f"{mean([r['dress_miss'] for r in tr['morning']])[0]:.2f}" if tr["morning"] else "—",
                       f"{mean([r['dress_miss'] for r in fin])[0]:.2f}",
                       pct(mean([1 - r["p_eq_f_full"] for r in fin if r["p_eq_f_full"] is not None])[0])])
    body.sort(key=lambda r: float(r[4].rstrip("%")) if r[4] != "—" else 0)
    out.append("## Per team (sorted worst final F-strict first)\n\n"
               + f"League F strict: morning {pct(lg['morning'])}, pregame {pct(lg['pregame'])}, final {pct(lg['final'])}\n\n"
               + table(["Team", "N", "F strict AM", "F strict pre", "F strict final", "Top-6 AM", "Top-6 pre", "Top-6 final",
                        "Dress miss AM", "Dress miss final", "Chart changed inside 90 min"], body))

    # conditional: morning == pregame?
    pre = [r for r in by("pregame") if r["m_eq_p_f"] is not None]
    body = []
    for label, sel in (("Morning F lines = pregame F lines", [r for r in pre if r["m_eq_p_f"] == 1]),
                       ("Morning F lines ≠ pregame", [r for r in pre if r["m_eq_p_f"] == 0]),
                       ("Whole chart identical (F+D+PP1)", [r for r in pre if r["m_eq_p_full"] == 1]),
                       ("Whole chart changed", [r for r in pre if r["m_eq_p_full"] == 0])):
        body.append(summary_row(label, sel))
    out.append("## Pregame chart accuracy, conditioned on morning vs pregame\n\n" + table(HEAD, body))
    mor = {(r["game_id"], r["team"]): r for r in by("morning")}
    body = []
    for label, flag in (("Morning chart, when pregame later matched it", 1), ("Morning chart, when pregame later differed", 0)):
        body.append(summary_row(label, [mor[(r["game_id"], r["team"])] for r in pre if r["m_eq_p_f"] == flag and (r["game_id"], r["team"]) in mor]))
    out.append("## Morning chart accuracy, split by whether pregame ended up matching it\n\n" + table(HEAD, body))

    # warm-up chart or not
    fin = by("final")
    body = [summary_row("Final chart · warm-up chart posted (DFO stamp <= 45 min before puck)", [r for r in fin if r["warm"]]),
            summary_row("Final chart · no warm-up chart", [r for r in fin if not r["warm"]]),
            summary_row("Morning chart · games where a warm-up chart came later", [r for r in by("morning") if r["warm"]]),
            summary_row("Morning chart · games with no warm-up chart", [r for r in by("morning") if not r["warm"]]),
            summary_row("Morning chart · identical to final chart (F+D+PP1)", [r for r in by("morning") if r["m_eq_f_full"] == 1]),
            summary_row("Morning chart · final chart differed", [r for r in by("morning") if r["m_eq_f_full"] == 0])]
    out.append("## Warm-up chart: the split that matters\n\n" + table(HEAD, body))
    body = []
    for t in teams:
        tf = [r for r in fin if r["team"] == t]
        tm = [r for r in by("morning") if r["team"] == t]
        body.append([t, len(tf), pct(mean([r["warm"] for r in tf])[0]), pct(mean([r["f_strict"] for r in tm])[0]),
                     pct(mean([r["f_strict"] for r in tf if r["warm"]])[0]), pct(mean([r["f_strict"] for r in tf if not r["warm"]])[0]),
                     pct(mean([r["top6_pair"] for r in tm])[0]), pct(mean([r["top6_pair"] for r in tf])[0])])
    body.sort(key=lambda r: -float(r[2].rstrip("%")))
    out.append("## Per team: how often the chart is rewritten at warmups\n\n"
               + table(["Team", "N", "Warm-up chart rate", "F strict AM", "F strict final (warm)", "F strict final (no warm)", "Top-6 AM", "Top-6 final"], body))
    out.append("## Goalie board (data/goalies) vs boxscore starter\n\n" + goalie_board())

    # other cuts on each read
    body = []
    for k in READS:
        rk = by(k)
        for label, sel in ((f"{k} · home", [r for r in rk if r["home"]]), (f"{k} · away", [r for r in rk if not r["home"]]),
                           (f"{k} · B2B 2nd leg", [r for r in rk if r["b2b"]]), (f"{k} · rested", [r for r in rk if not r["b2b"]]),
                           (f"{k} · DFO touched chart on game day", [r for r in rk if not r["stale"]]),
                           (f"{k} · carried-over chart (not touched game day)", [r for r in rk if r["stale"]])):
            body.append(summary_row(label, sel))
    out.append("## Other cuts\n\n" + table(HEAD, body))
    return "\n\n".join(out)


def goalie_board() -> str:
    """DFO starting-goalie page as captured, by status, at three lead times."""
    starters = {}
    for f in (DATA / "boxscores").glob("*.csv"):
        for r in read_csv(f):
            if r["pos"] == "G" and r.get("starter") == "True":
                starters[(r["date"], r["team"])] = r["full_name"]
    caps = defaultdict(list)
    for f in (DATA / "goalies").glob("*.csv"):
        for r in read_csv(f):
            caps[(r["date"], r["team"])].append(r)
    body = []
    for label, mins in (("6h before puck", 360), ("90 min before", 90), ("at puck drop", 0)):
        tally = defaultdict(lambda: [0, 0])
        for key, rows in caps.items():
            if key not in starters:
                continue
            ok = [r for r in rows if ts(r["captured_utc"]) <= ts(r["start_utc"]) - timedelta(minutes=mins)]
            if not ok:
                continue
            r = max(ok, key=lambda r: r["captured_utc"])
            a, b = norm(r["goalie"]).split(), norm(starters[key]).split()
            hit = a[-1] == b[-1] and a[0][0] == b[0][0]
            for k in (r.get("status") or "no status", "all"):
                tally[k][0] += int(hit)
                tally[k][1] += 1
        body.append([label] + [f"{pct(tally[k][0] / tally[k][1])} ({tally[k][1]})" if tally[k][1] else "—"
                               for k in ("Confirmed", "Likely", "no status", "all")])
    return table(["Lead time", "Confirmed", "Likely", "No status", "All"], body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md")
    ap.add_argument("--csv", default=str(DATA / "analysis" / "lineup_reliability.csv"))
    a = ap.parse_args()
    rows = build()
    p = Path(a.csv)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    text = report(rows)
    if a.md:
        Path(a.md).write_text(text)
    print(text)
    print(f"\n{len(rows)} rows -> {p}", file=sys.stderr)


if __name__ == "__main__":
    main()

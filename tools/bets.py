"""Grade JJ's Pikkit export leg-by-leg against our boxscores.

Usage: PYTHONPATH=src python3 tools/bets.py /path/to/transactions.csv [--legs out.csv] [--md out.md]
The CSV never goes in the repo (it's public). Each ticket's bet_info holds legs separated by " | ";
Pikkit reports results per ticket only, so every leg is re-graded from data/boxscores/<game_id>.csv.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import re
import statistics as st
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ET = ZoneInfo("America/New_York")
ICEBOARD_LIVE = "2026-11-06"  # first night JJ had a board in hand

ABBR = {  # book spellings -> NHL abbreviations
    "ANA": "ANA", "BOS": "BOS", "BUF": "BUF", "CGY": "CGY", "CAR": "CAR", "CHI": "CHI", "COL": "COL", "CLB": "CBJ", "CBJ": "CBJ",
    "DAL": "DAL", "DET": "DET", "EDM": "EDM", "FLA": "FLA", "LA": "LAK", "LAK": "LAK", "MIN": "MIN", "MTL": "MTL", "NSH": "NSH",
    "NJ": "NJD", "NJD": "NJD", "NYI": "NYI", "NYR": "NYR", "OTT": "OTT", "PHI": "PHI", "PIT": "PIT", "SJ": "SJS", "SJS": "SJS",
    "SEA": "SEA", "STL": "STL", "TB": "TBL", "TBL": "TBL", "TOR": "TOR", "UTA": "UTA", "VAN": "VAN", "VGS": "VGK", "VGK": "VGK",
    "WAS": "WSH", "WSH": "WSH", "WPG": "WPG",
}
NICK = {  # full team names -> abbreviation (word before "at"/"@"/"vs")
    "ducks": "ANA", "bruins": "BOS", "sabres": "BUF", "flames": "CGY", "hurricanes": "CAR", "blackhawks": "CHI", "avalanche": "COL",
    "blue jackets": "CBJ", "stars": "DAL", "red wings": "DET", "oilers": "EDM", "panthers": "FLA", "kings": "LAK", "wild": "MIN",
    "canadiens": "MTL", "predators": "NSH", "devils": "NJD", "islanders": "NYI", "rangers": "NYR", "senators": "OTT", "flyers": "PHI",
    "penguins": "PIT", "sharks": "SJS", "kraken": "SEA", "blues": "STL", "lightning": "TBL", "maple leafs": "TOR", "mammoth": "UTA",
    "canucks": "VAN", "golden knights": "VGK", "capitals": "WSH", "jets": "WPG",
    # city-only (FanDuel "Seattle vs Detroit")
    "anaheim": "ANA", "boston": "BOS", "buffalo": "BUF", "calgary": "CGY", "carolina": "CAR", "chicago": "CHI", "colorado": "COL",
    "columbus": "CBJ", "dallas": "DAL", "detroit": "DET", "edmonton": "EDM", "florida": "FLA", "los angeles": "LAK", "minnesota": "MIN",
    "montreal": "MTL", "nashville": "NSH", "new jersey": "NJD", "ottawa": "OTT", "philadelphia": "PHI", "pittsburgh": "PIT",
    "san jose": "SJS", "seattle": "SEA", "st. louis": "STL", "st louis": "STL", "tampa bay": "TBL", "toronto": "TOR", "utah": "UTA",
    "vancouver": "VAN", "vegas": "VGK", "washington": "WSH", "winnipeg": "WPG",
}
STAT_WORDS = [("power play points", "ppp"), ("shots on goal", "sog"), ("assists", "a"), ("points", "p"), ("goals", "g"),
              ("anytime goal scorer", "g")]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def teams_in(text: str) -> list[str]:
    """Find the two teams named in a leg, in the order written (away first for '@'/'at')."""
    t = text.replace("\xa0", " ")
    m = re.search(r"\b([A-Z]{2,3}) [A-Za-z .']+? @ ([A-Z]{2,3}) [A-Za-z .']+$", t)
    if m and m.group(1) in ABBR and m.group(2) in ABBR:
        return [ABBR[m.group(1)], ABBR[m.group(2)]]
    low = t.lower()
    found = []
    for name, ab in NICK.items():
        for mm in re.finditer(r"\b" + re.escape(name) + r"\b", low):
            found.append((mm.start(), ab))
    found.sort()
    out = []
    for _, ab in found:
        if ab not in out:
            out.append(ab)
    return out[:2] if len(out) >= 2 else out


def parse_leg(text: str) -> dict | None:
    t = text.replace("\xa0", " ").strip()
    low = t.lower()
    stat = next((code for word, code in STAT_WORDS if word in low), None)
    if stat is None:
        return None  # totals, BTTS, moneylines: not player props
    if "both teams" in low or "alternate total" in low or "team total" in low or re.search(r"^(Over|Under) \d+(\.\d+)? Total", t):
        return None
    if "total goals" in low and re.search(r"^(Over|Under) \d+(\.\d+)? [A-Z][a-z]+ ([A-Z][a-z]+ )?(Stars|Devils|Blackhawks|Jets|Wild|Kings)", t):
        return None  # team total goals
    if " - under " in low or re.search(r"^Under \d", t):
        return None  # unders on player props: a handful, graded differently; skip
    m = re.search(r"(\d+(?:\.\d+)?)\+", t) or re.search(r"over (\d+(?:\.\d+)?)", low)
    if "anytime goal scorer" in low:
        n = 1.0
    elif m:
        n = float(m.group(1))
        if "over" in low and not re.search(r"\d\+", t):
            n = n + 0.5  # Over 0.5 -> 1+
    else:
        return None
    # player: text before ':' (Bet365), before ' - ' after the threshold (DK), or leading words before the threshold (FD)
    player = None
    if ":" in t:
        player = t.split(":", 1)[0]
    else:
        mm = re.search(r"\d+\+\s+(.+?)\s+-\s+(Points|Assists|Shots on Goal|Goals)", t)
        if mm:
            player = mm.group(1)
        else:
            mm = re.match(r"(?:Yes\s+|Over \d+(?:\.\d+)?\s+)?(.+?)\s+(?:\d+\+\s+)?(Points|Assists|Shots on Goal|Anytime Goal Scorer|Goals)", t)
            if mm:
                player = mm.group(1)
            else:
                mm = re.search(r"\d+\+\s+(.+?)\s+(Points|Assists|Shots on Goal|Goals)", t)
                player = mm.group(1) if mm else None
    if not player:
        return None
    player = re.sub(r"^(Yes|Over \d+(\.\d+)?)\s+", "", player).strip()
    player = re.sub(r"\s+\d+\+\s+Yes$|\s+Total$|\s+Player to Score$|\s+Powerplay$|\s+\([A-Z]{2,3}\)$|^\d+\+\s+", "", player).strip()
    if "team total" in low or re.fullmatch(r"[A-Z]{2,3} [A-Za-z .]+|[A-Z][a-z]+( [A-Z][a-z]+)* (Stars|Devils|Jets|Wild|Kings)", player):
        return None  # team totals
    if "player to score" in low:
        n = 1.0 if n > 1 else n  # "Player to Score 2+" on some books is anytime; keep conservative
    return {"player": player, "stat": stat, "n": n, "teams": teams_in(t), "raw": t}


def load_tickets(path: str) -> list[dict]:
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r["leagues"] != "NHL" or r["time_placed_iso"] < "2026-09-29" or not r["status"].startswith("SETTLED"):
            continue
        placed = datetime.fromisoformat(r["time_placed_iso"].replace("Z", "+00:00")).astimezone(ET)
        legs = [parse_leg(l) for l in r["bet_info"].split(" | ")]
        out.append({"id": r["bet_id"], "book": r["sportsbook"], "type": r["type"], "status": r["status"], "odds": float(r["odds"] or 0),
                    "stake": float(r["amount"] or 0), "profit": float(r["profit"] or 0), "placed_et": placed, "date": placed.strftime("%Y-%m-%d"),
                    "n_legs": len(r["bet_info"].split(" | ")), "legs": legs})
    return out


class Finder:
    def __init__(self):
        self.sched = {}
        for f in glob.glob(str(DATA / "schedule" / "*.json")):
            d = json.load(open(f))
            for g in d.get("games", []):
                self.sched.setdefault(d["date"], []).append(g)
        self.box = {}
        self.lineups = {}

    def game(self, date: str, teams: list[str]) -> dict | None:
        for off in (0, 1, -1):
            d = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=off)).strftime("%Y-%m-%d")
            for g in self.sched.get(d, []):
                if set(teams) <= {g["away"], g["home"]} and len(teams) == 2:
                    return g
            if len(teams) == 1:
                for g in self.sched.get(d, []):
                    if teams[0] in (g["away"], g["home"]):
                        return g
        return None

    def boxscore(self, gid: int) -> list[dict]:
        if gid not in self.box:
            p = DATA / "boxscores" / f"{gid}.csv"
            self.box[gid] = list(csv.DictReader(open(p))) if p.exists() else []
        return self.box[gid]

    def player_row(self, gid: int, name: str) -> dict | None:
        rows = self.boxscore(gid)
        key = norm(name)
        for r in rows:
            if norm(r["full_name"]) == key:
                return r
        last = norm(name.split()[-1])
        first = norm(name.split()[0])[:1]
        rows = [r for r in rows if r.get("full_name")]
        cands = [r for r in rows if norm(r["full_name"].split()[-1]) == last]
        if len(cands) == 1:
            return cands[0]
        cands = [r for r in cands if norm(r["full_name"])[:1] == first]
        if len(cands) == 1:
            return cands[0]
        # Pikkit sometimes carries middle names ("Sebastian Antero Aho")
        for r in rows:
            fn = norm(r["full_name"])
            if fn and key.startswith(fn[:4]) and fn.endswith(last):
                return r
        return None

    def role(self, date: str, team: str, name: str) -> str:
        """PP1 / top6 / other / d / d_pp1 from the last DFO snapshot for that team on that date."""
        key = (date, team)
        if key not in self.lineups:
            files = sorted(glob.glob(str(DATA / "lineups" / date / team / "*.json")))
            self.lineups[key] = json.load(open(files[-1])) if files else None
        snap = self.lineups[key]
        if not snap:
            return "?"
        nm = norm(name)
        last = norm(name.split()[-1])
        rows = [l for l in snap["lines"] if norm(l["player"]) == nm] or [l for l in snap["lines"] if norm(l["player"]).endswith(last)]
        if not rows:
            return "?"
        pp1 = any(l.get("section") == "PP" and str(l.get("unit", "")).startswith("1st") for l in rows)
        f = [l for l in rows if l.get("section") == "F"]
        d = [l for l in rows if l.get("section") == "D"]
        if d and not f:
            return "d_pp1" if pp1 else "d"
        unit = min((l.get("unit_no") or 9) for l in f) if f else 9
        if pp1:
            return "pp1"
        return "top6" if unit <= 2 else "other"


def grade(tickets: list[dict], fx: Finder) -> list[dict]:
    legs = []
    for t in tickets:
        for leg in t["legs"]:
            if leg is None:
                legs.append({"ticket": t["id"], "date": t["date"], "book": t["book"], "type": t["type"], "n_legs": t["n_legs"], "status": t["status"],
                             "stake": t["stake"], "profit": t["profit"], "odds": t["odds"], "player": None, "stat": None, "n": None,
                             "team": None, "opp": None, "home": None, "actual": None, "hit": None, "role": None, "note": "not a player prop"})
                continue
            g = fx.game(t["date"], leg["teams"])
            row = fx.player_row(g["game_id"], leg["player"]) if g else None
            actual = hit = None
            team = opp = home = role = None
            note = ""
            if not g:
                note = "no game"
            elif not fx.boxscore(g["game_id"]):
                note = "no boxscore"
            elif not row:
                note = "player not in boxscore"
            else:
                team, opp, home = row["team"], row["opp"], row["home"] == "1"
                col = {"p": "points", "a": "assists", "g": "goals", "sog": "sog", "ppp": None}[leg["stat"]]
                if col:
                    actual = int(row[col] or 0)
                    hit = actual >= leg["n"]
                else:
                    note = "ppp not graded"
                role = fx.role(g["date"], team, leg["player"])
            legs.append({"ticket": t["id"], "date": t["date"], "book": t["book"], "type": t["type"], "n_legs": t["n_legs"], "status": t["status"],
                         "stake": t["stake"], "profit": t["profit"], "odds": t["odds"], "player": leg["player"], "stat": leg["stat"], "n": leg["n"],
                         "team": team, "opp": opp, "home": home, "actual": actual, "hit": hit, "role": role, "note": note,
                         "game_date": g["date"] if g else None})
    return legs


def pct(k, n):
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "0/0"


def report(tickets: list[dict], legs: list[dict]) -> str:
    L = []
    P = L.append
    graded = [l for l in legs if l["hit"] is not None]
    props = [l for l in legs if l["player"]]
    P("# Bet log review — Pikkit export, NHL, 2026-09-29 → " + max(t["date"] for t in tickets) + "\n")
    P(f"Tickets: {len(tickets)} settled · staked ${sum(t['stake'] for t in tickets):,.0f} · net {sum(t['profit'] for t in tickets):+,.2f} "
      f"· ROI {100 * sum(t['profit'] for t in tickets) / sum(t['stake'] for t in tickets):+.1f}%")
    P(f"Legs: {len(legs)} · player props {len(props)} · graded from boxscores {len(graded)} "
      f"({Counter(l['note'] for l in legs if l['note'])})\n")

    def block(title, groups, key=lambda l: l["hit"]):
        P(f"## {title}\n")
        P("| Group | Legs | Hit | Mean actual |")
        P("|---|---|---|---|")
        for name, grp in groups:
            if grp:
                P(f"| {name} | {len(grp)} | {pct(sum(key(l) for l in grp), len(grp))} | {st.mean(l['actual'] for l in grp):.2f} |")
        P("")

    by = lambda f: sorted(((k, [l for l in graded if f(l) == k]) for k in {f(l) for l in graded}), key=lambda kv: -len(kv[1]))
    block("Hit rate by market", by(lambda l: f"{l['stat']} {l['n']:g}+"))
    block("Hit rate by role that night (DFO)", by(lambda l: l["role"]))
    block("Hit rate: home vs away", by(lambda l: "home" if l["home"] else "away"))
    block("Hit rate: before vs after ICEBOARD (" + ICEBOARD_LIVE + ")", [("before", [l for l in graded if l["game_date"] < ICEBOARD_LIVE]),
                                                                         ("after", [l for l in graded if l["game_date"] >= ICEBOARD_LIVE])])
    pts = [l for l in graded if l["stat"] == "p"]
    block("Points legs by role × line", sorted(((f"{l['role']} {l['n']:g}+", None) for l in pts), key=lambda x: x[0]) and
          [(k, [l for l in pts if f"{l['role']} {l['n']:g}+" == k]) for k in sorted({f"{l['role']} {l['n']:g}+" for l in pts})])

    # tickets
    P("## Tickets: ROI by type and leg count\n")
    P("| Type | Tickets | Win | Staked | Net | ROI |")
    P("|---|---|---|---|---|---|")
    for k in sorted({(t["type"], min(t["n_legs"], 6)) for t in tickets}):
        grp = [t for t in tickets if (t["type"], min(t["n_legs"], 6)) == k]
        stk = sum(t["stake"] for t in grp)
        P(f"| {k[0]} {k[1]}{'+' if k[1] == 6 else ''} legs | {len(grp)} | {pct(sum(t['status'] == 'SETTLED_WIN' for t in grp), len(grp))} | ${stk:,.0f} | {sum(t['profit'] for t in grp):+,.0f} | {100 * sum(t['profit'] for t in grp) / stk:+.1f}% |")
    P("")
    P("## Tickets: ROI by book\n")
    P("| Book | Tickets | Staked | Net | ROI |")
    P("|---|---|---|---|---|")
    for k in sorted({t["book"] for t in tickets}):
        grp = [t for t in tickets if t["book"] == k]
        stk = sum(t["stake"] for t in grp)
        P(f"| {k} | {len(grp)} | ${stk:,.0f} | {sum(t['profit'] for t in grp):+,.0f} | {100 * sum(t['profit'] for t in grp) / stk:+.1f}% |")
    P("")
    P("## Tickets: before vs after ICEBOARD\n")
    P("| Period | Tickets | Staked | Net | ROI | Straight ROI | Parlay ROI |")
    P("|---|---|---|---|---|---|---|")
    for name, grp in (("before", [t for t in tickets if t["date"] < ICEBOARD_LIVE]), ("after", [t for t in tickets if t["date"] >= ICEBOARD_LIVE])):
        stk = sum(t["stake"] for t in grp)
        s = [t for t in grp if t["type"] == "straight"]
        p = [t for t in grp if t["type"] != "straight"]
        roi = lambda g: f"{100 * sum(t['profit'] for t in g) / sum(t['stake'] for t in g):+.1f}%" if g else "-"
        P(f"| {name} | {len(grp)} | ${stk:,.0f} | {sum(t['profit'] for t in grp):+,.0f} | {roi(grp)} | {roi(s)} | {roi(p)} |")
    P("")
    # straights: implied vs hit
    P("## Straight bets: did the price match the hit rate?\n")
    P("| Decimal odds band | Tickets | Book-implied win % | Actual win % | Net |")
    P("|---|---|---|---|---|")
    S = [t for t in tickets if t["type"] == "straight" and t["odds"] > 1]
    bands = [("≤1.50", lambda o: o <= 1.5), ("1.50–1.80", lambda o: 1.5 < o <= 1.8), ("1.80–2.20", lambda o: 1.8 < o <= 2.2), ("2.20–3.00", lambda o: 2.2 < o <= 3.0), ("> 3.00", lambda o: o > 3.0)]
    for name, fn in bands:
        grp = [t for t in S if fn(t["odds"])]
        if grp:
            P(f"| {name} | {len(grp)} | {100 * st.mean(1 / t['odds'] for t in grp):.0f}% | {100 * st.mean(t['status'] == 'SETTLED_WIN' for t in grp):.0f}% | {sum(t['profit'] for t in grp):+,.0f} |")
    P("")
    # players
    P("## Most-bet players (graded legs)\n")
    P("| Player | Legs | Hit | Markets |")
    P("|---|---|---|---|")
    byp = defaultdict(list)
    for l in graded:
        byp[l["player"]].append(l)
    for pl, grp in sorted(byp.items(), key=lambda kv: -len(kv[1]))[:30]:
        mk = Counter(f"{l['stat']}{l['n']:g}+" for l in grp)
        P(f"| {pl} | {len(grp)} | {pct(sum(l['hit'] for l in grp), len(grp))} | {', '.join(f'{k}×{v}' for k, v in mk.most_common(3))} |")
    P("")
    P("## Teams bet on (graded legs)\n")
    P("| Team | Legs | Hit |")
    P("|---|---|---|")
    byt = defaultdict(list)
    for l in graded:
        byt[l["team"]].append(l)
    for tm, grp in sorted(byt.items(), key=lambda kv: -len(kv[1]))[:20]:
        P(f"| {tm} | {len(grp)} | {pct(sum(l['hit'] for l in grp), len(grp))} |")
    P("")
    # parlay leg count vs implied
    P("## Parlays: legs hit per ticket\n")
    P("| Legs on ticket | Tickets | All legs hit | Exactly one miss | Win % |")
    P("|---|---|---|---|---|")
    byl = defaultdict(list)
    for t in tickets:
        if t["type"] != "straight":
            byl[min(t["n_legs"], 6)].append(t)
    tl = defaultdict(list)
    for l in graded:
        tl[l["ticket"]].append(l)
    for n in sorted(byl):
        grp = byl[n]
        full = [t for t in grp if len(tl[t["id"]]) == t["n_legs"]]
        allhit = sum(all(l["hit"] for l in tl[t["id"]]) for t in full)
        one = sum(sum(not l["hit"] for l in tl[t["id"]]) == 1 for t in full)
        P(f"| {n}{'+' if n == 6 else ''} | {len(grp)} | {pct(allhit, len(full))} | {pct(one, len(full))} | {100 * st.mean(t['status'] == 'SETTLED_WIN' for t in grp):.0f}% |")
    P("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--legs")
    ap.add_argument("--md")
    a = ap.parse_args()
    tickets = load_tickets(a.csv)
    fx = Finder()
    legs = grade(tickets, fx)
    if a.legs:
        with open(a.legs, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(legs[0].keys()))
            w.writeheader()
            w.writerows(legs)
    text = report(tickets, legs)
    print(text)
    if a.md:
        Path(a.md).write_text(text)


if __name__ == "__main__":
    main()

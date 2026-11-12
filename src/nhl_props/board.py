"""board.json — the data contract behind ICEBOARD's Daily Slate ("The Board").

One file per date: every game, both teams (record, colors), markets (ML from DFO's goalie
page; total unavailable until the odds feed), and per-game *lenses*: ranked plays for each
bet type JJ actually makes. The front end picks one play per selected lens per card.
Live data only — nothing here is invented; a lens with no qualifying play is an empty list.
"""
from __future__ import annotations

import glob
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from . import analysis, lineup_view, market, model, results, schedule
from .common import read_json

DOCS = results.DATA.parent / "docs"

TEAM_META = {
    "ANA": ("Anaheim", "Ducks", "#F47A38", "#B9975B"), "BOS": ("Boston", "Bruins", "#FFB81C", "#000000"),
    "BUF": ("Buffalo", "Sabres", "#003087", "#FFB81C"), "CAR": ("Carolina", "Hurricanes", "#CC0000", "#000000"),
    "CBJ": ("Columbus", "Blue Jackets", "#002654", "#CE1126"), "CGY": ("Calgary", "Flames", "#D2001C", "#FAAF19"),
    "CHI": ("Chicago", "Blackhawks", "#CF0A2C", "#000000"), "COL": ("Colorado", "Avalanche", "#6F263D", "#236192"),
    "DAL": ("Dallas", "Stars", "#006847", "#8F8F8C"), "DET": ("Detroit", "Red Wings", "#CE1126", "#FFFFFF"),
    "EDM": ("Edmonton", "Oilers", "#041E42", "#FF4C00"), "FLA": ("Florida", "Panthers", "#C8102E", "#041E42"),
    "LAK": ("Los Angeles", "Kings", "#111111", "#A2AAAD"), "MIN": ("Minnesota", "Wild", "#154734", "#A6192E"),
    "MTL": ("Montreal", "Canadiens", "#AF1E2D", "#192168"), "NJD": ("New Jersey", "Devils", "#CE1126", "#000000"),
    "NSH": ("Nashville", "Predators", "#FFB81C", "#041E42"), "NYI": ("New York", "Islanders", "#00539B", "#F47D30"),
    "NYR": ("New York", "Rangers", "#0038A8", "#CE1126"), "OTT": ("Ottawa", "Senators", "#000000", "#DA1A32"),
    "PHI": ("Philadelphia", "Flyers", "#F74902", "#000000"), "PIT": ("Pittsburgh", "Penguins", "#000000", "#FCB514"),
    "SEA": ("Seattle", "Kraken", "#001628", "#99D9D9"), "SJS": ("San Jose", "Sharks", "#006D75", "#000000"),
    "STL": ("St. Louis", "Blues", "#002F87", "#FCB514"), "TBL": ("Tampa Bay", "Lightning", "#002868", "#FFFFFF"),
    "TOR": ("Toronto", "Maple Leafs", "#00205B", "#FFFFFF"), "UTA": ("Utah", "Mammoth", "#69B3E7", "#010101"),
    "VAN": ("Vancouver", "Canucks", "#00205B", "#00843D"), "VGK": ("Vegas", "Golden Knights", "#B4975A", "#333F42"),
    "WPG": ("Winnipeg", "Jets", "#041E42", "#004C97"), "WSH": ("Washington", "Capitals", "#041E42", "#C8102E"),
}

def manual_odds(date: str) -> dict[tuple[str, str], dict]:
    """Book lines JJ typed in for the day (data/odds_manual/<date>.json) until the odds feed exists."""
    d = read_json(results.DATA / "odds_manual" / f"{date}.json")
    if not d:
        return {}
    out = {}
    for g in d.get("games", []):
        out[(g["away"], g["home"])] = {**g, "source": d.get("source"), "as_of": d.get("as_of")}
    return out


LENSES = {
    "point": "Point",
    "pair": "Linemate pair · both score",
    "two": "2+ points",
    "pp1": "PP1 mates · both score",
    "btts2": "Both teams 2+ goals",
}


def records(before_date: str) -> dict[str, dict]:
    """W-L-OTL per team from finished games strictly before `before_date`."""
    rec: dict[str, dict] = defaultdict(lambda: {"w": 0, "l": 0, "otl": 0, "gp": 0})
    for f in glob.glob(str(results.DATA / "games" / "*.json")):
        g = read_json(Path(f))
        if not g or g.get("state") not in ("OFF", "FINAL") or g.get("date", "") >= before_date:
            continue
        a, h = g["away"], g["home"]
        aw = g["away_score"] > g["home_score"]
        ot = g.get("periods", 3) > 3
        w, l = (a, h) if aw else (h, a)
        rec[w]["w"] += 1
        rec[l]["otl" if ot else "l"] += 1
        rec[w]["gp"] += 1
        rec[l]["gp"] += 1
    return {t: {**r, "text": f"{r['w']}-{r['l']}-{r['otl']}"} for t, r in rec.items()}


RATE_KEYS = ["gf", "ga", "sf", "sa", "pp", "pk"]


def _rates_block(r: dict, r5: dict) -> dict:
    """The six metrics JJ wants on every team, season + L5, with ranks (1 = most / best)."""
    def pct(v):
        return None if v is None else round(100 * v, 1)
    return {
        "gp": r.get("gp"), "pp_gp": r.get("pp_gp"),
        "gf": round(r.get("gf", 0), 2), "gf_rk": r.get("gf_rk"), "gf_l5": round(r5.get("gf", 0), 2),
        "ga": round(r.get("ga", 0), 2), "ga_rk": r.get("ga_rk"), "ga_l5": round(r5.get("ga", 0), 2),
        "sf": round(r.get("sf", 0), 1), "sf_rk": r.get("sf_rk"), "sf_l5": round(r5.get("sf", 0), 1),
        "sa": round(r.get("sa", 0), 1), "sa_rk": r.get("sa_rk"), "sa_l5": round(r5.get("sa", 0), 1),
        "pp": pct(r.get("pp_pct")), "pp_rk": r.get("pp_rk"), "pp_l5": pct(r5.get("pp_pct")), "pp_opps": r.get("pp_opps"),
        "pk": pct(r.get("pk_pct")), "pk_rk": r.get("pk_rk"), "pk_l5": pct(r5.get("pk_pct")), "pk_faced": r.get("pk_faced"),
        "ppg": round(r.get("ppg", 0), 2), "ppg_rk": r.get("ppg_rk"), "ppga": round(r.get("ppga", 0), 2), "ppga_rk": r.get("ppga_rk"),
    }


def _play(selection: str, p: float, rationale: str, **extra) -> dict:
    return {"selection": selection, "prob": round(p, 3), "fair": model.american(p),
            "need": model.american(p / model.EDGE), "rationale": rationale, **extra}


def _last(n: str) -> str:
    return n.split()[-1]


def lenses_for(g: dict, ids: dict | None = None) -> dict[str, list[dict]]:
    ids = ids or {}
    pid = lambda p: (ids.get((p["team"], analysis.norm(p["name"]))) or {}).get("id")
    a, h = g["teams"]["away"], g["teams"]["home"]
    players = sorted(a["players"] + h["players"], key=lambda p: -p["p"])
    index = {p["name"]: p for p in players}
    opp_of = lambda p: h if p["team"] == a["team"] else a
    team_of = lambda p: a if p["team"] == a["team"] else h

    point = []
    for p in players[:6]:
        why = model.why(p, team_of(p), opp_of(p))
        point.append(_play(f"{p['name']} · 1+ point", p["p"], " · ".join(w.rstrip(".") for w in why[:2]),
                           player=p["name"], team=p["team"], pp=p["pp"], line=p["line"], bias=p["bias"], players=[pid(p)]))

    pairs, pp1, seen = [], [], set()
    for p in players:
        for q in p["partners"]:
            key = tuple(sorted((p["name"], q["name"])))
            o = index.get(q["name"])
            if key in seen or not o or q["n"] < 1:
                continue
            seen.add(key)
            ind = p["p"] * o["p"]
            obs = q["both"] / q["n"]
            blend = (obs * q["n"] + ind * 6) / (q["n"] + 6)
            read = "new pair" if q["n"] < 6 else ("correlated" if obs > ind * 1.15 else ("negative" if obs < ind * 0.8 else "independent"))
            item = _play(f"{_last(p['name'])} + {_last(q['name'])} · both 1+ point", blend,
                         f"Both scored {q['both']} of {q['n']} games together · independent {round(ind*100)}% · {read}",
                         team=p["team"], line=p["line"], read=read, both=q["both"], n=q["n"], players=[pid(p), pid(o)])
            pairs.append(item)
            if p["pp"] == 1 and o["pp"] == 1:
                pp1.append({**item, "selection": item["selection"].replace("both 1+ point", "PP1 mates · both 1+ point")})
    pairs.sort(key=lambda x: -x["prob"])
    pp1.sort(key=lambda x: -x["prob"])

    two = []
    for p in sorted(players, key=lambda x: -x["p2"])[:5]:
        if p["p2"] < 0.12:
            break
        two.append(_play(f"{p['name']} · 2+ points", p["p2"],
                         f"2+ in {p['two_games']} of {p['gp']} · {p['pp_toi']} PP min/game · {'PP1' if p['pp']==1 else 'L'+str(p['line'])}"
                         + (" · B2B haircut applied" if team_of(p)["b2b"] else ""),
                         player=p["name"], team=p["team"], pp=p["pp"], line=p["line"], players=[pid(p)]))

    # Both teams 2+ goals: Poisson on each team's expected goals vs this opponent (season GF, opp GA, B2B)
    import math
    def lam(t, o):
        base = ((t.get("gf") or 3.0) + (o.get("ga") or 3.0)) / 2
        return base * (model.B2B_POINT if t.get("b2b") else 1.0)
    la, lh = lam(a, h), lam(h, a)
    p2 = lambda l: 1 - math.exp(-l) * (1 + l)
    pb = p2(la) * p2(lh)
    verdict = "Yes" if pb >= 0.62 else ("Maybe" if pb >= 0.52 else "No")
    btts = [_play(f"Both teams 2+ goals · {verdict}", pb,
                  f"{a['team']} xG {la:.2f} · {h['team']} xG {lh:.2f} · P({a['team']} 2+) {round(p2(la)*100)}% · P({h['team']} 2+) {round(p2(lh)*100)}%",
                  verdict=verdict)]
    return {"point": point, "pair": pairs[:5], "two": two, "pp1": pp1[:4], "btts2": btts}


def build(date: str | None = None) -> Path:
    date = date or datetime.now().strftime("%Y-%m-%d")
    slate = model.build_slate(date)
    rec = records(date)
    boxes = analysis.all_boxscores()
    season = analysis.team_rates(boxes)
    l5 = analysis.team_rates(boxes, 5)
    logs = analysis.player_logs(boxes)
    ids = lineup_view.player_ids()
    grec = lineup_view.goalie_records()
    odds = manual_odds(date)
    out_games = []
    for i, g in enumerate(slate["games"], 1):
        def team(side):
            t = g["teams"][side]
            city, name, c1, c2 = TEAM_META.get(t["team"], (t["team"], "", "#888", "#444"))
            return {"abbr": t["team"], "city": city, "name": name, "color": c1, "color2": c2,
                    "record": rec.get(t["team"], {}).get("text", "0-0-0"), "b2b": t["b2b"],
                    "goalie": t["goalie"], "goalie_status": t["goalie_status"], "goalie_news": t["goalie_news"],
                    "goalie_source": t["goalie_source"], "sv": t["sv"], "gaa": t["gaa"],
                    "lineup_as_of": t["lineup_as_of"], "lineup_stale": t["lineup_stale"],
                    "ga_rk": t["ga_rk"], "gf_rk": t["gf_rk"], "ppga_rk": t["ppga_rk"],
                    "rates": _rates_block(season.get(t["team"], {}), l5.get(t["team"], {}))}
        a, h = team("away"), team("home")
        ml_a, ml_h = g["teams"]["away"]["ml"], g["teams"]["home"]["ml"]
        book = odds.get((g["away"], g["home"]), {})
        mkt = market.analyze(book) if book else None
        def amer(v):
            try:
                v = int(float(v)); return f"+{v}" if v > 0 else str(v)
            except (TypeError, ValueError):
                return None
        out_games.append({
            "id": f"{i:02d}", "game_id": g["game_id"], "start_utc": g["start_utc"], "status": g.get("state"),
            "venue": g["venue"], "away": a, "home": h,
            "markets": {
                "moneyline": {"away": amer(ml_a), "home": amer(ml_h), "provider": "Daily Faceoff",
                              "as_of": g["teams"]["home"]["lineup_as_of"]},
                "total": {"line": book.get("total"), "over": book.get("over"), "under": book.get("under"),
                          "provider": book.get("source"), "as_of": book.get("as_of"), "status": book.get("status")},
                "book_moneyline": {"away": book.get("ml_away"), "home": book.get("ml_home"), "provider": book.get("source")} if book.get("ml_away") is not None else None,
            },
            "market": mkt,
            "smash": market.smash(mkt, g["away"], g["home"]) if mkt else {"flag": None, "kind": None, "side": None, "label": "NO LINE", "why": "No book line for this game."},
            "lenses": lenses_for(g, ids),
            "lineup": lineup_view.game_lineups(g["away"], g["home"], date, logs, ids, grec),
        })
    team_rates = {t: {**_rates_block(season[t], l5.get(t, {})), **dict(zip(("city", "name", "color", "color2"), TEAM_META.get(t, (t, "", "#888", "#444"))))}
                  for t in season}
    (DOCS / "team_rates.json").write_text(json.dumps({"date": date, "teams": team_rates}, indent=1), encoding="utf-8")
    board = {"mode": "live", "date": date, "team_rates": team_rates, "generated_utc": datetime.now(timezone.utc).isoformat(),
             "lenses": LENSES, "default_slots": ["point", "pair", "two"], "games": out_games,
             "sources": {"schedule": "NHL API", "lineups": "Daily Faceoff", "goalies": "Daily Faceoff",
                         "moneyline": "Daily Faceoff", "stats": "NHL API boxscores", "model": "nhl_props.model v1"}}
    DOCS.mkdir(exist_ok=True)
    from . import players as _players
    _players.build()
    out = DOCS / "board.json"
    out.write_text(json.dumps(board, indent=1), encoding="utf-8")
    (DOCS / "boards").mkdir(exist_ok=True)
    (DOCS / "boards" / f"{date}.json").write_text(json.dumps(board, indent=1), encoding="utf-8")
    return out

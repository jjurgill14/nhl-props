"""Team and player splits for the Matchup page and the board's rank strip.

Three windows (season / last 10 / last 5) x three venues (all / home / away) = nine cuts. "L5 away" means
the team's last five AWAY games, not the away games among its last five.

teams   : every team, every cut -> the same six rates and ranks the main board shows (ranks are within the cut),
          plus games played and W-L-OTL in the cut. The season|all cut is identical to board.team_rates.
results : slate teams only -> every finished game (date, opponent, venue, final score, OT/SO) so the page can
          show the games behind any cut.
leaders : slate teams only, every cut -> top players by points, goals, assists and shots on goal over the
          team's games in the cut. Only players whose most recent game was for this team are listed.
"""
from __future__ import annotations

from collections import defaultdict

from . import analysis

WINDOWS = {"season": None, "l10": 10, "l5": 5}
VENUES = ("all", "home", "away")
STATS = {"p": "points", "g": "goals", "a": "assists", "sog": "sog"}
TOP_N = 5


def _cut(games: list[dict], venue: str, last_n: int | None) -> list[dict]:
    gs = games if venue == "all" else [g for g in games if g["home"] == (venue == "home")]
    return gs[-last_n:] if last_n else gs


def _fmt(r: dict) -> dict:
    def pct(v):
        return None if v is None else round(100 * v, 1)
    if not r.get("gp"):
        return {"gp": 0, "rec": "0-0-0", **{k: None for k in ("gf", "ga", "sf", "sa", "pp", "pk")},
                **{k + "_rk": None for k in ("gf", "ga", "sf", "sa", "pp", "pk")}}
    return {"gp": r["gp"], "rec": f"{r['w']}-{r['l']}-{r['otl']}", "pp_gp": r.get("pp_gp"),
            "gf": round(r["gf"], 2), "gf_rk": r.get("gf_rk"), "ga": round(r["ga"], 2), "ga_rk": r.get("ga_rk"),
            "sf": round(r["sf"], 1), "sf_rk": r.get("sf_rk"), "sa": round(r["sa"], 1), "sa_rk": r.get("sa_rk"),
            "pp": pct(r.get("pp_pct")), "pp_rk": r.get("pp_rk"), "pk": pct(r.get("pk_pct")), "pk_rk": r.get("pk_rk")}


def build(boxes: dict[int, list[dict]], slate_teams: set[str], ids: dict | None = None) -> dict:
    per_game = analysis.team_games(boxes)
    teams: dict[str, dict] = defaultdict(dict)
    game_ids: dict[tuple[str, str], set[int]] = {}
    for w, n in WINDOWS.items():
        for v in VENUES:
            key = f"{w}|{v}"
            raw = {}
            for t, gs in per_game.items():
                cut = _cut(gs, v, n)
                raw[t] = analysis.rate_block(cut)
                game_ids[(t, key)] = {g["game_id"] for g in cut}
            analysis.rank_rates(raw)
            for t, r in raw.items():
                teams[t][key] = _fmt(r)

    # player totals per (team, game): one pass over the boxscores
    last_team: dict[str, tuple[str, str]] = {}  # player_id -> (date, team) of most recent game
    rows_by_team: dict[str, list[dict]] = defaultdict(list)
    for gid in sorted(boxes):
        for r in boxes[gid]:
            if r.get("pos") == "G" or r["team"] not in slate_teams or analysis._i(r.get("toi_s")) <= 0:
                continue
            rows_by_team[r["team"]].append({**r, "_gid": gid})
    for gid in sorted(boxes):
        for r in boxes[gid]:
            if r.get("pos") != "G":
                last_team[r["player_id"]] = (r.get("date") or "", r["team"])

    leaders: dict[str, dict] = {}
    for t in sorted(slate_teams):
        leaders[t] = {}
        for key in teams.get(t, {}):
            gids = game_ids.get((t, key), set())
            tot: dict[str, dict] = {}
            for r in rows_by_team.get(t, []):
                if r["_gid"] not in gids or last_team.get(r["player_id"], ("", ""))[1] != t:
                    continue
                d = tot.setdefault(r["player_id"], {"id": int(r["player_id"]), "name": r.get("full_name") or r["player"],
                                                    "pos": r.get("pos"), "gp": 0, "p": 0, "g": 0, "a": 0, "sog": 0})
                d["gp"] += 1
                for k, col in STATS.items():
                    d[k] += analysis._i(r.get(col))
            block = {}
            for k in STATS:
                top = sorted(tot.values(), key=lambda d: (-d[k], d["gp"], d["name"]))[:TOP_N]
                block[k] = [{"id": d["id"], "name": d["name"], "pos": d["pos"], "gp": d["gp"], "v": d[k]} for d in top if d[k] > 0]
            leaders[t][key] = block
    # every finished game for the slate teams, oldest first; the app applies the window/venue cut itself
    results = {t: [{"date": g["date"], "game_id": g["game_id"], "opp": g["opp"], "home": g["home"],
                    "tf": g["tf"], "ta": g["ta"], "ot": g.get("ot", "")}
                   for g in per_game.get(t, []) if g.get("tf") is not None] for t in sorted(slate_teams)}
    return {"windows": list(WINDOWS), "venues": list(VENUES), "teams": dict(teams), "leaders": leaders, "results": results}

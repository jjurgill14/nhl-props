"""Per-player game logs for ICEBOARD's Player Props view.

docs/players/index.json      -> [{id, name, team, pos, jersey, gp}]
docs/players/<player_id>.json -> {id, name, team, pos, jersey, log: [{date, game_id, opp, home, g, a, p, sog, pp_toi_s, toi_s, pp_g}]}

The view computes hit rates, averages and pair correlation client-side from these logs,
so one data shape serves single players, pairs, and anything we add later.
"""
from __future__ import annotations

import csv
import glob
import json
from collections import defaultdict
from pathlib import Path

from . import analysis, results

DOCS = results.DATA.parent / "docs"


def build() -> Path:
    logs: dict[int, dict] = {}
    for f in sorted(glob.glob(str(results.DATA / "boxscores" / "*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if not r.get("player_id") or r.get("pos") == "G":
                continue
            pid = int(r["player_id"])
            p = logs.setdefault(pid, {"id": pid, "name": r.get("full_name") or r["player"], "team": r["team"],
                                      "pos": r.get("pos"), "jersey": analysis._i(r.get("sweater")) or None, "log": []})
            p["team"], p["jersey"] = r["team"], analysis._i(r.get("sweater")) or p["jersey"]  # latest wins
            p["log"].append({
                "date": r["date"], "game_id": int(r["game_id"]), "opp": r["opp"], "home": r.get("home") == "1",
                "g": analysis._i(r.get("goals")), "a": analysis._i(r.get("assists")), "p": analysis._i(r.get("points")),
                "sog": analysis._i(r.get("sog")), "pp_g": analysis._i(r.get("pp_goals")),
                "toi_s": analysis._i(r.get("toi_s")), "pp_toi_s": analysis._i(r.get("pp_toi_s")),
            })
    out = DOCS / "players"
    out.mkdir(parents=True, exist_ok=True)
    for p in logs.values():
        p["log"].sort(key=lambda x: (x["date"], x["game_id"]))
        (out / f"{p['id']}.json").write_text(json.dumps(p, separators=(",", ":")), encoding="utf-8")
    index = sorted(({"id": p["id"], "name": p["name"], "team": p["team"], "pos": p["pos"], "jersey": p["jersey"], "gp": len(p["log"])}
                    for p in logs.values()), key=lambda x: (x["team"], x["name"]))
    (out / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    return out

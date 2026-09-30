"""Projected line combinations from Daily Faceoff.

DFO is a Next.js site: every team page embeds a `__NEXT_DATA__` JSON blob with the full
`combinations` object (players with group/position identifiers, injuries, PP/PK units, last-5/10
stats). We read that instead of scraping the rendered HTML.

Snapshots live at data/lineups/YYYY-MM-DD/<TEAM>/<UTCSTAMP>.json and are only written when the
parsed lineup differs from the previous snapshot for that team on that day, so the folder is a
change log: one file per meaningful update.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from .common import DATA, DFO, TEAM_SLUGS, content_hash, get, log, now_utc, read_json, stamp, write_json

LINEUP_DIR = DATA / "lineups"
DEBUG_DIR = DATA / "debug"
MAX_DEBUG_FILES = 6

# categoryIdentifier -> our section code
CATEGORY = {"ev": None, "pp": "PP", "pk": "PK", "oi": "INJ"}  # ev is split by group below


def fetch_html(abbrev: str) -> str:
    slug = TEAM_SLUGS[abbrev]
    r = get(f"{DFO}/teams/{slug}/line-combinations")
    if r.status_code != 200:
        raise RuntimeError(f"DFO {abbrev}: HTTP {r.status_code}")
    return r.text


def next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _stat(block: dict | None) -> dict:
    if not block:
        return {}
    return {
        "gp": block.get("gamesPlayed"), "g": block.get("goals"), "a": block.get("assists"),
        "p": block.get("points"), "sog": block.get("shots"), "ppp": block.get("powerplayPoints"),
        "toi_s": (block.get("toiMinutes") or 0) * 60 + (block.get("toiSeconds") or 0),
    }


def parse(html: str) -> dict:
    nd = next_data(html)
    comb = (((nd or {}).get("props") or {}).get("pageProps") or {}).get("combinations")
    if not comb:
        return {"updated_dfo": None, "source": None, "lines": [], "injuries": [], "players": []}

    lines: list[dict] = []
    injuries: list[dict] = []
    players: dict[int, dict] = {}
    for p in comb.get("players", []):
        cat = p.get("categoryIdentifier")
        grp = (p.get("groupIdentifier") or "").lower()
        posid = (p.get("positionIdentifier") or "").lower()
        pid = p.get("playerId")
        name = p.get("name")
        m = re.match(r"([a-z]+?)(\d+)$", grp)
        unit_no = int(m.group(2)) if m else None

        if cat == "oi":  # out / injured
            injuries.append({"player": name, "dfo_id": pid, "status": (p.get("injuryStatus") or "").upper() or None,
                             "gtd": bool(p.get("gameTimeDecision")),
                             "news": ((p.get("latestNews") or {}).get("details") or "").strip() or None})
            continue

        if cat == "ev":
            if grp.startswith("f"):
                section, pos = "F", posid.upper()
            elif grp.startswith("d"):
                section, pos = "D", posid.upper()
            elif grp == "g":
                section, pos = "G", "G"
                unit_no = int(posid[-1]) if posid[-1:].isdigit() else None  # g1 = starter, g2 = backup
            else:
                section, pos = "EV?", posid.upper()
        else:
            section, pos = CATEGORY.get(cat, cat.upper() if cat else "?"), None

        slot = int(posid[-1]) if posid[-1:].isdigit() else None
        lines.append({
            "section": section, "unit": p.get("groupName"), "unit_no": unit_no,
            "slot": slot, "pos": pos, "player": name, "dfo_id": pid,
            "gtd": bool(p.get("gameTimeDecision")), "injury_status": p.get("injuryStatus"),
        })
        if pid not in players:
            players[pid] = {
                "dfo_id": pid, "player": name, "pos": posid.upper() if cat == "ev" else None,
                "jersey": p.get("jerseyNumber"), "rating": p.get("rating"), "pos_rank": p.get("positionRank"),
                "season": _stat(p.get("season")), "last5": _stat(p.get("last5")), "last10": _stat(p.get("last10")),
            }

    # unit quality ratings DFO assigns to each line/pair/unit
    unit_ratings = {l.get("groupIdentifier"): {"rating": l.get("rating"), "rank": l.get("rank")}
                    for l in comb.get("lines", []) if l.get("groupIdentifier")}

    return {
        "updated_dfo": comb.get("updatedAt"),
        "source": comb.get("source"),
        "source_name": comb.get("sourceName"),
        "lines": lines,
        "injuries": injuries,
        "players": list(players.values()),
        "unit_ratings": unit_ratings,
    }


def _save_debug(name: str, html: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    if len(list(DEBUG_DIR.glob("*.html"))) >= MAX_DEBUG_FILES:
        return
    (DEBUG_DIR / f"{name}_{stamp()}.html").write_text(html)


def snapshot_team(abbrev: str, date: str) -> tuple[str, bool]:
    """Fetch+parse one team; write a snapshot only if changed. Returns (status, changed)."""
    html = fetch_html(abbrev)
    parsed = parse(html)
    n_f = sum(1 for r in parsed["lines"] if r["section"] == "F")
    if n_f < 9:
        _save_debug(f"dfo_{abbrev}", html)
        log.warning("DFO %s: parsed only %d forwards — saved HTML for debugging", abbrev, n_f)
        return "parse_failed", False

    team_dir = LINEUP_DIR / date / abbrev
    prev_files = sorted(team_dir.glob("*.json")) if team_dir.exists() else []
    # hash only the deployment itself (not rolling stats), so a stats refresh doesn't count as a change
    h = content_hash({"lines": parsed["lines"], "injuries": parsed["injuries"]})
    if prev_files:
        prev = read_json(prev_files[-1])
        if prev and prev.get("hash") == h:
            return "unchanged", False

    out = {"team": abbrev, "date": date, "captured_utc": now_utc().isoformat(), "hash": h, **parsed}
    write_json(team_dir / f"{stamp()}.json", out)
    log.info("DFO %s: new lineup snapshot (%d skaters, %d injuries, dfo updated %s)", abbrev,
             sum(1 for r in parsed["lines"] if r["section"] in ("F", "D")), len(parsed["injuries"]),
             parsed.get("updated_dfo"))
    return "written", True


def snapshot_teams(abbrevs: list[str], date: str) -> dict[str, str]:
    results = {}
    for ab in sorted(set(abbrevs)):
        try:
            results[ab], _ = snapshot_team(ab, date)
        except Exception as e:  # keep going for other teams
            log.error("DFO %s failed: %s", ab, e)
            results[ab] = f"error: {e}"
    return results


def latest_snapshot(abbrev: str, date: str) -> dict | None:
    d = LINEUP_DIR / date / abbrev
    files = sorted(d.glob("*.json")) if d.exists() else []
    return read_json(files[-1]) if files else None

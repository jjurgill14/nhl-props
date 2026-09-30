"""Projected line combinations from Daily Faceoff.

Snapshots live at data/lineups/YYYY-MM-DD/<TEAM>/<UTCSTAMP>.json and are only written when the
parsed lineup differs from the previous snapshot for that team on that day, so the folder is a
change log: one file per meaningful update.
"""
from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Tag

from .common import DATA, DFO, TEAM_SLUGS, content_hash, get, log, now_utc, read_json, stamp, write_json

LINEUP_DIR = DATA / "lineups"
DEBUG_DIR = DATA / "debug"

SECTIONS = {"forward": "F", "forwards": "F", "defense": "D", "defence": "D", "goalies": "G",
            "goalie": "G", "power play": "PP", "powerplay": "PP", "penalty kill": "PK", "injuries": "INJ"}
POS = {"LW", "C", "RW", "LD", "RD", "G", "D", "F"}
LINE_RE = re.compile(r"^(1st|2nd|3rd|4th|5th)\s+(line|pairing|pair|powerplay unit|power play unit|penalty kill unit|pp unit|pk unit|unit)\s*$", re.I)
PLAYER_HREF = re.compile(r"/players/(?:news/)?([a-z0-9\-']+)/(\d+)", re.I)
UPDATED_RE = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)")
STATUS_WORDS = {"OUT", "IR", "LTIR", "DAY-TO-DAY", "DAY TO DAY", "QUESTIONABLE", "DOUBTFUL", "PROBABLE", "GTD", "SUSPENDED"}


def fetch_html(abbrev: str) -> str:
    slug = TEAM_SLUGS[abbrev]
    r = get(f"{DFO}/teams/{slug}/line-combinations")
    if r.status_code != 200:
        raise RuntimeError(f"DFO {abbrev}: HTTP {r.status_code}")
    return r.text


def _short_text(t: Tag) -> str:
    return " ".join(t.get_text(" ", strip=True).split())


def parse(html: str) -> dict:
    """Walk the page in document order, tracking the current H4 section and line label."""
    soup = BeautifulSoup(html, "lxml")
    m = UPDATED_RE.search(html)
    updated = m.group(1) if m else None

    section = None
    line_label = None
    slot_pos = None
    slot_idx = 0
    seen: set[tuple] = set()
    rows: list[dict] = []
    injuries: list[dict] = []
    last_injury: dict | None = None

    for el in soup.find_all(True):
        name = el.name.lower()
        if name in ("h2", "h3", "h4"):
            txt = _short_text(el).lower()
            if name == "h2" and section is not None and "line combinations" not in txt:
                break  # left the lineup block (e.g. "Using ... for Betting and DFS")
            key = SECTIONS.get(txt)
            if key:
                section, line_label, slot_idx = key, None, 0
            continue
        if section is None:
            continue
        if name == "a" and el.get("href"):
            pm = PLAYER_HREF.search(el["href"])
            if not pm:
                continue
            pname = _short_text(el)
            if not pname:
                continue
            dfo_id = int(pm.group(2))
            if section == "INJ":
                last_injury = {"player": pname, "dfo_id": dfo_id, "status": None}
                injuries.append(last_injury)
                continue
            key = (section, line_label, dfo_id)
            if key in seen:
                continue
            seen.add(key)
            slot_idx += 1
            rows.append({
                "section": section,          # F / D / G / PP / PK
                "unit": line_label,          # "1st Line", "2nd Pairing", "1st Powerplay Unit" ...
                "unit_no": _unit_no(line_label, section, slot_idx),
                "slot": slot_idx,
                "pos": slot_pos if section in ("F", "D", "G") else None,
                "player": pname,
                "dfo_id": dfo_id,
            })
            slot_pos = None
            continue
        # leaf-ish text nodes for labels: only look at elements with no element children
        if not el.find(True):
            txt = _short_text(el)
            if LINE_RE.match(txt):
                line_label, slot_idx = txt, 0
                continue
            if txt.upper() in POS:
                slot_pos = txt.upper()
                continue
            if section == "INJ" and last_injury and txt.upper() in STATUS_WORDS and not last_injury.get("status"):
                last_injury["status"] = txt.upper()
                continue

    return {"updated_dfo": updated, "lines": rows, "injuries": injuries}


def _unit_no(label: str | None, section: str, slot: int) -> int | None:
    if label:
        m = re.match(r"(\d)", label)
        if m:
            return int(m.group(1))
    if section == "G":
        return slot  # 1 = listed starter, 2 = backup
    return None


def snapshot_team(abbrev: str, date: str) -> tuple[str, bool]:
    """Fetch+parse one team; write a snapshot only if changed. Returns (status, changed)."""
    html = fetch_html(abbrev)
    parsed = parse(html)
    n_f = sum(1 for r in parsed["lines"] if r["section"] == "F")
    if n_f < 9:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"dfo_{abbrev}_{stamp()}.html").write_text(html)
        log.warning("DFO %s: parsed only %d forwards — saved HTML for debugging", abbrev, n_f)
        return "parse_failed", False

    team_dir = LINEUP_DIR / date / abbrev
    prev_files = sorted(team_dir.glob("*.json")) if team_dir.exists() else []
    h = content_hash({"lines": parsed["lines"], "injuries": parsed["injuries"]})
    if prev_files:
        prev = read_json(prev_files[-1])
        if prev and prev.get("hash") == h:
            return "unchanged", False

    out = {
        "team": abbrev,
        "date": date,
        "captured_utc": now_utc().isoformat(),
        "hash": h,
        **parsed,
    }
    write_json(team_dir / f"{stamp()}.json", out)
    log.info("DFO %s: new lineup snapshot (%d skaters, %d injuries)", abbrev,
             sum(1 for r in parsed["lines"] if r["section"] in ("F", "D")), len(parsed["injuries"]))
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

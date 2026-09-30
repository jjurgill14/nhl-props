"""Starting goalies from Daily Faceoff (/starting-goalies/YYYY-MM-DD).

Every run appends one row per goalie to data/goalies/YYYY-MM-DD.csv, so you can see when a
start went from Unconfirmed -> Confirmed.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from .common import DATA, DFO, TEAM_NAMES, get, log, now_utc, stamp, write_csv

GOALIE_DIR = DATA / "goalies"
DEBUG_DIR = DATA / "debug"

MATCHUP_RE = re.compile(r"^(.+?)\s+at\s+(.+?)$")
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
PLAYER_HREF = re.compile(r"/players/(?:news/)?([a-z0-9\-']+)/(\d+)", re.I)
STATUSES = {"confirmed": "Confirmed", "unconfirmed": "Unconfirmed", "likely": "Likely",
            "expected": "Expected", "projected": "Projected"}

FIELDS = ["date", "captured_utc", "away", "home", "start_utc", "team", "goalie", "dfo_id", "status", "news"]


def fetch_html(date: str) -> str:
    r = get(f"{DFO}/starting-goalies/{date}")
    if r.status_code != 200:
        raise RuntimeError(f"DFO goalies {date}: HTTP {r.status_code}")
    return r.text


def parse(html: str, date: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    away = home = start = None
    side = 0  # 0 = away goalie next, 1 = home goalie next
    cur: dict | None = None
    cap = now_utc().isoformat()

    for el in soup.find_all(True):
        name = el.name.lower()
        if name == "a" and el.get("href") and PLAYER_HREF.search(el["href"]):
            txt = " ".join(el.get_text(" ", strip=True).split())
            if not txt or not away:
                continue
            # skip nav links (team line combos etc.) — those don't hit /players/
            dfo_id = int(PLAYER_HREF.search(el["href"]).group(2))
            if cur and cur["dfo_id"] == dfo_id:
                continue
            team = away if side == 0 else home
            cur = {"date": date, "captured_utc": cap, "away": away, "home": home, "start_utc": start,
                   "team": team, "goalie": txt, "dfo_id": dfo_id, "status": None, "news": ""}
            rows.append(cur)
            side = 1 - side
            continue
        if el.find(True):
            continue  # only leaf text from here on
        txt = " ".join(el.get_text(" ", strip=True).split())
        if not txt:
            continue
        m = MATCHUP_RE.match(txt)
        if m and m.group(1) in TEAM_NAMES and m.group(2) in TEAM_NAMES:
            away, home, start, side, cur = TEAM_NAMES[m.group(1)], TEAM_NAMES[m.group(2)], None, 0, None
            continue
        if ISO_RE.match(txt):
            start = txt
            continue
        low = txt.lower()
        if cur and cur["status"] is None and low in STATUSES:
            cur["status"] = STATUSES[low]
            continue
        if cur and cur["status"] and not cur["news"] and len(txt) > 40 and name in ("p", "div", "span"):
            cur["news"] = txt[:500]
    return rows


def snapshot(date: str) -> list[dict]:
    html = fetch_html(date)
    rows = parse(html, date)
    if not rows:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"dfo_goalies_{date}_{stamp()}.html").write_text(html)
        log.warning("DFO goalies %s: parsed 0 rows — saved HTML for debugging", date)
        return rows
    write_csv(GOALIE_DIR / f"{date}.csv", rows, FIELDS, append=True)
    conf = sum(1 for r in rows if r["status"] == "Confirmed")
    log.info("DFO goalies %s: %d goalies, %d confirmed", date, len(rows), conf)
    return rows

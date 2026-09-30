"""Starting goalies from Daily Faceoff (/starting-goalies/YYYY-MM-DD), read from the page's
`__NEXT_DATA__` JSON. Every run appends one row per goalie to data/goalies/YYYY-MM-DD.csv, so you
can see when a start went from Unconfirmed -> Likely -> Confirmed, and what the line was.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from .common import DATA, DFO, TEAM_NAMES, get, log, now_utc, stamp, write_csv
from .lineups import next_data, _save_debug

GOALIE_DIR = DATA / "goalies"

FIELDS = ["date", "captured_utc", "away", "home", "start_utc", "team", "side", "goalie", "dfo_id",
          "status", "news_utc", "news", "source", "moneyline", "spread", "season_sv_pct", "season_gaa"]


def fetch_html(date: str) -> str:
    r = get(f"{DFO}/starting-goalies/{date}")
    if r.status_code != 200:
        raise RuntimeError(f"DFO goalies {date}: HTTP {r.status_code}")
    return r.text


def parse(html: str, date: str) -> list[dict]:
    nd = next_data(html)
    games = (((nd or {}).get("props") or {}).get("pageProps") or {}).get("data") or []
    cap = now_utc().isoformat()
    rows: list[dict] = []
    for g in games:
        away = TEAM_NAMES.get(g.get("awayTeamName"), g.get("awayTeamName"))
        home = TEAM_NAMES.get(g.get("homeTeamName"), g.get("homeTeamName"))
        for side in ("away", "home"):
            k = lambda s: g.get(f"{side}{s}")  # noqa: E731
            rows.append({
                "date": g.get("date") or date, "captured_utc": cap, "away": away, "home": home,
                "start_utc": g.get("dateGmt"), "team": away if side == "away" else home, "side": side,
                "goalie": k("GoalieName"), "dfo_id": k("GoalieId"),
                "status": k("NewsStrengthName"),           # Confirmed / Likely / Unconfirmed ...
                "news_utc": k("NewsCreatedAt"), "news": (k("NewsDetails") or "").strip(),
                "source": k("NewsSourceName"),
                "moneyline": k("TeamMoneylinePointSpread"), "spread": g.get("pointSpread"),
                "season_sv_pct": k("GoalieSavePercentage"), "season_gaa": k("GoalieGoalsAgainstAvg"),
            })
    return rows


def snapshot(date: str) -> list[dict]:
    html = fetch_html(date)
    rows = parse(html, date)
    if not rows:
        _save_debug(f"dfo_goalies_{date}", html)
        log.warning("DFO goalies %s: parsed 0 rows — saved HTML for debugging", date)
        return rows
    write_csv(GOALIE_DIR / f"{date}.csv", rows, FIELDS, append=True)
    conf = sum(1 for r in rows if r["status"] == "Confirmed")
    log.info("DFO goalies %s: %d goalies, %d confirmed", date, len(rows), conf)
    return rows

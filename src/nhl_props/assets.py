"""Static assets for the front end: the 32 team logos (dark + light) and player headshots.
Fetched from the NHL's public asset CDN, written under docs/assets/ so GitHub Pages serves them.
Idempotent — files that already exist are skipped, so this is cheap to call every run."""
from __future__ import annotations

import logging
from pathlib import Path

from . import analysis, results
from .common import get

log = logging.getLogger(__name__)

ASSETS = results.DATA.parent / "docs" / "assets"
LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{team}_{variant}.svg"
MUG_URL = "https://assets.nhle.com/mugs/nhl/{season}/{team}/{player_id}.png"

TEAMS = ["ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA",
         "LAK", "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS",
         "STL", "TBL", "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"]


def _save(url: str, path: Path) -> bool:
    if path.exists() and path.stat().st_size > 0:
        return False
    r = get(url, timeout=20)
    if r.status_code != 200 or not r.content:
        log.warning("asset %s -> %s", url, r.status_code)
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return True


def logos() -> int:
    n = 0
    for t in TEAMS:
        for v in ("dark", "light"):
            n += _save(LOGO_URL.format(team=t, variant=v), ASSETS / "logos" / f"{t}_{v}.svg")
    log.info("logos: %d new", n)
    return n


def headshots(season: str = "20262027") -> int:
    """One PNG per player seen in this season's boxscores, keyed by NHL player_id."""
    n = 0
    seen: set[tuple[str, str]] = set()
    for rows in analysis.all_boxscores().values():
        for r in rows:
            key = (r["team"], r["player_id"])
            if key in seen or not r.get("player_id"):
                continue
            seen.add(key)
            n += _save(MUG_URL.format(season=season, team=r["team"], player_id=r["player_id"]),
                       ASSETS / "mugs" / f"{r['player_id']}.png")
    log.info("headshots: %d new (%d players)", n, len(seen))
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logos()
    headshots()

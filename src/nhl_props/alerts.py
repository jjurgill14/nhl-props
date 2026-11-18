"""Late lineup changes: diff consecutive Daily Faceoff snapshots (and goalie rows) for teams close to
puck drop, persist them, and push a GitHub issue comment so the change reaches a phone. One issue per
game; a pre-game card (both goalies + every lineup change since the morning) is posted about an hour out.

data/alerts/<date>.jsonl   every alert of the day (append-only)
docs/alerts.json           today's alerts for the app (board.build attaches them per team)
data/alerts/<date>.pregame.json  game_id -> when its pre-game card was posted
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from .analysis import read_csv, slots
from .common import DATA, log, now_utc

ALERT_DIR = DATA / "alerts"
DOCS = Path(__file__).resolve().parents[2] / "docs"

_STATUS_RANK = {None: 0, "": 0, "GTD": 1, "DTD": 2, "OUT": 3, "IR": 4, "LTIR": 5}


def _injury_map(snap: dict) -> dict[str, str]:
    return {i["player"]: (i.get("status") or "") for i in snap.get("injuries", [])}


def _pos(snap: dict, player: str) -> str:
    for r in snap.get("lines", []):
        if r["player"] == player and r["section"] in ("F", "D"):
            return r.get("pos") or r["section"]
    return ""


def diff_snapshots(prev: dict | None, cur: dict | None) -> list[dict]:
    """Structural changes only (who dresses, which line/PP unit, injury status) — not news-text edits."""
    if not prev or not cur:
        return []
    a, b = slots(prev), slots(cur)
    ia, ib = _injury_map(prev), _injury_map(cur)
    out: list[dict] = []
    for p in b:
        if p not in a:
            s = b[p]
            where = f"L{s['ev']}" if s["ev"] else "lineup"
            if s["pp"]:
                where += f", PP{s['pp']}"
            was = f" (was {ia[p]})" if ia.get(p) else ""
            out.append({"kind": "in", "player": p, "text": f"IN: {p}{was} → {where}"})
    for p in a:
        if p not in b:
            now = f" → {ib[p]}" if ib.get(p) else ""
            out.append({"kind": "out", "player": p, "text": f"OUT: {p} (was L{a[p]['ev']}){now}"})
    for p in b:
        if p in a:
            ea, eb = a[p]["ev"], b[p]["ev"]
            pa, pb = a[p]["pp"], b[p]["pp"]
            bits = []
            if ea and eb and ea != eb:
                bits.append(f"L{ea}→L{eb}")
            if pa != pb:
                bits.append(f"PP{pa or '-'}→PP{pb or '-'}")
            if bits:
                out.append({"kind": "move", "player": p, "text": f"{p}: " + ", ".join(bits)})
    for p, st in ib.items():
        if p in a or p in b:
            continue  # covered above
        if (ia.get(p) or "") != st and p not in ia:
            out.append({"kind": "injury", "player": p, "text": f"{p}: added to injuries ({st})"})
    return out


def diff_goalies(date: str, team: str) -> list[dict]:
    """Goalie name or confirmation change between the last two DFO goalie rows for the team today."""
    rows = [r for r in (read_csv(ALERT_DIR.parent / "goalies" / f"{date}.csv") or []) if r.get("team") == team]
    if len(rows) < 2:
        return []
    a, b = rows[-2], rows[-1]
    if a.get("goalie") != b.get("goalie"):
        return [{"kind": "goalie", "player": b.get("goalie"), "text": f"G: {b.get('goalie')} ({b.get('status')}) replaces {a.get('goalie')}"}]
    if a.get("status") != b.get("status") and b.get("status") == "Confirmed":
        return [{"kind": "goalie", "player": b.get("goalie"), "text": f"G: {b.get('goalie')} confirmed"}]
    return []


def record(date: str, team: str, opp: str, start_utc: str, items: list[dict], dfo_updated: str | None) -> list[dict]:
    if not items:
        return []
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_utc().isoformat()
    rows = [{"date": date, "team": team, "opp": opp, "start_utc": start_utc, "at": ts, "dfo_updated": dfo_updated, **i} for i in items]
    with open(ALERT_DIR / f"{date}.jsonl", "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows


def load(date: str) -> list[dict]:
    p = ALERT_DIR / f"{date}.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def publish(date: str) -> None:
    DOCS.mkdir(exist_ok=True)
    (DOCS / "alerts.json").write_text(json.dumps({"date": date, "alerts": load(date)}, separators=(",", ":")))


# ----------------------------------------------------------------------------- GitHub notification
def _gh(method: str, path: str, **body):
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not tok or not repo:
        return None
    r = requests.request(method, f"https://api.github.com/repos/{repo}{path}", json=body or None,
                         headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code >= 300:
        log.warning("GitHub %s %s: %s %s", method, path, r.status_code, r.text[:200])
        return None
    return r.json()


def _game_key(date: str, team: str, opp: str, start_utc: str) -> tuple[str, str, str]:
    """(away, home, start_et) for the game between team and opp, from the day's schedule."""
    from . import schedule
    for g in schedule.load_day(date):
        if {g["away"], g["home"]} == {team, opp}:
            return g["away"], g["home"], _start_et(g["start_utc"])
    return team, opp, _start_et(start_utc) if start_utc else ""


def _start_et(start_utc: str) -> str:
    from .common import ET, parse_utc
    return parse_utc(start_utc).astimezone(ET).strftime("%-I:%M %p ET") if start_utc else ""


def _when_et(iso: str | None) -> str:
    """'11/17 12:49 PM' from a DFO ISO timestamp, or '?'."""
    from .common import ET, parse_utc
    try:
        return parse_utc(iso).astimezone(ET).strftime("%-m/%-d %-I:%M %p") if iso else "?"
    except Exception:
        return iso or "?"


def _issue_title(date: str, away: str, home: str, start_et: str) -> str:
    return f"{away} @ {home} — {date}" + (f" {start_et}" if start_et else "")


def game_issue(date: str, away: str, home: str, start_et: str, *, mention: str = "") -> dict | None:
    """One open 'alerts' issue per game (created on first use). Issues from earlier dates are closed."""
    title = _issue_title(date, away, home, start_et)
    issues = _gh("GET", "/issues?state=open&labels=alerts&per_page=50") or []
    issue = next((i for i in issues if i["title"] == title), None)
    if issue is not None:
        return issue
    for i in issues:
        if date not in i["title"]:  # yesterday's games
            _gh("PATCH", f"/issues/{i['number']}", state="closed")
    body = (f"{away} @ {home}, puck drop {start_et}. The evening loop posts the pre-game card about an hour out "
            f"and every Daily Faceoff change after it as a comment here. Board: https://jjurgill14.github.io/nhl-props/ {mention}").strip()
    return _gh("POST", "/issues", title=title, body=body, labels=["alerts"],
               assignees=[mention.lstrip("@")] if mention else [])


def notify(date: str, rows: list[dict], *, mention: str | None = None) -> None:
    """Comment the new alerts on the game's issue (one issue per game), mentioning the owner."""
    if not rows:
        return
    mention = mention or os.environ.get("ALERT_MENTION") or ""
    by_game: dict[tuple, list[dict]] = {}
    for r in rows:
        by_game.setdefault(_game_key(date, r["team"], r["opp"], r.get("start_utc") or ""), []).append(r)
    for (away, home, start_et), game_rows in by_game.items():
        issue = game_issue(date, away, home, start_et, mention=mention)
        if issue is None:
            continue
        by_team: dict[str, list[dict]] = {}
        for r in game_rows:
            by_team.setdefault(f"{r['team']} (vs {r['opp']})", []).append(r)
        text = []
        for k, v in by_team.items():
            text.append(f"**{k}**")
            text.extend(f"- {r['text']}" for r in v)
        comment = ("\n".join(text) + f"\n\n{mention}").strip()
        _gh("POST", f"/issues/{issue['number']}/comments", body=comment)
        log.info("alerts: posted %d changes to issue #%s (%s @ %s)", len(game_rows), issue["number"], away, home)


# ----------------------------------------------------------------------------- pre-game card
PREGAME_HOURS = 1.0  # post the card once a game is inside this window (the loop polls every 5 min there)


def _pregame_marker(date: str) -> Path:
    return ALERT_DIR / f"{date}.pregame.json"


def pregame_sent(date: str) -> dict:
    p = _pregame_marker(date)
    return json.loads(p.read_text()) if p.exists() else {}


def _goalie_row(date: str, team: str) -> dict | None:
    rows = [r for r in (read_csv(ALERT_DIR.parent / "goalies" / f"{date}.csv") or []) if r.get("team") == team]
    return rows[-1] if rows else None


def _goalie_line(date: str, team: str) -> str:
    r = _goalie_row(date, team)
    if not r or not r.get("goalie"):
        return f"**{team}** G: not listed on Daily Faceoff yet"
    status = r.get("status") or "Unconfirmed"
    bits = [f"**{team}** G: {r['goalie']} ({status})"]
    if r.get("season_sv_pct") or r.get("season_gaa"):
        bits.append(f"{r.get('season_sv_pct') or '?'} SV% / {r.get('season_gaa') or '?'} GAA")
    if r.get("moneyline"):
        bits.append(f"ML {r['moneyline']}")
    line = " · ".join(bits)
    if r.get("news"):
        line += f"\n  _{r['news'].strip()}_" + (f" — {r['source']}" if r.get("source") else "")
    return line


def _first_snapshot(team: str, date: str) -> dict | None:
    from .lineups import LINEUP_DIR
    from .common import read_json
    d = LINEUP_DIR / date / team
    files = sorted(d.glob("*.json")) if d.exists() else []
    return read_json(files[0]) if files else None


def pregame_card(date: str, game: dict) -> str:
    """Markdown: both goalies as DFO lists them now, and every lineup change since the morning snapshot."""
    from .lineups import latest
    away, home = game["away"], game["home"]
    out = [f"### Pre-game card — {away} @ {home}, {_start_et(game.get('start_utc', ''))}", ""]
    for t in (away, home):
        out.append("- " + _goalie_line(date, t))
    out.append("")
    for t in (away, home):
        first, cur = _first_snapshot(t, date), latest(t, date)
        if not cur:
            out.append(f"**{t} lines:** no Daily Faceoff snapshot today")
            continue
        changes = diff_snapshots(first, cur) if first and first.get("hash") != cur.get("hash") else []
        if changes:
            out.append(f"**{t} lines since this morning** (DFO updated {_when_et(cur.get('updated_dfo'))}):")
            out.extend(f"- {c['text']}" for c in changes)
        else:
            out.append(f"**{t} lines:** no changes since this morning (DFO updated {_when_et(cur.get('updated_dfo'))})")
    out.append("")
    out.append("_Anything that changes from here lands as a comment on this issue._")
    return "\n".join(out)


def pregame(date: str, games: list[dict], *, mention: str | None = None) -> list[dict]:
    """Post one pre-game card per game inside PREGAME_HOURS that hasn't had one. Returns the games carded."""
    from . import schedule
    mention = mention or os.environ.get("ALERT_MENTION") or ""
    sent = pregame_sent(date)
    done: list[dict] = []
    for g in schedule.games_starting_within(games, PREGAME_HOURS):
        gid = str(g["game_id"])
        if gid in sent:
            continue
        issue = game_issue(date, g["away"], g["home"], _start_et(g.get("start_utc", "")), mention=mention)
        if issue is None:
            continue
        body = (pregame_card(date, g) + f"\n\n{mention}").strip()
        if _gh("POST", f"/issues/{issue['number']}/comments", body=body) is None:
            continue
        sent[gid] = now_utc().isoformat()
        ALERT_DIR.mkdir(parents=True, exist_ok=True)
        _pregame_marker(date).write_text(json.dumps(sent, indent=1))
        log.info("pregame: posted card for %s @ %s to issue #%s", g["away"], g["home"], issue["number"])
        done.append(g)
    return done

"""Late lineup changes: diff consecutive Daily Faceoff snapshots (and goalie rows) for teams close to
puck drop, persist them, and push a GitHub issue comment so the change reaches a phone.

data/alerts/<date>.jsonl   every alert of the day (append-only)
docs/alerts.json           today's alerts for the app (board.build attaches them per team)
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


def notify(date: str, rows: list[dict], *, mention: str | None = None) -> None:
    """Comment the new alerts on today's 'Lineup alerts' issue (created on first use), assigning/mentioning the owner."""
    if not rows:
        return
    mention = mention or os.environ.get("ALERT_MENTION") or ""
    title = f"Lineup alerts {date}"
    issues = _gh("GET", f"/issues?state=open&labels=alerts&per_page=20") or []
    issue = next((i for i in issues if i["title"] == title), None)
    if issue is None:
        for i in issues:  # one open alerts issue at a time
            _gh("PATCH", f"/issues/{i['number']}", state="closed")
        body = f"Late lineup changes for {date}, posted by the evening loop as Daily Faceoff updates. {mention}".strip()
        issue = _gh("POST", "/issues", title=title, body=body, labels=["alerts"],
                    assignees=[mention.lstrip("@")] if mention else [])
        if issue is None:
            return
    by_game: dict[str, list[dict]] = {}
    for r in rows:
        by_game.setdefault(f"{r['team']} (vs {r['opp']})", []).append(r)
    text = []
    for k, v in by_game.items():
        text.append(f"**{k}**")
        text.extend(f"- {r['text']}" for r in v)
    comment = ("\n".join(text) + f"\n\n{mention}").strip()
    _gh("POST", f"/issues/{issue['number']}/comments", body=comment)
    log.info("alerts: posted %d changes to issue #%s", len(rows), issue["number"])

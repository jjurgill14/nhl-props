"""Daily one-pager, written to docs/index.html (served by GitHub Pages) after every job.

Sections: tonight's slate (goalies, lines, PP1, injuries, lineup changes), hot list from DFO rolling
stats, last night's results + projection check, data health.
"""
from __future__ import annotations

import csv
import html
import json
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from . import lineups, results, schedule
from .common import DATA, ET, ROOT, log, now_utc, parse_utc, read_json

DOCS = ROOT / "docs"
RUNS_LOG = DATA / "runs.jsonl"


# ----------------------------------------------------------------------------- helpers
def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def norm(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").replace(".", "").split())


def et(ts: str | None, fmt: str = "%-I:%M %p") -> str:
    if not ts:
        return "—"
    try:
        return parse_utc(ts).astimezone(ET).strftime(fmt)
    except Exception:
        return ts


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def log_run(job: str, **counts) -> None:
    RUNS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUNS_LOG.open("a") as f:
        f.write(json.dumps({"job": job, "utc": now_utc().isoformat(), **counts}) + "\n")


def last_runs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if RUNS_LOG.exists():
        for line in RUNS_LOG.read_text().splitlines()[-400:]:
            try:
                r = json.loads(line)
                out[r["job"]] = r
            except json.JSONDecodeError:
                pass
    return out


def team_snapshots(team: str, date: str) -> list[dict]:
    d = lineups.LINEUP_DIR / date / team
    return [read_json(p) for p in sorted(d.glob("*.json"))] if d.exists() else []


def slot_map(snap: dict) -> dict[str, str]:
    """player -> 'F1' / 'D2' / 'G1' / 'PP1' ... for diffing."""
    m: dict[str, set[str]] = defaultdict(set)
    for r in snap.get("lines", []):
        sec, no = r["section"], r.get("unit_no")
        m[r["player"]].add(f"{sec}{no}" if no else sec)
    return {p: "/".join(sorted(v)) for p, v in m.items()}


def diff_snapshots(prev: dict | None, cur: dict) -> list[str]:
    if not prev:
        return []
    a, b = slot_map(prev), slot_map(cur)
    out = []
    for p in sorted(set(a) | set(b)):
        if a.get(p) != b.get(p):
            out.append(f"{p}: {a.get(p, 'out')} → {b.get(p, 'out')}")
    ia = {i["player"]: i.get("status") for i in prev.get("injuries", [])}
    ib = {i["player"]: i.get("status") for i in cur.get("injuries", [])}
    for p in sorted(set(ia) | set(ib)):
        if ia.get(p) != ib.get(p):
            out.append(f"{p}: {ia.get(p) or 'healthy'} → {ib.get(p) or 'healthy'} (injury list)")
    return out


def unit(snap: dict, section: str, no: int) -> list[dict]:
    return [r for r in snap.get("lines", []) if r["section"] == section and r.get("unit_no") == no]


# ----------------------------------------------------------------------------- sections
def goalie_board(date: str) -> dict[tuple[str, str], dict]:
    """latest row per (team) from today's goalie csv, plus history of status changes."""
    rows = read_csv(results.DATA / "goalies" / f"{date}.csv")
    latest: dict[str, dict] = {}
    history: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        latest[r["team"]] = r
        h = history[r["team"]]
        if not h or h[-1][1] != (r.get("goalie"), r.get("status")):
            h.append((r["captured_utc"], (r.get("goalie"), r.get("status"))))
    return {"latest": latest, "history": history}


def render_game(g: dict, date: str, gb: dict) -> str:
    start = et(g["start_utc"])
    cols = []
    for side in ("away", "home"):
        team = g[side]
        snaps = team_snapshots(team, date)
        cur = snaps[-1] if snaps else None
        prev = snaps[-2] if len(snaps) > 1 else None
        gl = gb["latest"].get(team, {})
        status = gl.get("status") or "—"
        badge = {"Confirmed": "ok", "Likely": "warn", "Expected": "warn"}.get(status, "bad" if status not in ("—",) else "")
        parts = [f'<div class="team"><h3>{esc(team)} <span class="ml">{esc(gl.get("moneyline") or "")}</span></h3>']
        parts.append(
            f'<div class="goalie"><span class="badge {badge}">{esc(status)}</span> <b>{esc(gl.get("goalie") or "no goalie listed")}</b>'
            + (f' <span class="muted">— {esc(gl["news"][:140])}</span>' if gl.get("news") else "") + "</div>")
        if cur:
            def line(sec, no, label):
                ps = unit(cur, sec, no)
                if not ps:
                    return ""
                names = " – ".join(
                    f'<span class="{"gtd" if p.get("gtd") else ""}">{esc(p["player"])}</span>' for p in ps)
                return f'<div class="line"><span class="lbl">{label}</span>{names}</div>'
            parts += [line("F", 1, "L1"), line("F", 2, "L2"), line("F", 3, "L3"), line("D", 1, "D1"),
                      line("PP", 1, "PP1"), line("PP", 2, "PP2")]
            inj = cur.get("injuries", [])
            if inj:
                parts.append('<div class="line"><span class="lbl">OUT</span>' + ", ".join(
                    f'{esc(i["player"])} <span class="muted">({esc(i.get("status") or "?")}{", GTD" if i.get("gtd") else ""})</span>'
                    for i in inj) + "</div>")
            changes = diff_snapshots(prev, cur)
            meta = f'{len(snaps)} snapshot{"s" if len(snaps) != 1 else ""} today · DFO updated {et(cur.get("updated_dfo"))} · captured {et(cur.get("captured_utc"))}'
            parts.append(f'<div class="muted small">{esc(meta)}</div>')
            if changes:
                parts.append('<details><summary class="small">Latest change (' + str(len(changes)) + ')</summary><ul class="small">'
                             + "".join(f"<li>{esc(c)}</li>" for c in changes[:14]) + "</ul></details>")
        else:
            parts.append('<div class="muted small">no lineup snapshot yet</div>')
        parts.append("</div>")
        cols.append("".join(parts))
    spread = gb["latest"].get(g["home"], {}).get("spread")
    return (f'<section class="game"><div class="gamehead"><span class="time">{esc(start)}</span> '
            f'<b>{esc(g["away"])} @ {esc(g["home"])}</b>'
            + (f' <span class="muted">puck line {esc(spread)}</span>' if spread else "")
            + f'</div><div class="cols">{"".join(cols)}</div></section>')


def hot_list(games: list[dict], date: str) -> str:
    rows = []
    for g in games:
        for team in (g["away"], g["home"]):
            snaps = team_snapshots(team, date)
            if not snaps:
                continue
            cur = snaps[-1]
            on_pp1 = {r["player"] for r in unit(cur, "PP", 1)}
            line_of = {r["player"]: r.get("unit_no") for r in cur.get("lines", []) if r["section"] == "F"}
            for p in cur.get("players", []):
                l10 = p.get("last10") or {}
                if not l10.get("gp"):
                    continue
                rows.append({
                    "team": team, "player": p["player"], "pos": p.get("pos"), "line": line_of.get(p["player"]),
                    "pp1": p["player"] in on_pp1, "gp": l10["gp"],
                    "ppg": (l10.get("p") or 0) / l10["gp"], "spg": (l10.get("sog") or 0) / l10["gp"],
                    "gpg": (l10.get("g") or 0) / l10["gp"], "ppp": l10.get("ppp") or 0,
                    "toi": (l10.get("toi_s") or 0) / l10["gp"] / 60,
                })
    if not rows:
        return '<p class="muted">No rolling stats yet (DFO last-10 shows up once the season has games).</p>'

    def table(title, key, fmt, n=12):
        top = sorted(rows, key=lambda r: r[key], reverse=True)[:n]
        trs = "".join(
            f'<tr><td>{esc(r["player"])}{" <span class=pp>PP1</span>" if r["pp1"] else ""}</td>'
            f'<td class="muted">{esc(r["team"])} {esc(r["pos"] or "")}{(" L" + str(r["line"])) if r["line"] else ""}</td>'
            f'<td class="num">{fmt(r[key])}</td><td class="num muted">{r["toi"]:.1f}</td></tr>' for r in top)
        return (f'<div class="tbl"><h4>{title}</h4><table><thead><tr><th>Player</th><th></th>'
                f'<th class="num">{title.split(" ")[0]}</th><th class="num">TOI</th></tr></thead><tbody>{trs}</tbody></table></div>')

    return ('<div class="cols3">'
            + table("Points / game (last 10)", "ppg", lambda v: f"{v:.2f}")
            + table("Shots / game (last 10)", "spg", lambda v: f"{v:.1f}")
            + table("Goals / game (last 10)", "gpg", lambda v: f"{v:.2f}")
            + "</div>")


def last_night(yday: str) -> str:
    games = schedule.load_day(yday)
    if not games:
        return '<p class="muted">No games yesterday.</p>'
    gb = goalie_board(yday)
    blocks = []
    top_rows = []
    for g in games:
        info = read_json(results.GAMEINFO_DIR / f"{g['game_id']}.json")
        box = read_csv(results.BOX_DIR / f"{g['game_id']}.csv")
        if not info or not box:
            blocks.append(f'<div class="muted small">{esc(g["away"])} @ {esc(g["home"])}: not ingested yet (state {esc(g.get("state"))})</div>')
            continue
        ot = info.get("last_period_type")
        score = f'{g["away"]} {info.get("away_score")} – {info.get("home_score")} {g["home"]}' + (f" ({ot})" if ot in ("OT", "SO") else "")
        checks = []
        for team in (g["away"], g["home"]):
            snaps = team_snapshots(team, yday)
            cur = snaps[-1] if snaps else None
            trows = [r for r in box if r["team"] == team]
            # goalie check
            actual_g = next((r for r in trows if r["pos"] == "G" and r.get("starter") == "True"), None)
            proj_g = gb["latest"].get(team, {}).get("goalie")
            if actual_g:
                same = norm(actual_g.get("full_name") or "") == norm(proj_g) or (proj_g and norm(proj_g).split()[-1] in norm(actual_g["player"]))
                checks.append(f'{team} G: {esc(actual_g.get("full_name") or actual_g["player"])} '
                              f'({esc(actual_g.get("saves"))}/{esc(actual_g.get("shots_against"))}) '
                              + ('<span class="ok">as projected</span>' if same else f'<span class="bad">projected {esc(proj_g)}</span>'))
            # PP1 check
            if cur:
                proj = {norm(r["player"]) for r in unit(cur, "PP", 1)}
                sk = [r for r in trows if r["pos"] != "G" and r.get("pp_toi_s")]
                sk.sort(key=lambda r: int(r["pp_toi_s"] or 0), reverse=True)
                actual = [norm(r.get("full_name") or r["player"]) for r in sk[:5]]
                hit = sum(1 for a in actual if a in proj)
                if proj:
                    checks.append(f'{team} PP1: {hit}/{len(proj)} projected skaters led PP TOI'
                                  + (f' <span class="muted">(top PP: {", ".join(esc(r.get("full_name") or r["player"]) for r in sk[:3])})</span>' if sk else ""))
        for r in box:
            if r["pos"] != "G" and (int(r["points"] or 0) >= 2 or int(r["sog"] or 0) >= 6):
                top_rows.append((int(r["points"] or 0), int(r["sog"] or 0), r))
        blocks.append(f'<div class="result"><b>{esc(score)}</b><ul class="small">' + "".join(f"<li>{c}</li>" for c in checks) + "</ul></div>")
    top_rows.sort(key=lambda t: (t[0], t[1]), reverse=True)
    perf = "".join(
        f'<tr><td>{esc(r.get("full_name") or r["player"])}</td><td class="muted">{esc(r["team"])}</td>'
        f'<td class="num">{r["goals"]}</td><td class="num">{r["assists"]}</td><td class="num"><b>{p}</b></td>'
        f'<td class="num">{s}</td><td class="num muted">{int(r["pp_toi_s"] or 0) // 60}:{int(r["pp_toi_s"] or 0) % 60:02d}</td></tr>'
        for p, s, r in top_rows[:15])
    perf_tbl = ('<div class="tbl"><h4>Big nights (2+ pts or 6+ shots)</h4><table><thead><tr><th>Player</th><th></th>'
                '<th class="num">G</th><th class="num">A</th><th class="num">P</th><th class="num">SOG</th><th class="num">PP TOI</th>'
                f'</tr></thead><tbody>{perf}</tbody></table></div>') if top_rows else ""
    return '<div class="cols">' + "".join(blocks) + "</div>" + perf_tbl


def health(date: str) -> str:
    runs = last_runs()
    items = []
    for job in ("morning", "evening", "overnight", "backfill"):
        r = runs.get(job)
        items.append(f'<li><b>{job}</b>: {et(r["utc"], "%a %-I:%M %p") if r else "never"}</li>')
    n_box = len(list(results.BOX_DIR.glob("*.csv"))) if results.BOX_DIR.exists() else 0
    n_snap = len(list((lineups.LINEUP_DIR).glob("*/*/*.json"))) if lineups.LINEUP_DIR.exists() else 0
    items.append(f"<li>{n_box} games with boxscores · {n_snap} lineup snapshots on file</li>")
    return "<ul class='small'>" + "".join(items) + "</ul>"


# ----------------------------------------------------------------------------- page
CSS = """
:root{--bg:#fff;--fg:#111;--muted:#6b7280;--line:#e5e7eb;--card:#f8fafc;--ok:#15803d;--warn:#b45309;--bad:#b91c1c;--acc:#1d4ed8}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--fg:#e5e7eb;--muted:#9aa3b2;--line:#262a33;--card:#161a21;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--acc:#93c5fd}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}h1{font-size:22px;margin:0 0 2px}h2{font-size:17px;margin:28px 0 10px;border-bottom:1px solid var(--line);padding-bottom:4px}
h3{font-size:15px;margin:0 0 6px}h4{font-size:13px;margin:0 0 6px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.muted{color:var(--muted)}.small{font-size:12.5px}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.game{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.gamehead{font-size:16px;margin-bottom:8px}.time{display:inline-block;min-width:72px;color:var(--acc);font-weight:600}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}.cols3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
@media(max-width:720px){.cols,.cols3{grid-template-columns:1fr}}
.line{margin:2px 0}.lbl{display:inline-block;min-width:36px;color:var(--muted);font-size:12px;font-weight:600}
.gtd{text-decoration:underline dotted var(--warn)}.ml{font-weight:400;color:var(--muted);font-size:13px}
.badge{display:inline-block;font-size:11px;font-weight:600;padding:1px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.badge.ok{color:var(--ok);border-color:var(--ok)}.badge.warn{color:var(--warn);border-color:var(--warn)}.badge.bad{color:var(--bad);border-color:var(--bad)}
.goalie{margin:0 0 8px}table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:3px 6px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--muted);font-weight:600;font-size:12px}.num{text-align:right;font-variant-numeric:tabular-nums}.pp{font-size:10px;color:var(--acc);font-weight:700;margin-left:4px}
.tbl{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.result{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
details summary{cursor:pointer;color:var(--acc)}ul{margin:4px 0 0 18px;padding:0}footer{margin:30px 0 10px;color:var(--muted);font-size:12px}
"""


def build(date: str | None = None) -> Path:
    date = date or now_utc().astimezone(ET).strftime("%Y-%m-%d")
    yday = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    games = sorted(schedule.load_day(date), key=lambda g: g["start_utc"])
    gb = goalie_board(date)
    now_et = now_utc().astimezone(ET)
    pretty = datetime.strptime(date, "%Y-%m-%d").strftime("%A, %B %-d")

    slate = "".join(render_game(g, date, gb) for g in games) if games else '<p class="muted">No games today.</p>'
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NHL Props — {esc(pretty)}</title><style>{CSS}</style></head><body><main>
<h1>NHL Props · {esc(pretty)}</h1>
<div class="muted small">Updated {now_et.strftime("%-I:%M %p ET")} · {len(games)} game{"s" if len(games) != 1 else ""} · goalie badges: Confirmed / Unconfirmed from Daily Faceoff · dotted name = game-time decision</div>
<h2>Tonight</h2>{slate}
<h2>Hot list — players on tonight's slate</h2>{hot_list(games, date)}
<h2>Last night ({esc(datetime.strptime(yday, "%Y-%m-%d").strftime("%a %b %-d"))})</h2>{last_night(yday)}
<h2>Data health</h2>{health(date)}
<footer>Sources: Daily Faceoff (projected lines, goalies, rolling stats), NHL API (schedule, boxscores, TOI, shifts). Generated by nhl-props.</footer>
</main></body></html>"""
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / "index.html"
    out.write_text(page)
    log.info("report written: %s (%d games)", out, len(games))
    return out


if __name__ == "__main__":
    build()

"""Daily one-pager, written to docs/index.html (served by GitHub Pages) after every job.

Sections: tonight's slate (odds, goalies, lines with jersey numbers and PP1/PP2 tags, PP stacks, injuries,
lineup changes), hot list (L5/L10 from THIS season's boxscores only), last night's results + projection
check, data health.
"""
from __future__ import annotations

import csv
import html
import json
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from . import analysis, lineups, results, schedule
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


def american(v) -> str:
    """+120 / -142 with the sign always shown."""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return "—"
    return f"+{n}" if n > 0 else str(n)


def jersey_of(snap: dict | None) -> dict[str, int]:
    return {p["player"]: p.get("jersey") for p in (snap or {}).get("players", []) if p.get("jersey")}


def pp_units(snap: dict | None) -> dict[str, int]:
    """player -> 1 or 2 (their best PP unit)."""
    out: dict[str, int] = {}
    for r in (snap or {}).get("lines", []):
        if r["section"] == "PP" and r.get("unit_no") in (1, 2):
            out[r["player"]] = min(out.get(r["player"], 9), r["unit_no"])
    return out


def pp_tag(no: int | None) -> str:
    return f' <span class="pp pp{no}">PP{no}</span>' if no in (1, 2) else ""


def name_tag(player: str, jersey: dict[str, int], pp: dict[str, int] | None = None, gtd: bool = False,
             extra: dict[str, str] | None = None) -> str:
    j = jersey.get(player)
    cls = ' class="gtd"' if gtd else ""
    return (f'<span{cls}>{esc(player)}</span>' + (f' <span class="num-j">({j})</span>' if j else "")
            + ((extra or {}).get(player, "")) + (pp_tag(pp.get(player)) if pp else ""))


def extras_for(team: str, cur: dict | None, date: str, logs) -> dict[str, str]:
    """Per-player suffix html: promotion/demotion arrows vs. last game day, G/A bias tag."""
    out: dict[str, str] = {}
    prev = analysis.latest_snapshot_before(team, date)
    mv = analysis.movement(cur, prev)
    for pl, m in mv.items():
        bits = []
        if m.get("new"):
            bits.append('<span class="mv new" title="not in last game\'s lineup">NEW</span>')
        if m.get("ev") == 1:
            bits.append('<span class="mv up" title="moved up a line">&#9650;</span>')
        elif m.get("ev") == -1:
            bits.append('<span class="mv dn" title="moved down a line">&#9660;</span>')
        if m.get("pp") == 1:
            bits.append('<span class="mv up" title="promoted on the PP">PP&#9650;</span>')
        elif m.get("pp") == -1:
            bits.append('<span class="mv dn" title="demoted on the PP">PP&#9660;</span>')
        out[pl] = " " + " ".join(bits)
    for pl in {r["player"] for r in (cur or {}).get("lines", [])}:
        b = analysis.bias(logs.get((team, norm(pl)), []))
        if b:
            out[pl] = out.get(pl, "") + f' <span class="bias b{b}" title="{"goal" if b == "G" else "assist"}-biased (L10)">({b})</span>'
    return out


def season_logs() -> dict[tuple[str, str], list[dict]]:
    """(team, normalized full name) -> this season's game rows from our boxscores, oldest first."""
    logs: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in sorted(results.BOX_DIR.glob("*.csv")) if results.BOX_DIR.exists() else []:
        for r in read_csv(f):
            if r.get("pos") == "G":
                continue
            key = (r["team"], norm(r.get("full_name") or r["player"]))
            logs[key].append(r)
    for rows in logs.values():
        rows.sort(key=lambda r: (r.get("date") or "", r.get("game_id") or ""))
    return logs


def rolling(rows: list[dict], n: int) -> dict:
    last = rows[-n:]
    gp = len(last)
    if not gp:
        return {}
    tot = lambda k: sum(int(r.get(k) or 0) for r in last)  # noqa: E731
    return {"gp": gp, "p": tot("points"), "g": tot("goals"), "a": tot("assists"), "sog": tot("sog"),
            "ppg": tot("points") / gp, "gpg": tot("goals") / gp, "spg": tot("sog") / gp,
            "toi": sum(int(r.get("toi_s") or 0) for r in last) / gp / 60,
            "pp_toi": sum(int(r.get("pp_toi_s") or 0) for r in last) / gp / 60}


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


def pp_stacks(snap: dict, team: str = "", pairs: dict | None = None) -> list[str]:
    """EV linemates who also share a PP unit — the correlated-parlay signal. Appends how often the pair
    has both scored in games they actually played together this season (from shift overlap)."""
    out = []
    pairs = pairs or {}

    def together(a: str, b: str) -> str:
        ps = pairs.get((team,) + tuple(sorted((norm(a), norm(b)))))
        if not ps or not ps["n"]:
            return ""
        return f' <span class="muted small">both {ps["both"]}/{ps["n"]}, either {ps["either"]}/{ps["n"]}</span>'
    pp_members: dict[int, set[str]] = {1: {r["player"] for r in unit(snap, "PP", 1)},
                                       2: {r["player"] for r in unit(snap, "PP", 2)}}
    for sec, label in (("F", "L"), ("D", "D")):
        for no in (1, 2, 3, 4):
            members = [r["player"] for r in unit(snap, sec, no)]
            if len(members) < 2:
                continue
            for ppno, pset in pp_members.items():
                shared = [m for m in members if m in pset]
                if len(shared) >= 2:
                    corr = together(shared[0], shared[1]) if len(shared) == 2 else ""
                    out.append(f'<span class="pp pp{ppno}">PP{ppno}</span> {label}{no}: ' + ", ".join(esc(x) for x in shared) + corr)
    return out


def render_game(g: dict, date: str, gb: dict, logs=None, pairs=None) -> str:
    logs = logs or {}
    pairs = pairs or {}
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
        jersey, pp = jersey_of(cur), pp_units(cur)
        extra = extras_for(team, cur, date, logs)
        parts = [f'<div class="team"><h3>{esc(team)} <span class="ml">{esc(american(gl.get("moneyline")))}</span></h3>']
        parts.append(
            f'<div class="goalie"><span class="badge {badge}">{esc(status)}</span> <b>{esc(gl.get("goalie") or "no goalie listed")}</b>'
            + (f' <span class="muted">— {esc(gl["news"][:140])}</span>' if gl.get("news") else "") + "</div>")
        if cur:
            def line(sec, no, label, tags=True):
                ps = unit(cur, sec, no)
                if not ps:
                    return ""
                names = " – ".join(name_tag(p["player"], jersey, pp if tags else None, p.get("gtd"), extra if tags else None) for p in ps)
                return f'<div class="line"><span class="lbl">{label}</span>{names}</div>'
            parts += [line("F", 1, "L1"), line("F", 2, "L2"), line("F", 3, "L3"), line("F", 4, "L4"),
                      line("D", 1, "D1"), line("D", 2, "D2"),
                      line("PP", 1, '<span class="pp pp1">PP1</span>', tags=False),
                      line("PP", 2, '<span class="pp pp2">PP2</span>', tags=False)]
            stacks = pp_stacks(cur, team, pairs)
            if stacks:
                parts.append('<div class="line stack"><span class="lbl">STACK</span>' + " · ".join(stacks) + "</div>")
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
    away_ml = american(gb["latest"].get(g["away"], {}).get("moneyline"))
    home_ml = american(gb["latest"].get(g["home"], {}).get("moneyline"))
    total = g.get("total")  # filled once the odds feed exists
    head = (f'<b>{esc(g["away"])}</b> <span class="ml">({away_ml})</span> @ <b>{esc(g["home"])}</b> <span class="ml">({home_ml})</span>'
            f' <span class="muted">· O/U {esc(total) if total else "—"}</span>')
    return (f'<section class="game"><div class="gamehead"><span class="time">{esc(start)}</span> {head}</div>'
            f'<div class="cols">{"".join(cols)}</div></section>')


def hot_list(games: list[dict], date: str) -> str:
    logs = analysis.player_logs(analysis.all_boxscores())
    rows = []
    for g in games:
        for team in (g["away"], g["home"]):
            snaps = team_snapshots(team, date)
            if not snaps:
                continue
            cur = snaps[-1]
            pp, jersey = pp_units(cur), jersey_of(cur)
            line_of = {r["player"]: r.get("unit_no") for r in cur.get("lines", []) if r["section"] in ("F", "D")}
            for p in cur.get("players", []):
                if p.get("pos") in ("G", None):
                    continue
                rowsp = logs.get((team, norm(p["player"])), [])
                if not rowsp:
                    continue
                rows.append({"team": team, "player": p["player"], "pos": p.get("pos"), "line": line_of.get(p["player"]),
                             "pp": pp.get(p["player"]), "jersey": jersey.get(p["player"]), "bias": analysis.bias(rowsp),
                             "l5": rolling(rowsp, 5), "l10": rolling(rowsp, 10)})
    if not rows:
        return '<p class="muted">No games played yet this season for tonight\'s teams.</p>'

    def jtag(j):
        return f' <span class="num-j">({j})</span>' if j else ""

    def btag(b):
        return f' <span class="bias b{b}">({b})</span>' if b else ""

    def table(window, title, key, fmt, n=12):
        pool = [r for r in rows if r[window]]
        top = sorted(pool, key=lambda r: (r[window][key], r[window]["gp"]), reverse=True)[:n]
        trs = "".join(
            f'<tr><td>{esc(r["player"])}{jtag(r["jersey"])}{btag(r["bias"])}{pp_tag(r["pp"])}</td>'
            f'<td class="muted">{esc(r["team"])} {esc(r["pos"] or "")}{((" D" if (r["pos"] or "") in ("LD", "RD", "D") else " L") + str(r["line"])) if r["line"] else ""}</td>'
            f'<td class="num">{fmt(r[window][key])}</td><td class="num muted">{r[window]["gp"]}</td>'
            f'<td class="num muted">{r[window]["toi"]:.1f}</td></tr>' for r in top)
        return (f'<div class="tbl"><h4>{title}</h4><table><thead><tr><th>Player</th><th></th>'
                f'<th class="num">{title.split(" ")[0]}</th><th class="num">GP</th><th class="num">TOI</th></tr></thead><tbody>{trs}</tbody></table></div>')

    blocks = []
    for window, label in (("l5", "Last 5"), ("l10", "Last 10")):
        blocks.append(f'<h3 class="sub">{label} <span class="muted small">(this season only; GP = games in window)</span></h3><div class="cols3">'
                      + table(window, "Points / game", "ppg", lambda v: f"{v:.2f}")
                      + table(window, "Shots / game", "spg", lambda v: f"{v:.1f}")
                      + table(window, "Goals / game", "gpg", lambda v: f"{v:.2f}")
                      + "</div>")
    return "".join(blocks)


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


def best_bets_section(games: list[dict], date: str, logs, pairs) -> str:
    boxes = analysis.all_boxscores()
    season, l5 = analysis.team_rates(boxes), analysis.team_rates(boxes, 5)
    bets = analysis.best_bets(games, date, logs, season, l5, pairs)
    if not bets:
        return '<p class="muted">Nothing to rank yet — needs this-season games for tonight\'s teams.</p>'
    trs = []
    for b in bets[:15]:
        why = []
        if b["pp"] == 1:
            why.append('<span class="pp pp1">PP1</span>')
        elif b["pp"] == 2:
            why.append('<span class="pp pp2">PP2</span>')
        if b["partners"]:
            why.append("stack w/ " + ", ".join(esc(x) for x in b["partners"]))
        if b["opp_ga_rk"]:
            why.append(f'opp {esc(b["opp"])} allows {b["opp_ga"]:.1f} G ({b["opp_ga_rk"]}{_ord(b["opp_ga_rk"])} most) / {b["opp_sa"]:.0f} SOG ({b["opp_sa_rk"]}{_ord(b["opp_sa_rk"])} most)')
        if b["pair_lines"]:
            why.append("; ".join(esc(x) for x in b["pair_lines"]))
        l5 = b["l5"]
        jt = f' <span class="num-j">({b["jersey"]})</span>' if b["jersey"] else ""
        bt = f' <span class="bias b{b["bias"]}">({b["bias"]})</span>' if b["bias"] else ""
        is_d = (b["pos"] or "") in ("LD", "RD", "D")
        slot = (("D" if is_d else "L") + str(b["ev"])) if b["ev"] else ""
        trs.append(
            f'<tr><td>{esc(b["player"])}{jt}{bt}</td>'
            f'<td class="muted">{esc(b["team"])} {esc(b["pos"] or "")} {slot}</td>'
            f'<td class="num">{l5["ppg"]:.2f}</td><td class="num">{l5["pt_games"]}/{l5["gp"]}</td><td class="num">{l5["spg"]:.1f}</td>'
            f'<td class="num">{b["score"]:.2f}</td><td class="small">{" · ".join(why)}</td></tr>')
    return ('<div class="tbl"><table><thead><tr><th>Player</th><th></th><th class="num">L5 P/G</th><th class="num">pt games</th>'
            '<th class="num">L5 SOG/G</th><th class="num">score</th><th>why</th></tr></thead><tbody>' + "".join(trs) + "</tbody></table></div>"
            '<p class="muted small">Score = 2×L5 points/game + 0.15×L5 shots/game + PP unit (0.6/0.25) + 0.5 if a same-line-and-same-PP partner exists '
            '+ up to 1.0 for opponent weakness (GA and SOG allowed rank) + 0.2 for L1. This season only; discount small samples.</p>')


def pp1_stacks_section(games: list[dict], date: str, logs, pairs) -> str:
    """The nightly headline: players who share an EV line AND are both on PP1, per game.
    Shows each player's L5 (this season) and how often each pair has both scored when actually together."""
    from itertools import combinations
    season = analysis.team_rates(analysis.all_boxscores())
    blocks = []
    for g in games:
        teams_html = []
        for side, opp_side in (("away", "home"), ("home", "away")):
            team, opp = g[side], g[opp_side]
            snaps = team_snapshots(team, date)
            cur = snaps[-1] if snaps else None
            if not cur:
                continue
            jersey, extra = jersey_of(cur), extras_for(team, cur, date, logs)
            pp1 = {r["player"] for r in unit(cur, "PP", 1)}
            opp_r = season.get(opp) or {}
            opp_txt = (f'vs {esc(opp)} — allows {opp_r["ga"]:.1f} G/gm ({opp_r["ga_rk"]}{_ord(opp_r["ga_rk"])} most), '
                       f'{opp_r["sa"]:.0f} SOG/gm ({opp_r["sa_rk"]}{_ord(opp_r["sa_rk"])} most)') if opp_r else f"vs {esc(opp)}"
            groups = []
            for sec, label in (("F", "L"), ("D", "D")):
                for no in (1, 2, 3, 4):
                    members = [r["player"] for r in unit(cur, sec, no)]
                    shared = [m for m in members if m in pp1]
                    if len(shared) < 2:
                        continue
                    names = []
                    for m in shared:
                        l5 = analysis.rolling(logs.get((team, norm(m)), []), 5)
                        st = (f' <span class="muted small">{l5["ppg"]:.2f} P/G, {l5["pt_games"]}/{l5["gp"]} pt games</span>'
                              if l5 else ' <span class="muted small">no games</span>')
                        names.append(name_tag(m, jersey, None, False, extra) + st)
                    corr = []
                    for a, b in combinations(shared, 2):
                        ps = pairs.get((team,) + tuple(sorted((norm(a), norm(b)))))
                        short = lambda x: esc(x.split()[-1])  # noqa: E731
                        if ps and ps["n"]:
                            corr.append(f'{short(a)}+{short(b)}: both {ps["both"]}/{ps["n"]}, either {ps["either"]}/{ps["n"]}')
                        else:
                            corr.append(f"{short(a)}+{short(b)}: no games together yet")
                    groups.append(f'<div class="line"><span class="lbl">{label}{no}</span>' + "<br>".join(names)
                                  + f'<div class="muted small">{" · ".join(corr)}</div></div>')
            if groups:
                teams_html.append(f'<div class="team"><h3>{esc(team)} <span class="muted small">{opp_txt}</span></h3>' + "".join(groups) + "</div>")
            else:
                teams_html.append(f'<div class="team"><h3>{esc(team)}</h3><div class="muted small">no line with 2+ PP1 guys</div></div>')
        if teams_html:
            blocks.append(f'<section class="game"><div class="gamehead"><span class="time">{esc(et(g["start_utc"]))}</span> '
                          f'<b>{esc(g["away"])}</b> @ <b>{esc(g["home"])}</b></div><div class="cols">{"".join(teams_html)}</div></section>')
    if not blocks:
        return '<p class="muted">No lineup snapshots yet for tonight.</p>'
    return ("".join(blocks) + '<p class="muted small">Same EV line and both on PP1 (Daily Faceoff projection, latest snapshot). '
            '"both x/n" = games this season they were actually linemates (shift overlap) in which both got a point.</p>')


def _ord(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def team_rates_section(games: list[dict]) -> str:
    boxes = analysis.all_boxscores()
    season, l5 = analysis.team_rates(boxes), analysis.team_rates(boxes, 5)
    if not season:
        return '<p class="muted">No games yet.</p>'
    tonight = {t for g in games for t in (g["away"], g["home"])}

    def table(title, key, desc):
        order = sorted(season, key=lambda t: season[t][key], reverse=True)
        trs = "".join(
            f'<tr class="{"hl" if t in tonight else ""}"><td>{season[t][key + "_rk"]}</td><td><b>{esc(t)}</b></td>'
            f'<td class="num">{season[t][key]:.2f}</td><td class="num muted">{l5.get(t, {}).get(key, 0):.2f}</td><td class="num muted">{season[t]["gp"]}</td></tr>'
            for t in order)
        return (f'<div class="tbl"><h4>{title}</h4><div class="muted small">{desc}</div><table><thead><tr><th>#</th><th>Team</th>'
                f'<th class="num">season</th><th class="num">L5</th><th class="num">GP</th></tr></thead><tbody>{trs}</tbody></table></div>')

    return ('<div class="cols4">'
            + table("Goals for / game", "gf", "who scores")
            + table("Shots for / game", "sf", "who shoots")
            + table("Goals allowed / game", "ga", "weakest defenses first")
            + table("Shots allowed / game", "sa", "most shots given up first")
            + '</div><p class="muted small">Highlighted rows are on tonight\'s slate.</p>')


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
main{max-width:1680px;margin:0 auto;padding:16px}h1{font-size:22px;margin:0 0 2px}h2{font-size:17px;margin:28px 0 10px;border-bottom:1px solid var(--line);padding-bottom:4px}
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
th{color:var(--muted);font-weight:600;font-size:12px}.num{text-align:right;font-variant-numeric:tabular-nums}.pp{font-size:10px;font-weight:700;margin-left:4px;padding:0 4px;border-radius:4px;border:1px solid}
.pp1{color:var(--ok);border-color:var(--ok)}.pp2{color:var(--warn);border-color:var(--warn)}
.num-j{color:var(--muted);font-size:12px}
.mv{font-size:11px;font-weight:700}.mv.up{color:var(--ok)}.mv.dn{color:var(--bad)}.mv.new{color:var(--acc);font-size:10px}
.bias{font-size:11px;font-weight:700}.bias.bG{color:var(--ok)}.bias.bA{color:var(--acc)}
.cols4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}tr.hl td{background:rgba(147,197,253,.08)}.stack{margin-top:4px}.sub{margin:14px 0 6px;font-size:14px}
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

    logs = analysis.player_logs(analysis.all_boxscores())
    pairs = analysis.pair_stats(analysis.all_boxscores())
    slate = "".join(render_game(g, date, gb, logs, pairs) for g in games) if games else '<p class="muted">No games today.</p>'
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NHL Props — {esc(pretty)}</title><style>{CSS}</style></head><body><main>
<h1>NHL Props · {esc(pretty)}</h1>
<div class="muted small">Updated {now_et.strftime("%-I:%M %p ET")} · {len(games)} game{"s" if len(games) != 1 else ""} · <span class="pp pp1">PP1</span> <span class="pp pp2">PP2</span> · <span class="mv up">&#9650;</span>/<span class="mv dn">&#9660;</span> moved up/down vs. last game · <span class="bias bG">(G)</span> goal-biased, <span class="bias bA">(A)</span> assist-biased (L10) · dotted name = game-time decision</div>
<h2>Same line + PP1 — tonight's stacks</h2>{pp1_stacks_section(games, date, logs, pairs)}
<h2>Best bets on the slate</h2>{best_bets_section(games, date, logs, pairs)}
<h2>Tonight</h2>{slate}
<h2>Hot list — players on tonight's slate</h2>{hot_list(games, date)}
<h2>Team rates</h2>{team_rates_section(games)}
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

"""Slate De-Brief — the daily front page. Dark, one game card per game,
ranked player cards with why-bullets, pair-with meters, a 2+ table, and a pass list.
Renders from model.build_slate() output; also writes the JSON next to the page."""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

from . import model, report, results

DOCS = results.DATA.parent / "docs"


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def ml(v) -> str:
    try:
        v = int(float(v))
    except (TypeError, ValueError):
        return "—"
    return f"+{v}" if v > 0 else str(v)


def pct(p: float) -> str:
    return f"{round(p * 100)}%"


def tag(text: str, cls: str) -> str:
    return f'<span class="tag {cls}">{esc(text)}</span>'


def pp_tag(u) -> str:
    return tag("PP1", "pp1") if u == 1 else (tag("PP2", "pp2") if u == 2 else "")


def bias_tag(b) -> str:
    return tag("G", "bias-g") if b == "G" else (tag("A", "bias-a") if b == "A" else "")


def move_tag(mv: dict) -> str:
    if mv.get("new"):
        return tag("NEW", "new")
    out = []
    if mv.get("ev", 0) < 0:
        out.append(tag("▲ line", "up"))
    elif mv.get("ev", 0) > 0:
        out.append(tag("▼ line", "down"))
    if mv.get("pp", 0) < 0:
        out.append(tag("PP ▲", "up"))
    elif mv.get("pp", 0) > 0:
        out.append(tag("PP ▼", "down"))
    return "".join(out)


def meter(both: int, n: int, p1: float, p2: float) -> str:
    """both-scored meter: observed rate vs. independence product."""
    if not n:
        return '<span class="muted">no games together yet</span>'
    obs = both / n
    ind = p1 * p2
    return (f'<div class="meter"><div class="bar"><i style="width:{round(obs*100)}%"></i>'
            f'<b style="left:{round(ind*100)}%" title="independent {pct(ind)}"></b></div>'
            f'<span>{both}/{n} both · ind {pct(ind)}</span></div>')


def player_card(p: dict, team: dict, opp: dict, rank: int) -> str:
    bullets = "".join(f"<li>{esc(b)}</li>" for b in model.why(p, team, opp))
    ha = "HOME" if p["home"] else "AWAY"
    gtd = tag("GTD", "gtd") if p.get("gtd") else ""
    return f"""
<article class="card">
  <div class="rank">{rank}</div>
  <div class="who">
    <div class="name">{esc(p['name'])} <span class="jersey">#{esc(p['jersey'] or '')}</span> {gtd}</div>
    <div class="meta"><b>{esc(p['team'])}</b> {ha} · L{p['line']} {pp_tag(p['pp'])} {bias_tag(p['bias'])} {move_tag(p['move'])}</div>
  </div>
  <div class="odds">
    <div class="big">{pct(p['p'])}</div>
    <div class="fair">fair <b>{esc(p['fair'])}</b></div>
    <div class="min">need <b>{esc(p['min'])}</b> or better</div>
  </div>
  <ul class="why">{bullets}</ul>
  <div class="intel"><span class="lbl">Intel</span><span class="muted">—</span></div>
</article>"""


def pairs_table(players: list[dict], index: dict[str, dict]) -> str:
    rows = []
    seen = set()
    for p in players:
        for q in p["partners"]:
            key = tuple(sorted((p["name"], q["name"])))
            if key in seen or q["n"] < 1:
                continue
            seen.add(key)
            o = index.get(q["name"])
            if not o:
                continue
            ind = p["p"] * o["p"]
            obs = q["both"] / q["n"]
            blend = (obs * q["n"] + ind * 6) / (q["n"] + 6)
            read = "new pair" if q["n"] < 6 else ("correlated" if obs > ind * 1.15 else ("negative" if obs < ind * 0.8 else "independent"))
            rows.append((blend, f"""<tr>
<td>{esc(p['name'].split()[-1])} + {esc(q['name'].split()[-1])} <span class="muted">{esc(p['team'])} L{p['line']}</span> {pp_tag(p['pp']) if p['pp']==q.get('pp') else ''}</td>
<td>{meter(q['both'], q['n'], p['p'], o['p'])}</td>
<td class="num">{pct(blend)}</td><td class="num">{esc(model.american(blend))}</td>
<td class="num">{esc(model.american(blend/model.EDGE))}</td>
<td><span class="read {read.split()[0]}">{read}</span></td></tr>"""))
    rows.sort(key=lambda r: -r[0])
    if not rows:
        return '<p class="muted">No pair data yet.</p>'
    return ("<table class=\"tbl\"><thead><tr><th>Pair (both score a point)</th><th>Both / games together</th>"
            "<th>Our %</th><th>Fair</th><th>Need</th><th>Read</th></tr></thead><tbody>"
            + "".join(r for _, r in rows[:8]) + "</tbody></table>")


def two_plus_table(players: list[dict]) -> str:
    rows = [p for p in players if p["p2"] >= 0.15]
    if not rows:
        return '<p class="muted">Nobody clears 15% for 2+ tonight.</p>'
    body = "".join(f"""<tr><td>{esc(p['name'])} <span class="muted">{esc(p['team'])} L{p['line']}</span> {pp_tag(p['pp'])}</td>
<td class="num">{p['two_games']}/{p['gp']}</td><td class="num">{p['pp_toi']}</td>
<td class="num">{pct(p['p2'])}</td><td class="num">{esc(p['fair2'])}</td><td class="num">{esc(p['min2'])}</td></tr>"""
                   for p in sorted(rows, key=lambda x: -x["p2"]))
    return ("<table class=\"tbl\"><thead><tr><th>2+ points (1.5 line)</th><th>2+ games</th><th>PP min</th>"
            "<th>Our %</th><th>Fair</th><th>Need</th></tr></thead><tbody>" + body + "</tbody></table>")


def team_header(t: dict) -> str:
    st = t.get("goalie_status") or ""
    cls = "ok" if st == "Confirmed" else ("likely" if st in ("Likely", "Expected") else "")
    stale = tag("STALE LINEUP", "down") if t.get("lineup_stale") else ""
    b2b = tag("B2B", "b2b") if t.get("b2b") else ""
    out = ", ".join(f"{o['player']} ({o['status']})" for o in t["out"][:5]) or "—"
    note = f'<div class="gnote">{esc(t["goalie_news"])} <span class="muted">— {esc(t["goalie_source"])}</span></div>' if t.get("goalie_news") else ""
    return f"""
<div class="team">
  <div class="tname">{esc(t['team'])} <span class="muted">{'home' if t['home'] else 'away'}</span> {b2b} {stale}</div>
  <div class="goalie {cls}">🥅 {esc(t['goalie'] or 'TBD')} <span class="muted">{esc(st or 'unconfirmed')} · {esc(t['sv'])} sv% · {esc(t['gaa'])} GAA</span></div>
  {note}
  <div class="rates">
    <span>GF {t['gf']:.2f} <i>#{t['gf_rk']}</i></span>
    <span>GA {t['ga']:.2f} <i>#{t['ga_rk']}</i></span>
    <span>SA {t['sa']:.1f} <i>#{t['sa_rk']}</i></span>
    <span>PPGA {t['ppga']:.2f} <i>#{t['ppga_rk']}</i></span>
    <span class="muted">L5: {t['l5_gf']:.1f} GF / {t['l5_ga']:.1f} GA</span>
  </div>
  <div class="lines">{''.join(f'<span><i>L{no}</i> {esc(" – ".join(x.split()[-1] for x in ps))}</span>' for no, ps in t['lines'].items())}
    <span class="pp1row"><i>PP1</i> {esc(" · ".join(x.split()[-1] for x in t['pp1']))}</span></div>
  <div class="out"><i>OUT</i> {esc(out)}</div>
  <div class="asof muted">lineup as of {esc(report.et(t['lineup_as_of'], '%-I:%M %p %b %-d') if t['lineup_as_of'] else '—')}</div>
</div>"""


def game_section(g: dict) -> str:
    a, h = g["teams"]["away"], g["teams"]["home"]
    players = sorted(a["players"] + h["players"], key=lambda p: -p["p"])
    index = {p["name"]: p for p in players}
    top = [p for p in players if p["p"] >= 0.45][:5] or players[:3]
    passes = [p for p in players if p not in top and p["line"] <= 2]
    cards = "".join(player_card(p, a if p["team"] == a["team"] else h, h if p["team"] == a["team"] else a, i + 1)
                    for i, p in enumerate(top))
    pass_rows = "".join(f"<li><b>{esc(p['name'].split()[-1])}</b> <span class=\"muted\">{esc(p['team'])} L{p['line']}</span> {pct(p['p'])} · fair {esc(p['fair'])}</li>" for p in passes[:10])
    return f"""
<section class="game" id="g{g['game_id']}">
  <header class="ghead">
    <h2>{esc(a['team'])} <span class="ml">({ml(a['ml'])})</span> <span class="at">@</span> {esc(h['team'])} <span class="ml">({ml(h['ml'])})</span></h2>
    <div class="when">{esc(g['start_et'])} ET · {esc(g['venue'])}</div>
  </header>
  <div class="teams">{team_header(a)}{team_header(h)}</div>
  <h3>The guys that matter</h3>
  <div class="cards">{cards}</div>
  <h3>Pair with</h3>
  {pairs_table(players, index)}
  <h3>2+ points</h3>
  {two_plus_table(players)}
  <h3>Pass / re-check at puck drop</h3>
  <ul class="pass">{pass_rows}</ul>
</section>"""


CSS = """
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2330;--line:#2a3442;--fg:#e6edf3;--muted:#8b98a8;
--green:#3fb950;--yellow:#d29922;--red:#f85149;--blue:#58a6ff;--purple:#bc8cff;--orange:#f0883e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,"Segoe UI",Inter,Roboto,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:24px 28px 80px}
h1{font-size:30px;margin:0;letter-spacing:-.5px}h1 small{color:var(--muted);font-weight:400;font-size:16px;margin-left:12px}
.sub{color:var(--muted);margin:4px 0 22px}
.game{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin-bottom:28px}
.ghead{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:16px}
.ghead h2{margin:0;font-size:26px}.ml{color:var(--muted);font-weight:400;font-size:18px}.at{color:var(--muted);font-weight:300;margin:0 6px}.when{color:var(--muted)}
.teams{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:8px}
.team{background:var(--panel2);border-radius:10px;padding:14px 16px;font-size:14px}
.tname{font-size:20px;font-weight:700;margin-bottom:6px}
.goalie{margin:4px 0}.goalie.ok{color:var(--green)}.goalie.likely{color:var(--yellow)}
.gnote{font-size:13px;color:var(--fg);opacity:.85;margin:2px 0 6px}
.rates{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0}.rates i{font-style:normal;color:var(--muted);font-size:12px}
.lines{display:flex;flex-direction:column;gap:2px;margin:8px 0;font-size:13px}.lines i{font-style:normal;color:var(--muted);display:inline-block;width:34px}
.pp1row{color:var(--green)}.out{font-size:13px;color:var(--red)}.out i{font-style:normal;color:var(--muted);margin-right:6px}
.asof{font-size:12px;margin-top:6px}
h3{margin:22px 0 10px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:14px}
.card{position:relative;background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:16px 18px 14px 56px;display:grid;grid-template-columns:1fr auto;gap:4px 12px}
.card .rank{position:absolute;left:0;top:0;bottom:0;width:40px;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:800;color:var(--muted);border-right:1px solid var(--line)}
.card:first-child .rank{color:var(--green)}
.name{font-size:19px;font-weight:700}.jersey{color:var(--muted);font-weight:400;font-size:15px}
.meta{color:var(--muted);margin-top:2px}.meta b{color:var(--fg)}
.who{grid-column:1}.odds{grid-column:2;grid-row:1/3;text-align:right}.big{font-size:32px;font-weight:800;line-height:1}.fair,.min{font-size:13px;color:var(--muted)}.fair b{color:var(--fg)}.min b{color:var(--green)}
.why{grid-column:1/3;margin:8px 0 0;padding-left:18px;font-size:14px}.why li{margin:2px 0}
.intel{grid-column:1/3;margin-top:8px;padding-top:8px;border-top:1px dashed var(--line);font-size:13px}.lbl{color:var(--purple);font-weight:700;margin-right:8px;letter-spacing:.08em;font-size:11px}
.tag{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;margin-left:4px;vertical-align:middle;letter-spacing:.04em}
.pp1{background:#1a3d24;color:var(--green)}.pp2{background:#3d3416;color:var(--yellow)}
.bias-g{background:#3b2a13;color:var(--orange)}.bias-a{background:#15304d;color:var(--blue)}
.up{background:#1a3d24;color:var(--green)}.down{background:#4a1d1d;color:var(--red)}.new{background:#2d2250;color:var(--purple)}
.gtd{background:#4a1d1d;color:var(--red)}.b2b{background:#4a2a10;color:var(--orange)}
.tbl{width:100%;border-collapse:collapse;font-size:14px}.tbl th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;letter-spacing:.06em;padding:6px 10px;border-bottom:1px solid var(--line)}
.tbl td{padding:8px 10px;border-bottom:1px solid var(--line)}.num{text-align:right;font-variant-numeric:tabular-nums}
.meter{display:flex;align-items:center;gap:10px}.bar{position:relative;width:140px;height:8px;background:#0d1117;border-radius:4px;overflow:visible}
.bar i{display:block;height:100%;background:var(--green);border-radius:4px}.bar b{position:absolute;top:-3px;width:2px;height:14px;background:var(--yellow)}
.meter span{font-size:12px;color:var(--muted)}
.read{font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px}.read.correlated{background:#1a3d24;color:var(--green)}.read.negative{background:#4a1d1d;color:var(--red)}
.read.independent{background:#243041;color:var(--muted)}.read.new{background:#2d2250;color:var(--purple)}
.pass{columns:2;font-size:14px;padding-left:18px}.pass li{margin:2px 0}
.muted{color:var(--muted)}
.foot{color:var(--muted);font-size:13px;margin-top:30px;border-top:1px solid var(--line);padding-top:12px}
.foot a{color:var(--blue)}
"""


def build(date: str | None = None, only_games: list[int] | None = None) -> Path:
    date = date or datetime.now().strftime("%Y-%m-%d")
    slate = model.build_slate(date)
    games = slate["games"]
    if only_games:
        games = [g for g in games if g["game_id"] in only_games]
    gen = report.et(slate["generated_utc"], "%-I:%M %p %b %-d")
    body = "".join(game_section(g) for g in games)
    nice = datetime.fromisoformat(date).strftime("%A, %B %-d")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Slate De-Brief — {esc(date)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body><div class="wrap">
<h1>Slate De-Brief <small>{esc(nice)}</small></h1>
<div class="sub">Point props, this season only. % = our probability · fair = break-even price · need = the worst price worth taking (+6% expected return). Generated {esc(gen)} ET.</div>
{body}
<div class="foot">Method: hit rate shrunk to role prior (8 pseudo-games); opponent ±8% by GA rank; lopsided home/road split; back-to-back second leg ×0.86 (2+ ×0.78). Pair "ind" = independence product. <a href="detail.html">Full detail page →</a></div>
</div></body></html>"""
    DOCS.mkdir(exist_ok=True)
    out = DOCS / "index.html"
    out.write_text(page, encoding="utf-8")
    (DOCS / "slate.json").write_text(json.dumps(slate, indent=1), encoding="utf-8")
    return out

"""Market-implied numbers from book lines — vig removed first, always.

implied total : line + SIG * z(true P(over)), SIG = typical SD of an NHL game total
team xG       : split of the implied total that reproduces the vig-free P(home win) under
                independent Poisson scoring (ties go to the better team slightly more than half)
"""
from __future__ import annotations

import math
from statistics import NormalDist

SIG = 2.3          # SD of an NHL game total, goals
_ND = NormalDist()

# thresholds (JJ, 2026-11-12): implied game total and team xG, green / amber / red
TOTAL_GREEN, TOTAL_AMBER = 6.35, 6.2
XG_GREEN, XG_AMBER = 3.2, 2.9


def implied(american) -> float | None:
    try:
        a = int(american)
    except (TypeError, ValueError):
        return None
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def devig(a, b) -> tuple[float, float] | None:
    """Two-way market -> true probabilities summing to 1 (proportional / multiplicative method)."""
    pa, pb = implied(a), implied(b)
    if pa is None or pb is None:
        return None
    s = pa + pb
    return pa / s, pb / s


def american(p: float) -> str:
    p = min(max(p, 0.02), 0.98)
    return f"+{round(100 * (1 - p) / p)}" if p < 0.5 else f"-{round(100 * p / (1 - p))}"


def _pois(l: float, k: int) -> float:
    return math.exp(-l) * l ** k / math.factorial(k)


def p_home_win(la: float, lh: float) -> float:
    ph = pt = 0.0
    for a in range(0, 15):
        pa = _pois(la, a)
        for h in range(0, 15):
            p = pa * _pois(lh, h)
            if h > a:
                ph += p
            elif h == a:
                pt += p
    edge = min(max(0.5 + 0.15 * (lh - la), 0.35), 0.65)  # OT/SO leans to the better team
    return ph + pt * edge


def split_total(total: float, p_home: float) -> tuple[float, float]:
    lo, hi = 0.2, 0.8
    for _ in range(40):
        m = (lo + hi) / 2
        if p_home_win(total * (1 - m), total * m) < p_home:
            lo = m
        else:
            hi = m
    share = (lo + hi) / 2
    return total * (1 - share), total * share


def tone_total(t: float | None) -> str:
    if t is None:
        return ""
    return "good" if t >= TOTAL_GREEN else "mid" if t >= TOTAL_AMBER else "bad"


def tone_xg(x: float | None) -> str:
    if x is None:
        return ""
    return "good" if x >= XG_GREEN else "mid" if x >= XG_AMBER else "bad"


def analyze(book: dict) -> dict:
    """book: {total, over, under, ml_away, ml_home, status}. Returns the market block for a game."""
    out = {"status": book.get("status"), "line": book.get("total"), "over": book.get("over"), "under": book.get("under"),
           "vig_total": None, "p_over": None, "fair_over": None, "fair_under": None, "implied_total": None,
           "ml_away": book.get("ml_away"), "ml_home": book.get("ml_home"), "vig_ml": None, "p_home": None,
           "xg_away": None, "xg_home": None, "tone": "", "xg_tone_away": "", "xg_tone_home": ""}
    if book.get("total") is None:
        return out
    dv = devig(book.get("over"), book.get("under"))
    if dv:
        po, pu = dv
        io, iu = implied(book["over"]), implied(book["under"])
        out.update(vig_total=round(io + iu - 1, 4), p_over=round(po, 4), fair_over=american(po), fair_under=american(pu),
                   implied_total=round(book["total"] + SIG * _ND.inv_cdf(po), 2))
        out["tone"] = tone_total(out["implied_total"])
    dm = devig(book.get("ml_away"), book.get("ml_home"))
    if dm and out["implied_total"]:
        pa, ph = dm
        ia, ih = implied(book["ml_away"]), implied(book["ml_home"])
        xa, xh = split_total(out["implied_total"], ph)
        out.update(vig_ml=round(ia + ih - 1, 4), p_home=round(ph, 4), xg_away=round(xa, 2), xg_home=round(xh, 2),
                   xg_tone_away=tone_xg(xa), xg_tone_home=tone_xg(xh))
    return out


def smash(m: dict) -> dict:
    """v2 rule (JJ, 2026-11-12): market-implied total >= TOTAL_GREEN."""
    if m.get("status") == "in process" or m.get("line") is None:
        return {"flag": None, "label": "IN PROCESS", "why": "No line entered yet."}
    t = m.get("implied_total")
    if t is None:
        return {"flag": None, "label": "NO PRICE", "why": "Total known, prices missing."}
    ok = t >= TOTAL_GREEN
    return {"flag": ok, "label": "SMASH" if ok else "",
            "why": f"Implied total {t:.2f} (line {m['line']}, over {m['over']:+d} / under {m['under']:+d}, vig removed) · threshold {TOTAL_GREEN}"}

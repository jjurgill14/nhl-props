"""badge.py — render a team badge with any name/number from a designer template.

Template contract (per team SVG): the badge artwork, plus two live <text> elements we replace.
Until the designer delivers that, we strip the hand-outlined letter shapes from his sample and
treat the remaining artwork as the template.

Output is an SVG with the font embedded (base64 @font-face) so it renders anywhere, and the
stroke is generated from the text itself (paint-order: stroke) so it follows any name.
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

FONT_PATH = Path(__file__).parent / "src" / "NHLNewJersey.ttf"
VB = 1034.96
CX = VB / 2
NUM_SIZE, NUM_BASE, NUM_SPACING = 291.08, 373.44, 0.03
NAME_SIZE, NAME_BASE, NAME_SPACING, NAME_MAXW = 131.39, 565.37, 0.07, 905.0
NUM_STROKE, NAME_STROKE = 14.0, 7.0  # ≈ the designer's outlined offsets

_font = TTFont(FONT_PATH)
_cmap = _font.getBestCmap()
_hmtx = _font["hmtx"]
_upem = _font["head"].unitsPerEm


def text_width(s: str, size: float, spacing_em: float) -> float:
    adv = sum(_hmtx[_cmap.get(ord(c), _cmap.get(ord("?")))][0] for c in s) * size / _upem
    return adv + spacing_em * size * (len(s) - 1)


def font_css() -> str:
    b64 = base64.b64encode(FONT_PATH.read_bytes()).decode()
    return (f"@font-face{{font-family:'NHL New Jersey';src:url(data:font/ttf;base64,{b64}) format('truetype')}}")


def artwork_from_designer(svg: str) -> str:
    """Strip the sample's lettering (both the live text and the hand-outlined shapes) and keep the badge."""
    # drop every <text> element
    svg = re.sub(r"<text\b.*?</text>", "", svg, flags=re.S)
    # drop the two groups of outlined letter shapes: the number polygons (first <g> inside the badge
    # after the disc rect) and the name glyph group (the <g> of polygons/paths/rects before the name text)
    # Identify them as <g> elements whose children are ALL polygon/path/rect with class cls-2 and no clip.
    def is_letter_group(m):
        inner = m.group(1)
        kids = re.findall(r"<(polygon|path|rect)\b", inner)
        return bool(kids) and len(kids) >= 2 and "clip-path" not in inner and "<g" not in inner
    svg = re.sub(r"<g>\s*((?:\s*<(?:polygon|path|rect)\b[^>]*/>\s*)+)</g>", lambda m: "" if is_letter_group(m) else m.group(0), svg, flags=re.S)
    # remove now-empty wrapper groups
    for _ in range(3):
        svg = re.sub(r"<g>\s*</g>", "", svg)
    return svg


def render(template_svg: str, name: str, number: str, fill="#fff", stroke="#f4c250") -> str:
    name = name.upper()
    size = NAME_SIZE
    while text_width(name, size, NAME_SPACING) > NAME_MAXW and size > 40:
        size -= 2
    css = font_css()
    lettering = f"""
  <g id="lettering" font-family="'NHL New Jersey'" text-anchor="middle" fill="{fill}" stroke="{stroke}" stroke-linejoin="round" paint-order="stroke">
    <text id="number" x="{CX}" y="{NUM_BASE}" font-size="{NUM_SIZE}" letter-spacing="{NUM_SPACING * NUM_SIZE:.2f}" stroke-width="{NUM_STROKE}">{number}</text>
    <text id="name" x="{CX}" y="{NAME_BASE}" font-size="{size:.2f}" letter-spacing="{NAME_SPACING * size:.2f}" stroke-width="{NAME_STROKE}">{name}</text>
  </g>
"""
    out = template_svg.replace("<style>", f"<style>{css}", 1)
    # insert lettering before the final outer ring path (last <path ...> before </g></g></g></svg>)
    idx = out.rfind("<path")
    out = out[:idx] + lettering + out[idx:]
    return out


if __name__ == "__main__":
    tpl = artwork_from_designer(Path(sys.argv[1]).read_text())
    Path("out/template_BOS.svg").write_text(tpl)
    svg = render(tpl, sys.argv[2], sys.argv[3])
    Path(sys.argv[4]).write_text(svg)
    print("ok", len(svg) // 1024, "KB")

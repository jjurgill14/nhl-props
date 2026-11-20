"""Team badges ("pucks"): a circular back-of-jersey graphic the app letters with any name/number.

Contract per team: docs/badges/<ABBR>.svg is the artwork only (no lettering), root carries
data-fill / data-stroke for the lettering colors. The app inserts the text at render time using
the NHL New Jersey font (docs/fonts/) and the glyph widths in docs/badges/widths.json.

Sources, in priority order:
  1. badges/templates/<ABBR>.svg — the designer's badge (lettering already stripped)
  2. badges/palette.json       — placeholder: the designer's Boston construction, recolored
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "badges"
OUT = ROOT / "docs" / "badges"
FONT = SRC / "NHLNewJersey.ttf"

VB = 1034.96
# The designer's Boston construction: outer ring, disc, three clipped hem bands, inner ring.
_OUTER = "M517.48,0C232.14,0,0,232.14,0,517.48s232.14,517.48,517.48,517.48,517.48-232.14,517.48-517.48S802.82,0,517.48,0ZM517.48,967.46c-248.52,0-449.98-201.46-449.98-449.98S268.96,67.5,517.48,67.5s449.98,201.46,449.98,449.98-201.46,449.98-449.98,449.98Z"
_INNER = "M517.48,35.46c266.21,0,482.02,215.81,482.02,482.02s-215.81,482.02-482.02,482.02S35.46,783.69,35.46,517.48,251.27,35.46,517.48,35.46h0ZM517.48,19.39c-67.23,0-132.47,13.17-193.88,39.15-59.31,25.09-112.58,61-158.32,106.74-45.74,45.74-81.65,99-106.74,158.32-25.98,61.42-39.15,126.65-39.15,193.88s13.17,132.47,39.15,193.88c25.09,59.31,61,112.58,106.74,158.32s99,81.65,158.32,106.74c61.42,25.98,126.65,39.15,193.88,39.15s132.47-13.17,193.88-39.15c59.31-25.09,112.58-61,158.32-106.74s81.65-99,106.74-158.32c25.98-61.42,39.15-126.65,39.15-193.88s-13.17-132.47-39.15-193.88c-25.09-59.31-61-112.58-106.74-158.32-45.74-45.74-99-81.65-158.32-106.74-61.42-25.98-126.65-39.15-193.88-39.15h0Z"
_BANDS_Y = (652.36, 779.24, 906.13)


def placeholder(p: dict) -> str:
    bands = "".join(f'<rect fill="{c}" x="-73.92" y="{y}" width="1182.79" height="107.09"/>' for y, c in zip(_BANDS_Y, p["stripes"]))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VB} {VB}" data-fill="{p["fill"]}" data-stroke="{p["stroke"]}">'
        f'<defs><clipPath id="{p["abbr"]}-disc"><rect x="35.46" y="35.46" width="964.04" height="964.04" rx="482.02" ry="482.02"/></clipPath></defs>'
        f'<path fill="{p["ring"]}" d="{_OUTER}"/>'
        f'<rect fill="{p["field"]}" x="35.46" y="35.46" width="964.04" height="964.04" rx="482.02" ry="482.02"/>'
        f'<g clip-path="url(#{p["abbr"]}-disc)">{bands}</g>'
        f'<g id="{p["abbr"]}-lettering"></g>'
        f'<path fill="{p["ring"]}" d="{_INNER}"/>'
        f"</svg>"
    )


def _css_rules(svg: str) -> dict[str, dict[str, str]]:
    """{'cls-3': {'fill': '#efbf23', 'font-size': '216.08px', ...}} from the <style> block (Illustrator export)."""
    rules: dict[str, dict[str, str]] = {}
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", re.search(r"<style>(.*?)</style>", svg, re.S).group(1) if "<style>" in svg else ""):
        props = dict(kv.split(":", 1) for kv in (x.strip() for x in body.split(";")) if ":" in kv)
        for cls in sel.split(","):
            rules.setdefault(cls.strip().lstrip("."), {}).update({k.strip(): v.strip() for k, v in props.items()})
    return rules


def _lettering_spec(svg: str) -> dict[str, str]:
    """Read where/how big the designer set the number and name, and their colors, before we strip them.
    Falls back to the Boston-era constants (viewBox 1034.96) when a file has no live text."""
    vb = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
    rules = _css_rules(svg)
    texts = re.findall(r'<text class="([^"]+)" transform="translate\(([\d.\-]+) ([\d.\-]+)\)">(.*?)</text>', svg, re.S)
    spec = {"vb": f"{vb:g}"}
    if len(texts) >= 2:
        # the number is the larger font; the name the smaller
        def size(cls):
            return float(rules.get(cls, {}).get("font-size", "0").replace("px", "") or 0)
        texts.sort(key=lambda t: -size(t[0]))
        (ncls, nx, ny, _), (mcls, mx, my, mbody) = texts[0], texts[1]
        first_span = re.search(r'<tspan class="([^"]+)"', mbody)
        sp = rules.get(first_span.group(1), {}).get("letter-spacing", "0em") if first_span else "0em"
        spec.update({
            "num_size": f"{size(ncls):g}", "num_base": ny, "num_fill": rules.get(ncls, {}).get("fill", "#000"),
            "num_spacing": rules.get(ncls, {}).get("letter-spacing", "0em").replace("em", ""),
            "name_size": f"{size(mcls):g}", "name_base": my, "name_fill": rules.get(mcls, {}).get("fill", "#000"),
            "name_spacing": sp.replace("em", ""), "name_maxw": f"{vb - 2 * float(mx):g}",
            "stroke": "none",
        })
    return spec


def _designer(abbr: str, svg: str, fill: str, stroke: str) -> str:
    """Normalise a designer template: strip lettering, namespace ids/classes so many badges can share a page, tag colors."""
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", svg)
    spec = _lettering_spec(svg)
    svg = re.sub(r"<text\b.*?</text>", "", svg, flags=re.S)
    svg = re.sub(r'\sdata-name="[^"]*"', "", svg)
    svg = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{abbr}-{m.group(1)}"', svg)
    svg = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{abbr}-{m.group(1)})", svg)
    svg = re.sub(r"\.cls-(\d+)", lambda m: f".{abbr}-cls-{m.group(1)}", svg)
    svg = re.sub(r'class="([^"]+)"', lambda m: 'class="' + " ".join(f"{abbr}-{c}" for c in m.group(1).split()) + '"', svg)
    # lettering goes right under the inner ring: mark the spot so the app never lands inside a clipped group
    cx = f"{float(spec['vb']) / 2:g}"
    rings = list(re.finditer(rf'<path[^>]*\sd="M{re.escape(cx)},', svg))  # outer ring first, inner ring last
    if rings:
        at = rings[-1].start()
        svg = svg[:at] + f'<g id="{abbr}-lettering"></g>' + svg[at:]
    attrs = " ".join(f'data-{k.replace("_", "-")}="{v}"' for k, v in spec.items())
    if "stroke" not in spec:
        attrs += f' data-fill="{fill}" data-stroke="{stroke}"'
    svg = svg.replace("<svg ", f"<svg {attrs} ", 1)
    svg = re.sub(r"\n\s*", "", svg)
    return svg


def widths() -> dict:
    """Advance widths (em units) for the lettering font so the app can fit long names without measuring."""
    from fontTools.ttLib import TTFont

    f = TTFont(FONT)
    cmap, hmtx, upem = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '-."
    return {c: round(hmtx[cmap[ord(c)]][0] / upem, 4) for c in chars if ord(c) in cmap}


def build() -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "fonts").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FONT, ROOT / "docs" / "fonts" / "NHLNewJersey.ttf")
    palette = {k: v for k, v in json.loads((SRC / "palette.json").read_text()).items() if not k.startswith("_")}
    designer = {p.stem: p for p in (SRC / "templates").glob("*.svg")}
    # lettering colors for designer files: from palette if present, else the Boston default
    letters = {"BOS": ("#ffffff", "#f4c250")}
    made = []
    for abbr in sorted(set(palette) | set(designer)):
        if abbr in designer:
            fill, stroke = letters.get(abbr) or (palette[abbr]["fill"], palette[abbr]["stroke"])
            svg = _designer(abbr, designer[abbr].read_text(), fill, stroke)
        else:
            svg = placeholder({**palette[abbr], "abbr": abbr})
        (OUT / f"{abbr}.svg").write_text(svg)
        made.append(abbr)
    (OUT / "widths.json").write_text(json.dumps(widths(), separators=(",", ":")))
    (OUT / "index.json").write_text(json.dumps({"teams": made, "designer": sorted(designer)}))
    return made


if __name__ == "__main__":
    print(build())

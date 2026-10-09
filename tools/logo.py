"""Draw the Katagami logo: a square of material with three cuts, and the K that is left.

    python tools/logo.py

A kerf is the width a saw or laser removes. The mark starts as a solid
square. One vertical kerf separates the stem; two straight cuts run from the
stem's edge to the right side and the wedge between them falls away as the
offcut. What remains reads as a K. Writes:

    docs/logo/katagami-mark.svg        the mark, ink
    docs/logo/katagami-mark-cut.svg    the mark with the cut lines in red, as on the specimen
    docs/logo/katagami-logo.svg        the mark and the word Katagami set in Katagami Sans SemiBold
    Katagami-Website/favicon.svg       the mark, following the browser's light or dark theme
    Katagami-Website/favicon.png, apple-touch-icon.png   the mark on the paper colour
"""

from __future__ import annotations

import os
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("KATAGAMI_SITE", ROOT.parent / "Katagami-Website"))
OUT = ROOT / "docs" / "logo"
INK, PAPER, CUT = "#111214", "#f1f2ef", "#d92d20"
INK_DARK = "#ebece9"

# The square is 100 units. The vertical kerf is 7 wide, left of centre; the two
# diagonal cuts start where the kerf's right edge crosses the middle and reach
# the right side 30 units from the top and the bottom.
KERF = 7
STEM = 31
APEX = (STEM + KERF, 50)
REACH = 30


def pieces() -> list[list[tuple[float, float]]]:
    x0 = STEM + KERF
    return [
        [(0, 0), (STEM, 0), (STEM, 100), (0, 100)],                 # the stem
        [(x0, 0), (100, 0), (100, REACH), APEX],                    # the arm
        [APEX, (100, 100 - REACH), (100, 100), (x0, 100)],          # the leg
    ]


def path(poly) -> str:
    return "M" + " L".join(f"{x:g} {y:g}" for x, y in poly) + " Z"


def mark_svg(fill: str = INK, cut_lines: bool = False, size: int = 100, theme: bool = False) -> str:
    style = ""
    if theme:
        style = (f"<style>path{{fill:{INK}}}@media (prefers-color-scheme: dark){{path{{fill:{INK_DARK}}}}}</style>")
    body = "".join(f'<path d="{path(p)}"{"" if theme else f" fill={chr(34)}{fill}{chr(34)}"}/>' for p in pieces())
    if cut_lines:
        x = STEM + KERF / 2
        body += (f'<g stroke="{CUT}" stroke-width="1" fill="none" stroke-linecap="square">'
                 f'<line x1="{x:g}" y1="0" x2="{x:g}" y2="100"/>'
                 f'<polyline points="100,{REACH} {APEX[0]:g},{APEX[1]:g} 100,{100 - REACH}"/></g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="{size}" height="{size}">'
            f"{style}{body}</svg>\n")


def word_paths(text: str, weight: int, height: float, x0: float) -> tuple[str, float]:
    """The word set in Katagami Sans at `weight`, scaled so its cap height is `height`."""
    vf = TTFont(ROOT / "fonts" / "sans" / "KatagamiSans[wght].ttf")
    font = instantiateVariableFont(vf, {"wght": weight})
    gs, cmap = font.getGlyphSet(), font.getBestCmap()
    cap = font["OS/2"].sCapHeight
    s = height / cap
    out, x = [], x0
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        # flip y: font units grow upward, SVG grows downward; the baseline sits at y = height
        gs[name].draw(TransformPen(pen, (s, 0, 0, -s, x, height)))
        out.append(pen.getCommands())
        x += gs[name].width * s
    return " ".join(out), x


def logo_svg() -> str:
    gap = 30
    word, end = word_paths("Katagami", 600, 100, 100 + gap)
    body = "".join(f'<path d="{path(p)}"/>' for p in pieces()) + f'<path d="{word}"/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {end:.0f} 100" height="100" fill="{INK}">'
            f"{body}</svg>\n")


def png(path: Path, size: int, inset: float) -> None:
    """The mark in ink on a paper square, `inset` of the size clear on each side."""
    from drawbot_skia.drawing import Drawing
    from drawbot_skia.path import BezierPath

    db = Drawing()
    db.newPage(size, size)
    rgb = lambda h: tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))  # noqa: E731
    db.fill(*rgb(PAPER))
    db.rect(0, 0, size, size)
    db.fill(*rgb(INK))
    k = size * (1 - 2 * inset) / 100
    for poly in pieces():
        bp = BezierPath()
        pts = [(size * inset + x * k, size - (size * inset + y * k)) for x, y in poly]
        bp.moveTo(pts[0])
        for pt in pts[1:]:
            bp.lineTo(pt)
        bp.closePath()
        db.drawPath(bp)
    db.saveImage(str(path))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "katagami-mark.svg").write_text(mark_svg())
    (OUT / "katagami-mark-cut.svg").write_text(mark_svg(cut_lines=True))
    (OUT / "katagami-logo.svg").write_text(logo_svg())
    (SITE / "favicon.svg").write_text(mark_svg(theme=True, size=32))
    png(SITE / "favicon.png", 64, 0.08)
    png(SITE / "apple-touch-icon.png", 180, 0.2)
    for p in sorted(OUT.iterdir()) + [SITE / "favicon.svg", SITE / "favicon.png", SITE / "apple-touch-icon.png"]:
        print(p)


if __name__ == "__main__":
    main()

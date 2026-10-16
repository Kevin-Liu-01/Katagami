"""Braille patterns (U+2800-28FF) and the status symbols terminal agents print.

Braille dots are squares the size of the mono's period, on a 2 by 4 grid
spread evenly over the full line height, so patterns tile across cells and
lines the way box drawing does. Bit k of (codepoint - 0x2800) raises dot k+1.

The symbols are measured from their neighbours in each master, so they keep
the font's weight from Thin to Bold:
  - the record circle, fisheye, stop, pause, play and the stars take their
    size from the black square, sit on the middle of the cap height, and use
    true circles like the font's other circles
  - stroked symbols use the light box line (rings, the connector) or the
    asterisk's spoke (stars), with square ends
  - the heavy check and ballot X are the light ones with every edge moved
    out, then fitted back into the light glyph's box
  - the small triangle is a smaller black triangle on the small square's centre
Codepoints the font already maps are left alone.
"""

from __future__ import annotations

import math

from ufoLib2.objects import Contour

from .boxdraw import LIGHT, UP, Cell, _pt, _rect
from .outline import KAPPA

# dots 1 to 8 as (column, row from the top)
DOT_GRID = [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2), (0, 3), (1, 3)]
SYMBOL = 0.90       # record circle, fisheye and stars span this share of the black square's ink width
STOP = 0.86         # stop square and pause bars: side as a share of the symbol size
PAUSE = (0.24, 0.4)  # pause bar width: this share of its height plus this share of the hyphen
PLAY = 0.85         # right-pointing triangles: width over height, as Katagami Sans's black triangle
SMALL = 1.3         # small triangle: height over the small square's side
HEAVY = 0.45        # heavy check and X: each edge moves out by this share of the hyphen
HEAVY_SPOKE = 1.6   # heavy asterisk spokes over the light ones
EYE = 0.55          # fisheye dot radius over the ring's inner radius
BRAILLE_BIT = 82    # OS/2 ulUnicodeRange bit for Braille Patterns


def braille(cp: int, width: float, bottom: float, top: float, dot_w: float, dot_h: float) -> list[Contour]:
    bits = cp - 0x2800
    pitch_x, pitch_y = width / 2, (top - bottom) / 4
    out = []
    for k, (col, row) in enumerate(DOT_GRID):
        if not bits >> k & 1:
            continue
        x0 = round(pitch_x * (col + 0.5) - dot_w / 2)
        y0 = round(top - pitch_y * (row + 0.5) - dot_h / 2)
        out.append(_rect(x0, y0, x0 + round(dot_w), y0 + round(dot_h)))
    return out


def circle(cx: float, cy: float, r: float, hole: bool = False) -> Contour:
    """A true circle (handles at 0.5523), counter-clockwise, or clockwise as a hole."""
    k = KAPPA * r
    pts = [(0, -r, "curve"), (k, -r, None), (r, -k, None), (r, 0, "curve"), (r, k, None), (k, r, None),
           (0, r, "curve"), (-k, r, None), (-r, k, None), (-r, 0, "curve"), (-r, -k, None), (-k, -r, None)]
    s = -1 if hole else 1
    return Contour(points=[_pt(cx + s * x, cy + y, t) for x, y, t in pts])


def spoke_bar(cx: float, cy: float, reach: float, thick: float, degrees: float) -> Contour:
    """A bar through the centre at `degrees`, ending square `reach` out on each side."""
    a = math.radians(degrees)
    ux, uy = math.cos(a), math.sin(a)
    h = thick / 2
    return Contour(points=[_pt(cx + ux * s - uy * t, cy + uy * s + ux * t)
                           for s, t in ((-reach, -h), (reach, -h), (reach, h), (-reach, h))])


def play(cx: float, cy: float, height: float) -> Contour:
    """Right-pointing triangle, its box centred on (cx, cy)."""
    w = PLAY * height
    x0 = cx - w / 2
    return Contour(points=[_pt(x0, cy - height / 2), _pt(x0 + w, cy), _pt(x0, cy + height / 2)])


def hexagram(cx: float, cy: float, r: float) -> Contour:
    """Six-pointed star, point up: two equilateral triangles as one outline."""
    pts = []
    for i in range(12):
        a = math.radians(90 + 30 * i)
        rr = r if i % 2 == 0 else r / math.sqrt(3)
        pts.append(_pt(cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return Contour(points=pts)


def _box(contours) -> tuple[float, float, float, float]:
    xs = [p.x for c in contours for p in c.points]
    ys = [p.y for c in contours for p in c.points]
    return min(xs), min(ys), max(xs), max(ys)


def _place(contours, box, scale: float) -> list[Contour]:
    """Scale about the contours' box centre and move that centre to `box`'s centre."""
    x0, y0, x1, y1 = _box(contours)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    tx, ty = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return [Contour(points=[_pt(tx + (p.x - cx) * scale, ty + (p.y - cy) * scale, p.type) for p in c.points])
            for c in contours]


def heavier(contours, grow: float) -> list[Contour]:
    """Straight-sided outlines with every edge moved out by `grow`, mitred,
    then fitted back into the original box. Points are only moved."""
    out = []
    for c in contours:
        pts = [(p.x, p.y) for p in c.points]
        assert all(p.type == "line" for p in c.points), "heavier() takes straight-sided outlines"
        n = len(pts)
        normals = []
        for i in range(n):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            d = math.hypot(bx - ax, by - ay)
            normals.append(((by - ay) / d, -(bx - ax) / d))  # right of travel: away from the ink
        moved = []
        for i in range(n):
            (nx0, ny0), (nx1, ny1) = normals[i - 1], normals[i]
            k = grow / (1 + nx0 * nx1 + ny0 * ny1)
            moved.append((pts[i][0] + (nx0 + nx1) * k, pts[i][1] + (ny0 + ny1) * k))
        out.append(Contour(points=[_pt(x, y) for x, y in moved]))
    box = _box(contours)
    nb = _box(out)
    scale = min((box[2] - box[0]) / (nb[2] - nb[0]), (box[3] - box[1]) / (nb[3] - nb[1]))
    return _place(out, box, scale)


def _bounds(font, name: str):
    return font[name].getBounds(font)


def _foot_width(font, name: str) -> float:
    """Width of a glyph at its lowest points: the asterisk's lower spoke."""
    pts = [p for c in font[name].contours for p in c.points]
    low = min(p.y for p in pts)
    xs = [p.x for p in pts if p.y - low < 1]
    return max(xs) - min(xs)


def draw_terminal_glyphs(font, width: float, bar: float) -> None:
    by_cp = {u: g.name for g in font for u in g.unicodes}
    glyphs: dict[int, list[Contour]] = {}

    dot = _bounds(font, by_cp[0x2E])
    for cp in range(0x2800, 0x2900):
        glyphs[cp] = braille(cp, width, font.info.descender, font.info.ascender,
                             dot.xMax - dot.xMin, dot.yMax - dot.yMin)

    cx, cy = width / 2, font.info.capHeight / 2
    square = _bounds(font, by_cp[0x25A0])
    size = SYMBOL * (square.xMax - square.xMin)
    r = size / 2
    cell = Cell(width, font.info.descender, font.info.ascender, round(bar * 0.9))
    line = cell.t[LIGHT]

    glyphs[0x23FA] = [circle(cx, cy, r)]  # ⏺
    inner = r - line
    glyphs[0x25C9] = [circle(cx, cy, r), circle(cx, cy, inner, hole=True), circle(cx, cy, EYE * inner)]  # ◉
    side = STOP * size
    glyphs[0x23F9] = [_rect(cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2)]  # ⏹
    pause = PAUSE[0] * side + PAUSE[1] * bar
    glyphs[0x23F8] = [_rect(cx - side / 2, cy - side / 2, cx - side / 2 + pause, cy + side / 2),  # ⏸
                      _rect(cx + side / 2 - pause, cy - side / 2, cx + side / 2, cy + side / 2)]
    glyphs[0x23F5] = [play(cx, cy, size)]  # ⏵
    small = _bounds(font, by_cp[0x25AA])
    glyphs[0x25B8] = [play(cx, (small.yMin + small.yMax) / 2, SMALL * (small.yMax - small.yMin))]  # ▸

    # ⎿: the light box line from the top of the cell, turning right along its bottom
    glyphs[0x23BF] = [cell.span(UP, cell.y0, cell.y1, 0, line),
                      _rect(cx - line / 2, cell.y0, width, cell.y0 + line)]

    glyphs[0x2714] = heavier(font[by_cp[0x2713]].contours, HEAVY * bar)  # ✔ from ✓
    ballot = font[by_cp[0x2717]].contours
    glyphs[0x2718] = heavier(ballot, HEAVY * bar)  # ✘ from ✗
    times = font[by_cp[0xD7]].contours
    tb, bb = _box(times), _box(ballot)
    glyphs[0x2715] = _place(times, bb, (bb[3] - bb[1]) / (tb[3] - tb[1]))  # ✕: × at ✗'s height and place

    spoke = _foot_width(font, by_cp[0x2A])
    glyphs[0x2722] = [spoke_bar(cx, cy, r, spoke, a) for a in (90, 0)]  # ✢
    glyphs[0x2733] = [spoke_bar(cx, cy, r, spoke, a) for a in (90, 0, 45, 135)]  # ✳
    glyphs[0x273B] = [spoke_bar(cx, cy, r, spoke, a) for a in (90, 30, 150)]  # ✻
    glyphs[0x273D] = [spoke_bar(cx, cy, r, HEAVY_SPOKE * spoke, a) for a in (90, 30, 150)]  # ✽
    glyphs[0x2736] = [hexagram(cx, cy, r)]  # ✶

    for cp, contours in glyphs.items():
        if cp in by_cp:
            continue
        gname = f"uni{cp:04X}"
        g = font[gname] if gname in font else font.newGlyph(gname)
        g.clearContours()
        g.clearComponents()
        g.clearAnchors()
        g.unicodes = [cp]
        for c in contours:
            g.appendContour(c)
        g.width = width

    ranges = font.info.openTypeOS2UnicodeRanges
    if ranges is not None and BRAILLE_BIT not in ranges:
        font.info.openTypeOS2UnicodeRanges = sorted([*ranges, BRAILLE_BIT])

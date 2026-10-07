"""Box drawing (U+2500-257F) and block elements (U+2580-259F) on the mono cell.

Each box-drawing glyph is read from its Unicode name into four arms
(up, right, down, left), each light, heavy or double, and drawn so lines
meet their neighbours across the full line height. Rounded corners use the
same squared curve as the letters.
"""

from __future__ import annotations

import math
import unicodedata

from ufoLib2.objects import Contour, Point

UP, RIGHT, DOWN, LEFT = "UP", "RIGHT", "DOWN", "LEFT"
NONE, LIGHT, HEAVY, DOUBLE = 0, 1, 2, 3
WEIGHT_WORDS = {"LIGHT": LIGHT, "SINGLE": LIGHT, "HEAVY": HEAVY, "DOUBLE": DOUBLE}
DIR_WORDS = {"UP": [UP], "DOWN": [DOWN], "LEFT": [LEFT], "RIGHT": [RIGHT],
             "VERTICAL": [UP, DOWN], "HORIZONTAL": [LEFT, RIGHT]}
ARC_HANDLE = 0.73  # matches the squared letter curves


def parse_arms(name: str) -> dict[str, int] | None:
    words = name.removeprefix("BOX DRAWINGS ").split()
    if any(w in ("DASH", "ARC", "DIAGONAL") for w in words):
        return None
    weights = [w for w in words if w in WEIGHT_WORDS]
    arms = {UP: NONE, RIGHT: NONE, DOWN: NONE, LEFT: NONE}
    if len(weights) == 1:
        for w in words:
            for d in DIR_WORDS.get(w, []):
                arms[d] = WEIGHT_WORDS[weights[0]]
        return arms
    for part in " ".join(words).split(" AND "):
        toks = part.split()
        weight = next(WEIGHT_WORDS[t] for t in toks if t in WEIGHT_WORDS)
        for t in toks:
            for d in DIR_WORDS.get(t, []):
                arms[d] = weight
    return arms


def _pt(x, y, kind="line"):
    return Point(round(x), round(y), kind)


def _rect(x0, y0, x1, y1) -> Contour:
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    return Contour(points=[_pt(x0, y0), _pt(x1, y0), _pt(x1, y1), _pt(x0, y1)])


class Cell:
    def __init__(self, width, bottom, top, light):
        self.w, self.y0, self.y1 = width, bottom, top
        self.cx, self.cy = width / 2, (bottom + top) / 2
        self.t = {LIGHT: light, HEAVY: light * 2, DOUBLE: light}
        self.d = light  # double lines sit at centre +/- d

    def half(self, weight) -> float:
        """How far an arm of this weight reaches either side of the centre line."""
        if weight == DOUBLE:
            return self.d + self.t[LIGHT] / 2
        return self.t[weight] / 2 if weight else 0

    def edge(self, arm) -> float:
        return {UP: self.y1, DOWN: self.y0, LEFT: 0, RIGHT: self.w}[arm]

    def centre(self, arm) -> float:
        return self.cy if arm in (UP, DOWN) else self.cx

    def span(self, arm, a, b, off, thick) -> Contour:
        """Rectangle along `arm`'s axis from a to b, centred off the axis by off."""
        if arm in (UP, DOWN):
            return _rect(self.cx + off - thick / 2, a, self.cx + off + thick / 2, b)
        return _rect(a, self.cy + off - thick / 2, b, self.cy + off + thick / 2)


PERP = {UP: (LEFT, RIGHT), DOWN: (LEFT, RIGHT), LEFT: (DOWN, UP), RIGHT: (DOWN, UP)}
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}
SIGN = {UP: 1, RIGHT: 1, DOWN: -1, LEFT: -1}


def draw_arms(cell: Cell, arms: dict[str, int]) -> list[Contour]:
    out = []
    for arm, weight in arms.items():
        if not weight:
            continue
        edge, c, s = cell.edge(arm), cell.centre(arm), SIGN[arm]
        lo_side, hi_side = PERP[arm]
        if weight != DOUBLE:
            reach = max(cell.half(arms[lo_side]), cell.half(arms[hi_side]))
            out.append(cell.span(arm, c - s * reach, edge, 0, cell.t[weight]))
            continue
        for side, off in ((lo_side, -cell.d), (hi_side, cell.d)):
            other = hi_side if side == lo_side else lo_side
            if arms[side]:
                # inner line: stop where the arm on this side begins
                near = cell.d - cell.t[LIGHT] / 2 if arms[side] == DOUBLE else cell.half(arms[side])
                stop = c + s * near
            elif arms[OPPOSITE[arm]]:
                stop = c  # runs on through the centre
            elif arms[other]:
                # outer line of a corner: run across to the far side
                stop = c - s * cell.half(arms[other])
            else:
                stop = c
            out.append(cell.span(arm, stop, edge, off, cell.t[LIGHT]))
    return out


def draw_dashes(cell: Cell, name: str) -> list[Contour]:
    n = {"DOUBLE": 2, "TRIPLE": 3, "QUADRUPLE": 4}[next(w for w in name.split() if w in ("DOUBLE", "TRIPLE", "QUADRUPLE"))]
    weight = HEAVY if "HEAVY" in name else LIGHT
    vertical = "VERTICAL" in name
    a, b = (cell.y0, cell.y1) if vertical else (0, cell.w)
    pitch = (b - a) / n
    gap = pitch * 0.32
    arm = UP if vertical else RIGHT
    return [cell.span(arm, a + i * pitch + gap / 2, a + (i + 1) * pitch - gap / 2, 0, cell.t[weight])
            for i in range(n)]


def draw_arc(cell: Cell, name: str) -> list[Contour]:
    """Rounded corner. Drawn as DOWN AND RIGHT, then mirrored."""
    t = cell.t[LIGHT] / 2
    r = cell.w * 0.42
    cx, cy, k = cell.cx, cell.cy, ARC_HANDLE
    ro, ri = r + t, r - t
    ox, oy = cx + r, cy - r  # arc centre
    pts = [
        _pt(cx - t, cell.y0), _pt(cx + t, cell.y0), _pt(cx + t, oy),
        _pt(cx + t, oy + ri * k, None), _pt(ox - ri * k, cy - t, None), _pt(ox, cy - t, "curve"),
        _pt(cell.w, cy - t), _pt(cell.w, cy + t), _pt(ox, cy + t),
        _pt(ox - ro * k, cy + t, None), _pt(cx - t, oy + ro * k, None), _pt(cx - t, oy, "curve"),
    ]
    contour = Contour(points=pts)
    flip_x = "LEFT" in name
    flip_y = "UP" in name
    for p in contour.points:
        if flip_x:
            p.x = round(2 * cx - p.x)
        if flip_y:
            p.y = round(2 * cy - p.y)
    if flip_x != flip_y:
        _reverse(contour)
    return [contour]


def _reverse(contour: Contour) -> None:
    """Reverse direction, keeping each segment's type on its end point."""
    pts = contour.points
    types = [p.type for p in pts]
    on = [i for i, t in enumerate(types) if t]
    # the segment prev -> i (type on i) now runs i -> prev and ends on prev
    for j, i in enumerate(on):
        pts[on[j - 1]].type = types[i]
    contour.points[:] = list(reversed(pts))


def draw_diagonal(cell: Cell, name: str) -> list[Contour]:
    t = cell.t[LIGHT]
    h = cell.y1 - cell.y0
    w = t / 2 * math.hypot(cell.w, h) / h  # horizontal half-width of a sloped stroke
    up = Contour(points=[_pt(-w, cell.y0), _pt(w, cell.y0), _pt(cell.w + w, cell.y1), _pt(cell.w - w, cell.y1)])
    down = Contour(points=[_pt(-w, cell.y1), _pt(cell.w - w, cell.y0), _pt(cell.w + w, cell.y0), _pt(w, cell.y1)])
    if "CROSS" in name:
        return [up, down]
    return [up] if "UPPER RIGHT" in name else [down]


def draw_block(cell: Cell, cp: int) -> list[Contour]:
    W, y0, y1 = cell.w, cell.y0, cell.y1
    H = y1 - y0
    if cp == 0x2580:
        return [_rect(0, y0 + H / 2, W, y1)]
    if 0x2581 <= cp <= 0x2588:
        return [_rect(0, y0, W, y0 + H * (cp - 0x2580) / 8)]
    if 0x2589 <= cp <= 0x258F:
        return [_rect(0, y0, W * (0x2590 - cp) / 8, y1)]
    if cp == 0x2590:
        return [_rect(W / 2, y0, W, y1)]
    if cp == 0x2594:
        return [_rect(0, y1 - H / 8, W, y1)]
    if cp == 0x2595:
        return [_rect(W * 7 / 8, y0, W, y1)]
    if 0x2591 <= cp <= 0x2593:
        return _shade(cell, cp - 0x2590)
    quads = {0x2596: "3", 0x2597: "4", 0x2598: "1", 0x2599: "134", 0x259A: "14",
             0x259B: "123", 0x259C: "124", 0x259D: "2", 0x259E: "23", 0x259F: "234"}
    boxes = {"1": (0, y0 + H / 2, W / 2, y1), "2": (W / 2, y0 + H / 2, W, y1),
             "3": (0, y0, W / 2, y0 + H / 2), "4": (W / 2, y0, W, y0 + H / 2)}
    return [_rect(*boxes[q]) for q in quads.get(cp, "")]


def _shade(cell: Cell, level: int) -> list[Contour]:
    """Light 25%, medium 50%, dark 75%, as a square dot grid."""
    cols = 4
    p = cell.w / cols
    rows = round((cell.y1 - cell.y0) / p)
    ph = (cell.y1 - cell.y0) / rows
    out = []
    if level == 3:
        out.append(_rect(0, cell.y0, cell.w, cell.y1))
    for r in range(rows):
        for c in range(cols):
            x, y = c * p, cell.y0 + r * ph
            if level == 2:
                if (r + c) % 2 == 0:
                    out.append(_rect(x, y, x + p, y + ph))
            elif r % 2 == 0 and c % 2 == 0:
                hole = _rect(x + p / 4, y + ph / 4, x + p * 3 / 4, y + ph * 3 / 4)
                if level == 3:
                    hole.points[:] = list(reversed(hole.points))  # clockwise = cut out
                out.append(hole)
    return out


def draw_box_glyphs(font, width: float, stem: float, bar: float) -> None:
    cell = Cell(width, font.info.descender, font.info.ascender, round(bar * 0.9))
    by_cp = {u: g.name for g in font for u in g.unicodes}
    for cp in range(0x2500, 0x25A0):
        name = unicodedata.name(chr(cp), "")
        if cp < 0x2580:
            arms = parse_arms(name)
            if arms is not None:
                contours = draw_arms(cell, arms)
            elif "DASH" in name:
                contours = draw_dashes(cell, name)
            elif "ARC" in name:
                contours = draw_arc(cell, name)
            else:
                contours = draw_diagonal(cell, name)
        else:
            contours = draw_block(cell, cp)
        gname = by_cp.get(cp, f"uni{cp:04X}")
        g = font[gname] if gname in font else font.newGlyph(gname)
        g.clearContours()
        g.clearComponents()
        g.clearAnchors()
        g.unicodes = [cp]
        for c in contours:
            g.appendContour(c)
        g.width = width

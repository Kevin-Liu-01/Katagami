"""Katagami Serif's moved beaks (lab version, not yet in tools/build_sans.py).

0.2 hung each curved terminal's beak under the level cut, at its outer
corner: the stroke ran down into the cut and a tab hung on, which read as
teeth. Here a curved stroke ends the way a text serif face ends its C, G, S,
c, s and a (Times New Roman's C and s, Charter, Signifier, Tiempos): a
vertical face at the letter's outer extreme, which the stroke runs into at a
slant, and a spur carrying that face on past the stroke's inner edge, down
from a top terminal and up from a foot.

The face: the old level cut's inner corner keeps its height; the stroke's
outer edge is cut back to where it stands over that corner (no further than
where it runs SHOULDER degrees steep); then both edges are stretched
sideways about their far ends until the cut stands upright at the old outer
corner's x. The spur: as wide as the stem serifs are thick, reaching past the
inner corner as far as they reach past a stem (serif_depth, serif_reach,
with their weight scaling; a capital's or a figure's in proportion to its
height), square-ended, with the arm serifs' bracket into
the stroke's inner edge. The ends 0.2 already cut upright (the arm of r, the
tails of j and y) keep 0.2's face and take the same spur; f's hook, which
leans too far to cut upright in every master, is cut like a level end.

plan_terminals and cut_terminals replace build_sans.py's; every helper they
import (recut, _split, _upright, _walk_to_x, ...) is the same in 0.2
(328c6c6), the barbs (387577b) and the flat slabs (cf7f611). lablib.build
runs them on the pickled masters.
"""
from __future__ import annotations

import copy
import math
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_sans import (  # noqa: E402
    BRACKET, SERIF_DEPTH_SCALE, SERIF_REACH_POWER, TERMINAL_FACE, TERMINAL_REF, TERMINAL_SYMBOLS,
    _contour, _ink_side, _point, _split, _upright, _walk_to_x, flag_overlaps, serif_parts, stem,
)

SHOULDER = 30  # degrees: the outer edge is cut back no further than where it runs this steep
LEVEL_BEAK_ANGLE = 6  # degrees: a cut further from level than this (Inter's a.2, £, §) ends plain
TERMINAL_ROOM = 1 / 3  # the most of the white past a terminal its spur may take, so facing beaks leave a third open
BEAK_WIDTH = 1.0  # the spur's width, as a share of the master's serif thickness
BEAK_REACH = 1.0  # the spur's reach past the stroke's inner edge, as a share of the stem serifs' reach
# How far the face goes back out toward where the stroke ended (its old outer corner): the
# cut-back end is stretched sideways, so the stroke keeps its reach and meets the face at a
# slant, as a text face's arc runs out to its beak. 0 leaves the face over the inner corner.
FACE_OUT = 1.0
# The spur's reach grows with the letter's height over the x-height to this power, so a capital's
# or a figure's beak keeps the share of its height a lowercase one has (Times New Roman's C and s
# both drop about a third of theirs); 0 gives every beak the stem serifs' reach.
BEAK_BY_HEIGHT = 1.0
RIGHT_EXITS = False  # whether a stroke rising out at the foot of a letter's right side (c, C, e, t) takes a beak


def plan_terminals(fonts, plan: dict) -> dict:
    """Where Katagami Serif's terminals take a beak, found on Regular: every
    stroke end the serif plan leaves bare in letters, figures, their
    alternates, the stems of f and t and the symbols drawn like letters.

    A stroke end is a straight cut 0.45 to 1.6 stems long between two
    corners whose sides run back the way they came, with ink on one side of
    it and none on the other. A level cut (within LEVEL_BEAK_ANGLE of
    horizontal) between two curves is the end of a curved stroke (C, G, S,
    a, c, s, the figures); its beak points into the letter. An upright cut
    (within 30 degrees of vertical) ends a hook, an arm or a tail (r, f, j,
    y), unless it ends a stub in the middle third of the letter (the waist
    of 3) or a stroke lying on the baseline, x-height or cap height. A bar's
    end (the crossbars of f and t, the foot of 2) is not a terminal. The
    stroke rising out at the foot of a letter's right side (c, C, e, ε, the
    hook of t) ends plain, as in a text face, and so does the lower end of
    an opening whose upper end has a beak on the same side (ɔ, Ↄ).
    Returns {glyph: [(kind, contour, i, j, outer, way, scale)]}: for a
    level cut the corner on the outside of the letter, for an upright cut
    the corner the spur grows from; way is 1 for a spur pointing up and -1
    for one pointing down; scale is the cut's length over TERMINAL_REF
    stems, at most 1.
    """
    ref = fonts["Regular"]
    sw = stem(ref)
    cat = lambda g: unicodedata.category(chr(g.unicodes[0])) if g.unicodes else ""  # noqa: E731
    drawn = {g.name for g in ref if g.unicodes and (cat(g)[0] in "LN" or chr(g.unicodes[0]) in TERMINAL_SYMBOLS)}
    names = [g.name for g in ref if g.contours and g.width and (g.name in drawn or (not g.unicodes and g.name.split(".")[0] in drawn))]
    names += sorted(serif_parts(ref) - set(names))
    metrics = (ref["x"].getBounds(ref).yMax, ref["H"].getBounds(ref).yMax)
    out = {}
    for name in names:
        g = ref[name]
        ends, arms = plan.get(name, ([], []))
        taken = {(e[0], k) for e in ends + arms for k in (e[1], e[2])}
        b = g.getBounds(ref)
        found = []
        for ci, c in enumerate(g.contours):
            pts = c.points
            n = len(pts)
            for i in range(n):
                j = (i + 1) % n
                a, q = pts[i], pts[j]
                if a.type is None or q.type != "line" or a.smooth or q.smooth or (ci, i) in taken or (ci, j) in taken:
                    continue
                length = math.hypot(q.x - a.x, q.y - a.y)
                if not TERMINAL_FACE[0] * sw <= length <= TERMINAL_FACE[1] * sw:
                    continue
                prev, nxt = pts[(i - 1) % n], pts[(j + 1) % n]
                din, dout = (a.x - prev.x, a.y - prev.y), (nxt.x - q.x, nxt.y - q.y)
                li, lo = math.hypot(*din), math.hypot(*dout)
                if li < 1 or lo < 1 or (din[0] * dout[0] + din[1] * dout[1]) / (li * lo) > -0.5:
                    continue
                into_curve, out_curve = a.type == "curve", nxt.type is None
                bar = (not into_curve and li >= 1.8 * sw) or (nxt.type == "line" and lo >= 1.8 * sw)
                angle = abs(math.degrees(math.atan2(q.y - a.y, q.x - a.x))) % 180
                angle = min(angle, 180 - angle)
                mid_x, mid_y, cut_y = (b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2, (a.y + q.y) / 2
                if angle <= 30:
                    if angle > LEVEL_BEAK_ANGLE:
                        continue
                    kind = "level"
                    # the ink is left of travel, so the bare side faces up when the cut runs right to left
                    way = 1 if q.x < a.x else -1
                    # a beak points into the letter, never past its top or foot (the arms of ω)
                    if (way > 0) != (cut_y < mid_y):
                        continue
                    # only the end of a curved stroke can be cut back to a face its stroke meets at a slant
                    if not (into_curve and out_curve):
                        continue
                elif angle >= 60 and not bar:
                    kind = "upright"
                    lo_y, hi_y = sorted((a.y, q.y))
                    if abs(lo_y) < 3 or any(abs(hi_y - m) < 3 for m in metrics):
                        continue
                    if abs(cut_y - mid_y) < (b.yMax - b.yMin) / 6:
                        continue
                    way = -1 if cut_y > mid_y else 1
                else:
                    continue
                ink_left, bare_right = _ink_side(ref, g, a, q)
                if not (ink_left and bare_right):
                    continue
                if not RIGHT_EXITS and way > 0 and (a.x + q.x) / 2 > mid_x:
                    continue
                scale = min(1.0, length / (TERMINAL_REF * sw))
                if kind == "level":
                    outer = i if abs(a.x - mid_x) > abs(q.x - mid_x) else j
                else:
                    lo_k, hi_k = (i, j) if a.y < q.y else (j, i)
                    outer = lo_k if way < 0 else hi_k
                found.append((kind, ci, i, j, outer, way, scale))
        found = [term for term in found if not _jaw(ref, g, term, found, mid_x)]
        if found:
            out[name] = found
    return out


def _jaw(font, g, term, found, mid_x: float) -> bool:
    """Whether a rising beak at the foot of an opening would face the beak above
    it across that opening, as in ɔ and Ↄ: both cuts on the same side of the
    letter and nothing between them (the white at their mid-height reaches
    the letter's middle, where 3 has its waist). The upper beak stays."""
    from fontTools.pens.pointInsidePen import PointInsidePen
    kind, ci, i, j, outer, way, _ = term
    if kind != "level" or way < 0:
        return False
    pts = g.contours[ci].points
    side = 1 if pts[outer].x > mid_x else -1
    y = (pts[i].y + pts[j].y) / 2
    for k2, c2, i2, j2, o2, w2, _ in found:
        if k2 != "level" or w2 > 0:
            continue
        p2 = g.contours[c2].points
        if (p2[o2].x > mid_x) != (side > 0) or (p2[i2].y + p2[j2].y) / 2 <= y:
            continue
        mid_y = (y + (p2[i2].y + p2[j2].y) / 2) / 2
        x0 = (pts[outer].x + p2[o2].x) / 2
        for t in range(1, 21):
            pen = PointInsidePen(font, (x0 + (mid_x - x0) * t / 20, mid_y))
            g.draw(pen)
            if pen.getResult():
                break
        else:
            return True
    return False


def _edges(pts, i: int, j: int, outer: int):
    """The cubics on either side of the cut from i to j, each as its four
    points' indices from the cut's corner outward: (outer edge, inner edge).
    None where one side is not a single curve."""
    n = len(pts)
    into = [i, (i - 1) % n, (i - 2) % n, (i - 3) % n]  # from corner i back along the arriving edge
    out = [j, (j + 1) % n, (j + 2) % n, (j + 3) % n]
    for side in (into, out):
        if pts[side[1]].type is not None or pts[side[2]].type is not None or pts[side[3]].type is None:
            return None
    return (into, out) if outer == i else (out, into)


def _at_x(pts, side, x: float):
    """Where the cubic `side` (indices from the corner outward) crosses x: (t from
    the corner, y), or None where it does not within the curve."""
    c = [(pts[k].x, pts[k].y) for k in side]
    steps = 64
    prev = _point(c, 0.0)
    for s in range(1, steps + 1):
        t = s / steps
        cur = _point(c, t)
        if (prev[0] - x) * (cur[0] - x) <= 0 and prev[0] != cur[0]:
            lo, hi = t - 1 / steps, t
            for _ in range(40):
                mid = (lo + hi) / 2
                if (_point(c, lo)[0] - x) * (_point(c, mid)[0] - x) <= 0:
                    hi = mid
                else:
                    lo = mid
            t = (lo + hi) / 2
            return t, _point(c, t)[1]
        prev = cur
    return None


def _trim(pts, side, t: float) -> None:
    """Cut the cubic `side` at t (from its corner), keeping the part away from
    the corner: the corner moves to the cut and both handles shrink with it,
    so the edge stays a piece of its own curve."""
    c = [(pts[k].x, pts[k].y) for k in side]
    _, rest = _split(c, t)
    for k, (x, y) in zip(side[:3], rest[:3]):
        pts[k].x, pts[k].y = x, y


def _slope(pts, side, t: float) -> float:
    """How steep the cubic `side` runs at t, in degrees from level."""
    c = [(pts[k].x, pts[k].y) for k in side]
    a, b = _point(c, max(0.0, t - 1e-4)), _point(c, min(1.0, t + 1e-4))
    return abs(math.degrees(math.atan2(b[1] - a[1], abs(b[0] - a[0]) or 1e-9)))


def _face(pts, i: int, j: int, outer: int):
    """Where a cut's outer edge is cut back to, as its t from the outer corner:
    above (or below) the cut's inner corner, where the stroke still runs at a
    slant, but no further back than where the edge runs SHOULDER degrees
    steep, so a heavy stroke, whose inner corner stands near the top of the
    letter, keeps a round shoulder. None where an edge is not a single curve
    or never reaches the inner corner's x."""
    sides = _edges(pts, i, j, outer)
    if sides is None:
        return None
    o_side, n_side = sides
    corner = pts[n_side[0]]
    back = 1 if pts[n_side[3]].x > corner.x else -1  # from the inner corner back along the stroke
    if back * (pts[o_side[0]].x - corner.x) > 0 or back * (pts[o_side[3]].x - corner.x) <= 0:
        return None
    hit = _at_x(pts, o_side, corner.x)
    if hit is None:
        return None
    t = hit[0]
    if _slope(pts, o_side, t) < SHOULDER:
        lo, hi = 0.0, t
        for _ in range(40):
            mid = (lo + hi) / 2
            if _slope(pts, o_side, mid) > SHOULDER:
                lo = mid
            else:
                hi = mid
        t = (lo + hi) / 2
    return t


def _stretch(pts, side, x: float) -> None:
    """Stretch the cubic `side` sideways about its far end, so its corner lands
    on x: heights stay, so the stroke's drop and its height at the face stay,
    and the far end's handle keeps its direction (a level one stays level)."""
    x0 = pts[side[3]].x
    if abs(pts[side[0]].x - x0) < 1:
        return
    k = (x - x0) / (pts[side[0]].x - x0)
    for idx in side[:3]:
        pts[idx].x = x0 + k * (pts[idx].x - x0)


def _spur_nodes(x_f, y_n, way, h, w, length, y_face, x_end, y_end, lip) -> list:
    """The spur on a vertical face at x_f: its outer edge carries the face on
    from the inner corner (x_f, y_n) `length` further in the direction way,
    its square end is `w` wide toward the stroke (h), and its inner edge
    meets the stroke's inner edge in the arm serifs' bracket: it leaves the
    spur BRACKET[0] of the spur's length short of the stroke (y_face is the
    stroke's edge over the spur's inner edge) and lands at (x_end, y_end).
    `lip` are points inside the stroke the contour returns through, so spur
    and stroke overlap."""
    x1 = x_f + h * w
    rise = BRACKET[0] * length
    run = x_end - x1
    nodes = [(x_f, y_n, True), (x_f, y_n + way * length, True), (x1, y_n + way * length, True),
             (x1, y_face + way * rise, True), (x1, y_face + way * 0.55 * rise, False),
             (x1 + 0.45 * run, y_end, False), (x_end, y_end, True)] + [(x, y, True) for x, y in lip]
    on = [(x, y) for x, y, keep in nodes if keep]
    area = sum(on[k - 1][0] * on[k][1] - on[k][0] * on[k - 1][1] for k in range(len(on)))
    return nodes if area > 0 else nodes[::-1]


def _room(font, g, x: float, y: float, way: int, most: float) -> float:
    """How far the white runs from (x, y) straight up (way 1) or down (-1)
    before it meets ink, looked for up to `most` units."""
    from fontTools.pens.pointInsidePen import PointInsidePen
    d = 4.0
    while d < most:
        pen = PointInsidePen(font, (x, y + way * d))
        g.draw(pen)
        if pen.getResult():
            return d
        d += 4.0
    return most


def cut_terminals(fonts, plan: dict, depth: float, reach: float) -> None:
    """Give every terminal plan_terminals found a moved beak.

    A level cut (the end of a curved stroke) becomes a vertical face at the
    letter's outer extreme. Its inner corner keeps its height. The stroke's
    outer edge is cut back to where it stands over that corner (`_face`),
    where it still runs at a slant, and both edges are then stretched
    sideways about their far ends until the corners stand at the old outer
    corner's x (FACE_OUT), so the stroke keeps its reach and runs out over
    the face. Edges are split by de Casteljau and stretched, so they stay
    single curves and every master keeps its points. An upright cut (the arm
    of r, the tails of j and y) is cut exactly upright through its middle,
    as in 0.2; one that leans too far for that in some master (the hook of
    f) is cut like a level one, at its back corner.

    The face then carries on past the stroke's inner edge as a spur: as wide
    as the master's serifs are thick (SERIF_DEPTH_SCALE, so Thin's holds and
    Black's stays light), reaching past the inner corner the stem serifs'
    reach (serif_reach of a Regular stem, scaled with the stem as theirs
    is, and shorter on a short cut, a superior's) times the letter's height
    over the x-height (BEAK_BY_HEIGHT), square-ended, with the
    arm serifs' bracket into the stroke's inner edge. A spur takes at most
    TERMINAL_ROOM of the white past its terminal. Every spur is its own
    contour, the same in every master, and a terminal takes one only where
    every master can cut it.
    """
    ref = fonts["Regular"]
    sw_ref = stem(ref)

    def crossbar(font) -> float:
        ys = sorted({round(pt.y) for c in font["H"].contours for pt in c.points if 0 < round(pt.y) < round(font["H"].getBounds(font).yMax)})
        return ys[-1] - ys[0] if len(ys) >= 2 else stem(font)
    sizes = {}
    for style, f in fonts.items():
        k = (stem(f) / sw_ref) ** SERIF_REACH_POWER
        t = depth * crossbar(f) * dict(zip(("Thin", "Regular", "Black"), SERIF_DEPTH_SCALE)).get(style, 1.0)
        sizes[style] = (t, k)

    xheight = {style: f["x"].getBounds(f).yMax for style, f in fonts.items()}
    heights = {}

    def _height(f, name):
        # the letter's height from the baseline (or its own foot, for a superior), before any end is cut
        if (id(f), name) not in heights:
            b = f[name].getBounds(f)
            heights[(id(f), name)] = b.yMax - max(b.yMin, 0.0)
        return heights[(id(f), name)]

    def face(f, name, term):
        kind, ci, i, j, outer, way, scale = term
        return _face(f[name].contours[ci].points, i, j, outer)

    # a terminal takes a beak only where every master can cut it
    kept = {}
    for name, terms in plan.items():
        for term in terms:
            if term[0] == "upright":
                if all(_upright(copy.deepcopy(f[name].contours[term[1]].points), *term[2:5]) for f in fonts.values()):
                    kept.setdefault(name, []).append(term)
                    continue
                # cut like a level one, its outer corner the one the spur does not grow from
                kind, ci, i, j, outer, way, scale = term
                term = ("leaning", ci, i, j, j if outer == i else i, way, scale)
            if all(face(f, name, term) is not None for f in fonts.values()):
                kept.setdefault(name, []).append(term)
    for f in fonts.values():
        for name in kept:
            _height(f, name)
    for style, f in fonts.items():
        t, k = sizes[style]
        for name, terms in kept.items():
            g = f[name]
            shapes = []
            for term in terms:
                kind, ci, i, j, outer, way, scale = term
                pts = g.contours[ci].points
                a, q = pts[i], pts[j]
                if kind == "upright":
                    _upright(pts, i, j, outer)
                    for pt in (a, q):
                        pt.x = (a.x + q.x) / 2
                    spur_at = outer
                    toward = pts[(spur_at + (-1 if spur_at == i else 1)) % len(pts)].x
                else:
                    t_out = _face(pts, i, j, outer)
                    o_side, n_side = _edges(pts, i, j, outer)
                    x_in, x_out = pts[n_side[0]].x, pts[outer].x
                    _trim(pts, o_side, t_out)
                    x_f = x_in + FACE_OUT * (x_out - x_in)
                    _stretch(pts, o_side, x_f)
                    _stretch(pts, n_side, x_f)
                    for pt in (a, q):
                        pt.x = x_f
                    spur_at = n_side[0]  # the spur grows from the inner corner
                    # toward the stroke: its inner edge's far end (its handle may stand straight over the corner, as in 2)
                    toward = pts[n_side[3]].x
                x_f = a.x
                w = BEAK_WIDTH * t * scale
                length = BEAK_REACH * reach * sw_ref * k * scale * (_height(f, name) / xheight[style]) ** BEAK_BY_HEIGHT
                run = BRACKET[1] * w
                o = pts[spur_at]
                step = -1 if spur_at == i else 1
                h = 1 if toward > x_f else -1
                x1, x2 = x_f + h * w, x_f + h * (w + run)
                length = min(length, TERMINAL_ROOM * _room(f, g, x_f + h * w / 2, _walk_to_x(pts, spur_at, step, x_f + h * w / 2), way, 3 * length))
                dip = 0.3 * abs(q.y - a.y)
                y2 = _walk_to_x(pts, spur_at, step, x2)
                shapes.append(_spur_nodes(x_f, o.y, way, h, w, length, _walk_to_x(pts, spur_at, step, x1), x2, y2,
                                          [(x2, y2 - way * dip), (x_f, o.y - way * dip)]))
            for nodes in shapes:
                g.appendContour(_contour(nodes))
            if shapes:
                g.lib["public.truetype.overlap"] = True
        flag_overlaps(f)

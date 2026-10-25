"""End treatments for Katagami Serif's terminals that keep Text's curve exactly (lab only).

The upright face that was built stretched the end of the stroke sideways to reach the old outer
extreme; without a spur Kevin read that as warped. Every option here keeps each edge a piece of
its own curve (split, or carried on along its own cubic), and moves no point off it:

  A  Text's terminal: the level cut, untouched.
  B  An upright cut over the level cut's inner corner: the outer edge is trimmed where it stands
     over that corner, nothing is stretched. An upright cut (r, j, y) is cut upright through its
     middle; f's hook, which leans, at its back corner.
  C  A cut turned halfway from Text's toward square to the stroke, through the cut's middle:
     each edge is split, or carried on along its own curve, where it crosses the new line.
  D  Text's level cut with a small square facet at its outer corner, as tall as the stem serifs
     are thick: the outer edge is trimmed where it reaches that height and the corner becomes a
     short face square to the cut. The facet's foot is a new point, added after the stem serifs
     are cut (their plan holds point numbers), the same in every master.

cut(fonts, plan, option) runs where build_sans.cut_terminals does; after_serifs(fonts, plan,
option) after cut_serifs, for D."""
from __future__ import annotations

import math
import sys
from pathlib import Path

from ufoLib2.objects import Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_sans as B  # noqa: E402

LABELS = {"A": "A  Text's level cut", "B": "B  upright cut, no stretch", "C": "C  cut turned halfway to square",
          "D": "D  level cut, square facet"}
FACET = 1.0  # D: the facet's height, as a share of the master's stem serif thickness


def _side_curve(pts, side):
    return [(pts[k].x, pts[k].y) for k in side]


def _tangent_out(pts, side):
    """The edge's direction arriving at its corner (from its handle to the corner), as a unit vector."""
    c, h = pts[side[0]], pts[side[1]]
    dx, dy = c.x - h.x, c.y - h.y
    if math.hypot(dx, dy) < 1e-6:
        h = pts[side[2]]
        dx, dy = c.x - h.x, c.y - h.y
    d = math.hypot(dx, dy) or 1.0
    return dx / d, dy / d


def _crossing(c, side_fn, lo, hi):
    """The parameter in lo..hi nearest the corner end where the cubic c (corner first) crosses the line."""
    steps = 120
    ts = [lo + (hi - lo) * k / steps for k in range(steps + 1)]
    vals = [side_fn(B._point(c, t)) for t in ts]
    best = None
    for k in range(steps):
        if vals[k] == 0 or vals[k] * vals[k + 1] < 0:
            a, b = ts[k], ts[k + 1]
            for _ in range(50):
                m = (a + b) / 2
                if side_fn(B._point(c, a)) * side_fn(B._point(c, m)) <= 0:
                    b = m
                else:
                    a = m
            t = (a + b) / 2
            if best is None or abs(t) < abs(best):
                best = t
    return best


def _recut_line(pts, sides, through, direction) -> bool:
    """Split each edge (corner first) where it crosses the line through `through` along
    `direction`, trimming it or carrying it on along its own cubic (t below 0)."""
    side_fn = lambda p: (p[0] - through[0]) * direction[1] - (p[1] - through[1]) * direction[0]  # noqa: E731
    ts = []
    for side in sides:
        t = _crossing(_side_curve(pts, side), side_fn, -0.45, 0.6)
        if t is None:
            return False
        ts.append(t)
    for side, t in zip(sides, ts):
        c = _side_curve(pts, side)
        _, rest = B._split(c, t)
        for k, (x, y) in zip(side[:3], rest[:3]):
            pts[k].x, pts[k].y = x, y
    return True


def _sides(pts, kind, i, j, outer):
    """(outer edge, inner edge) as cubics from their corners, or None."""
    if kind in ("upright", "leaning"):
        outer = j if outer == i else i  # an upright term records the corner the spur grew from
    return B._edges(pts, i, j, outer), outer


def plan_ok(fonts, plan, option):
    """The terms every master can cut with this option. An upright cut that some master
    cannot cut exactly upright (the hook of f) is cut as a leaning one in every master."""
    import copy
    kept = {}
    for name, terms in plan.items():
        for term in terms:
            if term[0] == "upright" and not all(B._upright(copy.deepcopy(f[name].contours[term[1]].points), *term[2:5])
                                                for f in fonts.values()):
                term = ("leaning",) + tuple(term[1:])
            if all(_cut_one(copy.deepcopy(f[name].contours[term[1]].points), term, option, f) for f in fonts.values()):
                kept.setdefault(name, []).append(term)
    return kept


def _cut_one(pts, term, option, font) -> bool:
    kind, ci, i, j, outer, way, scale = term
    a, q = pts[i], pts[j]
    if option == "A":
        return True
    if option == "B":
        if kind == "upright" and B._upright(pts, i, j, outer):
            for pt in (a, q):
                pt.x = (a.x + q.x) / 2
            return True
        o = outer if kind == "level" else (j if outer == i else i)  # an upright term records its other corner
        sides = B._edges(pts, i, j, o)
        if sides is None:
            return False
        o_side, n_side = sides
        corner = pts[n_side[0]]
        hit = B._at_x(pts, o_side, corner.x)
        if hit is None:
            return False
        B._trim(pts, o_side, hit[0])
        pts[o_side[0]].x = corner.x
        return True
    if option == "C":
        sides, o = _sides(pts, kind, i, j, outer)
        if sides is None:
            return False
        o_side, n_side = sides
        u, v = _tangent_out(pts, o_side), _tangent_out(pts, n_side)
        sx, sy = u[0] + v[0], u[1] + v[1]
        stroke = math.degrees(math.atan2(sy, sx))
        square = stroke + 90.0
        now = math.degrees(math.atan2(q.y - a.y, q.x - a.x))
        diff = (square - now + 90.0) % 180.0 - 90.0  # the shorter turn between two undirected lines
        ang = math.radians(now + 0.5 * diff)
        mid = ((a.x + q.x) / 2, (a.y + q.y) / 2)
        return _recut_line(pts, (o_side, n_side), mid, (math.cos(ang), math.sin(ang)))
    if option == "D":
        sides, o = _sides(pts, kind, i, j, outer)
        return sides is not None
    raise ValueError(option)


def cut(fonts, plan, option):
    """Options A, B and C, before the stem serifs; returns the terms cut."""
    kept = plan_ok(fonts, plan, option)
    if option in ("A", "D"):
        return kept
    for f in fonts.values():
        for name, terms in kept.items():
            for term in terms:
                _cut_one(f[name].contours[term[1]].points, term, option, f)
    return kept


def _facet(pts, term, t) -> bool:
    """D on one term: trim the outer edge where it stands t from the cut's line and set a
    square face from there down to the cut, its foot a new point between the corners."""
    kind, ci, i, j, outer, way, scale = term
    sides, o = _sides(pts, kind, i, j, outer)
    if sides is None:
        return False
    o_side, n_side = sides
    oc = Point(pts[o_side[0]].x, pts[o_side[0]].y)  # a copy: the trim moves the corner itself
    nc = pts[n_side[0]]
    L = math.hypot(nc.x - oc.x, nc.y - oc.y)
    ux, uy = (nc.x - oc.x) / L, (nc.y - oc.y) / L  # along the cut, outer to inner
    nx, ny = -uy, ux  # square to the cut, into the stroke: toward the outer edge's far end
    far = pts[o_side[3]]
    if (far.x - oc.x) * nx + (far.y - oc.y) * ny < 0:
        nx, ny = -nx, -ny
    h = min(t, 0.45 * L)
    fn = lambda p: (p[0] - oc.x) * nx + (p[1] - oc.y) * ny - h  # noqa: E731
    tt = _crossing(_side_curve(pts, o_side), fn, 0.0, 0.95)
    if tt is None:
        return False
    B._trim(pts, o_side, tt)
    top = pts[o_side[0]]
    d = (top.x - oc.x) * ux + (top.y - oc.y) * uy
    foot = Point(oc.x + d * ux, oc.y + d * uy, "line")
    lo, hi = sorted((i, j))
    if (lo, hi) == (0, len(pts) - 1):
        pts.append(foot)
    else:
        pts.insert(hi, foot)
    return True


def after_serifs(fonts, kept, option, depth):
    """Option D: a square facet at each cut's outer corner, after the stem serifs, only
    where every master can cut it."""
    if option != "D":
        return
    import copy

    def crossbar(font):
        ys = sorted({round(pt.y) for c in font["H"].contours for pt in c.points if 0 < round(pt.y) < round(font["H"].getBounds(font).yMax)})
        return ys[-1] - ys[0] if len(ys) >= 2 else B.stem(font)
    thick = {style: depth * crossbar(f) * dict(zip(("Thin", "Regular", "Black"), B.SERIF_DEPTH_SCALE)).get(style, 1.0) * FACET
             for style, f in fonts.items()}
    ok = {name: [tm for tm in terms if all(_facet(copy.deepcopy(f[name].contours[tm[1]].points), tm, thick[s])
                                           for s, f in fonts.items())] for name, terms in kept.items()}
    for style, f in fonts.items():
        for name, terms in ok.items():
            # later points first, so earlier numbers stay valid
            for term in sorted(terms, key=lambda tm: (tm[1], -max(tm[2], tm[3]))):
                _facet(f[name].contours[term[1]].points, term, thick[style])

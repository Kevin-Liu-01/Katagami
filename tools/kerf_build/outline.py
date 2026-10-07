"""Point-preserving outline transforms.

Every function here moves points and never adds or removes them, so a
transform applied to each master keeps the masters interpolation-compatible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ufoLib2.objects import Contour, Glyph


def signed_area(contour: Contour) -> float:
    pts = contour.points
    return 0.5 * sum(
        pts[i - 1].x * pts[i].y - pts[i].x * pts[i - 1].y for i in range(len(pts))
    )


def bounds(glyph: Glyph, font) -> tuple[float, float, float, float] | None:
    return glyph.getBounds(font)


# --- Curve squaring -------------------------------------------------------
#
# A cubic quarter arc from P0 to P3 has handles C1, C2 that lie on the
# tangents. K is where the two tangents meet (the corner of the arc's box).
# The handle fraction f = |C1 - P0| / |K - P0| sets the shape: 0.552 is a
# circle, Inter sits near 0.60 (superellipse n ~ 2.16), Camber near 0.73-0.76
# (n ~ 2.7-2.85). Squaring moves f toward 1 by a fraction s.


@dataclass(frozen=True)
class SegmentRef:
    contour: int
    c1: int  # index of first off-curve point
    c2: int
    p0: int
    p3: int


def _intersect(p, d, q, e):
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    a = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    b = ((q[0] - p[0]) * d[1] - (q[1] - p[1]) * d[0]) / den
    return a, b


def _segment_fractions(contour: Contour, seg: SegmentRef):
    pts = contour.points
    p0, c1, c2, p3 = pts[seg.p0], pts[seg.c1], pts[seg.c2], pts[seg.p3]
    t0 = (c1.x - p0.x, c1.y - p0.y)
    t1 = (c2.x - p3.x, c2.y - p3.y)
    if math.hypot(*t0) < 1 or math.hypot(*t1) < 1:
        return None
    hit = _intersect((p0.x, p0.y), t0, (p3.x, p3.y), t1)
    if hit is None:
        return None
    a, b = hit
    if a <= 1 or b <= 1:
        return None
    cos = (t0[0] * t1[0] + t0[1] * t1[1]) / (math.hypot(*t0) * math.hypot(*t1))
    return 1 / a, 1 / b, cos


def curve_segments(contour: Contour) -> list[SegmentRef]:
    pts = contour.points
    n = len(pts)
    out = []
    for i, p in enumerate(pts):
        if p.type == "curve":
            c2, c1, p0 = (i - 1) % n, (i - 2) % n, (i - 3) % n
            if pts[c1].type is None and pts[c2].type is None and pts[p0].type:
                out.append(SegmentRef(-1, c1, c2, p0, i))
    return out


def plan_squaring(glyph: Glyph) -> list[tuple[int, SegmentRef, bool]]:
    """Choose which segments to square, from the reference master.

    Returns (contour index, segment, is_counter). Only near-quarter arcs
    whose handles look circular qualify; flat curves and tight joins are left.
    """
    plan = []
    for ci, contour in enumerate(glyph.contours):
        counter = signed_area(contour) < 0
        for seg in curve_segments(contour):
            fr = _segment_fractions(contour, seg)
            if fr is None:
                continue
            f0, f1, cos = fr
            if abs(cos) > 0.5:  # tangents not roughly perpendicular
                continue
            if not (0.35 < f0 < 0.85 and 0.35 < f1 < 0.85):
                continue
            plan.append((ci, seg, counter))
    return plan


def apply_squaring(glyph: Glyph, plan, s_outer: float, s_inner: float, join: float = 1.0) -> None:
    """Square each planned arc. A handle anchored on a corner point (where a
    curve meets a stem) gets `join` times the strength, so the curve eases
    into the stem instead of cutting a deep notch at the join."""
    for ci, seg, counter in plan:
        contour = glyph.contours[ci]
        fr = _segment_fractions(contour, seg)
        if fr is None:
            continue
        f0, f1, _ = fr
        s = s_inner if counter else s_outer
        pts = contour.points
        for fi, ci_, pi in ((f0, seg.c1, seg.p0), (f1, seg.c2, seg.p3)):
            k_s = s if pts[pi].smooth else s * join
            target = fi + k_s * (1 - fi)
            k = target / fi
            c, p = pts[ci_], pts[pi]
            c.x = p.x + (c.x - p.x) * k
            c.y = p.y + (c.y - p.y) * k


# --- Horizontal emboldening ----------------------------------------------
# Port of FreeType's FT_Outline_EmboldenXY with ystrength = 0. Edges move
# outward by strength/2 on each side; negative strength thins.


def embolden_x(glyph: Glyph, strength: float) -> None:
    half = strength / 2
    for contour in glyph.contours:
        pts = contour.points
        n = len(pts)
        if n < 3:
            continue
        # UFO outlines are PostScript-oriented (outer contours counter-clockwise).
        orig = [(p.x, p.y) for p in pts]
        new_x = []
        for i in range(n):
            prv, cur, nxt = orig[i - 1], orig[i], orig[(i + 1) % n]
            vin = (cur[0] - prv[0], cur[1] - prv[1])
            vout = (nxt[0] - cur[0], nxt[1] - cur[1])
            l_in, l_out = math.hypot(*vin), math.hypot(*vout)
            if l_in < 1e-6 or l_out < 1e-6:
                # degenerate: borrow the neighbour that has length
                j = i
                while l_in < 1e-6 and j > i - n:
                    j -= 1
                    prv = orig[j % n]
                    vin = (cur[0] - prv[0], cur[1] - prv[1])
                    l_in = math.hypot(*vin)
                j = i
                while l_out < 1e-6 and j < i + n:
                    j += 1
                    nxt = orig[j % n]
                    vout = (nxt[0] - cur[0], nxt[1] - cur[1])
                    l_out = math.hypot(*vout)
                if l_in < 1e-6 or l_out < 1e-6:
                    new_x.append(cur[0])
                    continue
            ix, iy = vin[0] / l_in, vin[1] / l_in
            ox, oy = vout[0] / l_out, vout[1] / l_out
            d = ix * ox + iy * oy
            shift = 0.0
            if d > -0.9375:
                d += 1
                sx = iy + oy  # lateral bisector, PostScript orientation
                q = ox * iy - oy * ix
                l = min(l_in, l_out)
                if abs(half) * q <= l * d:
                    shift = sx * half / d
                else:
                    shift = sx * l / q * (1 if half >= 0 else -1)
            new_x.append(cur[0] + shift)
        for p, x in zip(pts, new_x):
            p.x = x


# --- Horizontal remapping ------------------------------------------------


@dataclass(frozen=True)
class XMap:
    """x -> new_origin + scale * (x - old_origin)."""

    old_origin: float
    new_origin: float
    scale: float

    def __call__(self, x: float) -> float:
        return self.new_origin + self.scale * (x - self.old_origin)

    def shifted(self, dx: float) -> "XMap":
        """The same map seen from a glyph that places this one at offset dx."""
        return XMap(self.old_origin + dx, self.new_origin + dx, self.scale)


IDENTITY = XMap(0, 0, 1)


def scale_contours_x(glyph: Glyph, xmap: XMap) -> None:
    for contour in glyph.contours:
        for p in contour.points:
            p.x = xmap(p.x)
    for a in glyph.anchors:
        a.x = xmap(a.x)

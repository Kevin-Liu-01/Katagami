"""Point-preserving outline transforms.

Every function here moves points and never adds or removes them, so a
transform applied to each master keeps the masters interpolation-compatible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ufoLib2.objects import Contour, Glyph, Point


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


def plan_squaring(glyph: Glyph, tight: float = 0.0) -> list[tuple[int, SegmentRef, bool, float]]:
    """Choose which segments to square, from the reference master.

    Returns (contour index, segment, is_counter, strength factor). Only
    near-quarter arcs whose handles look circular qualify. An arc whose
    radius is under `tight` units (the hooks of f, t, j and r) gets a
    factor below 1 in proportion, so small curves stay supple.
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
            pts = contour.points
            p0, p3, c1, c2 = pts[seg.p0], pts[seg.p3], pts[seg.c1], pts[seg.c2]
            radius = min(math.hypot(c1.x - p0.x, c1.y - p0.y) / f0, math.hypot(c2.x - p3.x, c2.y - p3.y) / f1)
            factor = min(1.0, radius / tight) if tight else 1.0
            plan.append((ci, seg, counter, factor))
    return plan


def apply_squaring(glyph: Glyph, plan, s_outer: float, s_inner: float, join: float = 1.0) -> None:
    """Square each planned arc. A handle anchored on a corner point (where a
    curve meets a stem) gets `join` times the strength, so the curve eases
    into the stem instead of cutting a deep notch at the join."""
    for ci, seg, counter, factor in plan:
        contour = glyph.contours[ci]
        fr = _segment_fractions(contour, seg)
        if fr is None:
            continue
        f0, f1, _ = fr
        s = (s_inner if counter else s_outer) * factor
        pts = contour.points
        for fi, ci_, pi in ((f0, seg.c1, seg.p0), (f1, seg.c2, seg.p3)):
            k_s = s if pts[pi].smooth else s * join
            target = fi + k_s * (1 - fi)
            k = target / fi
            c, p = pts[ci_], pts[pi]
            c.x = p.x + (c.x - p.x) * k
            c.y = p.y + (c.y - p.y) * k


# --- Stroke width --------------------------------------------------------
# The stroke's width at points along the outline: from each point a ray runs
# inward (in PostScript-oriented outlines the ink lies left of the direction
# of travel) to where it leaves the ink. Points near sharp corners are left
# out, where the ray would meet the neighbouring edge at once.


def _polylines(glyph: Glyph, steps: int = 12):
    """Edges of every contour, flattened: start and end points, and the key of
    the curve segment each edge comes from (contour * 10000 + its end point),
    or -1 for straight segments."""
    A, B, keys = [], [], []
    for ci, contour in enumerate(glyph.contours):
        pts = contour.points
        n = len(pts)
        start = next((i for i, q in enumerate(pts) if q.type), None)
        if start is None or n < 2:
            continue
        prev, off = pts[start], []
        for k in range(1, n + 1):
            idx = (start + k) % n
            q = pts[idx]
            if q.type is None:
                off.append(q)
                continue
            if q.type == "curve" and len(off) == 2:
                (ax, ay), (bx, by), (cx, cy), (dx, dy) = ((t.x, t.y) for t in (prev, off[0], off[1], q))
                last = (ax, ay)
                for j in range(1, steps + 1):
                    t = j / steps
                    u = 1 - t
                    nxt = (u**3 * ax + 3 * u * u * t * bx + 3 * u * t * t * cx + t**3 * dx,
                           u**3 * ay + 3 * u * u * t * by + 3 * u * t * t * cy + t**3 * dy)
                    A.append(last); B.append(nxt); keys.append(ci * 10000 + idx)
                    last = nxt
            else:
                A.append((prev.x, prev.y)); B.append((q.x, q.y)); keys.append(-1)
            prev, off = q, []
    return np.array(A, float).reshape(-1, 2), np.array(B, float).reshape(-1, 2), np.array(keys)


def _winding(Q, A, B):
    """Nonzero winding number of each point in Q around the edges A to B."""
    ay, by = A[None, :, 1], B[None, :, 1]
    qx, qy = Q[:, None, 0], Q[:, None, 1]
    side = (B[None, :, 0] - A[None, :, 0]) * (qy - ay) - (qx - A[None, :, 0]) * (by - ay)
    up = (ay <= qy) & (by > qy) & (side > 0)
    down = (by <= qy) & (ay > qy) & (side < 0)
    return up.sum(1) - down.sum(1)


def stroke_widths(glyph: Glyph, step: float = 6.0, corner: float = 35.0, skip: float = 12.0):
    """Width, own segment key and hit segment key at points along the outline."""
    A, B, keys = _polylines(glyph)
    if not len(A):
        return np.zeros(0), np.zeros(0, int), np.zeros(0, int)
    E = B - A
    L = np.hypot(E[:, 0], E[:, 1])
    keep = L > 1e-6
    A, B, E, L, keys = A[keep], B[keep], E[keep], L[keep], keys[keep]
    T = E / L[:, None]
    # corners: where one edge turns into the next by more than `corner` degrees
    nxt = np.roll(T, -1, axis=0)
    turn = np.degrees(np.arccos(np.clip((T * nxt).sum(1), -1, 1)))
    joined = np.hypot(*(np.roll(A, -1, axis=0) - B).T) < 1e-6
    corners = B[(turn > corner) & joined]
    # samples every `step` units along each edge
    count = np.maximum(1, (L // step).astype(int))
    e = np.repeat(np.arange(len(A)), count)
    t = (np.concatenate([np.arange(c) for c in count]) + 0.5) / np.repeat(count, count)
    P = A[e] + E[e] * t[:, None]
    N = np.stack([-T[e, 1], T[e, 0]], axis=1)
    ok = np.ones(len(P), bool)
    if len(corners):
        ok &= np.hypot(*(P[:, None, :] - corners[None]).transpose(2, 0, 1)).min(1) > skip
    ok &= _winding(P - N * 0.75, A, B) == 0  # an edge inside the ink (an overlap) has no width
    P, N, own = P[ok], N[ok], keys[e[ok]]
    W = A[None] - P[:, None]
    den = N[:, None, 0] * E[None, :, 1] - N[:, None, 1] * E[None, :, 0]
    safe = np.where(np.abs(den) < 1e-9, 1e-9, den)
    tt = (W[..., 0] * E[None, :, 1] - W[..., 1] * E[None, :, 0]) / safe
    uu = (W[..., 0] * N[:, None, 1] - W[..., 1] * N[:, None, 0]) / safe
    tt = np.where((np.abs(den) > 1e-9) & (tt > 0.5) & (uu >= 0) & (uu <= 1), tt, np.inf)
    width = np.full(len(P), np.inf)
    hit = np.full(len(P), -1)
    for _ in range(4):  # the first crossing that leaves the ink; overlaps can hide it behind others
        j = tt.argmin(1)
        tj = tt[np.arange(len(P)), j]
        out = _winding(P + N * (np.where(np.isfinite(tj), tj, 0) + 0.75)[:, None], A, B) == 0
        done = np.isfinite(tj) & out & ~np.isfinite(width)
        width[done], hit[done] = tj[done], keys[j[done]]
        tt[np.arange(len(P)), j] = np.where(out, tt[np.arange(len(P)), j], np.inf)
        if not (np.isfinite(tj) & ~out).any():
            break
    found = np.isfinite(width)
    return width[found], own[found], hit[found]


def handles(glyph: Glyph, plan) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    out = []
    for ci, seg, *_ in plan:
        pts = glyph.contours[ci].points
        out.append(((pts[seg.c1].x, pts[seg.c1].y), (pts[seg.c2].x, pts[seg.c2].y)))
    return out


def keep_stroke(glyph: Glyph, plan, before, floor: float) -> int:
    """Give back the squaring of the planned arcs that thin a stroke under `floor`.

    `before` holds the handles from before squaring (`handles`). The arcs
    that the thin points lie on or look across to move back toward their
    unsquared shape by the least share that brings the stroke to `floor`, or
    to what the unsquared outline had if that was less. Returns the number of
    arcs moved.
    """
    after = handles(glyph, plan)
    keys = [ci * 10000 + seg.p3 for ci, seg, *_ in plan]
    w, own, hit = stroke_widths(glyph)
    thin = w < floor
    involved = (set(own[thin].tolist()) | set(hit[thin].tolist())) & set(keys)
    if not involved:
        return 0
    idx = [i for i, k in enumerate(keys) if k in involved]
    look = list(involved)

    def width(share: float) -> float:
        for i in idx:
            ci, seg, *_ = plan[i]
            pts = glyph.contours[ci].points
            for pi, (b, a) in ((seg.c1, (before[i][0], after[i][0])), (seg.c2, (before[i][1], after[i][1]))):
                pts[pi].x = b[0] + (a[0] - b[0]) * share
                pts[pi].y = b[1] + (a[1] - b[1]) * share
        w, own, hit = stroke_widths(glyph)
        m = np.isin(own, look) | np.isin(hit, look)
        return float(w[m].min()) if m.any() else math.inf

    target = min(floor, 0.95 * width(0.0))
    lo, hi = 0.0, 1.0
    for _ in range(7):
        mid = (lo + hi) / 2
        if width(mid) >= target:
            lo = mid
        else:
            hi = mid
    width(lo)
    return len(idx)


# --- Horizontal emboldening ----------------------------------------------
# Port of FreeType's FT_Outline_EmboldenXY with ystrength = 0. Edges move
# outward by strength/2 on each side; negative strength thins.


def _embolden(glyph: Glyph, strength: float, axis: int) -> None:
    """FreeType-style emboldening along one axis (0 = x, 1 = y): every edge
    moves outward by half the strength, so stems (x) or horizontal strokes (y)
    gain `strength` in thickness and the outline grows by it on that axis."""
    half = strength / 2
    for contour in glyph.contours:
        pts = contour.points
        n = len(pts)
        if n < 3:
            continue
        # UFO outlines are PostScript-oriented (outer contours counter-clockwise).
        orig = [(p.x, p.y) for p in pts]
        new = []
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
                    new.append(cur[axis])
                    continue
            ix, iy = vin[0] / l_in, vin[1] / l_in
            ox, oy = vout[0] / l_out, vout[1] / l_out
            d = ix * ox + iy * oy
            shift = 0.0
            if d > -0.9375:
                d += 1
                # lateral bisector, PostScript orientation: x outward is +(iy + oy), y outward is -(ix + ox)
                lateral = iy + oy if axis == 0 else -(ix + ox)
                q = ox * iy - oy * ix
                l = min(l_in, l_out)
                if abs(half) * q <= l * d:
                    shift = lateral * half / d
                else:
                    shift = lateral * l / q * (1 if half >= 0 else -1)
            new.append(cur[axis] + shift)
        for p, v in zip(pts, new):
            if axis == 0:
                p.x = v
            else:
                p.y = v


def embolden_x(glyph: Glyph, strength: float) -> None:
    _embolden(glyph, strength, 0)


def embolden_y(glyph: Glyph, strength: float) -> None:
    _embolden(glyph, strength, 1)


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


# --- Rounded vertices ------------------------------------------------------
# A sharp on-curve corner becomes a short quarter-ish arc: the corner point is
# replaced by an entry point, two handles and an exit point. Which corners to
# round is decided once (on Regular) so every master gains the same points.

KAPPA = 0.5523


def _unit(dx: float, dy: float):
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-6 else None


def plan_corners(glyph: Glyph, min_turn: float = 20.0) -> list[tuple[int, list[int]]]:
    """Per contour, the convex corners that turn by at least min_turn degrees.

    Only outer vertices (stem ends, terminals, apexes) are rounded; concave
    joins, where a crossbar or bowl meets a stem, stay crisp.
    """
    plan = []
    for ci, c in enumerate(glyph.contours):
        pts = c.points
        n = len(pts)
        orient = 1 if signed_area(c) >= 0 else -1
        idx = []
        for i, p in enumerate(pts):
            if p.type is None or p.smooth or n < 3:
                continue
            a, b = pts[i - 1], pts[(i + 1) % n]
            din, dout = _unit(p.x - a.x, p.y - a.y), _unit(b.x - p.x, b.y - p.y)
            if din is None or dout is None:
                continue
            cos = max(-1.0, min(1.0, din[0] * dout[0] + din[1] * dout[1]))
            cross = din[0] * dout[1] - din[1] * dout[0]
            if math.degrees(math.acos(cos)) >= min_turn and cross * orient > 0:
                idx.append(i)
        if idx:
            plan.append((ci, idx))
    return plan


def round_corners(glyph: Glyph, plan, radius: float) -> None:
    """Replace each planned corner by an arc of `radius` units (0 keeps the shape)."""
    for ci, idx in plan:
        pts = glyph.contours[ci].points
        for i in sorted(idx, reverse=True):
            n = len(pts)
            p, a, b = pts[i], pts[i - 1], pts[(i + 1) % n]
            to_a, to_b = _unit(a.x - p.x, a.y - p.y), _unit(b.x - p.x, b.y - p.y)
            if to_a is None or to_b is None:
                to_a = to_b = (0.0, 0.0)
            r = min(radius, 0.45 * math.hypot(a.x - p.x, a.y - p.y), 0.45 * math.hypot(b.x - p.x, b.y - p.y))
            ax, ay = p.x + to_a[0] * r, p.y + to_a[1] * r
            bx, by = p.x + to_b[0] * r, p.y + to_b[1] * r
            k = 1 - KAPPA
            new = [
                Point(ax, ay, p.type, smooth=True),
                Point(p.x + to_a[0] * r * k, p.y + to_a[1] * r * k, None),
                Point(p.x + to_b[0] * r * k, p.y + to_b[1] * r * k, None),
                Point(bx, by, "curve", smooth=True),
            ]
            pts[i:i + 1] = new

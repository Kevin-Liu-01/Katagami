"""Contour repairs on a finished variable font that keep every instance's
filled shape: segments that two contours share, and duplicate contours and
points.

A glyph's outline at a location is its glyf points plus the gvar deltas there,
with the deltas a variation leaves out inferred (IUP) from the points around
them. A changed glyph keeps that pattern: only the points that move get new
deltas, and a change is kept only when the filled shape (nonzero winding,
overlaps resolved) the font itself will draw is the same as before.
"""

from __future__ import annotations

import pathops
from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import (
    OVERLAP_COMPOUND, USE_MY_METRICS, Glyph, GlyphCoordinates, flagOnCurve, flagOverlapSimple,
)
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.iup import iup_delta
from fontTools.varLib.models import supportScalar

SAME_FILL = 0.5  # largest area, in square units, by which two filled shapes may differ and count as one
STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))  # a shared segment moves one unit along an axis


class Outline:
    """A simple glyph as plain lists: default points, on-curve flags, contour
    ends, and per variation region a delta for each point and the four phantom
    points, None where the font infers it."""

    def __init__(self, coords, flags, ends, deltas: dict, overlap: bool):
        self.coords = [tuple(p) for p in coords]
        self.flags = [1 if f & flagOnCurve else 0 for f in flags]
        self.ends = list(ends)
        self.deltas = {k: [None if d is None else tuple(d) for d in v] for k, v in deltas.items()}
        self.overlap = overlap
        self._filled = {}

    def copy(self) -> Outline:
        return Outline(self.coords, self.flags, self.ends, self.deltas, self.overlap)

    def contours(self) -> list[range]:
        start, out = 0, []
        for end in self.ends:
            out.append(range(start, end + 1))
            start = end + 1
        return out

    def filled(self, key) -> list[tuple]:
        """A region's deltas with the inferred ones worked out, as the rasterizer does."""
        if key not in self._filled:
            v = self.deltas[key]
            self._filled[key] = iup_delta(v, self.coords + [(0, 0)] * 4, self.ends) if None in v else list(v)
        return self._filled[key]

    def at(self, loc: dict) -> list[tuple]:
        """The points at a normalized location."""
        pts = [list(p) for p in self.coords]
        for key in self.deltas:
            s = supportScalar(loc, dict(key))
            if s:
                for p, d in zip(pts, self.filled(key)):
                    p[0] += s * d[0]
                    p[1] += s * d[1]
        return [tuple(p) for p in pts]

    def drop(self, points: set[int]) -> None:
        """Remove points, and a contour left with none."""
        keep = [i for i in range(len(self.coords)) if i not in points]
        ends, start = [], 0
        for end in self.ends:
            n = sum(1 for i in range(start, end + 1) if i not in points)
            if n:
                ends.append((ends[-1] if ends else -1) + n)
            start = end + 1
        self.coords = [self.coords[i] for i in keep]
        self.flags = [self.flags[i] for i in keep]
        self.ends = ends
        self.deltas = {k: [v[i] for i in keep] + v[-4:] for k, v in self.deltas.items()}
        self._filled = {}

    def move(self, points, step, fade: bool = False, infer: bool = False) -> None:
        """Move points by a step at the default. Faded, their deltas take the
        step back, so they stay put at every master; otherwise they keep their
        deltas, and a point whose delta was inferred either stays inferred
        (`infer`) or takes its inferred delta, rounded."""
        old = {k: self.filled(k) for k in self.deltas}
        for k, v in self.deltas.items():
            for i in points:
                if fade:
                    d = old[k][i]
                    v[i] = (otRound(d[0] - step[0]), otRound(d[1] - step[1]))
                elif v[i] is None and not infer:
                    v[i] = (otRound(old[k][i][0]), otRound(old[k][i][1]))
        for i in points:
            self.coords[i] = (self.coords[i][0] + step[0], self.coords[i][1] + step[1])
        self._filled = {}

    def insert(self, after: int, points: list[tuple], deltas: dict) -> None:
        """Insert on-curve points after point `after`, in its contour."""
        pos, n = after + 1, len(points)
        self.coords[pos:pos] = points
        self.flags[pos:pos] = [1] * n
        self.ends = [e + n if e >= after else e for e in self.ends]
        for k, v in self.deltas.items():
            v[pos:pos] = deltas[k]
        self._filled = {}

    def cover(self, keys) -> None:
        """A delta list for every region the font varies over, inferred (zero) where the glyph had none."""
        for k in keys:
            self.deltas.setdefault(k, [None] * (len(self.coords) + 4))
        self._filled = {}


def _raw(font: TTFont, name: str) -> dict:
    """A glyph's gvar deltas by region, None where inferred."""
    out = {}
    if "gvar" not in font:
        return out
    for v in font["gvar"].variations.get(name, []):
        key = tuple(sorted(v.axes.items()))
        if key in out:
            raise ValueError(f"{name}: two variations for one region")
        out[key] = list(v.coordinates)
    return out


def load(font: TTFont, name: str) -> Outline | None:
    """The simple glyph `name`, or None for a composite or an empty glyph."""
    g = font["glyf"][name]
    if g.isComposite() or g.numberOfContours <= 0:
        return None
    return Outline(g.coordinates, g.flags, g.endPtsOfContours, _raw(font, name),
                   any(f & flagOverlapSimple for f in g.flags))


def decompose(font: TTFont, name: str) -> Outline | None:
    """A composite of plain components (offsets only, no transform, no point
    matching) as one simple glyph: each component's points moved by its
    offset, and at every location by the offset's delta too, so a contour
    the component's deltas leave wholly inferred takes the offset's delta at
    every point. None when a component is transformed, matched by points or
    itself a composite."""
    glyf = font["glyf"]
    comps = glyf[name].components
    if any(getattr(c, "transform", None) is not None or hasattr(c, "firstPt")
           or glyf[c.glyphName].isComposite() for c in comps):
        return None
    own = {k: [(0, 0) if d is None else d for d in v] for k, v in _raw(font, name).items()}
    parts = [load(font, c.glyphName) for c in comps]
    keys = sorted(set(own) | {k for p in parts if p for k in p.deltas})
    coords, flags, ends, deltas = [], [], [], {k: [] for k in keys}
    metrics = own
    for i, (c, part) in enumerate(zip(comps, parts)):
        if part is None:
            continue
        base = len(coords)
        coords += [(x + c.x, y + c.y) for x, y in part.coords]
        flags += part.flags
        ends += [base + e for e in part.ends]
        for k in keys:
            off = own[k][i] if k in own else (0, 0)
            pd = part.deltas.get(k, [None] * (len(part.coords) + 4))
            for run in part.contours():
                d = [pd[j] for j in run]
                if off != (0, 0):
                    if all(x is None for x in d):
                        d = [(0, 0)] * len(d)
                    d = [None if x is None else (x[0] + off[0], x[1] + off[1]) for x in d]
                deltas[k] += d
        if c.flags & USE_MY_METRICS:
            metrics = {k: [(0, 0) if d is None else d for d in part.deltas[k][-4:]] if k in part.deltas else [(0, 0)] * 4
                       for k in keys}
    for k in keys:
        deltas[k] += list(metrics[k][-4:]) if k in metrics else [(0, 0)] * 4
    overlap = bool(comps[0].flags & OVERLAP_COMPOUND) or any(p.overlap for p in parts if p)
    return Outline(coords, flags, ends, deltas, overlap)


def store(font: TTFont, name: str, o: Outline) -> None:
    """Write an outline back as a simple glyph, its left side bearing
    following its new xMin."""
    glyf = font["glyf"]
    g = Glyph()
    g.numberOfContours = len(o.ends)
    g.coordinates = GlyphCoordinates([(int(x), int(y)) for x, y in o.coords])
    g.endPtsOfContours = list(o.ends)
    g.flags = bytearray(o.flags)
    if o.overlap and g.flags:
        g.flags[0] |= flagOverlapSimple
    g.program = ttProgram.Program()
    g.program.fromBytecode(b"")
    glyf[name] = g
    g.recalcBounds(glyf)
    adv, _ = font["hmtx"][name]
    font["hmtx"][name] = (adv, g.xMin)
    if "gvar" in font:
        font["gvar"].variations[name] = [
            TupleVariation(dict(k), [None if d is None else (int(d[0]), int(d[1])) for d in v])
            for k, v in o.deltas.items() if any(d is not None and d != (0, 0) for d in v)]


def _fill(pts, flags, ends) -> pathops.Path:
    g = Glyph()
    g.numberOfContours = len(ends)
    g.coordinates = GlyphCoordinates(pts)
    g.endPtsOfContours = list(ends)
    g.flags = bytearray(flags)
    path = pathops.Path()
    g.draw(path.getPen(), None)
    return path


def locations(o: Outline) -> list[dict]:
    """The default, every master and the points a quarter, half and three quarters of the way to each."""
    out = [{}]
    for key in sorted(o.deltas):
        peak = {tag: p for tag, (_, p, _) in key}
        out += [{tag: v * f for tag, v in peak.items()} for f in (0.25, 0.5, 0.75, 1.0)]
    return out


def same_fill(a: Outline, b: Outline, locs: list[dict]) -> bool:
    """Whether two outlines fill the same shape at every location."""
    for loc in locs:
        try:
            xor = pathops.op(_fill(a.at(loc), a.flags, a.ends), _fill(b.at(loc), b.flags, b.ends), pathops.PathOp.XOR)
        except pathops.PathOpsError:
            return False
        if xor.area > SAME_FILL:
            return False
    return True


def segments(o: Outline, pts=None) -> list[tuple]:
    """Every segment as fontbakery's overlapping_path_segments reads it, in
    drawing order: (contour, start, end, is_curve, glyf points that define it,
    in drawing order). A contour starts at its first on-curve point; two
    off-curve points in a row imply an on-curve point between them; a closing
    line of zero length is not drawn."""
    pts = pts or o.coords
    out = []
    for ci, run in enumerate(o.contours()):
        idx = list(run)
        on = [i for i in idx if o.flags[i]]
        if not on:
            continue
        k = idx.index(on[0])
        idx = idx[k:] + idx[:k]
        nodes = []  # (point, on-curve, defining glyf points)
        for j, i in enumerate(idx):
            prev = idx[j - 1]
            if j and not o.flags[i] and not o.flags[prev]:
                mid = ((pts[prev][0] + pts[i][0]) / 2, (pts[prev][1] + pts[i][1]) / 2)
                nodes.append((mid, True, (prev, i)))
            nodes.append((tuple(map(float, pts[i])), bool(o.flags[i]), (i,)))
        nodes.append(nodes[0])  # back to the first point, which is on-curve
        start, ctrl = 0, []
        for j in range(1, len(nodes)):
            if not nodes[j][1]:
                ctrl.append(j)
                continue
            a, b = nodes[start][0], nodes[j][0]
            if not (j == len(nodes) - 1 and not ctrl and a == b):
                defining = tuple(dict.fromkeys(p for n in [start, *ctrl, j] for p in nodes[n][2]))
                out.append((ci, a, b, bool(ctrl), defining))
            start, ctrl = j, []
    return out


def shared(o: Outline) -> list[tuple]:
    """The segments fontbakery reports: each with the earlier segment it repeats, in either direction."""
    seen, hits = {}, []
    for seg in segments(o):
        _, a, b, _, _ = seg
        first = seen.get((a, b)) or seen.get((b, a))
        if first is not None:
            hits.append((seg, first))
        seen.setdefault((a, b), seg)
    return hits


def _duplicate_contour(o: Outline, ci: int, cj: int, locs) -> bool:
    """Whether contour ci repeats contour cj point for point at every location, from any start."""
    ri, rj = list(o.contours()[ci]), list(o.contours()[cj])
    if ci == cj or len(ri) != len(rj):
        return False
    fi, fj = [o.flags[i] for i in ri], [o.flags[i] for i in rj]
    at = [o.at(loc) for loc in locs]
    for k in range(len(ri)):
        if fi[k:] + fi[:k] == fj and all([p[i] for i in ri[k:] + ri[:k]] == [p[i] for i in rj] for p in at):
            return True
    return False


def _repeated_point(o: Outline, seg, locs) -> int | None:
    """The later end of a zero-length line when its ends coincide at every location."""
    _, a, b, curve, defining = seg
    if curve or a != b or len(defining) != 2:
        return None
    i, j = defining
    if all(p[i] == p[j] for p in (o.at(loc) for loc in locs)):
        return max(i, j)
    return None


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _notch(o: Outline, seg, step, fade: bool, infer: bool) -> Outline | None:
    """A line a to b replaced by a, a', b', b, where a' and b' sit one unit
    along `step` and one unit in from the ends: a shallow trapezoid that
    reaches into the other contour's ink. Faded, a' and b' fall back onto a
    and b at every master; otherwise they follow a and b, or (`infer`) their
    deltas are inferred."""
    _, a, b, curve, defining = seg
    if curve or len(defining) != 2:
        return None
    i, j = defining
    dx, dy = b[0] - a[0], b[1] - a[1]
    u = (_sign(dx), 0) if abs(dx) >= abs(dy) else (0, _sign(dy))
    if abs(dx * u[0] + dy * u[1]) < 3 or step in (u, (-u[0], -u[1])):
        return None
    ma, mb = (step[0] + u[0], step[1] + u[1]), (step[0] - u[0], step[1] - u[1])
    na = (o.coords[i][0] + ma[0], o.coords[i][1] + ma[1])
    nb = (o.coords[j][0] + mb[0], o.coords[j][1] + mb[1])
    new = {}
    for k in o.deltas:
        d = o.filled(k)
        if fade:
            new[k] = [(otRound(d[i][0] - ma[0]), otRound(d[i][1] - ma[1])), (otRound(d[j][0] - mb[0]), otRound(d[j][1] - mb[1]))]
        elif infer:
            new[k] = [None, None]
        else:
            new[k] = [(otRound(d[i][0]), otRound(d[i][1])), (otRound(d[j][0]), otRound(d[j][1]))]
    t = o.copy()
    t.insert(i, [na, nb], new)
    return t


def _changes(cur: Outline, seg, first, locs):
    """Changes that might remove one shared segment, in order of preference,
    each with whether it must keep the shape at every location (exact) or
    only at the default and the masters (faded: the moved points return to
    their place at each master, so between them nothing moves a unit or more)."""
    if _duplicate_contour(cur, seg[0], first[0], locs):
        t = cur.copy()
        t.drop(set(cur.contours()[seg[0]]))
        yield t, True
    for s in (seg, first):
        i = _repeated_point(cur, s, locs)
        if i is not None:
            t = cur.copy()
            t.drop({i})
            yield t, True
    for fade, infer in ((False, True), (False, False), (True, False)):
        for s in (seg, first):
            for step in STEPS:
                t = cur.copy()
                t.move(s[4], step, fade, infer)
                yield t, not fade
        for s in (seg, first):
            for step in STEPS:
                t = _notch(cur, s, step, fade, infer)
                if t is not None:
                    yield t, not fade


def repair(o: Outline) -> tuple[Outline, int, int, bool]:
    """Remove the shared segments of one outline, one at a time: a contour
    that repeats an earlier one is dropped, a point that repeats its neighbour
    is dropped, or one of the two segments moves one unit along an axis, or
    takes a one-unit notch, into ink the other contour already fills. Returns
    the new outline, how many shared segments went, how many are left, and
    whether a faded change was needed (the segments meet only near the
    default, so no change can hold at the masters too)."""
    locs = locations(o)
    masters = [loc for loc in locs if loc and all(abs(v) == 1 for v in loc.values())]
    cur, stuck, fixed, faded = o.copy(), set(), 0, False
    for _ in range(4 * len(shared(o)) + 4):
        hits = [h for h in shared(cur) if (h[0][1], h[0][2]) not in stuck]
        if not hits:
            break
        seg, first = hits[0]
        before = len(shared(cur))
        for t, exact in _changes(cur, seg, first, locs):
            after = len(shared(t))
            if after < before and same_fill(cur, t, locs if exact else [{}] + masters):
                cur, fixed, faded = t, fixed + before - after, faded or not exact
                break
        else:
            stuck.add((seg[1], seg[2]))
    return cur, fixed, len(shared(cur)), faded


def _regions(font: TTFont) -> list:
    if "gvar" not in font:
        return []
    return sorted({tuple(sorted(v.axes.items())) for vs in font["gvar"].variations.values() for v in vs})


def _flat_shares(font: TTFont, name: str) -> bool:
    glyf = font["glyf"]
    coords, ends, flags = glyf[name].getCoordinates(glyf)
    return bool(shared(Outline(coords, flags, ends, {}, False)))


def fix_shared_segments(font: TTFont) -> tuple[list[str], list[str], list[str]]:
    """Repair every glyph whose contours share a segment: simple glyphs first,
    then each composite that still shares one once its parts are repaired,
    drawn in as a simple glyph. Returns the glyphs changed, those of them that
    needed a faded change, and the glyphs that still share a segment."""
    glyf = font["glyf"]
    keys = _regions(font)
    changed, faded, left = [], [], []

    def run(name, o):
        o.cover(keys)
        new, fixed, rest, fade = repair(o)
        if fixed:
            store(font, name, new)
            changed.append(name)
            if fade:
                faded.append(name)
        if rest:
            left.append(name)

    order = font.getGlyphOrder()
    for name in order:
        o = load(font, name)
        if o is not None and shared(o):
            run(name, o)
    for name in order:
        if not glyf[name].isComposite() or not _flat_shares(font, name):
            continue
        o = decompose(font, name)
        if o is None:
            left.append(name)
        else:
            run(name, o)
    return changed, faded, left


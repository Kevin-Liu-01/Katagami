"""Serif's facets against Text's own curve, on the real masters: build_sans.transform runs twice,
once as built and once with cut_terminals doing nothing, and every glyph of every master is
compared. A glyph that differs must differ only by its facets: every segment of its outline lies
on the plain outline (within TOL units, sampled densely) or along the line of one of its cuts
(where the facet's foot falls just past the old corner), except one straight segment per facet.
So no point has moved off Text's curve and nothing is stretched.

    .venv/bin/python tools/serif_lab/facet_check.py [--italic] [--reuse]

The two transforms are pickled to build/serif-lab/facet-check-<part>.pkl; --reuse reads them back."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402
import build_sans as B  # noqa: E402
from kerf_build.profiles import PROFILES  # noqa: E402

TOL = 0.05
italic = "--italic" in sys.argv
p = PROFILES["serif"]
cache = Path(__file__).resolve().parents[2] / "build" / "serif-lab" / f"facet-check-{'italic' if italic else 'roman'}.pkl"
if "--reuse" in sys.argv and cache.exists():
    import pickle
    built, plain = pickle.load(open(cache, "rb"))
else:
    import pickle
    built = B.transform(p, italic)[0]
    cut = B.cut_terminals
    B.cut_terminals = lambda fonts, plan: None
    plain = B.transform(p, italic)[0]
    B.cut_terminals = cut
    pickle.dump((built, plain), open(cache, "wb"), protocol=pickle.HIGHEST_PROTOCOL)


def segments(contour):
    """(kind, points) per segment, the start point first."""
    pts = contour.points
    n = len(pts)
    starts = [k for k, q in enumerate(pts) if q.type is not None]
    segs = []
    for a, b in zip(starts, starts[1:] + [starts[0] + n]):
        seq = [pts[k % n] for k in range(a, b + 1)]
        segs.append(("line" if len(seq) == 2 else "curve", [(q.x, q.y) for q in seq]))
    return segs


def sample(seg, step):
    kind, P = seg
    if kind == "line":
        L = math.dist(P[0], P[1])
        m = max(2, int(L / step) + 1)
        return [(P[0][0] + (P[1][0] - P[0][0]) * k / (m - 1), P[0][1] + (P[1][1] - P[0][1]) * k / (m - 1)) for k in range(m)]
    L = sum(math.dist(P[k], P[k + 1]) for k in range(3))
    m = max(3, int(L / step) + 1)
    return [B._point(P, k / (m - 1)) for k in range(m)]


bad, changed, facets = [], 0, 0
longest = [0.0]  # how far a cut is carried past its old corner to a facet's foot
for style in built:
    fb, fp = built[style], plain[style]
    for g in fb:
        h = fp[g.name]
        if [[(q.x, q.y, q.type) for q in c.points] for c in g.contours] == [[(q.x, q.y, q.type) for q in c.points] for c in h.contours]:
            continue
        changed += 1
        if len(g.contours) != len(h.contours) or g.width != h.width:
            bad.append((style, g.name, "contour count or width"))
            continue
        plain_segs = [s for c in h.contours for s in segments(c)]
        same = {tuple(s[1]) for s in plain_segs} | {tuple(s[1][::-1]) for s in plain_segs}
        extra = sum(len(c.points) for c in g.contours) - sum(len(c.points) for c in h.contours)
        off = []
        for c in g.contours:
            for s in segments(c):
                if tuple(s[1]) in same:
                    continue  # a segment of Text's outline, point for point
                pts = sample(s, 1.0)
                x0, y0 = min(q[0] for q in s[1]) - 2, min(q[1] for q in s[1]) - 2
                x1, y1 = max(q[0] for q in s[1]) + 2, max(q[1] for q in s[1]) + 2
                near = [r for r in plain_segs if min(q[0] for q in r[1]) <= x1 and max(q[0] for q in r[1]) >= x0
                        and min(q[1] for q in r[1]) <= y1 and max(q[1] for q in r[1]) >= y0]
                ref = np.array([pt for r in near for pt in sample(r, 0.02)]) if near else np.zeros((1, 2)) + 1e9
                d = max(float(np.min(np.hypot(*(ref - pt).T))) for pt in pts)
                if d > TOL:
                    off.append((s, d))
        # a line along one of Text's cuts, carried on past the old corner to the facet's foot, is the cut itself
        plain_lines = [r[1] for r in plain_segs if r[0] == "line"]

        def on_cut(seg):
            (x0, y0), (x1, y1) = seg[1]
            for (a0, b0), (a1, b1) in plain_lines:
                L = math.hypot(a1 - a0, b1 - b0)
                if L < 1:
                    continue
                dist = lambda x, y: abs((x - a0) * (b1 - b0) - (y - b0) * (a1 - a0)) / L  # noqa: E731
                if dist(x0, y0) <= TOL and dist(x1, y1) <= TOL:
                    reach = max(max(math.dist((x, y), (a0, b0)), math.dist((x, y), (a1, b1))) - L for x, y in seg[1])
                    longest[0] = max(longest[0], reach)
                    return True
            return False
        off = [(s, d) for s, d in off if not (s[0] == "line" and on_cut(s))]
        # every other segment off the plain outline must be a facet: a straight line
        if any(s[0] != "line" for s, _ in off) or len(off) != extra:
            bad.append((style, g.name, f"{len(off)} segments off Text's outline for {extra} facets",
                        [(s[0], [tuple(round(v) for v in q) for q in s[1]], round(d, 2)) for s, d in off][:4]))
        facets += extra
print(("Italic" if italic else "roman"), "masters:", changed, "glyph masters changed,", facets, "facets;",
      len(bad), "with anything else off Text's curve (tolerance", TOL, "units); cuts carried on along",
      "their own line by at most", round(longest[0], 1), "units to a facet's foot")
for b in bad[:30]:
    print("BAD", *b)

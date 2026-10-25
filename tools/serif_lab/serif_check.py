"""Serif's terminals rebuilt: which glyphs changed against an older font, and whether anything but
their terminals did. Every glyph is drawn decomposed at Thin, Regular and Black; its contours are
matched point for point (rounded to half units, any start point and direction; a contour within
one unit of an old one, gvar rounding, still matches). A changed glyph's
unmatched new contours must be its stroke (a large contour) or a terminal spur, never a small
contour on the baseline, x-height, cap height, ascender or descender, where stem serifs sit; and
every old contour on those lines must still be there, unless it was the old build's terminal piece.

    .venv/bin/python tools/serif_lab/serif_check.py OLD.ttf NEW.ttf [--names-out FILE]"""
import sys
import unicodedata
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

args = [a for a in sys.argv[1:] if not a.startswith("--")]
old, new = TTFont(args[0]), TTFont(args[1])
names_out = sys.argv[sys.argv.index("--names-out") + 1] if "--names-out" in sys.argv else None


def contours(gs, name):
    rec = DecomposingRecordingPen(gs)
    gs[name].draw(rec)
    out, cur = [], []
    for op, a in rec.value:
        cur += [(round(q[0] * 2) / 2, round(q[1] * 2) / 2) for q in a if q is not None]
        if op in ("closePath", "endPath"):
            out.append(cur)
            cur = []
    return out


def key(pts):
    """The same for a contour whatever its start point and direction."""
    if not pts:
        return ()
    best = None
    for seq in (pts, pts[::-1]):
        for k in range(len(seq)):
            cand = tuple(seq[k:] + seq[:k])
            if best is None or cand < best:
                best = cand
    return best


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


TOL = 1.0
changed, flagged, gone = set(), [], []


def close(a, b):
    """Whether two contours are the same within TOL units, point for point, from any start, either way."""
    if len(a) != len(b):
        return False
    for seq in (b, b[::-1]):
        for k in range(len(seq)):
            if all(abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL for p, q in zip(a, seq[k:] + seq[:k])):
                return True
    return False
for w in (100, 400, 900):
    go, gn = old.getGlyphSet(location={"wght": w}), new.getGlyphSet(location={"wght": w})
    os2 = new["OS/2"]
    lines = [0, os2.sxHeight, os2.sCapHeight, new["hhea"].ascent, new["hhea"].descent]
    for n in new.getGlyphOrder():
        if n not in go:
            continue
        co, cn = contours(go, n), contours(gn, n)
        ko, kn = {}, {}
        for c in co:
            ko[key(c)] = ko.get(key(c), 0) + 1
        for c in cn:
            kn[key(c)] = kn.get(key(c), 0) + 1
        if ko == kn:
            continue
        # contours that differ by at most TOL units point for point (gvar rounding) still match
        lo = [c for c in co if ko.get(key(c), 0) > kn.get(key(c), 0)]
        ln = [c for c in cn if kn.get(key(c), 0) > ko.get(key(c), 0)]
        for c in list(ln):
            m = next((d for d in lo if close(c, d)), None)
            if m is not None:
                lo.remove(m)
                ln.remove(c)
        if not lo and not ln:
            continue
        changed.add(n)
        allpts = [p for c in cn for p in c] or [(0, 0)]
        _, ylo, _, yhi = bbox(allpts)
        height = max(1.0, yhi - ylo)

        def on_line(b):
            return any(abs(b[1] - m) <= 2 or abs(b[3] - m) <= 2 for m in lines)
        for c in ln:
            b = bbox(c)
            if c and b[3] - b[1] < 0.5 * height and on_line(b):
                flagged.append((w, n, "new small contour on a metric line", b))
        for c in lo:
            b = bbox(c)
            if c and b[3] - b[1] < 0.5 * height and on_line(b):
                gone.append((w, n, "old small contour on a metric line gone", b))
rev = {g: chr(u) for u, g in new.getBestCmap().items()}
base = sorted(n for n in changed if n in rev and not (unicodedata.decomposition(rev[n]) and not unicodedata.decomposition(rev[n]).startswith("<")))
print(len(changed), "glyphs changed;", len(base), "encoded base glyphs:", " ".join(rev[n] for n in base))
print("unencoded:", " ".join(sorted(n for n in changed if n not in rev)))
for f in flagged:
    print("FLAG", *f)
for f in gone:
    print("GONE", *f)
print(len(flagged), "flags (a new small contour on a metric line: a changed stem serif);", len(gone),
      "old small contours on a metric line gone (the old build's terminal pieces, or a changed stem serif)")
if names_out:
    open(names_out, "w").write("\n".join(sorted(changed)) + "\n")

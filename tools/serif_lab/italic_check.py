"""Serif Italic against its roman: for every glyph in a list (default: those the terminal rebuild
changed), the Italic stood upright again and the roman drawn decomposed at Thin, Regular and Black,
their contour counts and the largest distance between matching points, ink centred.
A glyph whose terminals differ from the roman's shows a different contour count.
    .venv/bin/python tools/serif_lab/italic_check.py ROMAN.ttf ITALIC.ttf NAMES.txt"""
import math
import sys
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

rom, ita = TTFont(sys.argv[1]), TTFont(sys.argv[2])
names = [n.strip() for n in open(sys.argv[3]) if n.strip()]
t = math.tan(math.radians(-(ita["post"].italicAngle or 0)))
y0 = ita["OS/2"].sxHeight / 2


def draw(gs, name, shear=0.0):
    rec = DecomposingRecordingPen(gs)
    gs[name].draw(rec)
    cs, cur = [], []
    for op, a in rec.value:
        cur += [(q[0] - (q[1] - y0) * shear, q[1]) for q in a if q is not None]
        if op in ("closePath", "endPath"):
            cs.append(cur)
            cur = []
    return cs


counts, worst = [], []
for w in (100, 400, 900):
    rg, ig = rom.getGlyphSet(location={"wght": w}), ita.getGlyphSet(location={"wght": w})
    for n in names:
        if n not in rg or n not in ig:
            continue
        a, b = draw(rg, n), draw(ig, n, t)
        if len(a) != len(b):
            counts.append((w, n, len(a), len(b)))
            continue
        pa, pb = [p for c in a for p in c], [p for c in b for p in c]
        if len(pa) != len(pb) or not pa:
            worst.append((None, w, n, "points", len(pa), len(pb)))
            continue
        ca = (min(x for x, _ in pa) + max(x for x, _ in pa)) / 2
        cb = (min(x for x, _ in pb) + max(x for x, _ in pb)) / 2
        d = max(math.hypot(p[0] - ca - q[0] + cb, p[1] - q[1]) for p, q in zip(pa, pb))
        worst.append((round(d, 1), w, n))
print(len(names), "glyphs at 3 weights;", len(counts), "with another contour count than the roman's")
for c in counts[:40]:
    print("COUNT", *c)
pts_diff = [x for x in worst if x[0] is None]
print(len(pts_diff), "with the same contours but other point counts (Inter Italic's own drawing)")
num = sorted((x for x in worst if x[0] is not None), reverse=True)
print("largest point distances (same structure):", num[:12])

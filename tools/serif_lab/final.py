"""Proofs of Katagami Serif's terminals rendered from the built font files: 0.2's beaks beside the
fonts in fonts/serif/, and a grid of every glyph whose outline differs from 0.2's at Thin, Regular
and Black.

    .venv/bin/python tools/serif_lab/final.py V02_DIR [OUT_DIR]

V02_DIR holds 0.2's KatagamiSerif[wght].ttf and KatagamiSerif-Italic[wght].ttf (git show d6880dd:...).
OUT_DIR defaults to build/proofs/final. The grid shows the glyphs listed in build/small-changed-vs-barb.txt
(and -italic.txt), the glyphs whose terminals changed, when those lists exist."""
import sys
import unicodedata
from pathlib import Path
import skia
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
V02 = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "build" / "proofs" / "final"
NOW = ROOT / "fonts" / "serif"
ROMAN, ITALIC = "KatagamiSerif[wght].ttf", "KatagamiSerif-Italic[wght].ttf"
GLYPHS = "S a c s e g C G J r y f 2 3 5 6 9 ?"
WORDS = ["Classic saga goes Jersey", "Cascades gracefully"]
NAMES = {100: "Thin", 400: "Regular", 900: "Black"}
TAG = (ord("w") << 24) | (ord("g") << 16) | (ord("h") << 8) | ord("t")
INK = skia.Paint(Color=skia.Color(17, 17, 17), AntiAlias=True)
GREY = skia.Paint(Color=skia.Color(120, 120, 120), AntiAlias=True)
RED = skia.Paint(Color=skia.Color(200, 40, 40), AntiAlias=True)
LABEL = skia.Font(skia.Typeface("Helvetica"), 13)
_keep, _faces = [], {}


def face(path, w):
    if (path, w) not in _faces:
        coord = skia.FontArguments.VariationPosition.Coordinate(TAG, float(w))
        coords = skia.FontArguments.VariationPosition.Coordinates([coord])
        pos = skia.FontArguments.VariationPosition(coords)
        args = skia.FontArguments()
        args.setVariationDesignPosition(pos)
        _keep.extend([coord, coords, pos, args])  # skia keeps pointers into these
        _faces[(path, w)] = skia.Typeface.MakeFromFile(str(path)).makeClone(args)
    return _faces[(path, w)]


def font(path, w, px):
    f = skia.Font(face(path, w), px)
    f.setSubpixel(True)
    f.setEdging(skia.Font.Edging.kAntiAlias)
    return f


def sheet(out, lines, sizes, weights, columns):
    """Rows of size x weight x line, one column per (label, font path)."""
    rows = [(px, w, ln) for px in sizes for w in weights for ln in lines]
    lab, gap = 120, 40
    width = {label: max(font(p, w, px).measureText(ln) for px, w, ln in rows) for label, p in columns}
    W = int(lab + sum(width.values()) + gap * len(columns))
    H = int(sum(px * 1.45 for px, *_ in rows) + 40)
    surf = skia.Surface(W, H)
    c = surf.getCanvas()
    c.clear(skia.ColorWHITE)
    x = lab
    for label, _ in columns:
        c.drawString(label, x, 18, LABEL, GREY if label == "0.2" else RED)
        x += width[label] + gap
    y = 30
    for px, w, ln in rows:
        base = y + px
        c.drawString(f"{NAMES.get(w, w)} {int(px)}px", 6, base, LABEL, GREY)
        x = lab
        for label, p in columns:
            c.drawString(ln, x, base, font(p, w, px), INK)
            x += width[label] + gap
        y += px * 1.45
    surf.makeImageSnapshot().save(str(out), skia.kPNG)
    print(out, W, H)


def outline(gs, name):
    rec = DecomposingRecordingPen(gs)
    gs[name].draw(rec)
    return rec.value


def shape(gs, name):
    """The outline's points, rounded to half units, as a sorted list: the same for a drawn-in
    component and the composite it replaced, whatever the contour order."""
    return sorted((round(q[0] * 2) / 2, round(q[1] * 2) / 2) for _, a in outline(gs, name) for q in a if q is not None)


def skpath(value, x, base, s):
    pa = skia.Path()
    pa.setFillType(skia.PathFillType.kWinding)
    for op, a in value:
        if op == "moveTo":
            pa.moveTo(x + a[0][0] * s, base - a[0][1] * s)
        elif op == "lineTo":
            pa.lineTo(x + a[0][0] * s, base - a[0][1] * s)
        elif op == "qCurveTo":
            pts = list(a)
            if pts[-1] is None:
                pts = pts[:-1]
                start = ((pts[-1][0] + pts[0][0]) / 2, (pts[-1][1] + pts[0][1]) / 2)
                pa.moveTo(x + start[0] * s, base - start[1] * s)
                pts = pts + [start]
            for k in range(len(pts) - 1):
                end = pts[k + 1] if k == len(pts) - 2 else ((pts[k][0] + pts[k + 1][0]) / 2, (pts[k][1] + pts[k + 1][1]) / 2)
                pa.quadTo(x + pts[k][0] * s, base - pts[k][1] * s, x + end[0] * s, base - end[1] * s)
        elif op == "curveTo":
            pa.cubicTo(*[v for q in a for v in (x + q[0] * s, base - q[1] * s)])
        elif op in ("closePath", "endPath"):
            pa.close()
    return pa


def grid(prefix, old_path, new_path, only=None, per_band=20, bands=5, em=70.0):
    """Every encoded base glyph (no accented composites) whose outline differs from 0.2's at Regular,
    or only those in `only` (a set of names, from serif_check.py --names-out against the build before
    the terminals changed): 0.2 Regular, then the new font at Thin, Regular and Black."""
    old, new = TTFont(old_path), TTFont(new_path)
    sets = {("0.2", 400): old.getGlyphSet(location={"wght": 400})}
    for w in (100, 400, 900):
        sets[("new", w)] = new.getGlyphSet(location={"wght": w})
    cmap = new.getBestCmap()
    names = []
    for u, n in sorted(cmap.items()):
        ch = chr(u)
        if unicodedata.decomposition(ch) and not unicodedata.decomposition(ch).startswith("<"):
            continue  # an accented letter: its base is in the grid
        if n in names or n not in old.getGlyphOrder() or (only is not None and n not in only):
            continue
        if shape(sets[("0.2", 400)], n) != shape(sets[("new", 400)], n):
            names.append(n)
    rev = {n: chr(u) for u, n in cmap.items()}
    rows = [("0.2 Regular", "0.2", 400), ("Thin", "new", 100), ("Regular", "new", 400), ("Black", "new", 900)]
    s, cell, lab, small = em / 2048, em * 1.25, 90, skia.Font(skia.Typeface("Helvetica"), 10)
    band_h = 16 + len(rows) * em * 1.2
    outs = []
    for page in range(0, len(names), per_band * bands):
        chunk = names[page:page + per_band * bands]
        nb = (len(chunk) + per_band - 1) // per_band
        W, H = int(lab + cell * per_band + 10), int(nb * band_h + 20)
        surf = skia.Surface(W, H)
        c = surf.getCanvas()
        c.clear(skia.ColorWHITE)
        for b in range(nb):
            top = 10 + b * band_h
            for k, n in enumerate(chunk[b * per_band:(b + 1) * per_band]):
                x0 = lab + k * cell
                c.drawString(f"{rev.get(n, '')} {n}"[:14], x0, top + 10, small, GREY)
                for r, (label, key, w) in enumerate(rows):
                    gs = sets[(key, w)]
                    base = top + 16 + r * em * 1.2 + em * 0.92
                    if k == 0:
                        c.drawString(label, 4, base - em * 0.3, small, GREY if key == "0.2" else RED)
                    c.drawPath(skpath(outline(gs, n), x0 + (cell - gs[n].width * s) / 2, base, s), INK)
        out = f"{prefix}-{page // (per_band * bands):02d}.png"
        surf.makeImageSnapshot().save(out, skia.kPNG)
        outs.append(out)
        print(out, W, H)
    return names


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    weights = [100, 400, 900]
    roman = [("0.2", V02 / ROMAN), ("built", NOW / ROMAN)]
    italic = [("0.2", V02 / ITALIC), ("built", NOW / ITALIC)]
    sheet(OUT / "final-roman-48px.png", [GLYPHS], [48], weights, roman)
    half = GLYPHS.split(" ")
    sheet(OUT / "final-roman-120px.png", [" ".join(half[:9]), " ".join(half[9:])], [120], weights, roman)
    sheet(OUT / "final-italic-48px.png", ["S a c s g", "Classic saga goes Jersey"], [48], weights, italic)
    sheet(OUT / "final-words.png", WORDS, [48], weights, roman)
    for f in OUT.glob("final-grid-*.png"):
        f.unlink()
    for part, name in (("roman", ROMAN), ("italic", ITALIC)):
        listing = OUT.parent.parent / f"small-changed-vs-barb{'' if part == 'roman' else '-italic'}.txt"
        only = {n.strip() for n in open(listing) if n.strip()} if listing.exists() else None
        names = grid(str(OUT / f"final-grid-{part}"), V02 / name, NOW / name, only)
        print(len(names), part, "base glyphs in the grid")


if __name__ == "__main__":
    main()

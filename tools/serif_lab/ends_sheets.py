"""Sheets of Serif's terminal end treatments A to D (ends.py), one column per option, cut in the lab
on the pickled masters. Also an overlay check: each option's outline against A's (Text's curve),
reporting how far any point of an option's edge lies from A's outline outside the terminals' ends.

    .venv/bin/python tools/serif_lab/ends_sheets.py [OUT_DIR]      # build/proofs/lab-ends by default"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import skia  # noqa: E402
from fontTools.pens.recordingPen import DecomposingRecordingPen  # noqa: E402
import lablib as L  # noqa: E402
import ends as E  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else L.ROOT / "build" / "proofs" / "lab-ends"
LETTERS = "c a g G C S s e r f"
WORDS = ["gauge cascade sage", "Classic Grace", "office cliffs"]
OPTIONS = "ABCD"
NAMES = {100: "Thin", 400: "Regular", 900: "Black"}


def sheet(out, lines, sizes, weights, built):
    rows = [(sz, w, ln) for sz in sizes for w in weights for ln in lines]
    cache = {}

    def at(o, w):
        if (o, w) not in cache:
            cache[(o, w)] = L.interpolate(built[o], w)
        return cache[(o, w)]
    lab, gap = 110, 36
    col = {o: max(L.text_width(at(o, w), ln, sz) for sz, w, ln in rows) for o in OPTIONS}
    W = int(lab + sum(col.values()) + gap * len(OPTIONS))
    H = int(sum(sz * 1.45 for sz, *_ in rows) + 40)
    surf = skia.Surface(W, H)
    c = surf.getCanvas()
    c.clear(skia.ColorWHITE)
    x = lab
    for o in OPTIONS:
        c.drawString(E.LABELS[o], x, 18, L.LABEL, L.GREY if o == "A" else L.RED)
        x += col[o] + gap
    y = 30
    for sz, w, ln in rows:
        base = y + sz
        c.drawString(f"{NAMES[w]} {int(sz)}px", 6, base, L.LABEL, L.GREY)
        x = lab
        for o in OPTIONS:
            L.draw_text(c, at(o, w), ln, sz, x, base)
            x += col[o] + gap
        y += sz * 1.45
    surf.makeImageSnapshot().save(str(out), skia.kPNG)
    print(out, W, H)


def samples(f, name, step=4.0):
    rec = DecomposingRecordingPen(f)
    f[name].draw(rec)
    out, cur = [], None
    for op, a in rec.value:
        if op == "moveTo":
            cur = a[0]
        elif op == "lineTo":
            n = max(1, int(math.dist(cur, a[0]) / step))
            out += [(cur[0] + (a[0][0] - cur[0]) * k / n, cur[1] + (a[0][1] - cur[1]) * k / n) for k in range(n)]
            cur = a[0]
        elif op == "curveTo":
            c = [cur, *a]
            n = max(2, int(sum(math.dist(c[k], c[k + 1]) for k in range(3)) / step))
            out += [L.NEW._point(c, k / n) for k in range(n)]
            cur = a[-1]
    return out


def overlay(built, plans, text):
    """For each option and master, the farthest any sampled point of a terminal glyph lies from A's
    outline, away from its terminals (more than 1.6 Regular stems from every cut's middle)."""
    a = built["A"]
    report = {}
    for o in "BCD":
        worst = (0.0, "")
        for style in ("Thin", "Regular", "Black"):
            fa, fo = a[style], built[o][style]
            sw = L.NEW.stem(fa)
            for name, terms in plans[o].items():
                if name not in fa:
                    continue
                g = fa[name]
                mids = []
                for term in terms:
                    pts = g.contours[term[1]].points
                    p, q = pts[term[2]], pts[term[3]]
                    mids.append(((p.x + q.x) / 2, (p.y + q.y) / 2))
                ref = samples(fa, name, 2.0)
                for pt in samples(fo, name, 6.0):
                    if any(math.dist(pt, m) < 1.6 * max(sw, 180 * 0.96) for m in mids):
                        continue
                    d = min(math.dist(pt, r) for r in ref)
                    if d > worst[0]:
                        worst = (d, f"{style} {name}")
        report[o] = worst
    return report


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    text = LETTERS.replace(" ", "") + "".join(WORDS)
    built, plans = {}, {}
    for o in OPTIONS:
        built[o], plans[o] = L.build("roman", text, "ends:" + o)
    half = LETTERS.split(" ")
    sheet(OUT / "ends-48px.png", [LETTERS], [48], [100, 400, 900], built)
    sheet(OUT / "ends-120px.png", [" ".join(half[:5]), " ".join(half[5:])], [120], [100, 400, 900], built)
    sheet(OUT / "ends-words.png", WORDS, [48], [100, 400, 900], built)
    for o, (d, where) in overlay(built, plans, text).items():
        print(f"overlay {o}: farthest from Text's outline away from the ends {d:.2f} units ({where})")


if __name__ == "__main__":
    main()

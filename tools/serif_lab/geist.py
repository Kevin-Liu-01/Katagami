"""Katagami Serif as build_sans.py cuts it now, on a few glyphs of the pickled masters
(prep.py), beside a reference serif face, in seconds and without a font build.

    .venv/bin/python tools/serif_lab/geist.py OUT.png "line|line" [100,400,700,900] [--ref=FONT] [--size=N] [--points] [--italic]

Each line is set at each weight, the lab's cut first and the reference face (a static font, set
once per line) under it. --points draws the outline with its on- and off-curve points."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import skia  # noqa: E402
import lablib as L  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in sys.argv[1:] if a.startswith("--"))
out, lines = args[0], args[1].split("|")
weights = [int(w) for w in args[2].split(",")] if len(args) > 2 else [100, 400, 700, 900]
size = float(opts.get("size", 140))
part = "slanted" if "italic" in opts else "roman"
fonts, _ = L.build(part, "".join(lines), "build")
ref = skia.Typeface.MakeFromFile(opts["ref"]) if "ref" in opts else None
inst = {w: L.interpolate(fonts, w) for w in weights}
rows = [(ln, w) for ln in lines for w in weights + ([None] if ref else [])]
W = int(max(L.text_width(inst[weights[0]], ln, size) for ln in lines) * 1.25 + 220)
H = int(len(rows) * size * 1.3 + 40)
surf = skia.Surface(W, H)
c = surf.getCanvas()
c.clear(skia.Color(250, 248, 244))
pts_on = skia.Paint(Color=skia.Color(220, 40, 40), AntiAlias=True)
pts_off = skia.Paint(Color=skia.Color(40, 90, 220), AntiAlias=True)
edge = skia.Paint(Color=skia.Color(20, 20, 20), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=1)
shade = skia.Paint(Color=skia.Color(20, 20, 20, 60), AntiAlias=True)
y = 20
for ln, w in rows:
    base = y + size * 0.95
    c.drawString("reference" if w is None else str(w), 10, base - size * 0.3, L.LABEL, L.RED)
    if w is None:
        c.drawString(ln, 110, base, skia.Font(ref, size), L.INK)
    elif "points" in opts:
        x = 110.0
        f = inst[w]
        for ch in ln:
            n = f.lib["_cmap"].get(ord(ch))
            if not n:
                x += 0.3 * size
                continue
            p = L.path(f, n, x, base, size / 2048)
            c.drawPath(p, shade)
            c.drawPath(p, edge)
            for ct in f[n].contours:
                for pt in ct.points:
                    c.drawCircle(x + pt.x * size / 2048, base - pt.y * size / 2048, 2.5 if pt.type else 1.8,
                                 pts_on if pt.type else pts_off)
            x += f[n].width * size / 2048
    else:
        L.draw_text(c, inst[w], ln, size, 110, base)
    y += size * 1.3
surf.makeImageSnapshot().save(out, skia.kPNG)
print(out, W, H)

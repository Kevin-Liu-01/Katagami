"""Glyphs large, filled in grey with every contour outlined and its points marked (on-curve red,
handles blue), 0.2 beside the moved version, one row per glyph and master.
    .venv/bin/python tools/serif_lab/zoom.py OUT.png roman|italic GLYPH:Master [GLYPH:Master ...] [CONST=value ...]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import skia  # noqa: E402
from fontTools.pens.recordingPen import RecordingPen  # noqa: E402
import lablib as L  # noqa: E402

out, part = sys.argv[1:3]
cells = [a.split(":") for a in sys.argv[3:] if ":" in a and "=" not in a]
consts = {k: eval(v) for k, v in (a.split("=", 1) for a in sys.argv[3:] if "=" in a)}
text = "".join(ch for ch, _ in cells)
built = {v: L.build(part, text, v, consts if v == "moved" else None)[0] for v in ("0.2", "moved")}
s = 0.25
fill = skia.Paint(Color=skia.Color(205, 205, 205), AntiAlias=True)
line = skia.Paint(Color=skia.Color(30, 30, 30), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=1)
dot = skia.Paint(Color=skia.Color(200, 40, 40), AntiAlias=True)
off = skia.Paint(Color=skia.Color(40, 90, 200), AntiAlias=True)
rows = []
for ch, style in cells:
    fs = [built[v][style] for v in ("0.2", "moved")]
    name = fs[0].lib["_cmap"][ord(ch)]
    rows.append((fs, name))
W = int(max(sum(f[n].width for f in fs) for fs, n in rows) * s + 100)
RH = 2300 * s
surf = skia.Surface(W, int(RH * len(rows)))
c = surf.getCanvas()
c.clear(skia.ColorWHITE)
for r, (fs, name) in enumerate(rows):
    x, base = 20, r * RH + 1750 * s
    c.drawString(f"{cells[r][0]} {cells[r][1]}", 4, r * RH + 16, L.LABEL, L.GREY)
    for f in fs:
        g = f[name]
        c.drawPath(L.path(f, name, x, base, s), fill)
        for ct in g.contours:
            rec = RecordingPen()
            ct.draw(rec)
            pa = skia.Path()
            for op, a in rec.value:
                tr = [(x + q[0] * s, base - q[1] * s) for q in a]
                if op == "moveTo":
                    pa.moveTo(*tr[0])
                elif op == "lineTo":
                    pa.lineTo(*tr[0])
                elif op == "curveTo":
                    pa.cubicTo(*tr[0], *tr[1], *tr[2])
                elif op == "closePath":
                    pa.close()
            c.drawPath(pa, line)
            for p in ct.points:
                c.drawCircle(x + p.x * s, base - p.y * s, 2.2 if p.type else 1.4, dot if p.type else off)
        x += g.width * s + 50
surf.makeImageSnapshot().save(out, skia.kPNG)
print(out, W, int(RH * len(rows)))

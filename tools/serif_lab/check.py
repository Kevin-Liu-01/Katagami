"""Every glyph through the lab's serif block, 0.2 and moved: which terminals take a beak in
each, whether the masters stay compatible, and whether a moved beak reaches past the ink
the letter had before its terminals were cut (it must stay inside the silhouette).
    .venv/bin/python tools/serif_lab/check.py [roman|slanted]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lablib as L  # noqa: E402

part = sys.argv[1] if len(sys.argv) > 1 else "roman"
src = L.pre("roman" if part == "slanted" else part)
text = "".join(chr(u) for g in src["Regular"] for u in g.unicodes[:1])
old, old_plan = L.build(part, text, "0.2")
new, new_plan = L.build(part, text, "moved")
plain, _ = L.build(part, text, "moved", {"plan_terminals": lambda fonts, plan: {}})
problems = []
for style in ("Thin", "Regular", "Black"):
    f, p = new[style], plain[style]
    for name in new_plan:
        if name not in f:
            continue
        b, c = f[name].getBounds(f), p[name].getBounds(p)
        if b and c and (b.xMin < c.xMin - 2 or b.xMax > c.xMax + 2 or b.yMin < c.yMin - 2 or b.yMax > c.yMax + 2):
            problems.append((style, name, "past the ink", [round(v) for v in (b.xMin - c.xMin, b.yMin - c.yMin, b.xMax - c.xMax, b.yMax - c.yMax)]))
for w in (100, 250, 400, 650, 900):
    L.interpolate(new, w)  # asserts the masters' contours and points match
beaked = lambda fonts: {g.name for g in fonts["Regular"] if len(g.contours) > len(plain["Regular"][g.name].contours)}  # noqa: E731
o, n = beaked(old), beaked(new)
print(part, "beaked glyphs: 0.2", len(o), "moved", len(n))
cm = {g.name: chr(g.unicodes[0]) for g in src["Regular"] if g.unicodes}
print("only 0.2:", " ".join(sorted(cm.get(x, x) for x in o - n)))
print("only moved:", " ".join(sorted(cm.get(x, x) for x in n - o)))
print("moved:", " ".join(sorted(cm.get(x, x) for x in n)))
for pr in problems:
    print("PROBLEM", *pr)
print("compatible at 100..900")

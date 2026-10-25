"""Reference terminals: the target letters set in the serif faces this Mac has (read-only),
for comparing terminal construction. .venv/bin/python tools/serif_lab/reference.py OUT.png [size]"""
import sys
import skia

FACES = [
    ("Times New Roman", "/System/Library/Fonts/Supplemental/Times New Roman.ttf", 0),
    ("Georgia", "/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
    ("Charter", "/System/Library/Fonts/Supplemental/Charter.ttc", 0),
    ("Baskerville", "/System/Library/Fonts/Supplemental/Baskerville.ttc", 0),
]
TEXT = sys.argv[3] if len(sys.argv) > 3 else "CGScsa2369?JjyrfgSe"
size = float(sys.argv[2]) if len(sys.argv) > 2 else 120
W, H = int(len(TEXT) * size * 0.62 + 200), int(len(FACES) * size * 1.3 + 20)
surf = skia.Surface(W, H)
c = surf.getCanvas()
c.clear(skia.ColorWHITE)
ink = skia.Paint(Color=skia.Color(20, 20, 20), AntiAlias=True)
lab = skia.Paint(Color=skia.Color(200, 40, 40), AntiAlias=True)
y = size * 1.05
for name, path, index in FACES:
    tf = skia.Typeface.MakeFromFile(path, index)
    c.drawString(name, 6, y, skia.Font(skia.Typeface("Helvetica"), 13), lab)
    c.drawString(TEXT, 170, y, skia.Font(tf, size), ink)
    y += size * 1.3
surf.makeImageSnapshot().save(sys.argv[1], skia.kPNG)
print(sys.argv[1], W, H)

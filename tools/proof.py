"""Render comparison proof sheets to PNG.

    python tools/proof.py sans   -> build/proofs/sans-vs-inter.png
    python tools/proof.py mono   -> build/proofs/mono.png
    python tools/proof.py family -> build/proofs/family.png
    python tools/proof.py round  -> build/proofs/round-vs-inter.png
    python tools/proof.py text   -> build/proofs/text-vs-inter.png
    python tools/proof.py detail -> build/proofs/detail.png (the letters under revision, large)
    python tools/proof.py serif  -> build/proofs/serif-*.png (Katagami Serif before and after a change, beside Geist Serif)

The serif sheets compare build/serif-before/ (a copy of fonts/serif/ taken before the
change) with fonts/serif/, and set Geist Serif (Vercel, SIL OFL 1.1, from the
github.com/vercel/geist-font releases) from build/ref/GeistSerif-Regular.ttf, its one weight.
"""

from __future__ import annotations

import sys
from pathlib import Path

from drawbot_skia.drawing import Drawing

ROOT = Path(__file__).resolve().parents[1]
INTER = ROOT / "build/ref/InterVariable.ttf"
SANS = ROOT / "fonts/sans/KatagamiSans[wght].ttf"
MONO = ROOT / "fonts/mono/KatagamiMono[wght].ttf"
ROUND = ROOT / "fonts/round/KatagamiRound[wght].ttf"
TEXT = ROOT / "fonts/text/KatagamiText[wght].ttf"
BERKELEY = Path.home() / "Library/Fonts/BerkeleyMono-Regular.ttf"
OUT = ROOT / "build/proofs"  # local only: sheets may show licensed reference fonts
SERIF = ROOT / "fonts/serif/KatagamiSerif[wght].ttf"
SERIF_ITALIC = ROOT / "fonts/serif/KatagamiSerif-Italic[wght].ttf"
SERIF_BEFORE = ROOT / "build/serif-before"  # fonts/serif/ copied before the change under review
GEIST_SERIF = ROOT / "build/ref/GeistSerif-Regular.ttf"

INK, PAPER, MUTED = (0.07, 0.07, 0.08), (0.97, 0.965, 0.95), (0.55, 0.55, 0.55)

LINES = [
    "HAMBURGEFONTSIV",
    "hamburgefontsiv",
    "OCGQDSobcdepq 0123456789",
    "Sphinx of black quartz, judge my vow.",
    "agjty fr 1lIi .,:;!?@&* (){}[]",
]
CODE = [
    "const kerf = (cut: number) => cut * 0.6;",
    "if (a != b && x <= 0) { return [i, l, 1, I, 0, O]; }",
    "┌─────┬─────┐  ▖▗▘▝ ░▒▓█",
    "│ 0O0 │ 1lI │  -> => != <= >=",
    "└─────┴─────┘  {}[]()<>/\\|@#$%^&*",
]


def row(db, label, path, wght, text, y, size, x=60):
    db.fill(*MUTED)
    db.font(str(INTER), 22)
    db.fontVariations(wght=400)
    db.text(label, (x, y + size * 0.15))
    db.fill(*INK)
    db.font(str(path), size)
    if wght is not None:
        db.fontVariations(wght=wght)
    db.text(text, (x + 260, y))


def sheet(name, blocks, width=2600, size=96, gap=1.35):
    n = sum(len(b[3]) * len(b[2]) for b in blocks) + len(blocks)
    height = int(n * size * gap + 160)
    db = Drawing()
    db.newPage(width, height)
    db.fill(*PAPER)
    db.rect(0, 0, width, height)
    y = height - 80 - size
    for title, _, rows, texts in blocks:
        db.fill(*INK)
        db.font(str(INTER), 30)
        db.fontVariations(wght=600)
        db.text(title, (60, y + size * 0.45))
        y -= size * 0.6
        for text in texts:
            for label, path, w in rows:
                row(db, label, path, w, text, y, size)
                y -= size * gap
        y -= size * 0.4
    OUT.mkdir(exist_ok=True)
    out = OUT / f"{name}.png"
    db.saveImage(str(out))
    print(out)


WEIGHTS = ((100, "Thin"), (400, "Regular"), (700, "Bold"), (900, "Black"))
SERIF_TEXT = [
    "Sphinx of black quartz, judge my vow.",
    "agertfy nmhu bdpq kvwxz cs",
    "AVWXYKMNU EFLTZ CGS JQR",
    "Typography 1.2: 0123456789 &?!",
]
SERIF_GROUPS = ["aegrtfy", "nmhucsk", "dbpqvwx", "AEGRSTC", "MNKVWYZ"]


def serif_sheets() -> None:
    """Katagami Serif before and after, beside Geist Serif: text lines at Thin, Regular, Bold
    and Black, large letters at each weight, and the Italic's text lines. Drawn with skia,
    one PNG per sheet, sized to read on a phone."""
    import skia

    def face(path, wght=None):
        tf = skia.Typeface.MakeFromFile(str(path))
        if wght is None:
            return tf
        tag = int.from_bytes(b"wght", "big")
        # skia keeps pointers to the coordinates, so each object stays named until the clone is made
        coord = skia.FontArguments.VariationPosition.Coordinate(tag, float(wght))
        coords = skia.FontArguments.VariationPosition.Coordinates([coord])
        position = skia.FontArguments.VariationPosition(coords)
        args = skia.FontArguments()
        args.setVariationDesignPosition(position)
        return tf.makeClone(args)

    before, before_italic = SERIF_BEFORE / SERIF.name, SERIF_BEFORE / SERIF_ITALIC.name
    for need in (before, SERIF, GEIST_SERIF):
        if not need.exists():
            sys.exit(f"{need} is missing: see the module's docstring.")
    label_face = face(SANS, 500)
    ink, muted, accent = skia.Color(18, 18, 20), skia.Color(120, 118, 112), skia.Color(176, 64, 32)
    W = 1600

    def render(name, blocks, size, row_gap=1.32):
        """blocks: (title, [(label, typeface, text)]). Each row is its label, then
        its line, `row_gap` of the size tall below the label; a line wider than the
        sheet is scaled down to fit."""
        label_h, title_h = 44, 70
        height = 40 + sum(title_h + len(rows) * (label_h + size * row_gap) + 50 for _, rows in blocks)
        surf = skia.Surface(W, int(height))
        c = surf.getCanvas()
        c.clear(skia.Color(249, 247, 242))
        y = 40.0
        for title, rows in blocks:
            title_font = skia.Font(label_face, 46)
            c.drawString(title, 40, y + 46, title_font, skia.Paint(Color=ink, AntiAlias=True))
            y += title_h
            for label, tf, text in rows:
                c.drawString(label, 40, y + 32, skia.Font(label_face, 30),
                             skia.Paint(Color=accent if label.startswith("Geist") else muted, AntiAlias=True))
                y += label_h
                font = skia.Font(tf, size)
                width = font.measureText(text)
                scale = min(1.0, (W - 80) / width) if width else 1.0
                c.save()
                c.translate(40, y + size * 0.95 * scale)
                c.scale(scale, scale)
                c.drawString(text, 0, 0, font, skia.Paint(Color=ink, AntiAlias=True))
                c.restore()
                y += size * row_gap
            y += 50
        OUT.mkdir(parents=True, exist_ok=True)
        out = OUT / name
        surf.makeImageSnapshot().save(str(out), skia.kPNG)
        print(out, W, int(height), f"{out.stat().st_size / 1e6:.1f} MB")

    geist = face(GEIST_SERIF)
    geist_label = "Geist Serif Regular (its only weight)"
    render("serif-1-text.png", [
        (f"{title} {w}", [row for text in SERIF_TEXT for row in (
            (f"Katagami Serif 1.3 as it ships, {w}", face(before, w), text),
            (f"Katagami Serif new, {w}", face(SERIF, w), text),
            (geist_label, geist, text))])
        for w, title in WEIGHTS], 70)
    for k, (w, title) in enumerate(WEIGHTS):
        render(f"serif-{k + 2}-letters-{title.lower()}.png", [
            (f"{title} {w}: {group}", [
                (f"Katagami Serif 1.3 as it ships, {w}", face(before, w), group),
                (f"Katagami Serif new, {w}", face(SERIF, w), group),
                (geist_label, geist, group)])
            for group in SERIF_GROUPS], 330, 1.22)
    if before_italic.exists():
        render("serif-6-italic.png", [
            (f"Italic {title} {w}", [row for text in SERIF_TEXT[:3] for row in (
                (f"Katagami Serif Italic 1.3 as it ships, {w}", face(before_italic, w), text),
                (f"Katagami Serif Italic new, {w}", face(SERIF_ITALIC, w), text))])
            for w, title in WEIGHTS], 70)


def main(which: str) -> None:
    if which == "serif":
        serif_sheets()
        return
    if which == "sans":
        rows = [("Inter 400", INTER, 400), ("Katagami Sans 400", SANS, 400),
                ("Inter 700", INTER, 700), ("Katagami Sans 700", SANS, 700)]
        sheet("sans-vs-inter", [("Katagami Sans vs Inter", None, rows, LINES)])
    elif which == "mono":
        rows = [("Katagami Mono 400", MONO, 400), ("Berkeley Mono", BERKELEY, None),
                ("Katagami Mono 700", MONO, 700)]
        sheet("mono", [("Katagami Mono", None, rows, LINES + CODE)], size=72)
    elif which == "round":
        rows = [("Inter 400", INTER, 400), ("Katagami Round 400", ROUND, 400),
                ("Inter 700", INTER, 700), ("Katagami Round 700", ROUND, 700)]
        sheet("round-vs-inter", [("Katagami Round vs Inter", None, rows, LINES + ["Revenue grew 12% in the third quarter."])])
    elif which == "text":
        rows = [("Inter 400", INTER, 400), ("Katagami Text 400", TEXT, 400), ("Katagami Sans 400", SANS, 400),
                ("Inter 700", INTER, 700), ("Katagami Text 700", TEXT, 700)]
        sheet("text-vs-inter", [("Katagami Text vs Inter", None, rows, LINES + ["Revenue grew 12% in the third quarter."])])
    elif which == "detail":
        rows = [(f"{n} {w}", path, w) for w in (400, 900) for n, path in
                (("Inter", INTER), ("Sans", SANS), ("Round", ROUND), ("Text", TEXT))]
        sheet("detail", [("Revision letters", None, rows, ["gmbdpqyt aeg"])], width=2400, size=200, gap=1.2)
    elif which == "family":
        rows = [("Katagami Sans", SANS, 400), ("Katagami Mono", MONO, 400)]
        sheet("family", [("Katagami family", None, rows, LINES)])


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sans")

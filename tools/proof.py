"""Render comparison proof sheets to PNG.

    python tools/proof.py sans   -> build/proofs/sans-vs-inter.png
    python tools/proof.py mono   -> build/proofs/mono.png
    python tools/proof.py family -> build/proofs/family.png
    python tools/proof.py round  -> build/proofs/round-vs-inter.png
    python tools/proof.py text   -> build/proofs/text-vs-inter.png
    python tools/proof.py detail -> build/proofs/detail.png (the letters under revision, large)
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


def main(which: str) -> None:
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

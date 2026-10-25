"""Proof sheets for Katagami Serif's terminals: 0.2's tooth beaks and the moved beaks side by
side, cut in the lab (lablib.py) on the pickled masters, no font build.

    .venv/bin/python tools/serif_lab/sheets.py            # the four small-* sheets in build/proofs/moved/
    .venv/bin/python tools/serif_lab/sheets.py custom OUT.png roman|slanted|italic "line|line" 48,120 100,400,900 ["label=CONST:value;CONST:value" ...]

A custom sheet sets 0.2 beside one column per label, each the moved beaks with moved.py
constants overridden (values read as Python)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import skia  # noqa: E402
import lablib as L  # noqa: E402

OUT = L.ROOT / "build" / "proofs" / "moved"
GLYPHS = "S a c s e g C G J r y f 2 3 5 6 9 ?"
WORDS = ["Classic saga goes Jersey", "Cascades gracefully"]
NAMES = {100: "Thin", 400: "Regular", 900: "Black"}
PREVIOUS = {"BEAK_REACH": 1.0, "BEAK_MIN": 0.0, "UPRIGHT_REACH": 1.0}  # the first moved spur, before Kevin asked for a far smaller one


def sheet(out, part, lines, sizes, weights, consts=None, variants=("0.2", "moved")):
    """Rows of size x weight x line; one column per variant: "0.2", "moved", or
    (label, consts) for the moved beaks with moved.py constants overridden."""
    text = "".join(lines)
    variants = [(v, v, consts if v == "moved" else None) if isinstance(v, str) else
                (v[0], v[2] if len(v) > 2 else "moved", v[1]) for v in variants]
    built = {label: L.build(part, text, v, cs)[0] for label, v, cs in variants}
    variants = [label for label, _, _ in variants]
    cache = {}

    def at(v, w):
        if (v, w) not in cache:
            cache[(v, w)] = L.interpolate(built[v], w)
        return cache[(v, w)]
    rows = [(sz, w, ln) for sz in sizes for w in weights for ln in lines]
    lab, gap = 120, 40
    col = {v: max(L.text_width(at(v, w), ln, sz) for sz, w, ln in rows) for v in variants}
    W = int(lab + sum(col.values()) + gap * len(variants) + 10)
    H = int(sum(sz * 1.45 for sz, *_ in rows) + 40)
    surf = skia.Surface(W, H)
    c = surf.getCanvas()
    c.clear(skia.ColorWHITE)
    x = lab
    for v in variants:
        c.drawString(v, x, 18, L.LABEL, L.GREY if v == "0.2" else L.RED)
        x += col[v] + gap
    y = 30
    for sz, w, ln in rows:
        base = y + sz * 1.0
        c.drawString(f"{NAMES.get(w, w)} {int(sz)}px", 6, base, L.LABEL, L.GREY)
        x = lab
        for v in variants:
            L.draw_text(c, at(v, w), ln, sz, x, base)
            x += col[v] + gap
        y += sz * 1.45
    surf.makeImageSnapshot().save(str(out), skia.kPNG)
    print(out, W, H)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "custom":
        out, part, lines, sizes, weights = sys.argv[2:7]
        variants = ["0.2", "moved", ("build", {}, "build")]
        for spec in sys.argv[7:]:
            label, _, rest = spec.partition("=")
            variants.append((label, {k: eval(v) for k, v in (kv.split(":", 1) for kv in filter(None, rest.split(";")))}))
        sheet(out, part, lines.split("|"), [float(s) for s in sizes.split(",")], [int(w) for w in weights.split(",")],
              variants=variants)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    weights = [100, 400, 900]
    # 0.2's teeth, the first moved spur (the stem serifs' full reach, Kevin: "far smaller"), the small spur
    three = ["0.2", ("moved", PREVIOUS), ("small", {})]
    sheet(OUT / "small-roman-48px.png", "roman", [GLYPHS], [48], weights, variants=three)
    half = GLYPHS.split(" ")
    sheet(OUT / "small-roman-120px.png", "roman", [" ".join(half[:9]), " ".join(half[9:])], [120], weights, variants=three)
    sheet(OUT / "small-words.png", "roman", WORDS, [48], weights, variants=three)
    # Serif Italic is the roman slanted: its beaked glyphs take the roman's design
    sheet(OUT / "small-italic-48px.png", "slanted", ["S a c s g", "Classic saga goes Jersey"], [48], weights, variants=three)

if __name__ == "__main__":
    main()

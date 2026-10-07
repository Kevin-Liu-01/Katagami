"""Build Kerf Sans masters from Inter's Thin, Regular and Black masters.

Inter -> Kerf Sans, in order:
  1. square punctuation (Inter's ss07) becomes the default; round moves to ss07
  2. quarter arcs squared toward a superellipse (planned on Regular)
  3. round letters narrowed, E F L S widened, stems held constant
  4. composites re-seated on their changed bases
"""

from __future__ import annotations

import shutil
import sys
import unicodedata
from pathlib import Path

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import (  # noqa: E402
    MASTERS, ROOT, assign_categories, load_inter_masters, reflow_composites, resize_glyph, set_names, snapshot, stem, swap_glyph_outlines,
)
from kerf_build.outline import apply_squaring, plan_squaring  # noqa: E402

FAMILY = "Kerf Sans"
OUT = ROOT / "build" / "sans"

# Squaring strength: fraction of the way from Inter's handles to a square corner.
SQUARE_UPPER = 0.36
SQUARE_LOWER = 0.32
COUNTER_BOOST = 1.25  # counters move further so corner strokes don't fatten

# Horizontal ink scale per glyph. Rounds come in toward the straights.
WIDTH = {
    "O": 0.90, "Q": 0.90, "C": 0.92, "G": 0.92, "D": 0.96,
    "o": 0.92, "c": 0.94, "e": 0.94,
    "b": 0.96, "d": 0.96, "p": 0.96, "q": 0.96, "g": 0.96,
    "E": 1.04, "F": 1.04, "L": 1.03, "S": 1.02,
}

KEEP_ROUND = ("circle", "circled", "ring", "degree", "bullet", "dotted")

# Kerf weights sit heavier than Inter's from SemiBold up (Camber Bold ~ Inter 780).
WEIGHT_MAP = [(100, 100), (200, 200), (300, 300), (400, 400), (500, 500),
              (600, 620), (700, 740), (800, 840), (900, 900)]
INSTANCES = ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black"]


def is_upper(font, name: str) -> bool:
    g = font[name]
    if g.unicodes:
        return unicodedata.category(chr(g.unicodes[0])) == "Lu"
    return name[:1].isupper()


def keeps_round(font, name: str) -> bool:
    if any(k in name.lower() for k in KEEP_ROUND):
        return True
    g = font[name]
    return any(0x25A0 <= u <= 0x25FF or 0x2460 <= u <= 0x24FF for u in g.unicodes)


def promote_square_punctuation(fonts) -> None:
    ref = fonts["Regular"]
    pairs = [(g.name[: -len(".ss07")], g.name) for g in ref if g.name.endswith(".ss07")]
    pairs = [(a, b) for a, b in pairs if a in ref]
    for f in fonts.values():
        for a, b in pairs:
            swap_glyph_outlines(f, a, b)
        f.features.text = f.features.text.replace('name "Square punctuation";', 'name "Round punctuation";')


def square_curves(fonts) -> None:
    ref = fonts["Regular"]
    for g in ref:
        if not g.contours or keeps_round(ref, g.name):
            continue
        plan = plan_squaring(g)
        if not plan:
            continue
        s = SQUARE_UPPER if is_upper(ref, g.name) else SQUARE_LOWER
        for f in fonts.values():
            apply_squaring(f[g.name], plan, s, min(0.9, s * COUNTER_BOOST))


def adjust_widths(fonts) -> None:
    for f in fonts.values():
        old = snapshot(f)
        sw = stem(f)
        maps = {name: resize_glyph(f, name, k, sw) for name, k in WIDTH.items()}
        reflow_composites(f, maps, old)


def write_designspace(paths: dict[str, Path]) -> Path:
    ds = DesignSpaceDocument()
    ax = AxisDescriptor()
    ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 100, 400, 900
    ax.map = WEIGHT_MAP
    ds.addAxis(ax)
    for style, w in MASTERS.items():
        s = SourceDescriptor()
        s.path = str(paths[style])
        s.familyName, s.styleName = FAMILY, style
        s.location = {"Weight": dict(WEIGHT_MAP)[w]}
        ds.addSource(s)
    for i, style in enumerate(INSTANCES):
        inst = InstanceDescriptor()
        inst.familyName, inst.styleName = FAMILY, style
        inst.location = {"Weight": dict(WEIGHT_MAP)[(i + 1) * 100]}
        ds.addInstance(inst)
    out = OUT / "KerfSans.designspace"
    ds.write(out)
    return out


def main() -> None:
    fonts = load_inter_masters()
    promote_square_punctuation(fonts)
    square_curves(fonts)
    adjust_widths(fonts)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ROOT / "vendor" / "inter" / "src" / "features", OUT / "features")
    paths = {}
    for style, f in fonts.items():
        set_names(f, FAMILY, style, MASTERS[style])
        assign_categories(f)
        p = OUT / f"KerfSans-{style}.ufo"
        f.save(p, overwrite=True)
        paths[style] = p
    print(write_designspace(paths))


if __name__ == "__main__":
    main()

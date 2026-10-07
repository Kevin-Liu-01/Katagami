"""Build Kerf Mono masters from the Kerf Sans masters.

Kerf Sans -> Kerf Mono:
  1. the disambiguation alternates become the default (serif I, tailed l, flagged 1)
  2. a Bold master is interpolated, so the mono runs Thin..Bold
  3. every glyph is fitted into a 1232-unit cell (0.6 em): wide glyphs
     condensed with stems partly held, narrow letters stretched, the rest centred
  4. dotless i is redrawn with a flag and a foot slab; l and dotless j get a
     flag; zero gets a centre bar
  5. box drawing and block elements are drawn on the cell grid
  6. composites re-seated; kerning dropped
Every fitting decision is made once, on the Regular master.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

import ufoLib2
from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from ufoLib2.objects import Contour, Glyph, Point

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.boxdraw import draw_box_glyphs  # noqa: E402
from kerf_build.fontops import ROOT, assign_categories, composites_to_flatten, decompose, reflow_composites, set_names, snapshot, swap_glyph_outlines  # noqa: E402
from kerf_build.outline import XMap, embolden_x  # noqa: E402

FAMILY = "Kerf Mono"
SANS = ROOT / "build" / "sans"
OUT = ROOT / "build" / "mono"
FEATURES = ROOT / "vendor" / "inter" / "src" / "features"

CELL = 1232
MAX_INK = {"upper": 0.76, "lower": 0.72, "other": 0.76}  # share of the cell
# narrow letters stretched to at least this share of the cell
STRETCH = {"f": 0.66, "t": 0.62, "r": 0.60, "ȷ": 0.50, "J": 0.62, "s": 0.66, "c": 0.66, "z": 0.66}
# Wide glyphs keep only part of the stem compensation. The stems thin, which
# is how a monospace m finds room for its counters.
COMP_FLOOR = 0.45

PROMOTE = ["cv05-l-tail.fea", "cv08-i-serif.fea"]  # the long-flag 1 already comes from Kerf Sans
MASTER_STYLES = {"Thin": (100, 100), "Regular": (400, 400), "Bold": (700, 740)}
INSTANCES = ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold"]
WEIGHT_MAP = [(100, 100), (200, 200), (300, 300), (400, 400), (500, 500), (600, 620), (700, 740)]

# v0.1 coverage: Latin, punctuation, currency, arrows, maths, technical, box drawing, shapes.
RANGES = [(0x20, 0x7E), (0xA0, 0x17F), (0x18F, 0x18F), (0x192, 0x192), (0x1A0, 0x1B0),
          (0x1CD, 0x1DC), (0x218, 0x21B), (0x237, 0x237), (0x259, 0x259),
          (0x2BB, 0x2BC), (0x2C6, 0x2DD), (0x300, 0x328), (0x1E00, 0x1EFF),
          (0x2010, 0x205E), (0x20AC, 0x20BF), (0x2100, 0x215F), (0x2190, 0x21FF),
          (0x2200, 0x22FF), (0x2300, 0x23FF), (0x2500, 0x259F), (0x25A0, 0x25FF)]

MONO_FEATURES = """\
languagesystem DFLT dflt;
languagesystem latn dflt;

# Slashed zero in place of the default centre-bar zero
feature zero {
  sub zero by zero.slash;
} zero;
"""


def interpolate_bold() -> Path:
    """Kerf Sans at design weight 740, as a UFO with the masters' point structure."""
    out = OUT / "instances"
    subprocess.run(
        [sys.executable, "-m", "fontmake", "-m", str(SANS / "KerfSans.designspace"),
         "-i", "Kerf Sans Bold", "-o", "ufo", "--output-dir", str(out)],
        check=True, capture_output=True,
    )
    return next(out.glob("*Bold.ufo"))


def promote_alternates(fonts) -> None:
    ref = fonts["Regular"]
    pairs = []
    for fea in PROMOTE:
        for a, b in re.findall(r"^sub (\S+) by (\S+);", (FEATURES / fea).read_text(), re.M):
            if a in ref and b in ref:
                pairs.append((a, b))
    for f in fonts.values():
        for a, b in pairs:
            swap_glyph_outlines(f, a, b)


def coverage(font) -> set[str]:
    names = {g.name for g in font if any(lo <= u <= hi for u in g.unicodes for lo, hi in RANGES)}
    names |= {"idotless", "jdotless", "zero.slash"}
    out, todo = set(), list(names)
    while todo:
        n = todo.pop()
        if n in out or n not in font:
            continue
        out.add(n)
        todo.extend(c.baseGlyph for c in font[n].components)
    return out


def kind(g: Glyph) -> str:
    if not g.unicodes:
        return "other"
    return {"Lu": "upper", "Ll": "lower"}.get(unicodedata.category(chr(g.unicodes[0])), "other")


def ink_width(font, name: str) -> float:
    b = font[name].getBounds(font)
    return b.xMax - b.xMin


def plan_scales(ref) -> dict[str, float]:
    """Horizontal scale for each outline glyph, decided on Regular."""
    scales = {}
    for g in ref:
        if not g.contours or g.components or g.width == 0:
            continue
        ink = ink_width(ref, g.name)
        first = chr(g.unicodes[0]) if g.unicodes else ""
        limit = MAX_INK[kind(g)] * CELL
        scale = 1.0
        if ink > limit:
            scale = limit / ink
        elif first in STRETCH and ink < STRETCH[first] * CELL:
            scale = min(1.4, STRETCH[first] * CELL / ink)
        scales[g.name] = scale
    return scales


def compensation(scale: float) -> float:
    """Share of the lost (or gained) stem weight to put back."""
    if scale >= 0.85:
        return 1.0
    return max(COMP_FLOOR, COMP_FLOOR + (1 - COMP_FLOOR) * (scale - 0.55) / 0.30)


def fit_to_cell(font, g: Glyph, scale: float, stem: float) -> XMap:
    b = g.getBounds(font)
    cx = (b.xMin + b.xMax) / 2
    if scale != 1.0:
        for c in g.contours:
            for p in c.points:
                p.x = cx + (p.x - cx) * scale
        embolden_x(g, stem * (1 - scale) * compensation(scale))
    nb = g.getBounds(font)
    dx = CELL / 2 - (nb.xMin + nb.xMax) / 2
    for c in g.contours:
        for p in c.points:
            p.x += dx
    xmap = XMap(cx, CELL / 2, scale)
    for a in g.anchors:
        a.x = xmap(a.x)
    g.width = CELL
    return xmap


def polygon(pts) -> Contour:
    return Contour(points=[Point(round(x), round(y), "line") for x, y in pts])


def stem_left_at(g: Glyph, y: float) -> float:
    """Leftmost outline crossing of the horizontal line at y (straight segments)."""
    xs = []
    for c in g.contours:
        pts = c.points
        for k in range(len(pts)):
            p, q = pts[k - 1], pts[k]
            if p.type and q.type and (p.y - y) * (q.y - y) < 0:
                xs.append(p.x + (y - p.y) * (q.x - p.x) / (q.y - p.y))
    return min(xs)


def draw_slabs(font, stem: float, bar: float) -> None:
    """Flags and foot slab, drawn in cell coordinates after fitting."""
    xh = font.info.xHeight
    cx = CELL / 2
    sl, sr = cx - stem / 2, cx + stem / 2
    flag = CELL * 0.20
    foot = CELL * 0.30

    g = font["idotless"]
    g.clearContours()
    g.appendContour(polygon([
        (cx - foot, 0), (cx + foot, 0), (cx + foot, bar), (sr, bar), (sr, xh),
        (sl - flag, xh), (sl - flag, xh - bar), (sl, xh - bar), (sl, bar), (cx - foot, bar),
    ]))

    for name, top in (("jdotless", xh), ("l", font["l"].getBounds(font).yMax)):
        g = font[name]
        left = stem_left_at(g, top - bar)
        g.appendContour(polygon([
            (left - flag, top - bar), (left + stem / 2, top - bar), (left + stem / 2, top), (left - flag, top),
        ]))


def bar_zero(font, stem: float) -> None:
    """A short vertical bar in the centre of the zero's counter."""
    g = font["zero"]
    b = g.getBounds(font)
    cx, cy = (b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2
    h, w = (b.yMax - b.yMin) * 0.30, stem * 0.9
    g.appendContour(polygon([(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2),
                             (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]))


def write_designspace(paths) -> Path:
    ds = DesignSpaceDocument()
    ax = AxisDescriptor()
    ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 100, 400, 700
    ax.map = WEIGHT_MAP
    ds.addAxis(ax)
    for style, (_, design) in MASTER_STYLES.items():
        s = SourceDescriptor()
        s.path = str(paths[style])
        s.familyName, s.styleName = FAMILY, style
        s.location = {"Weight": design}
        ds.addSource(s)
    for i, style in enumerate(INSTANCES):
        inst = InstanceDescriptor()
        inst.familyName, inst.styleName = FAMILY, style
        inst.location = {"Weight": dict(WEIGHT_MAP)[(i + 1) * 100]}
        ds.addInstance(inst)
    out = OUT / "KerfMono.designspace"
    ds.write(out)
    return out


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    bold = interpolate_bold()
    fonts = {
        "Thin": ufoLib2.Font.open(SANS / "KerfSans-Thin.ufo", lazy=False),
        "Regular": ufoLib2.Font.open(SANS / "KerfSans-Regular.ufo", lazy=False),
        "Bold": ufoLib2.Font.open(bold, lazy=False),
    }
    promote_alternates(fonts)
    keep = coverage(fonts["Regular"])
    flatten = composites_to_flatten(fonts["Regular"])
    for f in fonts.values():
        decompose(f, flatten)
        for name in [g.name for g in f if g.name not in keep]:
            del f[name]
    scales = plan_scales(fonts["Regular"])
    zero_width = {g.name for g in fonts["Regular"] if g.width == 0}

    for style, f in fonts.items():
        f.kerning.clear()
        f.groups.clear()
        f.features.text = MONO_FEATURES
        stem = ink_width(f, "idotless")
        b = f["hyphen"].getBounds(f)
        bar = b.yMax - b.yMin
        old = snapshot(f)
        maps = {name: fit_to_cell(f, f[name], k, stem) for name, k in scales.items()}
        draw_slabs(f, stem, bar)
        bar_zero(f, stem)
        reflow_composites(f, maps, old)
        for g in f:
            g.width = 0 if g.name in zero_width else CELL
        draw_box_glyphs(f, CELL, stem, bar)
        f.info.postscriptIsFixedPitch = True
        f.info.openTypeOS2Panose = [2, 11, 5, 9, 2, 2, 3, 2, 2, 4]
        set_names(f, FAMILY, style, MASTER_STYLES[style][0])
        assign_categories(f)

    paths = {}
    for style, f in fonts.items():
        p = OUT / f"KerfMono-{style}.ufo"
        f.save(p, overwrite=True)
        paths[style] = p
    print(write_designspace(paths))


if __name__ == "__main__":
    main()

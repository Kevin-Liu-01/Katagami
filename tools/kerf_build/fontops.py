"""Font-level operations shared by the sans and mono builds."""

from __future__ import annotations

import copy
import math

import numpy as np
import pathops
from fontTools.pens.pointPen import SegmentToPointPen
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from pathlib import Path

import ufoLib2
from ufoLib2.objects import Glyph

from .outline import IDENTITY, XMap, embolden_x, scale_contours_x

ROOT = Path(__file__).resolve().parents[2]
INTER_UFO = ROOT / "build" / "ufo"
INTER_ITALIC_UFO = ROOT / "build" / "ufo-italic"
MASTERS = {"Thin": 100, "Regular": 400, "Black": 900}
VERSION = (0, 200)  # major, minor: "Version 0.200"
VENDOR = "KATA"  # OS/2 achVendID and the vendor in each unique ID (name 3)
# The style name of each master in an Italic. The masters keep the roman keys
# (Thin, Regular, Black) inside the build, so every transform reads them alike.
ITALIC_STYLES = {"Thin": "Thin Italic", "Regular": "Italic", "Black": "Black Italic"}


def italic_style(style: str) -> str:
    """Thin -> Thin Italic, Regular -> Italic, Bold -> Bold Italic."""
    return "Italic" if style == "Regular" else f"{style} Italic"


def load_inter_masters(italic: bool = False) -> dict[str, ufoLib2.Font]:
    if italic:
        return {
            name: ufoLib2.Font.open(INTER_ITALIC_UFO / f"Inter-{ITALIC_STYLES[name].replace(' ', '')}.ufo", lazy=False)
            for name in MASTERS
        }
    return {
        name: ufoLib2.Font.open(INTER_UFO / f"Inter-{name}.ufo", lazy=False)
        for name in MASTERS
    }


def slant_tangent(font) -> float:
    """The italic's slant as dx per unit of height: tan 9.4 degrees for Inter Italic."""
    return math.tan(math.radians(-(font.info.italicAngle or 0)))


def shear(fonts: dict, t: float, y0: float) -> None:
    """Shear every glyph by x += (y - y0) * t: t < 0 stands an italic upright,
    t > 0 slants it again. Contours and anchors move as points and component
    offsets as vectors, so composites stay whole. Components with a scaled or
    flipped matrix must be decomposed first (`decompose_transformed`)."""
    for f in fonts.values():
        for g in f:
            for c in g.contours:
                for p in c.points:
                    p.x += (p.y - y0) * t
            for a in g.anchors:
                a.x += (a.y - y0) * t
            for comp in g.components:
                xx, xy, yx, yy, dx, dy = comp.transformation
                comp.transformation = (xx, xy, yx, yy, dx + dy * t, dy)


def decompose_transformed(fonts: dict) -> None:
    """Decompose every composite with a flipped, scaled or rotated component,
    whose matrix a shear would turn into a skew."""
    ref = next(iter(fonts.values()))
    names = [g.name for g in ref if any(tuple(c.transformation)[:4] != (1, 0, 0, 1) for c in g.components)]
    for f in fonts.values():
        decompose(f, names)


def stem(font: ufoLib2.Font) -> float:
    """Lowercase vertical stem thickness, read from the ink width of the dotless i,
    which is a plain stem in every member (Katagami Text's l has a tail)."""
    b = font["idotless" if "idotless" in font else "l"].getBounds(font)
    return b.xMax - b.xMin


def resize_glyph(font, name: str, scale: float, stem_w: float) -> XMap:
    """Scale a glyph's ink horizontally about its left sidebearing.

    Sidebearings stay; the advance changes by the change in ink width.
    Stems are restored to their original thickness by emboldening.
    """
    g = font[name]
    b = g.getBounds(font)
    if b is None or not g.contours:
        return IDENTITY
    xmap = XMap(b.xMin, b.xMin, scale)
    scale_contours_x(g, xmap)
    embolden_x(g, stem_w * (1 - scale))
    nb = g.getBounds(font)
    # emboldening grows or shrinks ink on both sides; put the left edge back
    dx = b.xMin - nb.xMin
    for c in g.contours:
        for p in c.points:
            p.x += dx
    new_ink = nb.xMax - nb.xMin
    old_ink = b.xMax - b.xMin
    g.width = round(g.width + (new_ink - old_ink))
    # anchors were already moved by scale_contours_x; compose the real map
    return XMap(b.xMin, b.xMin, new_ink / old_ink)


def is_mark(font, name: str) -> bool:
    return font[name].width == 0


def composites_to_flatten(font) -> list[str]:
    """Flatten every composite except base + combining marks.

    Accented letters keep their components so marks can be re-seated; glyphs
    built from parts (t from a contour and a part, colon from two periods)
    become plain outlines so they can be fitted as a whole.
    """
    return [
        g.name for g in font
        if g.components and (
            g.contours
            or is_mark(font, g.components[0].baseGlyph)
            or any(not is_mark(font, c.baseGlyph) for c in g.components[1:])
            # flipped or rotated parts (an arrow from another arrow, ¿ from ?)
            or any(tuple(c.transformation)[:4] != (1, 0, 0, 1) for c in g.components)
        )
    ]


def decompose(font, names: list[str]) -> None:
    for name in names:
        g = font[name]
        rec = DecomposingRecordingPen(font, reverseFlipped=True)
        for comp in g.components:
            comp.draw(rec)
        g.clearComponents()
        rec.replay(SegmentToPointPen(g.getPointPen()))


def snapshot(font) -> dict[str, tuple[float, float]]:
    """Advance and ink centre of every glyph, taken before any transform."""
    out = {}
    for g in font:
        b = g.getBounds(font)
        out[g.name] = (g.width, 0 if b is None else (b.xMin + b.xMax) / 2)
    return out


def reflow_composites(font, maps: dict[str, XMap], before: dict[str, tuple[float, float]]) -> None:
    """Re-seat components and advances after base glyphs changed width.

    `maps` holds glyphs whose outlines were remapped and how; `before` is a
    snapshot from before any change. A composite takes the map of its first
    component; every other component is moved so its centre lands where the
    map sends it.
    """
    resolved: dict[str, XMap] = dict(maps)

    def center_now(gname: str) -> float:
        b = font[gname].getBounds(font)
        return 0 if b is None else (b.xMin + b.xMax) / 2

    def visit(name: str, stack=()) -> XMap:
        if name in resolved:
            return resolved[name]
        g = font[name]
        if g.contours or not g.components or name in stack:
            resolved[name] = IDENTITY
            return IDENTITY
        base = g.components[0]
        base_map = visit(base.baseGlyph, stack + (name,))
        if base_map is IDENTITY or base.transformation[0] != 1:
            resolved[name] = IDENTITY
            return IDENTITY
        m = base_map.shifted(base.transformation[4])
        for comp in g.components[1:]:
            visit(comp.baseGlyph, stack + (name,))
            t = list(comp.transformation)
            if t[0] != 1:
                continue
            here = t[4] + before[comp.baseGlyph][1]
            t[4] = round(m(here) - center_now(comp.baseGlyph))
            comp.transformation = tuple(t)
        for a in g.anchors:
            a.x = round(m(a.x))
        if before[name][0]:  # a zero-width mark built from a spacing glyph stays zero width
            g.width = round(g.width + font[base.baseGlyph].width - before[base.baseGlyph][0])
        resolved[name] = m
        return m

    for g in list(font):
        if g.components and not g.contours:
            visit(g.name)


def promote_alternates(fonts: dict, fea_files, features_dir: Path) -> None:
    """Make the alternates named in Inter's feature files the default glyphs.

    Each `sub a by b;` swaps a and b, so the feature now turns the default
    back into Inter's original. Pairs are read on Regular and applied to all.
    """
    import re

    ref = fonts["Regular"]
    pairs = []
    for fea in fea_files:
        for a, b in re.findall(r"^sub\s+(\S+)\s+by\s+(\S+)\s*;", (features_dir / fea).read_text(), re.M):
            if a in ref and b in ref:
                pairs.append((a, b))
    # A swapped composite (aacute and aacute.2) points at a swapped base (a and a.2),
    # so its components follow the swap too: the default aacute is built on the new a.
    swap = {a: b for a, b in pairs} | {b: a for a, b in pairs}
    for f in fonts.values():
        for a, b in pairs:
            swap_glyph_outlines(f, a, b)
        for name in swap:
            for comp in f[name].components:
                if comp.baseGlyph in swap:
                    comp.baseGlyph = swap[comp.baseGlyph]


def respace(fonts: dict, delta) -> None:
    """Add `delta` units to both sidebearings of every spacing glyph.

    `delta` is one number for every master, or a {master: units} dict.

    Outlines and anchors move right by delta and advances grow by 2 delta.
    Composites follow their base; marks inside them move with the base.
    """
    deltas = delta if isinstance(delta, dict) else {style: delta for style in fonts}
    if not any(deltas.values()):
        return
    import unicodedata

    ref = fonts["Regular"]
    # nonspacing marks and glyphs narrower than the change keep their advance
    skip = {g.name for g in ref
            if g.width <= 2 * max(abs(d) for d in deltas.values())
            or (g.unicodes and unicodedata.category(chr(g.unicodes[0])) in ("Mn", "Me"))
            or g.name.endswith("comb")}
    for style, f in fonts.items():
        delta = deltas.get(style, 0)
        if not delta:
            continue
        widths = {g.name: g.width for g in f}
        for g in f:
            if g.name in skip:
                continue
            if g.contours:
                for c in g.contours:
                    for p in c.points:
                        p.x += delta
                for a in g.anchors:
                    a.x += delta
            elif g.components:
                for comp in g.components[1:]:
                    if comp.baseGlyph in skip or widths.get(comp.baseGlyph, 1) == 0:
                        t = list(comp.transformation)
                        t[4] += delta
                        comp.transformation = tuple(t)
                for a in g.anchors:
                    a.x += delta
            g.width = round(g.width + 2 * delta)


def assign_categories(font) -> None:
    """Write GDEF classes explicitly.

    The minimal Glyphs -> UFO conversion drops Glyphs' categories, and ufo2ft
    then guesses from anchors: Inter's j has a `_right` anchor and would
    become a zero-advance mark. Marks are the zero-width glyphs that attach,
    and the zero-width glyphs Unicode calls combining or enclosing marks.
    """
    import unicodedata

    def mark(g) -> bool:
        if g.width:
            return False
        # enclosing and combining marks without anchors (the Cyrillic U+0488 and U+0489) are marks too
        return any(a.name.startswith("_") for a in g.anchors) or any(unicodedata.category(chr(u)) in ("Mn", "Me") for u in g.unicodes)

    font.lib["public.openTypeCategories"] = {g.name: "mark" if mark(g) else "base" for g in font}


def swap_glyph_outlines(font, a: str, b: str) -> None:
    """Exchange drawing, anchors and width of two glyphs, keeping names and unicodes."""
    ga, gb = font[a], font[b]
    da = (copy.deepcopy(ga.contours), copy.deepcopy(ga.components),
          copy.deepcopy(ga.anchors), ga.width)
    for dst, src in ((ga, gb),):
        dst.clearContours(); dst.clearComponents(); dst.clearAnchors()
        for c in src.contours:
            dst.appendContour(copy.deepcopy(c))
        for c in src.components:
            dst.components.append(copy.deepcopy(c))
        for an in src.anchors:
            dst.appendAnchor(copy.deepcopy(an))
        dst.width = src.width
    gb.clearContours(); gb.clearComponents(); gb.clearAnchors()
    for c in da[0]:
        gb.appendContour(c)
    for c in da[1]:
        gb.components.append(c)
    for an in da[2]:
        gb.appendAnchor(an)
    gb.width = da[3]


def set_names(font, family: str, style: str, weight: int) -> None:
    i = font.info
    i.familyName = family
    i.styleName = style
    i.styleMapFamilyName = None
    i.styleMapStyleName = None
    i.openTypeNamePreferredFamilyName = None
    i.openTypeNamePreferredSubfamilyName = None
    i.postscriptFontName = f"{family.replace(' ', '')}-{style.replace(' ', '')}"
    i.postscriptFullName = f"{family} {style}"
    i.openTypeNameUniqueID = None
    i.openTypeOS2WeightClass = weight
    i.openTypeOS2VendorID = VENDOR
    i.copyright = (
        "Copyright 2026 The Katagami Project Authors (https://github.com/Kevin-Liu-01/Katagami). "
        "Derived from Inter, Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)."
    )
    i.trademark = None
    i.openTypeNameDesigner = "Kevin Liu"
    i.openTypeNameDesignerURL = "https://github.com/Kevin-Liu-01"
    i.openTypeNameManufacturer = "The Katagami Project Authors"
    i.openTypeNameManufacturerURL = "https://github.com/Kevin-Liu-01/Katagami"
    i.openTypeNameLicense = (
        "This Font Software is licensed under the SIL Open Font License, Version 1.1. "
        "This license is available with a FAQ at: https://openfontlicense.org"
    )
    i.openTypeNameLicenseURL = "https://openfontlicense.org"
    i.openTypeNameDescription = None
    i.openTypeNameSampleText = None
    i.versionMajor, i.versionMinor = VERSION
    i.openTypeNameVersion = None
    i.openTypeHeadCreated = None


FILTERS_KEY = "com.github.googlei18n.ufo2ft.filters"


def erase_open_corners(fonts: dict) -> int:
    """Run Inter's eraseOpenCorners filter here, where every master agrees.

    Inter's sources ask ufo2ft to erase open corners at compile time, master
    by master. Katagami's transforms can leave a corner open in one master and
    closed in another; erasing it in one master only breaks compatibility.
    Here the filter runs on copies of every master, its result is kept for a
    glyph only when all masters come out with the same structure, and the
    compile-time filter is removed. Returns the number of glyphs erased.
    """
    from glyphsLib.filters.eraseOpenCorners import EraseOpenCornersFilter

    results = {}
    for style, f in fonts.items():
        copies = {g.name: copy.deepcopy(g) for g in f}
        modified = EraseOpenCornersFilter()(f, copies)
        results[style] = (copies, modified)
    shape = lambda g: [[p.type for p in c.points] for c in g.contours]  # noqa: E731
    names = set().union(*(m for _, m in results.values()))
    kept = 0
    for name in names:
        outs = [results[style][0][name] for style in fonts]
        if any(shape(o) != shape(outs[0]) for o in outs):
            continue
        for (style, f), out in zip(fonts.items(), outs):
            g = f[name]
            g.clearContours()
            for c in out.contours:
                g.appendContour(copy.deepcopy(c))
        kept += 1
    for f in fonts.values():
        f.lib[FILTERS_KEY] = [x for x in f.lib.get(FILTERS_KEY, []) if x.get("name") != "eraseOpenCorners"]
    return kept


def ink_outline(font, g, steps: int = 12) -> tuple[int, np.ndarray]:
    """A glyph's filled shape: the number of contours once its overlaps are
    removed, and points every 1/steps of each segment of that outline, its
    ink centred on x = 0. Components are drawn in."""
    path = pathops.Path()
    rec = DecomposingRecordingPen(font)
    g.draw(rec)
    rec.replay(path.getPen())
    try:
        path = pathops.simplify(path, fix_winding=True, keep_starting_points=False)
    except pathops.PathOpsError:
        pass  # Skia cannot resolve some overlaps (Serif Black's k.sups): compare the outline as drawn
    out = RecordingPen()
    path.draw(out)
    ts = np.linspace(0, 1, steps + 1)[1:, None]
    pts, contours, cur, start = [], 0, None, None
    for op, args in out.value:
        if op == "moveTo":
            cur = start = np.array(args[0], float)
            contours += 1
            pts.append(cur[None])
            continue
        if op in ("closePath", "endPath"):
            seg = [cur, start]
        else:
            seg = [cur] + [np.array(a, float) for a in args]
        if len(seg) == 2:
            pts.append(seg[0] + (seg[1] - seg[0]) * ts)
        elif len(seg) == 3:  # quadratic
            u = 1 - ts
            pts.append(u * u * seg[0] + 2 * u * ts * seg[1] + ts * ts * seg[2])
        else:
            u = 1 - ts
            pts.append(u**3 * seg[0] + 3 * u * u * ts * seg[1] + 3 * u * ts * ts * seg[2] + ts**3 * seg[3])
        cur = seg[-1]
    if not pts:
        return 0, np.zeros((0, 2))
    a = np.concatenate(pts)
    a[:, 0] -= (a[:, 0].min() + a[:, 0].max()) / 2
    return contours, a


def outline_distance(a: np.ndarray, b: np.ndarray) -> float:
    """The farthest any point of either outline lies from the other (Hausdorff)."""
    if not len(a) or not len(b):
        return 0.0 if len(a) == len(b) else math.inf
    def one(p, q):
        worst = 0.0
        for k in range(0, len(p), 1024):
            d = ((p[k:k + 1024, None, :] - q[None, :, :]) ** 2).sum(-1).min(1).max()
            worst = max(worst, float(d))
        return worst
    return math.sqrt(max(one(a, b), one(b, a)))


def design_difference(fa, a, fb, b) -> tuple[int, int, float]:
    """Contours of each filled shape and the outline distance between them, in units."""
    ca, pa = ink_outline(fa, a)
    cb, pb = ink_outline(fb, b)
    return ca, cb, (outline_distance(pa, pb) if ca == cb else math.inf)


ITALIC_MATCH = 64  # units: the farthest an upright Italic glyph's outline may lie from its roman's and keep Inter Italic's drawing


def design_distances(italic: dict, roman: dict) -> dict[str, float]:
    """For every roman glyph, how far the upright Italic's glyph of the same
    name lies from it: the largest outline distance over the masters, or
    infinity where the Italic lacks the glyph or the filled shapes have a
    different number of contours."""
    out = {}
    for name in roman["Regular"].keys():
        if name not in italic["Regular"]:
            out[name] = math.inf
            continue
        out[name] = max(design_difference(roman[s], roman[s][name], italic[s], italic[s][name])[2] for s in roman)
    return out


def romanize(italic: dict, roman: dict, names) -> None:
    """Make an Italic its roman slanted: the glyphs in `names` take the
    roman's drawing, anchors and advance, so the slant is their only change,
    and the Italic takes the roman's glyph set and order, features, kerning
    and groups. Both are the member's masters upright (the Italic stood
    upright and put through the roman's transforms); the other glyphs keep
    the Italic's drawing, with Inter Italic's optical refinements.

    Where a composite and one of its components come from different fonts
    (a roman aacute over the Italic's acutecomb), the component moves by the
    difference between the two drawings' ink centres, so it lands where the
    composite's own font had it: Inter Italic draws its marks further left of
    their origin than the roman does."""
    names = set(names)
    def centre(font, name):
        b = font[name].getBounds(font)
        return (0.0, 0.0) if b is None else ((b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2)
    for style, f in italic.items():
        r = roman[style]
        own = {name: centre(f, name) for name in f.keys()}  # the Italic's drawing, before any glyph is replaced
        for name in names:
            f.layers.defaultLayer.insertGlyph(r[name], name, overwrite=True, copy=True)
        for g in f:
            for comp in g.components:
                base = comp.baseGlyph
                if (g.name in names) == (base in names) or base not in own or base not in r or tuple(comp.transformation[:4]) != (1, 0, 0, 1):
                    continue
                (ix, iy), (rx, ry) = own[base], centre(r, base)
                dx, dy = (rx - ix, ry - iy) if g.name in names else (ix - rx, iy - ry)
                xx, xy, yx, yy, ox, oy = comp.transformation
                comp.transformation = (xx, xy, yx, yy, ox + dx, oy + dy)
        extra = [name for name in f.keys() if name not in r]
        for g in f:
            if any(c.baseGlyph in extra for c in g.components):
                decompose(f, [g.name])
        for name in extra:
            del f[name]
        f.features.text = r.features.text
        f.kerning.clear()
        f.kerning.update(r.kerning)
        f.groups.clear()
        f.groups.update({k: list(v) for k, v in r.groups.items()})
        for key in ("public.glyphOrder", "public.postscriptNames", "public.skipExportGlyphs"):
            if key in r.lib:
                f.lib[key] = copy.deepcopy(r.lib[key])
            else:
                f.lib.pop(key, None)
    # roman composites with flipped or scaled parts are drawn in, as the Italic's were
    decompose_transformed(italic)


DOTTED_CIRCLE = "uni25CC"
DOTS = 10  # dots around the ring: as many as Black's dots leave white between
DOT_SHARE = 0.7  # a dot across, at Regular, as a share of the Regular stem
DOT_POWER = 0.5  # toward Thin and Black a dot grows with the master's stem to this power
DOT_GAP = 0.3  # the least white between two dots, as a share of the distance between their centres
KAPPA = 0.5523


def dot_size(stem_w: float, stem_regular: float) -> float:
    """A dotted circle's dot, across, for a master whose stem is stem_w."""
    return DOT_SHARE * stem_regular * (stem_w / stem_regular) ** DOT_POWER


# Anchors the circle takes from another letter than o: Inter's o has its ogonek
# anchor halfway up its side, for the ogonek.o it is built with (ǫ), where the
# plain ogonek mark would float; a's sits at the foot, as the mark expects.
DOTTED_REFS = {"ogonek": "a"}


def dotted_circle_anchors(font, ref: str = "o") -> dict[str, str]:
    """The base anchors a dotted circle needs, each with the letter it is
    taken from: every anchor a zero-width mark attaches by and some letter
    has, from the round letter `ref` where it has it (or the letter
    DOTTED_REFS names) and otherwise from the first letter in the glyph order
    that does. Decided on one master and used in all, so every master's
    circle has the same anchors."""
    marks = {a.name[1:] for m in font if m.width == 0 for a in m.anchors if a.name.startswith("_")}
    order = font.lib.get("public.glyphOrder") or list(font.keys())
    letters = [font[n] for n in order if n in font and font[n].width and font[n].unicodes]
    out = {}
    for an in sorted(marks):
        other = DOTTED_REFS.get(an)
        if other in font and any(a.name == an for a in font[other].anchors):
            out[an] = other
            continue
        if any(a.name == an for a in font[ref].anchors):
            out[an] = ref
            continue
        for h in letters:
            if any(a.name == an for a in h.anchors) and h.getBounds(font) is not None:
                out[an] = h.name
                break
    return out


def draw_dotted_circle(font, dot: float, diameter: float, advance: float, anchors: dict[str, str], ref: str = "o") -> None:
    """U+25CC DOTTED CIRCLE: DOTS round dots `dot` units across on a ring
    `diameter` across at its outside, centred in an `advance` and on half the
    x-height, with a dot at the top. Each of `anchors` (dotted_circle_anchors)
    is placed where its letter has it: at the letter's height and moved
    across with the ring where the letter is the round letter `ref`, and
    otherwise at the same place in the ring's box as in the letter's.
    Shaping engines set the circle under a mark that has no base, so the
    mark sits on it as on a letter."""
    name = DOTTED_CIRCLE
    g = font[name] if name in font else font.newGlyph(name)
    g.clearContours()
    g.clearComponents()
    g.clearAnchors()
    g.unicodes = [0x25CC]
    g.width = round(advance)
    cx, cy = advance / 2, font.info.xHeight / 2
    ring = diameter / 2 - dot / 2
    spacing = 2 * ring * math.sin(math.pi / DOTS)
    r = min(dot, (1 - DOT_GAP) * spacing) / 2
    k = KAPPA * r
    for n in range(DOTS):
        a = math.pi / 2 + 2 * math.pi * n / DOTS
        x, y = cx + ring * math.cos(a), cy + ring * math.sin(a)
        c = ufoLib2.objects.Contour()
        for px, py, kind in ((x + r, y, "curve"), (x + r, y + k, None), (x + k, y + r, None), (x, y + r, "curve"),
                             (x - k, y + r, None), (x - r, y + k, None), (x - r, y, "curve"),
                             (x - r, y - k, None), (x - k, y - r, None), (x, y - r, "curve"),
                             (x + k, y - r, None), (x + r, y - k, None)):
            c.points.append(ufoLib2.objects.Point(round(px, 1), round(py, 1), kind, smooth=kind is not None))
        g.appendContour(c)
    x0, y0 = cx - diameter / 2, cy - diameter / 2
    for an, src in anchors.items():
        h = font[src]
        hb = h.getBounds(font)
        ax, ay = next((a.x, a.y) for a in h.anchors if a.name == an)
        if src == ref:
            g.appendAnchor({"name": an, "x": round(ax - (hb.xMin + hb.xMax) / 2 + cx), "y": round(ay)})
        else:
            u, v = (ax - hb.xMin) / (hb.xMax - hb.xMin), (ay - hb.yMin) / (hb.yMax - hb.yMin)
            g.appendAnchor({"name": an, "x": round(x0 + u * diameter), "y": round(y0 + v * diameter)})
    order = font.lib.get("public.glyphOrder")
    if order is not None and name not in order:
        order.append(name)


DOUBLE_ACUTE = "hungarumlautcomb"


def combining_double_acute(font) -> None:
    """U+030B COMBINING DOUBLE ACUTE ACCENT, which Inter has no glyph for, as
    Inter's own double acute set as a mark: a component of hungarumlaut
    (U+02DD, which Inter draws as its double grave mirrored), no advance,
    hungarumlaut's _top anchor, and a top anchor as far above the ink as the
    double grave's, so marks stack on it. Nothing is drawn: it is the same
    outline as the spacing accent and the one in ő."""
    if "hungarumlaut" not in font or "dblgravecmb" not in font:
        return
    src, grave = font["hungarumlaut"], font["dblgravecmb"]
    top = next((a for a in src.anchors if a.name == "_top"), None)
    if top is None:
        return
    g = font[DOUBLE_ACUTE] if DOUBLE_ACUTE in font else font.newGlyph(DOUBLE_ACUTE)
    g.clearContours()
    g.clearComponents()
    g.clearAnchors()
    g.unicodes = [0x030B]
    g.width = 0
    g.components.append(ufoLib2.objects.Component("hungarumlaut"))
    g.appendAnchor({"name": "_top", "x": top.x, "y": top.y})
    above = next((a for a in grave.anchors if a.name == "top"), None)
    sb, gb = src.getBounds(font), grave.getBounds(font)
    if above is not None and sb is not None and gb is not None:
        g.appendAnchor({"name": "top", "x": top.x, "y": round(sb.yMax + above.y - gb.yMax)})
    order = font.lib.get("public.glyphOrder")
    if order is not None and DOUBLE_ACUTE not in order:
        order.append(DOUBLE_ACUTE)

"""Font-level operations shared by the sans and mono builds."""

from __future__ import annotations

import copy

from fontTools.pens.pointPen import SegmentToPointPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from pathlib import Path

import ufoLib2
from ufoLib2.objects import Glyph

from .outline import IDENTITY, XMap, embolden_x, scale_contours_x

ROOT = Path(__file__).resolve().parents[2]
INTER_UFO = ROOT / "build" / "ufo"
MASTERS = {"Thin": 100, "Regular": 400, "Black": 900}


def load_inter_masters() -> dict[str, ufoLib2.Font]:
    return {
        name: ufoLib2.Font.open(INTER_UFO / f"Inter-{name}.ufo", lazy=False)
        for name in MASTERS
    }


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


def respace(fonts: dict, delta: float) -> None:
    """Add `delta` units to both sidebearings of every spacing glyph.

    Outlines and anchors move right by delta and advances grow by 2 delta.
    Composites follow their base; marks inside them move with the base.
    """
    if not delta:
        return
    import unicodedata

    ref = fonts["Regular"]
    # nonspacing marks and glyphs narrower than the change keep their advance
    skip = {g.name for g in ref
            if g.width <= 2 * abs(delta)
            or (g.unicodes and unicodedata.category(chr(g.unicodes[0])) in ("Mn", "Me"))
            or g.name.endswith("comb")}
    for f in fonts.values():
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
    become a zero-advance mark. Marks are the zero-width glyphs that attach.
    """
    font.lib["public.openTypeCategories"] = {
        g.name: "mark" if g.width == 0 and any(a.name.startswith("_") for a in g.anchors) else "base"
        for g in font
    }


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
    i.openTypeOS2VendorID = "KERF"
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
    i.versionMajor = 0
    i.versionMinor = 100
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

"""Merge other scripts into a Katagami member, the way Pretendard joins Inter
and Source Han Sans.

    python tools/build_world.py sans|round|text [--only Devanagari,Thai]

Katagami draws Latin, Greek and Cyrillic. For 19 more scripts this takes the
outlines and OpenType layout of Google's Noto Sans fonts (SIL OFL 1.1,
vendor/noto, fetched by tools/build.sh), so one Katagami file sets them all:

  1. Each Noto font is subset to its script's Unicode blocks with its layout
     closure, so it adds no Latin, digits or punctuation of its own.
  2. It is instanced at Katagami's three master weights (100, 400, 900) and
     scaled from Noto's 1000-unit em to Katagami's 2048, times Katagami's x-height
     over Noto Sans's (536), so its letters sit at Katagami's size.
  3. Each Katagami master (instanced from fontmake's variable font) is merged
     with the scripts at the same weight.
  4. The three merged masters are built back into one variable font with
     Katagami's weight axis and named instances.

Katagami's own line spacing is kept; the Windows clipping box grows to the
tallest script. Katagami's dotted circle (U+25CC) becomes a base in every
script's mark-to-base lookups, at the anchors Noto gives its own, so shaping
engines set a mark without a base on it (`seat_dotted_circle`). The glyphs added here are Noto's design at Katagami's size and
weight, not redrawn in Katagami's style.
"""

from __future__ import annotations

import copy
import math
import sys
import tempfile
from pathlib import Path

from fontTools import subset
from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.merge import Merger, Options
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib import build as build_variable
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.outline import signed_area, sound  # noqa: E402
from kerf_build.profiles import PROFILES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOTO = ROOT / "vendor" / "noto"
NOTO_XHEIGHT = 536  # Noto Sans, per 1000
MASTERS = {"Thin": 100, "Regular": 400, "Black": 900}
INSTANCES = ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black"]

# Noto file stem -> the Unicode blocks taken from it
SCRIPTS = {
    "Devanagari": [(0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x1CD0, 0x1CFF)],
    "Arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x0870, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "Bengali": [(0x0980, 0x09FF)],
    "Gurmukhi": [(0x0A00, 0x0A7F)],
    "Gujarati": [(0x0A80, 0x0AFF)],
    "Oriya": [(0x0B00, 0x0B7F)],
    "Tamil": [(0x0B80, 0x0BFF), (0x11FC0, 0x11FFF)],
    "Telugu": [(0x0C00, 0x0C7F)],
    "Kannada": [(0x0C80, 0x0CFF)],
    "Malayalam": [(0x0D00, 0x0D7F)],
    "Sinhala": [(0x0D80, 0x0DFF), (0x111E0, 0x111FF)],
    "Thai": [(0x0E00, 0x0E7F)],
    "Lao": [(0x0E80, 0x0EFF)],
    "Myanmar": [(0x1000, 0x109F), (0xA9E0, 0xA9FF), (0xAA60, 0xAA7F)],
    "Ethiopic": [(0x1200, 0x139F), (0x2D80, 0x2DDF), (0xAB00, 0xAB2F), (0x1E7E0, 0x1E7FF)],
    "Hebrew": [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)],
    "Armenian": [(0x0530, 0x058F), (0xFB13, 0xFB17)],
    "Georgian": [(0x10A0, 0x10FF), (0x2D00, 0x2D2F), (0x1C90, 0x1CBF)],
    "Khmer": [(0x1780, 0x17FF), (0x19E0, 0x19FF)],
    # v0.2: the nine scripts of the eleven languages the map listed as missing
    "Tifinagh": [(0x2D30, 0x2D7F)],
    "OlChiki": [(0x1C50, 0x1C7F)],
    "Coptic": [(0x2C80, 0x2CFF), (0x03E2, 0x03EF), (0x102E0, 0x102FF)],
    "Tibetan": [(0x0F00, 0x0FFF)],  # only Noto Serif Tibetan exists
    "HanifiRohingya": [(0x10D00, 0x10D3F)],
    "NKo": [(0x07C0, 0x07FF)],
    "Thaana": [(0x0780, 0x07BF)],
    "Vai": [(0xA500, 0xA63F)],
    "CanadianAboriginal": [(0x1400, 0x167F), (0x18B0, 0x18FF), (0x11AB0, 0x11ABF)],
}
SERIF_ONLY = {"Tibetan"}  # Noto draws these only in its serif
# Noto Sans's vertical stem at each weight, per 1000 units (measured on Noto Sans
# Hebrew's vav). A script whose Noto font stops short of a Katagami master's weight
# (Tifinagh, Coptic, N'Ko and Vai come in Regular only; Ol Chiki and Hanifi
# Rohingya in 400 to 700) is emboldened or thinned from its nearest weight by the
# difference in stem, so every script follows the weight axis.
NOTO_STEM = {100: 32, 200: 46, 300: 66, 400: 92, 500: 112, 600: 132, 700: 152, 800: 172, 900: 192}


def noto_file(script: str) -> Path:
    stem = f"Noto{'Serif' if script in SERIF_ONLY else 'Sans'}{script}"
    found = sorted(NOTO.glob(f"{stem}[[]*.ttf")) or sorted(NOTO.glob(f"{stem}-Regular.ttf"))
    if not found:
        raise FileNotFoundError(f"{NOTO}/{stem}[...].ttf; run tools/build.sh to fetch Noto")
    return found[0]


def _moved(pts: list, half: float, truetype: bool) -> list:
    """The contour's points moved along their bisectors by `half`, as FT_Outline_EmboldenXY moves them."""
    n = len(pts)
    out = []
    for k in range(n):
        prv, cur, nxt = pts[k - 1], pts[k], pts[(k + 1) % n]
        vin = (cur[0] - prv[0], cur[1] - prv[1])
        vout = (nxt[0] - cur[0], nxt[1] - cur[1])
        l_in, l_out = math.hypot(*vin), math.hypot(*vout)
        sx = sy = 0.0
        if n >= 3 and l_in > 1e-6 and l_out > 1e-6:
            ix, iy, ox, oy = vin[0] / l_in, vin[1] / l_in, vout[0] / l_out, vout[1] / l_out
            d = ix * ox + iy * oy
            if d > -0.9375:
                d += 1
                lx, ly = iy + oy, ix + ox
                if truetype:
                    lx = -lx
                else:
                    ly = -ly
                q = ox * iy - oy * ix
                if truetype:
                    q = -q
                lim = min(l_in, l_out)
                scale = half / d if half * q <= lim * d else lim / q
                sx, sy = lx * scale, ly * scale
        out.append((cur[0] + sx, cur[1] + sy))
    return out


def embolden(font: TTFont, strength: float) -> list[str]:
    """Thicken (or, below zero, thin) every simple glyph by `strength` units on
    each axis, as FreeType's FT_Outline_EmboldenXY does: each point moves along
    the bisector of its two edges, so the point structure stays and the three
    masters still interpolate. Ink and advances grow by `strength`, and the
    outlines move right by half of it, so sidebearings stay. A contour that the
    move shrinks (a counter when thickening, an outer contour when thinning)
    moves only as far as it stays the same way round with no lobe inside out,
    so small counters stay open at Black. Returns the glyphs so limited."""
    if not strength:
        return []
    glyf, hmtx = font["glyf"], font["hmtx"]
    half = strength / 2
    order = font.getGlyphOrder()
    limited = []
    for name in order:
        g = glyf[name]
        if g.isComposite() or g.numberOfContours <= 0:
            continue
        coords = list(g.coordinates)
        ends = list(g.endPtsOfContours)
        contours, start = [], 0
        for end in ends:
            contours.append(coords[start:end + 1])
            start = end + 1
        total = sum(signed_area(pts) for pts in contours)
        truetype = total < 0  # outer contours clockwise
        new = []
        for pts in contours:
            moved = _moved(pts, half, truetype)
            counter = (signed_area(pts) < 0) != truetype
            if counter == (strength > 0) and not sound(pts, moved):
                lo, hi = 0.0, 1.0
                for _ in range(8):
                    mid = (lo + hi) / 2
                    if sound(pts, _moved(pts, half * mid, truetype)):
                        lo = mid
                    else:
                        hi = mid
                moved = _moved(pts, half * lo, truetype)
                limited.append(name)
            new += [(x + half, y) for x, y in moved]
        g.coordinates = type(g.coordinates)([(round(x), round(y)) for x, y in new])
        g.recalcBounds(glyf)
        width, _ = hmtx[name]
        hmtx[name] = (max(0, round(width + strength)) if width else 0, g.xMin)
    for name in order:
        g = glyf[name]
        if g.isComposite():
            g.recalcBounds(glyf)
            width, _ = hmtx[name]
            hmtx[name] = (max(0, round(width + strength)) if width else 0, g.xMin)
    return sorted(set(limited))


def _statics(font: TTFont, factor: float, work: Path, stem: str) -> dict[str, TTFont]:
    """A subset Noto font at Katagami's three master weights, at Katagami's units and size."""
    axes = {a.axisTag: (a.minValue, a.maxValue) for a in font["fvar"].axes} if "fvar" in font else {}
    lo, hi = axes.get("wght", (400, 400))
    out = {}
    for style, wght in MASTERS.items():
        near = min(max(wght, lo), hi)
        if axes:
            location = {"wght": near} | ({"wdth": 100} if "wdth" in axes else {})
            static = instantiateVariableFont(TTFont(_save(font, work / f"{stem}.ttf")), location)
        else:
            static = TTFont(_save(font, work / f"{stem}.ttf"))
        # a weight Noto does not draw, from the nearest one it does
        limited = embolden(static, (NOTO_STEM[wght] - NOTO_STEM[near]) * static["head"].unitsPerEm / 1000)
        if limited:
            print(f"  {stem} {style}: {len(limited)} glyphs keep a counter open by emboldening it less")
        scale_upem(static, round(2048 * factor))  # Noto's units times 2048 / its em, times factor
        static["head"].unitsPerEm = 2048
        out[style] = static
    return out


def script_masters(script: str, factor: float, have: set[int], work: Path) -> tuple[dict[str, Path], dict[str, tuple | None]]:
    """Noto's script at Katagami's three master weights, at Katagami's units and
    size, and for each master where its marks sit on Noto's dotted circle
    (`dotted_circle_anchors`), or None where Noto has no dotted circle."""
    cmap = TTFont(noto_file(script)).getBestCmap()
    unicodes = [u for lo, hi in SCRIPTS[script] for u in range(lo, hi + 1) if u in cmap and u not in have]
    statics = _statics(_subset(script, unicodes), factor, work, script)
    out = {style: _save(static, work / f"{script}-{style}.ttf") for style, static in statics.items()}
    dotted = dict.fromkeys(MASTERS)
    if 0x25CC in cmap:
        # the same subset with Noto's dotted circle kept, read for its anchors only
        with_dc = _statics(_subset(script, unicodes + [0x25CC]), factor, work, f"{script}-dc")
        dotted = {style: dotted_circle_anchors(with_dc[style], TTFont(out[style])) for style in MASTERS}
    return out, dotted


def _mark_base_subtables(font: TTFont) -> list:
    """Every mark-to-base subtable in the font's GPOS, in lookup order, inside extensions too."""
    if "GPOS" not in font or not font["GPOS"].table.LookupList:
        return []
    out = []
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for st in lookup.SubTable:
            ext = getattr(st, "ExtSubTable", None)
            st = ext if ext is not None else st
            if type(st).__name__ == "MarkBasePos" and st.Format == 1:
                out.append(st)
    return out


def _mark_classes(st) -> dict[str, int]:
    return {g: rec.Class for g, rec in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord)}


def _anchor(a) -> tuple[float, float] | None:
    return None if a is None else (a.XCoordinate, a.YCoordinate)


def dotted_circle_anchors(with_dc: TTFont, part: TTFont) -> tuple:
    """Where the part's marks sit on Noto's dotted circle: the circle's box
    and, for each of the part's mark-to-base subtables in order, its marks
    and an anchor for the circle in each mark class (None where there is
    none to give).

    Read from the subset that kept the circle. Noto often attaches marks to
    its circle in lookups of their own (Devanagari's vowel signs sit on it
    through `mark`, on letters through `abvm`), lookups the subset without
    the circle drops, so each mark's place on the circle is taken from
    wherever the circle is its base, as the step from the mark's anchor to
    the circle's, and given back in the part's own subtables from the
    mark's anchor there. A class none of whose marks Noto seats on its
    circle takes the place of its first base's anchor in that base's box,
    in the circle's box."""
    dc = with_dc.getBestCmap()[0x25CC]
    glyf = with_dc["glyf"]
    g = glyf[dc]
    g.recalcBounds(glyf)
    box = (g.xMin, g.yMin, g.xMax, g.yMax)
    step = {}  # mark -> where the circle's anchor lies from the mark's own anchor
    for st in _mark_base_subtables(with_dc):
        if dc not in st.BaseCoverage.glyphs:
            continue
        rec = st.BaseArray.BaseRecord[st.BaseCoverage.glyphs.index(dc)]
        for m, mrec in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord):
            base, own = _anchor(rec.BaseAnchor[mrec.Class]), _anchor(mrec.MarkAnchor)
            if m not in step and base is not None and own is not None:
                step[m] = (base[0] - own[0], base[1] - own[1])
    pglyf = part["glyf"]
    items = []
    for st in _mark_base_subtables(part):
        marks = _mark_classes(st)
        anchors = {}
        for m, mrec in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord):
            own = _anchor(mrec.MarkAnchor)
            if mrec.Class not in anchors and m in step and own is not None:
                anchors[mrec.Class] = (own[0] + step[m][0], own[1] + step[m][1])
        for c in range(st.ClassCount):
            if c not in anchors:
                a = _box_anchor(pglyf, st, c, box)
                if a is not None:
                    anchors[c] = a
        items.append((frozenset(marks), anchors or None))
    return box, items


def _box_anchor(glyf, st, c: int, box) -> tuple[float, float] | None:
    """A circle's anchor for mark class c of a mark-to-base subtable, where
    nothing better is known: the place of the first base's anchor in that
    base's box, in the circle's box."""
    for b, rec in zip(st.BaseCoverage.glyphs, st.BaseArray.BaseRecord):
        a = _anchor(rec.BaseAnchor[c])
        bg = glyf[b]
        if a is None or bg.numberOfContours == 0:
            continue
        bg.recalcBounds(glyf)
        if bg.xMax - bg.xMin < 1 or bg.yMax - bg.yMin < 1:
            continue
        u, v = (a[0] - bg.xMin) / (bg.xMax - bg.xMin), (a[1] - bg.yMin) / (bg.yMax - bg.yMin)
        return box[0] + u * (box[2] - box[0]), box[1] + v * (box[3] - box[1])
    return None


def seat_dotted_circle(merged: TTFont, sources: list[Path], dotted: list) -> None:
    """Make Katagami's dotted circle (U+25CC) a base in every merged script's
    mark-to-base subtables, at the anchors Noto gives its own dotted circle,
    taken about the circles' centres and scaled from Noto's circle to
    Katagami's, so a mark keeps its place around the ring. Shaping engines
    set the dotted circle under a mark that has no base (a vowel sign typed
    alone, a broken cluster); this way the mark sits on Katagami's circle as
    it sat on Noto's. `dotted` has one entry per part (after the Katagami
    master, sources[0]), from script_masters."""
    from types import SimpleNamespace
    from fontTools.merge.cmap import computeMegaGlyphOrder
    from fontTools.ttLib.tables import otTables

    fonts = [TTFont(p, lazy=True) for p in sources]
    orders = [list(f.getGlyphOrder()) for f in fonts]
    renamed = [list(o) for o in orders]
    computeMegaGlyphOrder(SimpleNamespace(), renamed)  # the names the merge gave each part's glyphs
    names = [dict(zip(o, r)) for o, r in zip(orders, renamed)]
    counts = [len(_mark_base_subtables(f)) for f in fonts]
    tables = _mark_base_subtables(merged)
    if sum(counts) != len(tables):
        raise ValueError("the merged font's mark-to-base subtables do not add up to its sources'")
    dc = merged.getBestCmap()[0x25CC]
    glyf = merged["glyf"]
    g = glyf[dc]
    g.recalcBounds(glyf)
    kbox = (g.xMin, g.yMin, g.xMax, g.yMax)
    kx, ky = (g.xMin + g.xMax) / 2, (g.yMin + g.yMax) / 2
    off = counts[0]
    for i, data in enumerate(dotted, start=1):
        n = counts[i]
        own = tables[off:off + n]
        if data is None:
            # Noto draws no circle for this script (Georgian, Ol Chiki, Vai): place it by the bases
            box = kbox
            items = [{c: a for c in range(st.ClassCount) if (a := _box_anchor(glyf, st, c, box)) is not None} for st in own]
        else:
            box, found = data
            if len(found) != n:
                raise ValueError(f"{sources[i].name}: {len(found)} dotted-circle entries for {n} mark-to-base subtables")
            items = []
            for st, (marks, anchors) in zip(own, found):
                if {names[i][m] for m in marks} != set(st.MarkCoverage.glyphs):
                    raise ValueError(f"{sources[i].name}: a merged mark-to-base subtable has other marks than its source")
                items.append(anchors)
        # the marks keep their place around the circle: about its centre, scaled from Noto's circle to Katagami's
        nx, ny = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        sx, sy = (kbox[2] - kbox[0]) / (box[2] - box[0]), (kbox[3] - kbox[1]) / (box[3] - box[1])
        for st, anchors in zip(own, items):
            if not anchors or dc in st.BaseCoverage.glyphs:
                continue
            rec = otTables.BaseRecord()
            rec.BaseAnchor = []
            for c in range(st.ClassCount):
                a = None
                if c in anchors:
                    a = otTables.Anchor()
                    a.Format = 1
                    a.XCoordinate, a.YCoordinate = round(kx + (anchors[c][0] - nx) * sx), round(ky + (anchors[c][1] - ny) * sy)
                rec.BaseAnchor.append(a)
            pairs = sorted(list(zip(st.BaseCoverage.glyphs, st.BaseArray.BaseRecord)) + [(dc, rec)],
                           key=lambda p: merged.getGlyphID(p[0]))
            st.BaseCoverage.glyphs = [p[0] for p in pairs]
            st.BaseArray.BaseRecord = [p[1] for p in pairs]
            st.BaseArray.BaseCount = len(pairs)
        off += n


def _save(font: TTFont, path: Path) -> Path:
    font.save(path)
    return path


def merge_master(kerf: Path, parts: list[Path], out: Path, dotted: list | None = None) -> Path:
    base = TTFont(kerf)
    keep = {
        "hhea": (base["hhea"].ascent, base["hhea"].descent, base["hhea"].lineGap),
        "typo": (base["OS/2"].sTypoAscender, base["OS/2"].sTypoDescender, base["OS/2"].sTypoLineGap),
        # the merge takes the largest x-height and cap height among the parts; Katagami's own are the right ones
        "heights": (base["OS/2"].sxHeight, base["OS/2"].sCapHeight),
    }
    merged = Merger(options=Options(drop_tables=["DSIG", "STAT", "meta", "vhea", "vmtx", "VVAR", "gasp", "prep"])).merge([str(kerf)] + [str(p) for p in parts])
    hhea, os2 = merged["hhea"], merged["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = keep["hhea"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = keep["typo"]
    os2.sxHeight, os2.sCapHeight = keep["heights"]
    merged["name"] = base["name"]
    merged["head"].unitsPerEm = 2048
    merged.save(out)
    merged = TTFont(out)
    # the Windows clipping box covers the tallest script
    head = merged["head"]
    merged["OS/2"].usWinAscent = max(merged["OS/2"].usWinAscent, head.yMax)
    merged["OS/2"].usWinDescent = max(merged["OS/2"].usWinDescent, -head.yMin)
    if dotted is not None and 0x25CC in merged.getBestCmap():
        seat_dotted_circle(merged, [kerf] + list(parts), dotted)
    merged.save(out)
    return out


NOTICE = " Merged scripts: Copyright 2022 The Noto Project Authors (https://github.com/notofonts)."


def stamp_copyright(path: Path) -> None:
    """Add Noto's copyright to the merged font's notice, as the OFL asks."""
    font = TTFont(path)
    for rec in font["name"].names:
        if rec.nameID == 0 and "Noto" not in rec.toUnicode():
            rec.string = rec.toUnicode() + NOTICE
    font.save(path)


def restore_feature_labels(core: Path, path: Path) -> None:
    """Give the merged font back the names of its stylistic sets and character
    variants. The merge drops their FeatureParams, and the name IDs they used
    are taken by the instance names, so each label gets a new ID."""
    src = TTFont(core)
    labels = {}
    for rec in src["GSUB"].table.FeatureList.FeatureRecord:
        params = rec.Feature.FeatureParams
        nid = params and (getattr(params, "UINameID", None) or getattr(params, "FeatUILabelNameID", None))
        if nid and rec.FeatureTag not in labels:
            labels[rec.FeatureTag] = (params, src["name"].getDebugName(nid))
    font = TTFont(path)
    ids = {}
    for rec in font["GSUB"].table.FeatureList.FeatureRecord:
        if rec.FeatureTag not in labels:
            continue
        params, text = labels[rec.FeatureTag]
        if text not in ids:
            ids[text] = font["name"].addName(text, platforms=((3, 1, 0x409),), minNameID=256)
        params = copy.deepcopy(params)
        setattr(params, "UINameID" if hasattr(params, "UINameID") else "FeatUILabelNameID", ids[text])
        rec.Feature.FeatureParams = params
    font.save(path)


def restore_gpos_labels(path: Path, scripts: list[str]) -> None:
    """Give GPOS features with labels (Noto Sans Canadian Aboriginal's ss01 and
    ss02, its mid-line and low-line finals) their names back. The merge keeps
    their FeatureParams but the name IDs they used belong to Katagami's name
    table, so each label is read from the Noto font and gets a new ID."""
    labels = {}
    for script in scripts:
        src = TTFont(noto_file(script))
        if "GPOS" not in src:
            continue
        for rec in src["GPOS"].table.FeatureList.FeatureRecord:
            nid = rec.Feature.FeatureParams is not None and getattr(rec.Feature.FeatureParams, "UINameID", None)
            if nid:
                labels.setdefault(rec.FeatureTag, src["name"].getDebugName(nid))
    font = TTFont(path)
    if "GPOS" not in font:
        return
    changed = False
    for rec in font["GPOS"].table.FeatureList.FeatureRecord:
        params = rec.Feature.FeatureParams
        if params is not None and getattr(params, "UINameID", None) and rec.FeatureTag in labels:
            params.UINameID = font["name"].addName(labels[rec.FeatureTag], platforms=((3, 1, 0x409),), minNameID=256)
            changed = True
    if changed:
        font.save(path)


def build(key: str, only: list[str] | None = None) -> Path:
    p = PROFILES[key]
    core = ROOT / "build" / key / f"{p.file_stem}-core[wght].ttf"
    target = ROOT / "fonts" / key / f"{p.file_stem}[wght].ttf"
    vf = TTFont(core)
    factor = vf["OS/2"].sxHeight / vf["head"].unitsPerEm * 1000 / NOTO_XHEIGHT
    have = set(vf.getBestCmap())
    scripts = only or list(SCRIPTS)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        kerf = {style: _save(instantiateVariableFont(TTFont(core), {"wght": w}), work / f"kerf-{style}.ttf")
                for style, w in MASTERS.items()}
        parts = {style: [] for style in MASTERS}
        dotted = {style: [] for style in MASTERS}
        for script in scripts:
            paths, anchors = script_masters(script, factor, have, work)
            for style, path in paths.items():
                parts[style].append(path)
                dotted[style].append(anchors[style])
            print(f"  {script}")
        merged = {style: merge_master(kerf[style], parts[style], work / f"merged-{style}.ttf", dotted[style]) for style in MASTERS}

        ds = DesignSpaceDocument()
        ax = AxisDescriptor()
        ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 100, 400, 900
        ax.map = list(p.weight_map)
        ds.addAxis(ax)
        design = dict(p.weight_map)
        for style, w in MASTERS.items():
            s = SourceDescriptor()
            s.path, s.styleName, s.familyName = str(merged[style]), style, p.family
            s.location = {"Weight": design[w]}
            ds.addSource(s)
        for i, style in enumerate(INSTANCES):
            inst = InstanceDescriptor()
            inst.familyName, inst.styleName = p.family, style
            inst.location = {"Weight": design[(i + 1) * 100]}
            ds.addInstance(inst)
        ds.write(work / "world.designspace")
        font, _, _ = build_variable(str(work / "world.designspace"))
        font.save(target)
    stamp_copyright(target)
    restore_feature_labels(core, target)
    restore_gpos_labels(target, scripts)
    out = TTFont(target)
    print(f"{target.relative_to(ROOT)}: {len(out.getGlyphOrder())} glyphs, {len(out.getBestCmap())} characters, "
          f"{target.stat().st_size / 1e6:.1f} MB")
    return target


if __name__ == "__main__":
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].split(",")
    build(sys.argv[1], only)

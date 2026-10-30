"""Finish a member's built fonts: version, naming, STAT, style bits, line metrics
and the tables an unhinted font needs.

    python tools/finish.py sans|round|text|serif|mono [...] [--roman|--italic]

Runs on fonts/<member>/<Stem>[wght].ttf and fonts/<member>/<Stem>-Italic[wght].ttf
in place, after fontmake (and, for the roman, the script merge):

  1. Version: head.fontRevision, the version string (name 5) and the unique ID
     (name 3) all read VERSION, and the vendor ID is VENDOR. The script merge
     otherwise leaves Noto's revision in the head table.
  2. Names: the default instance is Regular or Italic; every named instance
     has a PostScript name, and the variations PostScript prefix (name 25) is set.
  3. Style bits: fsSelection has REGULAR or ITALIC and USE_TYPO_METRICS, and
     macStyle matches.
  4. STAT: a weight axis value for every named weight (Regular elidable and
     linked to Bold) and an ital axis whose value is 0 (Roman, elidable,
     linked to Italic) or 1 (Italic), so a roman and its Italic link as one family.
  5. Line metrics: the Italic takes the roman's hhea and typo metrics, so both
     set the same line height, and both files clip at the tallest and deepest
     glyph of the two.
  6. Unhinted: a gasp table that asks for smoothing at every size, and a prep
     program that turns on smart dropout control (as gftools fix-unhinted does).
  7. Components: every glyph built from a flipped, rotated or scaled component
     (Inter's d from b, q from p, И from N) is drawn in, point for point from
     the compiled component at each master, so its outline does not change.
  8. Unreachable glyphs (the merge's .notdef copies, the parts components were
     drawn from) are dropped, layout records are put in tag order, and a meta
     table names the design and supported scripts.
  9. Shared segments: where two contours of a glyph run along the same segment,
     one of them moves a unit into the other's ink, takes a one-unit notch, or
     goes if it repeats the other (kerf_build.contours); a composite that
     shares one is drawn in first. The filled shape stays the same at every
     master; where the two segments meet only near the default, the points
     that move return to place at each master and move less than a unit between.
 10. Glyph classes: spacing signs of the merged scripts leave the GDEF mark
     class and unclassified Tibetan signs join it, where HarfBuzz shapes the
     same either way (GLYPH_CLASSES).
 11. Glyph names: a name longer than 31 characters is shortened in the post
     table, to uniXXXX where it names a character.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables._g_l_y_f import (
    OVERLAP_COMPOUND, SCALE_COMPONENT_OFFSET_DEFAULT, SCALED_COMPONENT_OFFSET, UNSCALED_COMPONENT_OFFSET, Glyph, GlyphCoordinates,
    flagOnCurve, flagOverlapSimple,
)
from fontTools.ttLib.tables.TupleVariation import TupleVariation

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.contours import fix_shared_segments  # noqa: E402
from kerf_build.fontops import VENDOR, VERSION  # noqa: E402
from kerf_build.profiles import PROFILES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STEMS = {key: p.file_stem for key, p in PROFILES.items()} | {"mono": "KatagamiMono"}
WEIGHTS = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
           700: "Bold", 800: "ExtraBold", 900: "Black"}

# GDEF classes for glyphs of the merged scripts that fontbakery's gdef checks flag, each kept only
# because HarfBuzz shapes every affected sign after each consonant, in conjuncts and in sample text
# the same in either class (glyph, cluster, advance and offset at Thin, Regular and Black). A sign
# with no advance stays a mark: a base without one fails base_has_width.
GLYPH_CLASSES = {
    # spacing vowel signs, visargas and anusvaras (Mc): base
    0x0C83: 1, 0x0CC0: 1, 0x0D02: 1, 0x0D03: 1, 0x0D3E: 1, 0x0D3F: 1, 0x0D40: 1, 0x0D46: 1, 0x0D47: 1,
    0x0D48: 1, 0x0D4A: 1, 0x0D4B: 1, 0x0D4C: 1, 0x0DDA: 1, 0x0DDC: 1, 0x0DDD: 1, 0x0DDE: 1,
    # Tibetan vowel signs, subjoined letters and signs the merge left without a class: mark
    0x0F71: 3, 0x0F73: 3, 0x0F76: 3, 0x0F77: 3, 0x0F78: 3, 0x0F79: 3, 0x0F81: 3, 0x0F8E: 3, 0x0F8F: 3,
    0x0FA9: 3, 0x0FAA: 3, 0x0FAB: 3, 0x0FC6: 3,
    # spacing forms of Kannada and Telugu subjoined letters and vowel signs, Tamil vowel sign forms: base
    "bapostscripttelu.spacing": 1, "basubscriptaltknda": 1, "baviramaknda": 1, "bhapostscripttelu.spacing": 1,
    "bharasubscriptknda": 1, "bhasubscriptaltknda": 1, "casubscriptaltknda": 1, "chapostscripttelu.spacing": 1,
    "chasubscriptaltknda": 1, "darasubscriptknda": 1, "dasubscriptaltknda": 1, "ddarasubscriptknda": 1,
    "ddasubscriptaltknda": 1, "ddhasubscriptaltknda": 1, "ddhasubscripttelu.spacing": 1,
    "dhasubscriptaltknda": 1, "garasubscriptknda": 1, "gasubscriptaltknda": 1, "ghasubscriptaltknda": 1,
    "hasubscriptaltknda": 1, "ivowelsign4tamil": 1, "januktasubscriptknda": 1, "jasubscriptaltknda": 1,
    "jhasubscriptaltknda": 1, "jhasubscripttelu.spacing": 1, "karasubscriptknda": 1, "kasubscriptaltknda": 1,
    "khasubscriptaltknda": 1, "lasubscriptaltknda": 1, "llapostscripttelu.spacing": 1, "llasubscriptaltknda": 1,
    "lllasubscripttelu.spacing": 1, "llvocalicvowelsigntelu.spacing": 1, "lvocalicvowelsigntelu.spacing": 1,
    "mapostscripttelu.spacing": 1, "masubscriptaltknda": 1, "napostscripttelu.spacing": 1,
    "nasubscriptaltknda": 1, "ngasubscriptaltknda": 1, "nnasubscriptaltknda": 1, "nyasubscriptaltknda": 1,
    "nyasubscripttelu.spacing": 1, "papostscripttelu.spacing": 1, "parasubscriptknda": 1,
    "pasubscriptaltknda": 1, "phanuktasubscriptknda": 1, "phapostscripttelu.spacing": 1,
    "phasubscriptaltknda": 1, "rasubscriptaltknda": 1, "rrasubscriptaltknda": 1, "rrasubscripttelu.spacing": 1,
    "rrvocalicvowelsigntelu.spacing": 1, "rvocalicvowelsigntelu.spacing": 1, "sapostscripttelu.spacing": 1,
    "sasubscriptaltknda": 1, "shapostscripttelu.spacing": 1, "shasubscriptaltknda": 1, "ssasubscriptaltknda": 1,
    "tarasubscriptknda": 1, "tasubscriptaltknda": 1, "thasubscriptaltknda": 1, "ttarasubscriptknda": 1,
    "ttasubscriptaltknda": 1, "tthasubscriptaltknda": 1, "tthasubscripttelu.spacing": 1,
    "uuvowelsignalt2knda": 1, "uuvowelsignaltknda": 1, "uuvowelsignalttamil": 1, "uuvowelsigntelu.spacing": 1,
    "uuvoweltelu.spacing2": 1, "uuvoweltelu.spacing3": 1, "uvowelsignalt2knda": 1, "uvowelsignaltknda": 1,
    "uvowelsignalttamil": 1, "uvowelsigntelu.spacing": 1, "uvoweltelu.spacing2": 1, "uvoweltelu.spacing3": 1,
    "vapostscripttelu.spacing": 1, "vasubscriptaltknda": 1, "yapostscripttelu.spacing": 1,
    "yasubscriptaltknda": 1,
}


def version(font: TTFont, ps: str) -> None:
    major, minor = VERSION
    text = f"{major}.{minor:03d}"
    font["head"].fontRevision = float(text)
    name = font["name"]
    name.setName(f"Version {text}", 5, 3, 1, 0x409)
    name.setName(f"{text};{VENDOR};{ps}", 3, 3, 1, 0x409)
    font["OS/2"].achVendID = VENDOR


def names(font: TTFont, family: str, italic: bool) -> str:
    """Family and default style names, and a PostScript name for every instance."""
    name = font["name"]
    style = "Italic" if italic else "Regular"
    ps_family = family.replace(" ", "")
    ps = f"{ps_family}-{style}"
    for nid in (16, 17, 21, 22):
        name.removeNames(nameID=nid)
    name.setName(family, 1, 3, 1, 0x409)
    name.setName(style, 2, 3, 1, 0x409)
    name.setName(f"{family} {style}", 4, 3, 1, 0x409)
    name.setName(ps, 6, 3, 1, 0x409)
    name.setName(ps_family + ("Italic" if italic else ""), 25, 3, 1, 0x409)
    for inst in font["fvar"].instances:
        text = f"{ps_family}-{name.getDebugName(inst.subfamilyNameID).replace(' ', '')}"
        # a record with the same text is reused, so finishing a font twice keeps its name IDs
        inst.postscriptNameID = next((r.nameID for r in name.names if r.nameID >= 256 and r.platformID == 3
                                      and r.toUnicode() == text), None) or name.addName(
            text, platforms=((3, 1, 0x409),), minNameID=256)
    # only Windows English names: the Mac records fontmake writes duplicate them
    name.names = [r for r in name.names if r.platformID == 3]
    return ps


def style_bits(font: TTFont, italic: bool) -> None:
    os2, head = font["OS/2"], font["head"]
    sel = os2.fsSelection & ~(1 << 0 | 1 << 5 | 1 << 6)
    sel |= (1 << 0) if italic else (1 << 6)
    os2.fsSelection = sel | 1 << 7  # USE_TYPO_METRICS
    head.macStyle = (head.macStyle & ~0b11) | (0b10 if italic else 0)


def stat(font: TTFont, italic: bool) -> None:
    axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
    values = []
    for w, label in WEIGHTS.items():
        if axis.minValue <= w <= axis.maxValue:
            v = {"value": w, "name": label}
            if w == 400:
                v |= {"flags": 0x2, "linkedValue": 700}
            values.append(v)
    ital = ({"value": 1, "name": "Italic"} if italic
            else {"value": 0, "name": "Roman", "flags": 0x2, "linkedValue": 1})
    buildStatTable(font, [
        {"tag": "wght", "name": "Weight", "values": values},
        {"tag": "ital", "name": "Italic", "values": [ital]},
    ], elidedFallbackName=2, macNames=False)  # Windows names only, as names() keeps, so existing IDs are reused


def metrics_from(font: TTFont, roman: TTFont) -> None:
    """The roman's line spacing (hhea and typo), so both set the same line height."""
    hhea, os2, src_hhea, src_os2 = font["hhea"], font["OS/2"], roman["hhea"], roman["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = src_hhea.ascent, src_hhea.descent, src_hhea.lineGap
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = src_os2.sTypoAscender, src_os2.sTypoDescender, src_os2.sTypoLineGap


def clipping(font: TTFont, family: list[TTFont]) -> None:
    """The Windows clipping box covers the tallest and deepest glyph of the
    roman and the Italic together, and never less than the typo metrics, so
    both files of a member have the same vertical metrics. USE_TYPO_METRICS
    keeps it out of the line spacing."""
    os2 = font["OS/2"]
    os2.usWinAscent = max([f["head"].yMax for f in family] + [os2.sTypoAscender])
    os2.usWinDescent = max([-f["head"].yMin for f in family] + [-os2.sTypoDescender])


def prune_names(font: TTFont) -> None:
    """Drop name records from 256 up that nothing points at any more. Only the
    tables that hold name IDs here are read (fvar, STAT and the feature labels
    in GSUB and GPOS), so glyf and gvar stay compiled and the font saves quickly."""
    used = set()
    fvar = font["fvar"]
    used |= {a.axisNameID for a in fvar.axes}
    used |= {i.subfamilyNameID for i in fvar.instances} | {i.postscriptNameID for i in fvar.instances}
    stat = font["STAT"].table
    used |= {a.AxisNameID for a in stat.DesignAxisRecord.Axis} | {v.ValueNameID for v in stat.AxisValueArray.AxisValue}
    used.add(stat.ElidedFallbackNameID)
    records = [rec for tag in ("GSUB", "GPOS") if tag in font for rec in font[tag].table.FeatureList.FeatureRecord]
    for rec in records:
        params = rec.Feature.FeatureParams
        for attr in ("UINameID", "FeatUILabelNameID", "FeatUITooltipTextNameID", "SampleTextNameID"):
            if params is not None and getattr(params, attr, None):
                used.add(getattr(params, attr))
        if params is not None and getattr(params, "FirstParamUILabelNameID", None):
            used |= set(range(params.FirstParamUILabelNameID, params.FirstParamUILabelNameID + params.NumNamedParameters))
    font["name"].names = [r for r in font["name"].names if r.nameID < 256 or r.nameID in used]


def prune_unreachable(font: TTFont) -> int:
    """Drop the glyphs no character and no feature reaches: the .notdef copies
    the script merge leaves and the parts that components were drawn from.
    Returns how many went."""
    from fontTools import subset

    before = len(font.getGlyphOrder())
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.name_legacy = True
    opts.glyph_names = True
    opts.notdef_glyph = True
    opts.notdef_outline = True
    opts.legacy_kern = True
    opts.symbol_cmap = True
    opts.legacy_cmap = True
    opts.drop_tables = []
    opts.passthrough_tables = True
    opts.prune_unicode_ranges = False
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=font.getBestCmap().keys())
    sub.subset(font)
    return before - len(font.getGlyphOrder())


def sort_layout(font: TTFont) -> None:
    """Script, language and feature records in tag order, as OpenType asks;
    the script merge appends them in merge order. Feature indices are remapped."""
    for tag in ("GSUB", "GPOS"):
        if tag not in font:
            continue
        t = font[tag].table
        t.ScriptList.ScriptRecord.sort(key=lambda r: r.ScriptTag)
        records = t.FeatureList.FeatureRecord
        order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
        index = {old: new for new, old in enumerate(order)}
        t.FeatureList.FeatureRecord = [records[i] for i in order]
        for sr in t.ScriptList.ScriptRecord:
            sr.Script.LangSysRecord.sort(key=lambda r: r.LangSysTag)
            for ls in [sr.Script.DefaultLangSys] + [r.LangSys for r in sr.Script.LangSysRecord]:
                if ls is None:
                    continue
                ls.FeatureIndex = sorted(index[i] for i in ls.FeatureIndex)
                if ls.ReqFeatureIndex != 0xFFFF:
                    ls.ReqFeatureIndex = index[ls.ReqFeatureIndex]
        if getattr(t, "FeatureVariations", None):
            for rec in t.FeatureVariations.FeatureVariationRecord:
                for sub in rec.FeatureTableSubstitution.SubstitutionRecord:
                    sub.FeatureIndex = index[sub.FeatureIndex]


def meta(font: TTFont) -> None:
    """A meta table: Latin, Greek and Cyrillic are the scripts Katagami draws,
    and every script with ten or more characters in the cmap is supported."""
    from collections import Counter
    from fontTools.unicodedata import script

    counts = Counter(script(chr(u)) for u in font.getBestCmap())
    supported = sorted(s for s, n in counts.items() if n >= 10 and s not in ("Zyyy", "Zinh", "Zzzz"))
    table = newTable("meta")
    table.data = {"dlng": "Latn, Grek, Cyrl", "slng": ", ".join(supported)}
    font["meta"] = table


def unhinted(font: TTFont) -> None:
    gasp = newTable("gasp")
    gasp.gaspRange = {0xFFFF: 0x000F}  # grid-fit and smooth, symmetric, at every size
    font["gasp"] = gasp
    prep = newTable("prep")
    program = ttProgram.Program()
    program.fromAssembly(["PUSHW[]", "511", "SCANCTRL[]", "PUSHB[]", "4", "SCANTYPE[]"])
    prep.program = program
    font["prep"] = prep


class _Varied:
    """The glyf table at a location: each glyph with the font's variations applied."""

    def __init__(self, glyph_set):
        self.gs = glyph_set

    def __getitem__(self, name):
        return self.gs[name]._getGlyphAndOffset()[0]


def _scales_offset(compo) -> bool:
    """Whether the rasterizer transforms this component's offset too (getCoordinates' rule)."""
    if compo.flags & SCALED_COMPONENT_OFFSET:
        return True
    return not compo.flags & UNSCALED_COMPONENT_OFFSET and bool(SCALE_COMPONENT_OFFSET_DEFAULT)


def _apply(t, x, y):
    return x * t[0][0] + y * t[1][0], x * t[0][1] + y * t[1][1]


def draw_in_transformed(font: TTFont) -> list[str]:
    """Draw in every glyph that has a flipped, rotated or scaled component.
    TrueType rasterizers and hinting tools handle such components badly
    (fontbakery's transformed_components), so each becomes a simple glyph
    made of its components' own compiled points, moved and transformed as
    the rasterizer does it, the contours of a flipped component reversed so
    they keep their turn. Its variations are the components' variations put
    through the same transform, points the font infers (IUP) left to be
    inferred, plus the composite's own offset deltas. Inter's transforms are
    flips and half turns, so every point and delta stays an integer and the
    outline is the same at every weight. Returns the glyphs drawn in."""
    glyf = font["glyf"]
    names = [n for n in font.getGlyphOrder() if glyf[n].isComposite()
             and any(getattr(c, "transform", None) is not None for c in glyf[n].components)]
    if not names:
        return []
    gvar = font["gvar"] if "gvar" in font else None
    key = lambda axes: tuple(sorted(axes.items()))  # noqa: E731
    out = {}
    for name in names:
        g = glyf[name]
        coords, flags, ends, parts = [], bytearray(), [], []
        for i, compo in enumerate(g.components):
            cg = glyf[compo.glyphName]
            if cg.isComposite():
                raise ValueError(f"{name}: nested component {compo.glyphName}; fontmake should have flattened it")
            t = getattr(compo, "transform", [[1, 0], [0, 1]])
            if any(v != int(v) for row in t for v in row):
                raise ValueError(f"{name}: a scaled component ({t}); its points would not stay integers")
            one = Glyph()
            one.numberOfContours = -1
            one.components = [compo]
            c, e, f = one.getCoordinates(glyf)
            flipped = t[0][0] * t[1][1] - t[0][1] * t[1][0] < 0
            perm, start = [], 0
            for end in e:
                idx = list(range(start, end + 1))
                perm += idx[:1] + idx[:0:-1] if flipped else idx
                ends.append(len(coords) + len(perm) - 1)
                start = end + 1
            coords += [c[k] for k in perm]
            flags += bytes(f[k] for k in perm)
            parts.append((i, compo, t, perm, list(e)))
        variations = {}
        if gvar is not None:
            own = {key(v.axes): v for v in gvar.variations.get(name, [])}
            comps = [{key(v.axes): v for v in gvar.variations.get(compo.glyphName, [])} for _, compo, *_ in parts]
            for k in sorted(set(own) | set().union(*comps)):
                deltas = []
                for (i, compo, t, perm, e), table in zip(parts, comps):
                    n = len(perm)
                    d = table[k].coordinates[:n] if k in table else [None] * n
                    d = [None if v is None else _apply(t, *v) for v in d]
                    off = own[k].coordinates[i] if k in own and own[k].coordinates[i] is not None else (0, 0)
                    if _scales_offset(compo):
                        off = _apply(t, *off)
                    if off != (0, 0):
                        start = 0
                        for end in e:
                            run = range(start, end + 1)
                            if all(d[j] is None for j in run):
                                for j in run:
                                    d[j] = (0, 0)  # nothing to infer from: the offset moves every point
                            start = end + 1
                        d = [None if v is None else (v[0] + off[0], v[1] + off[1]) for v in d]
                    deltas += [d[j] for j in perm]
                phantoms = own[k].coordinates[-4:] if k in own else [(0, 0)] * 4
                deltas += [(0, 0) if v is None else v for v in phantoms]
                if any(v is not None and v != (0, 0) for v in deltas):
                    variations[k] = TupleVariation(dict(k), [None if v is None else (int(v[0]), int(v[1])) for v in deltas])
        new = Glyph()
        new.numberOfContours = len(ends)
        new.coordinates = GlyphCoordinates([(int(x), int(y)) for x, y in coords])
        new.endPtsOfContours = ends
        overlap = bool(g.components[0].flags & OVERLAP_COMPOUND) or any(f & flagOverlapSimple for f in flags)
        new.flags = bytearray(f & flagOnCurve for f in flags)
        if overlap and new.flags:
            new.flags[0] |= flagOverlapSimple
        new.program = ttProgram.Program()
        new.program.fromBytecode(b"")
        out[name] = (new, list(variations.values()))
    # a glyph that is only a turned part (d, a turned b) is drawn in; a glyph that sets such
    # a part beside others (ď, ḋ, Й) keeps its components and takes the drawn-in glyph instead
    single = {n: glyf[n].components[0] for n in names if len(glyf[n].components) == 1}
    for name in names:
        g = glyf[name]
        if name in single or not _reuses(g, single):
            continue
        own = {key(v.axes): v for v in gvar.variations.get(name, [])} if gvar is not None else {}
        swaps = {}
        for i, compo in enumerate(g.components):
            if getattr(compo, "transform", None) is None:
                continue
            y = _part_for(compo, single)
            yc = single[y]
            swaps[i] = (y, (compo.x - yc.x, compo.y - yc.y))
            parts = {key(v.axes): v for v in gvar.variations.get(y, [])} if gvar is not None else {}
            for k, v in parts.items():  # the drawn-in glyph's own offset variation is now in its points
                d = v.coordinates[0] or (0, 0)
                if k not in own:
                    own[k] = TupleVariation(dict(k), [(0, 0)] * (len(g.components) + 4))
                c = own[k].coordinates[i] or (0, 0)
                own[k].coordinates[i] = (c[0] - d[0], c[1] - d[1])
        for i, (y, (dx, dy)) in swaps.items():
            compo = g.components[i]
            compo.glyphName = y
            compo.x, compo.y = dx, dy
            del compo.transform
            compo.flags &= ~0x00C8  # no scale, no x and y scale, no two by two
        out.pop(name, None)
        if gvar is not None:
            gvar.variations[name] = [v for v in own.values() if any(c not in (None, (0, 0)) for c in v.coordinates)]
    for name, (new, variations) in out.items():
        glyf[name] = new
        new.recalcBounds(glyf)
        if gvar is not None:
            gvar.variations[name] = variations
    return sorted(out)


def _part_for(compo, single: dict) -> str | None:
    """The drawn-in glyph that is exactly this component: the same base, turned the same way."""
    for y, yc in single.items():
        if yc.glyphName == compo.glyphName and getattr(yc, "transform", None) == compo.transform and not (
                (compo.flags | yc.flags) & SCALED_COMPONENT_OFFSET) and _scales_offset(compo) is False:
            return y
    return None


def _reuses(g, single: dict) -> bool:
    """Whether every turned component of a composite is a glyph that is drawn in on its own."""
    return all(getattr(c, "transform", None) is None or _part_for(c, single) is not None for c in g.components)


def glyph_classes(font: TTFont) -> list[str]:
    """Put the glyphs in GLYPH_CLASSES (a code point, or the name of a glyph no
    character maps to) in the GDEF class given there. Returns those moved."""
    cmap, order = font.getBestCmap(), set(font.getGlyphOrder())
    classes = font["GDEF"].table.GlyphClassDef.classDefs
    moved = []
    for key, cls in GLYPH_CLASSES.items():
        name = cmap.get(key) if isinstance(key, int) else key
        if name in order and classes.get(name) != cls:
            classes[name] = cls
            moved.append(name)
    return moved


def short_names(font: TTFont) -> list[str]:
    """Write every glyph name longer than 31 characters, the most some legacy
    systems read, to the post table in a shorter form. Each part of the name
    that names a character (in the cmap or the Adobe Glyph List) becomes
    uniXXXX, so chedescenderabkhasiancyrillic.smcp is uni04BF.smcp. A name
    still too long keeps its start and takes four hex digits of a hash of the
    whole name, so every run gives the same unique name. The font keeps its
    own names in memory; the post table's unused names are dropped. Returns
    the names shortened."""
    from fontTools import agl

    order = font.getGlyphOrder()
    codes = {}
    for cp, name in sorted(font.getBestCmap().items()):
        codes.setdefault(name, cp)

    def uni(part: str) -> str:
        cp = codes.get(part)
        if cp is None:
            text = agl.toUnicode(part)
            cp = ord(text) if len(text) == 1 else None
        return part if cp is None else f"uni{cp:04X}" if cp <= 0xFFFF else f"u{cp:X}"

    post = font["post"]
    mapping = dict(getattr(post, "mapping", {}))
    taken = set(order) | set(mapping.values())
    for name in order:
        if len(mapping.get(name, name)) <= 31:
            continue
        base, dot, suffix = name.partition(".")
        new = "_".join(uni(p) for p in base.split("_")) + dot + suffix
        if len(new) > 31 or new in taken:
            keep = 31 - len(dot + suffix) - 4
            new = new.partition(".")[0][:keep] + hashlib.sha1(name.encode()).hexdigest()[:4].upper() + dot + suffix
        if new in taken or len(new) > 31:
            raise ValueError(f"{name}: no short name ({new})")
        taken.add(new)
        mapping[name] = new
    post.mapping = mapping
    post.extraNames = []
    return sorted(n for n in mapping if mapping[n] != n)


def finish(key: str, only: str | None = None) -> None:
    stem = STEMS[key]
    family = PROFILES[key].family if key in PROFILES else "Katagami Mono"
    roman_path = ROOT / "fonts" / key / f"{stem}[wght].ttf"
    italic_path = ROOT / "fonts" / key / f"{stem}-Italic[wght].ttf"
    roman = TTFont(roman_path) if roman_path.exists() else None
    family_fonts = [TTFont(p) for p in (roman_path, italic_path) if p.exists()]
    for path, italic in ((roman_path, False), (italic_path, True)):
        if not path.exists() or only and only != ("italic" if italic else "roman"):
            continue
        font = roman if not italic else TTFont(path)
        drawn = draw_in_transformed(font)
        if drawn:
            print(f"{path.relative_to(ROOT)}: {len(drawn)} glyphs with transformed components drawn in")
        changed, faded, left = fix_shared_segments(font)
        if changed or left:
            print(f"{path.relative_to(ROOT)}: shared segments removed in {len(changed)} glyphs"
                  + (f" ({len(faded)} only near the default: {' '.join(faded)})" if faded else "")
                  + (f"; still shared in {' '.join(left)}" if left else ""))
        pruned = prune_unreachable(font)
        if pruned:
            print(f"{path.relative_to(ROOT)}: {pruned} unreachable glyphs dropped")
        ps = names(font, family, italic)
        version(font, ps)
        style_bits(font, italic)
        stat(font, italic)
        if italic and roman is not None:
            metrics_from(font, roman)
        clipping(font, family_fonts)
        unhinted(font)
        sort_layout(font)
        meta(font)
        moved = glyph_classes(font)
        if moved:
            print(f"{path.relative_to(ROOT)}: {len(moved)} glyphs moved to their GDEF class")
        prune_names(font)  # what an earlier STAT or a second run left behind
        shortened = short_names(font)  # last: only the post table sees the new names
        if shortened:
            print(f"{path.relative_to(ROOT)}: {len(shortened)} glyph names shortened")
        font.save(path)
        print(f"{path.relative_to(ROOT)}: finished")


if __name__ == "__main__":
    only = next((a[2:] for a in sys.argv[1:] if a in ("--roman", "--italic")), None)
    for key in (a for a in sys.argv[1:] if not a.startswith("--")):
        finish(key, only)

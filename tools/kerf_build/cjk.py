"""The parts of the Katagami CJK build that work on whole tables: Katagami Sans's
Latin core as a variable font on the CJK file's weight axis and its merge into
the CJK file, glyph names, the direction of Noto's outer contours and the
ligature carets."""

from __future__ import annotations

from pathlib import Path

import pathops
from fontTools import subset, varLib
from fontTools.designspaceLib import DesignSpaceDocument
from fontTools.otlLib import builder as otl
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
from fontTools.ttLib.tables.otBase import BaseTable, ValueRecord
from fontTools.varLib import instancer
from fontTools.varLib.featureVars import sortFeatureList
from fontTools.varLib.models import piecewiseLinearMap

# The features that shape Latin by default and change Katagami Sans's output:
# composition, language forms, contextual punctuation, kerning and marks.
LATIN_FEATURES = ["ccmp", "locl", "calt", "kern", "mark", "mkmk"]


def latin_chars() -> set[int]:
    """The characters a CJK file takes from Katagami Sans: Google Fonts' GF_Latin_Core,
    the Latin every Google Fonts family must cover; the auxiliary letters of its
    languages (ĕ, ŀ, ǿ), which Google Fonts' language shaping check asks for; and
    the dotted circle, which a shaper sets a mark on when it has no base."""
    import glyphsets
    from gflanguages import LoadLanguages

    core = glyphsets.unicodes_per_glyphset("GF_Latin_Core")
    languages = LoadLanguages()
    auxiliary = {ord(t.strip("{}")) for code in glyphsets.languages_per_glyphset("GF_Latin_Core")
                 for t in (languages[code].exemplar_chars.auxiliary or "").split() if len(t.strip("{}")) == 1}
    return set(core) | auxiliary | {0x25CC}


def _user(axis, n: float) -> float:
    """A normalized coordinate before avar, back in user units."""
    return axis.defaultValue + n * ((axis.defaultValue - axis.minValue) if n < 0 else (axis.maxValue - axis.defaultValue))


def master_weights(sans: TTFont, cjk: TTFont) -> list[float]:
    """Every weight where Katagami Sans's outlines or either avar change slope.
    Between two of them the Latin is linear in both fonts' coordinates, so
    masters at these weights reproduce Sans at every weight."""
    sans_axis, cjk_axis = sans["fvar"].axes[0], cjk["fvar"].axes[0]
    peaks = {c for tvs in sans["gvar"].variations.values() for tv in tvs for c in tv.axes["wght"]}
    if not peaks <= {-1.0, 0.0, 1.0}:
        raise ValueError(f"Katagami Sans has intermediate masters at {sorted(peaks)}")
    weights = {sans_axis.minValue, sans_axis.defaultValue, sans_axis.maxValue}
    weights |= {_user(sans_axis, k) for k in sans["avar"].segments["wght"]}
    weights |= {_user(cjk_axis, k) for k in cjk["avar"].segments["wght"]}
    # avar keys are 2.14 fixed point: -0.66668701171875 stands for 200
    return sorted({round(w) for w in weights if cjk_axis.minValue <= w <= cjk_axis.maxValue})


def build_latin(sans_path: Path, cjk: TTFont) -> TTFont:
    """Katagami Sans's `latin_chars` and the glyphs its Latin features reach, as a
    variable font with the CJK file's axis (default at its minimum) and avar, so
    its regions are in the CJK file's normalized coordinates."""
    sans = TTFont(sans_path)
    opts = subset.Options()
    opts.layout_features = LATIN_FEATURES
    opts.layout_scripts = ["*"]
    opts.glyph_names = True
    opts.notdef_outline = True
    opts.hinting = False
    opts.drop_tables += ["MVAR", "STAT", "meta"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=latin_chars())
    sub.subset(sans)

    axis = cjk["fvar"].axes[0]
    span = axis.maxValue - axis.minValue
    avar = {k: v for k, v in cjk["avar"].segments["wght"].items() if k >= 0}
    # design coordinates are the CJK file's normalized coordinates after avar, in user units
    design = lambda w: axis.minValue + span * piecewiseLinearMap((w - axis.minValue) / span, avar)  # noqa: E731
    doc = DesignSpaceDocument()
    doc.addAxisDescriptor(tag="wght", name="Weight", minimum=axis.minValue, default=axis.minValue, maximum=axis.maxValue,
                          map=[(axis.minValue + span * k, axis.minValue + span * v) for k, v in sorted(avar.items())])
    masters = []
    for w in master_weights(sans, cjk):
        static = instancer.instantiateVariableFont(sans, {"wght": w}, overlap=instancer.OverlapMode.KEEP_AND_DONT_SET_FLAGS)
        doc.addSourceDescriptor(name=f"w{w:g}", font=static, location={"Weight": design(w)})
        masters.append(((design(w) - axis.minValue) / span, static))
    latin, _, _ = varLib.build(doc, exclude=["STAT", "MVAR", "HVAR", "VVAR", "cvar"])
    _tent_per_master(latin, masters)
    return latin


def _tent_per_master(font: TTFont, masters: list[tuple[float, TTFont]]) -> None:
    """Rewrites each glyph's variations as one tent per master, rising from the
    master before it and falling to the master after it, with the master's whole
    offset from the default as its deltas. At a master's weight only its own tent
    counts, so its points come back exactly; between two masters they move in a
    straight line, as in Sans."""
    locs = [n for n, _ in masters]
    for g in font.getGlyphOrder():
        coords = [m["glyf"]._getCoordinatesAndControls(g, m["hmtx"].metrics)[0] for _, m in masters]
        variations = []
        for k in range(1, len(masters)):
            delta = coords[k] - coords[0]
            if any(x or y for x, y in delta):
                tent = (locs[k - 1], locs[k], locs[k + 1] if k + 1 < len(locs) else locs[k])
                variations.append(TupleVariation({"wght": tent}, list(delta)))
        font["gvar"].variations[g] = variations


def glyph_names(font: TTFont, encoded: set[int]) -> list[str]:
    """Names for font's glyph order: uniXXXX for each of the `encoded` characters
    (the first, where a glyph has several), and for each other glyph the name of a
    glyph that substitutes to it with the feature's tag (uni3001.vert), or its
    ligature's components joined (uniFF01_uniFF1F.liga). The rest, and names over
    31 characters, are glyphNNNNN by glyph ID."""
    order = font.getGlyphOrder()
    names = {order[0]: ".notdef"}
    for u, g in sorted(font.getBestCmap().items()):
        if u in encoded and g not in names:
            names[g] = f"uni{u:04X}" if u <= 0xFFFF else f"u{u:05X}"
    taken = set(names.values())
    gsub = font["GSUB"].table
    features = sorted(gsub.FeatureList.FeatureRecord, key=lambda fr: (fr.FeatureTag == "aalt", fr.FeatureTag))
    grew = True
    while grew:
        grew = False
        for fr in features:
            for i in fr.Feature.LookupListIndex:
                for st in gsub.LookupList.Lookup[i].SubTable:
                    st = getattr(st, "ExtSubTable", st)
                    pairs = []
                    if isinstance(st, ot.SingleSubst):
                        pairs = [([a], b, "") for a, b in st.mapping.items()]
                    elif isinstance(st, ot.AlternateSubst):
                        pairs = [([a], b, str(k + 1)) for a, bs in st.alternates.items() for k, b in enumerate(bs)]
                    elif isinstance(st, ot.LigatureSubst):
                        pairs = [([a, *lig.Component], lig.LigGlyph, "") for a, ligs in st.ligatures.items() for lig in ligs]
                    for src, dst, n in pairs:
                        if dst in names or not all(g in names for g in src):
                            continue
                        stem = "_".join(names[g].split(".")[0] for g in src) if len(src) > 1 else names[src[0]]
                        name = f"{stem}.{fr.FeatureTag}{n}"
                        if len(name) <= 31 and name not in taken:
                            names[dst] = name
                            taken.add(name)
                            grew = True
    return [names.get(g) or f"glyph{i:05d}" for i, g in enumerate(order)]


def _walk(obj, fn, seen=None) -> None:
    """Calls fn once on every OpenType layout object under obj."""
    seen = set() if seen is None else seen
    if isinstance(obj, list):
        for item in obj:
            _walk(item, fn, seen)
    elif isinstance(obj, (BaseTable, ValueRecord)) and id(obj) not in seen:
        seen.add(id(obj))
        fn(obj)
        for value in vars(obj).values():
            if isinstance(value, (list, BaseTable, ValueRecord)):
                _walk(value, fn, seen)


def _shift(lookups_by: int = 0, var_data_by: int = 0):
    """Moves nested lookup references and VariationIndex outer indices by fixed offsets."""
    def fn(o):
        if isinstance(o, (ot.SubstLookupRecord, ot.PosLookupRecord)):
            o.LookupListIndex += lookups_by
        elif isinstance(o, ot.Device) and o.DeltaFormat == 0x8000:
            o.StartSize += var_data_by
    return fn


def _merge_var_store(store, other) -> int:
    """Appends other's regions and item data to store; returns the outer index other's data starts at."""
    key = lambda r: tuple((a.StartCoord, a.PeakCoord, a.EndCoord) for a in r.VarRegionAxis)  # noqa: E731
    regions = store.VarRegionList.Region
    index = {key(r): i for i, r in enumerate(regions)}
    remap = []
    for r in other.VarRegionList.Region:
        if key(r) not in index:
            index[key(r)] = len(regions)
            regions.append(r)
        remap.append(index[key(r)])
    store.VarRegionList.RegionCount = len(regions)
    start = len(store.VarData)
    for data in other.VarData:
        data.VarRegionIndex = [remap[i] for i in data.VarRegionIndex]
        store.VarData.append(data)
    store.VarDataCount = len(store.VarData)
    return start


def _systems(table) -> dict:
    """{(script, language or None): LangSys} of a GSUB or GPOS table."""
    out = {}
    for sr in table.ScriptList.ScriptRecord:
        if sr.Script.DefaultLangSys:
            out[(sr.ScriptTag, None)] = sr.Script.DefaultLangSys
        for lr in sr.Script.LangSysRecord:
            out[(sr.ScriptTag, lr.LangSysTag)] = lr.LangSys
    return out


def _pick(systems: dict, script: str, lang):
    """The language system a shaper uses: the script's own, else DFLT, then latn;
    the language's own, else the script's default."""
    scripts = {s for s, _ in systems}
    for s in (script, "DFLT", "latn"):
        if s in scripts:
            return systems.get((s, lang)) or systems.get((s, None))
    return None


def _feature(lookups) -> ot.Feature:
    f = ot.Feature()
    f.FeatureParams = None
    f.LookupListIndex = sorted(set(lookups))
    f.LookupCount = len(f.LookupListIndex)
    return f


def _langsys(features: list[int]) -> ot.LangSys:
    ls = ot.LangSys()
    ls.LookupOrder, ls.ReqFeatureIndex = None, 0xFFFF
    ls.FeatureIndex, ls.FeatureCount = features, len(features)
    return ls


def _merge_layout(table, other) -> None:
    """Appends other's lookups to table and gives every language system the
    features each font applies to it. A feature in both becomes one feature with
    both lookup lists, and table's FeatureVariations carry over to it."""
    lookups = table.LookupList.Lookup
    base = len(lookups)
    for lookup in other.LookupList.Lookup:
        _walk(lookup, _shift(lookups_by=base))
        lookups.append(lookup)
    table.LookupList.LookupCount = len(lookups)

    mine, theirs = _systems(table), _systems(other)
    scripts = {s for s, _ in mine}
    keys = set(mine) | {k for k in theirs if k[0] in scripts}
    own, added = table.FeatureList.FeatureRecord, other.FeatureList.FeatureRecord
    records: dict[tuple, int] = {}
    systems = {}
    for key in keys:
        tags: dict[str, list] = {}
        for i in getattr(_pick(mine, *key), "FeatureIndex", []):
            if own[i].FeatureTag in tags:
                raise ValueError(f"{key} has two {own[i].FeatureTag} features")
            tags[own[i].FeatureTag] = [i, ()]
        for i in getattr(_pick(theirs, *key), "FeatureIndex", []):
            tags.setdefault(added[i].FeatureTag, [None, ()])[1] = tuple(j + base for j in added[i].Feature.LookupListIndex)
        systems[key] = sorted(records.setdefault((tag, i, extra), len(records)) for tag, (i, extra) in tags.items())

    feature_list = ot.FeatureList()
    feature_list.FeatureRecord = []
    for tag, i, extra in records:
        fr = ot.FeatureRecord()
        fr.FeatureTag = tag
        fr.Feature = _feature((own[i].Feature.LookupListIndex if i is not None else []) + list(extra))
        feature_list.FeatureRecord.append(fr)
    feature_list.FeatureCount = len(records)

    script_list = ot.ScriptList()
    script_list.ScriptRecord = []
    for script in sorted({s for s, _ in systems}):
        sr = ot.ScriptRecord()
        sr.ScriptTag = script
        sr.Script = ot.Script()
        sr.Script.DefaultLangSys = _langsys(systems[(script, None)]) if (script, None) in systems else None
        sr.Script.LangSysRecord = []
        for lang in sorted(l for s, l in systems if s == script and l):
            lr = ot.LangSysRecord()
            lr.LangSysTag = lang
            lr.LangSys = _langsys(systems[(script, lang)])
            sr.Script.LangSysRecord.append(lr)
        sr.Script.LangSysCount = len(sr.Script.LangSysRecord)
        script_list.ScriptRecord.append(sr)
    script_list.ScriptCount = len(script_list.ScriptRecord)

    variations = getattr(table, "FeatureVariations", None)
    if variations:
        for rec in variations.FeatureVariationRecord:
            alt = {s.FeatureIndex: s.Feature for s in rec.FeatureTableSubstitution.SubstitutionRecord}
            subs = []
            for (tag, i, extra), index in records.items():
                if i in alt:
                    s = ot.FeatureTableSubstitutionRecord()
                    s.FeatureIndex = index
                    s.Feature = _feature(alt[i].LookupListIndex + list(extra))
                    subs.append(s)
            rec.FeatureTableSubstitution.SubstitutionRecord = subs
            rec.FeatureTableSubstitution.SubstitutionCount = len(subs)
    table.FeatureList, table.ScriptList = feature_list, script_list
    sortFeatureList(table)


def merge_latin(font: TTFont, latin: TTFont, v_origin: int, marks: set[str]) -> list[str]:
    """Adds latin's glyphs (but its .notdef) to font with their outlines,
    variations, metrics, characters, layout and GDEF data; returns their names.
    Each new glyph's vertical origin is v_origin, at every weight. `marks` are
    font's own combining marks, which GDEF marks as such so a shaper treats them
    as it did when it read their class from Unicode."""
    font.ensureDecompiled()
    latin.ensureDecompiled()
    names = [g for g in latin.getGlyphOrder() if g != ".notdef"]
    clash = set(names) & set(font.getGlyphOrder())
    if clash:
        raise ValueError(f"glyph names in both fonts: {sorted(clash)}")
    order = font.getGlyphOrder() + names
    glyf, lglyf, upm = font["glyf"], latin["glyf"], font["head"].unitsPerEm
    for g in names:
        glyph = lglyf[g]
        coords = glyph.getCoordinates(lglyf)[0] if glyph.numberOfContours else []
        glyf.glyphs[g] = glyph
        font["gvar"].variations[g] = latin["gvar"].variations.get(g, [])
        font["hmtx"].metrics[g] = latin["hmtx"].metrics[g]
        font["vmtx"].metrics[g] = (upm, v_origin - (max(y for _, y in coords) if len(coords) else 0))
    glyf.setGlyphOrder(order)
    font.setGlyphOrder(order)
    have = latin.getBestCmap()
    for table in font["cmap"].tables:
        if table.format in (4, 12) and table.isUnicode():
            table.cmap.update(have)

    gdef, lgdef = font["GDEF"].table, latin["GDEF"].table
    start = _merge_var_store(gdef.VarStore, lgdef.VarStore) if lgdef.VarStore else 0
    shift = _shift(var_data_by=start)
    for tag in ("GSUB", "GPOS"):
        if tag == "GPOS":
            _walk(latin[tag].table.LookupList, shift)
        _merge_layout(font[tag].table, latin[tag].table)
    if gdef.GlyphClassDef or gdef.MarkAttachClassDef or getattr(gdef, "MarkGlyphSetsDef", None):
        raise ValueError("the CJK font's GDEF already has glyph classes")
    gdef.GlyphClassDef = ot.GlyphClassDef()
    gdef.GlyphClassDef.classDefs = {**(lgdef.GlyphClassDef.classDefs if lgdef.GlyphClassDef else {}), **{g: 3 for g in marks}}
    gdef.MarkAttachClassDef = lgdef.MarkAttachClassDef
    gdef.MarkGlyphSetsDef = getattr(lgdef, "MarkGlyphSetsDef", None)
    if lgdef.LigCaretList:
        _walk(lgdef.LigCaretList, shift)
    gdef.LigCaretList = lgdef.LigCaretList
    gdef.Version = 0x00010003
    return names


def unicode_marks(font: TTFont) -> set[str]:
    """The glyphs a shaper classes as marks from Unicode when GDEF has no glyph
    classes: those of nonspacing marks and their single substitutes, which keep
    the character's class."""
    import unicodedata

    found = {g for u, g in font.getBestCmap().items() if unicodedata.category(chr(u)) == "Mn"}
    gsub = font["GSUB"].table
    while True:
        more = set()
        for lookup in gsub.LookupList.Lookup:
            for st in lookup.SubTable:
                st = getattr(st, "ExtSubTable", st)
                if isinstance(st, ot.SingleSubst):
                    more |= {v for k, v in st.mapping.items() if k in found}
                elif isinstance(st, ot.AlternateSubst):
                    more |= {v for k, vs in st.alternates.items() if k in found for v in vs}
        if more <= found:
            return found
        found |= more


def lig_carets(font: TTFont, lig_glyphs: dict[str, list[str]]) -> None:
    """GDEF caret positions for each ligature, one between each pair of its
    components, at the components' share of its advance."""
    hmtx, gdef = font["hmtx"], font["GDEF"].table
    entries = {}
    if gdef.LigCaretList:
        entries = dict(zip(gdef.LigCaretList.Coverage.glyphs, gdef.LigCaretList.LigGlyph))
    for lig, parts in lig_glyphs.items():
        widths = [hmtx[g][0] for g in parts]
        total, adv = sum(widths), hmtx[lig][0]
        entries[lig] = otl.buildLigGlyph([round(adv * sum(widths[:k]) / total) for k in range(1, len(parts))], None)
    carets = ot.LigCaretList()
    carets.Coverage = otl.buildCoverage(entries, font.getReverseGlyphMap())
    carets.LigGlyph = [entries[g] for g in carets.Coverage.glyphs]
    carets.LigGlyphCount = len(carets.LigGlyph)
    gdef.LigCaretList = carets


def ligatures(font: TTFont, feature: str = "liga") -> dict[str, list[str]]:
    """{ligature glyph: its components} for the feature's ligature substitutions."""
    gsub = font["GSUB"].table
    out = {}
    for fr in gsub.FeatureList.FeatureRecord:
        if fr.FeatureTag != feature:
            continue
        for i in fr.Feature.LookupListIndex:
            for st in gsub.LookupList.Lookup[i].SubTable:
                st = getattr(st, "ExtSubTable", st)
                if isinstance(st, ot.LigatureSubst):
                    for first, ligs in st.ligatures.items():
                        out.update({lig.LigGlyph: [first, *lig.Component] for lig in ligs})
    return out


def _contours(glyph) -> list[tuple[int, int]]:
    starts = [0, *(e + 1 for e in glyph.endPtsOfContours[:-1])]
    return list(zip(starts, glyph.endPtsOfContours))


def _keep_points(font: TTFont, name: str, order: list[int], ends: list[int]) -> None:
    """Rebuilds a simple glyph from its points in `order`, with these contour ends;
    its variations' deltas follow the points and the four phantom points stay last."""
    glyph = font["glyf"][name]
    n = len(glyph.coordinates)
    glyph.coordinates = GlyphCoordinates([glyph.coordinates[i] for i in order])
    glyph.flags = bytearray(glyph.flags[i] for i in order)
    glyph.endPtsOfContours = ends
    glyph.numberOfContours = len(ends)
    for tv in font["gvar"].variations.get(name, []):
        tv.coordinates = [tv.coordinates[i] for i in order] + tv.coordinates[n:]


def reverse_ccw_outers(font: TTFont) -> list[str]:
    """Turns clockwise each outer contour that runs counter-clockwise, as fontbakery's
    outline_direction check finds them (a contour no other contour's box holds),
    together with the contours inside its box. Only a group that overlaps no other
    contour is reversed, so the fill stays the same under the nonzero and even-odd rules."""
    fixed = []
    for name in font.getGlyphOrder():
        glyph = font["glyf"][name]
        if glyph.isComposite() or glyph.numberOfContours < 1:
            continue
        facts = _contour_facts(glyph, font["glyf"])
        ranges = _contours(glyph)
        if len(facts) != len(ranges):
            continue
        n = len(ranges)
        inside = lambda a, b: a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]  # noqa: E731  b in a
        flip = set()
        for i, (area, box, _) in enumerate(facts):
            if area <= 0 or any(j != i and inside(facts[j][1], box) for j in range(n)):
                continue
            group = {i} | {j for j in range(n) if j != i and inside(box, facts[j][1])}
            rest = [j for j in range(n) if j not in group]
            if not rest or abs(pathops.op(_path(facts, group), _path(facts, rest), pathops.PathOp.INTERSECTION).area) < 1:
                flip |= group
        if not flip:
            continue
        order = []
        for i, (s, e) in enumerate(ranges):
            order += [s, *range(e, s, -1)] if i in flip else range(s, e + 1)
        _keep_points(font, name, order, list(glyph.endPtsOfContours))
        fixed.append(name)
    return fixed


def _path(facts, contours) -> pathops.Path:
    path = pathops.Path()
    pen = path.getPen()
    for i in sorted(contours):
        for op, args in facts[i][2]:
            getattr(pen, op)(*args)
    return path


def _contour_facts(glyph, glyf) -> list[tuple[float, tuple, list]]:
    """Signed area (positive when counter-clockwise), bounds and drawing of each contour."""
    rec = RecordingPen()
    glyph.draw(rec, glyf)
    out, ops = [], []
    for op, args in rec.value:
        ops.append((op, args))
        if op in ("closePath", "endPath"):
            area, box = AreaPen(), BoundsPen(None)
            for pen in (area, box):
                for o, a in ops:
                    getattr(pen, o)(*a)
            out.append((area.value, box.bounds, ops))
            ops = []
    return out

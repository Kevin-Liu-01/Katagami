"""Slant a compiled TrueType font the way the Italics' masters are slanted
(`fontops.shear`): x += (y - y0) * t.

The merged scripts and the CJK companions come to Katagami as compiled fonts,
so their Italics are slanted here, after they are scaled to Katagami's size.
Text set in the slanted font is the upright text slanted: contours move as
points, component offsets as vectors, every delta of a variable glyph so that
each master's point lands where the master's own point slants to, anchors as
points, and a GPOS placement or advance (dx, dy) becomes (dx + dy * t, dy).
Advances stay. Lookups that only vertical features reach stay too, so
vertical text keeps its column.
"""

from __future__ import annotations

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates

VERTICAL = {"vert", "vrt2", "vkna", "vkrn", "vpal", "vhal", "valt", "vchw"}
Y_PLACEMENT, Y_ADVANCE, Y_DEVICES = 0x0002, 0x0008, 0x0020 | 0x0080


def slant(font: TTFont, t: float, y0: float) -> None:
    """Slant every glyph, variation, anchor and placement of the font by
    x += (y - y0) * t. Raises on a component with a 2x2 transform, which a
    shear would turn into a skew, and on a Y device table in a lookup it
    slants, whose variation it cannot carry into X."""
    _glyphs(font, t, y0)
    if "GPOS" in font and font["GPOS"].table.LookupList:
        _gpos(font["GPOS"].table, t, y0)
    if "GDEF" in font and getattr(font["GDEF"].table, "LigCaretList", None):
        for lig in font["GDEF"].table.LigCaretList.LigGlyph:
            for caret in lig.CaretValue:
                if caret.Format in (1, 3):  # an x on the baseline; format 2 names a point, which moved with its glyph
                    caret.Coordinate = otRound(caret.Coordinate - y0 * t)


def _glyphs(font: TTFont, t: float, y0: float) -> None:
    glyf, hmtx = font["glyf"], font["hmtx"]
    gvar = font["gvar"] if "gvar" in font else None
    vmetrics = font["vmtx"].metrics if "vmtx" in font else None
    order = font.getGlyphOrder()
    moved = {}  # name -> the glyph's points with its phantoms, before and after, for its variations
    for name in order:
        g = glyf[name]
        varied = gvar is not None and bool(gvar.variations.get(name)) and g.numberOfContours != 0
        if varied:
            coords, controls = glyf._getCoordinatesAndControls(name, hmtx.metrics, vmetrics)
        if g.isComposite():
            for c in g.components:
                if getattr(c, "transform", None) is not None:
                    raise ValueError(f"{name}: component {c.glyphName} has a transform; draw it in first")
            # an offset is a vector: it slants about y = 0
            before = [(c.x, c.y) for c in g.components]
            after = [(otRound(x + y * t), y) for x, y in before]
            for c, (x, _) in zip(g.components, after):
                c.x = x
            origin = 0.0
        elif g.numberOfContours > 0:
            before = list(g.coordinates)
            after = [(otRound(x + (y - y0) * t), y) for x, y in before]
            g.coordinates = GlyphCoordinates(after)
            origin = y0
        else:
            continue
        if varied:
            moved[name] = (coords, before, after, origin, controls)
    for name in order:  # simple glyphs first moved, so a composite's bounds read its moved parts
        g = glyf[name]
        if g.numberOfContours != 0:
            g.recalcBounds(glyf)
            hmtx[name] = (hmtx[name][0], g.xMin)
    for name, (coords, before, after, origin, controls) in moved.items():
        _variations(gvar.variations[name], glyf, name, hmtx, vmetrics, coords, before, after, origin, t, controls)


def _variations(variations, glyf, name, hmtx, vmetrics, coords, before, after, origin, t, controls) -> None:
    """Each master's points slanted where they stand at the master, less the
    default's slanted points; the phantom points' deltas (the advances) stay."""
    composite = glyf[name].isComposite()
    n = len(before)
    for var in variations:
        if None in var.coordinates:
            if composite:
                var.coordinates = [(0, 0) if d is None else d for d in var.coordinates]
            else:
                var.calcInferredDeltas(coords, controls.endPts)
        deltas = list(var.coordinates)
        for i in range(n):
            (x, y), (nx, _), (dx, dy) = before[i], after[i], deltas[i]
            mx, my = otRound(x + dx), otRound(y + dy)  # the master's point, as an instancer rounds it
            deltas[i] = (otRound(mx + (my - origin) * t) - nx, my - y)
        for i in range(n, len(deltas)):
            deltas[i] = (otRound(deltas[i][0]), otRound(deltas[i][1]))
        var.coordinates = deltas
    new, _ = glyf._getCoordinatesAndControls(name, hmtx.metrics, vmetrics)
    for var in variations:
        var.optimize(new, controls.endPts, isComposite=composite)


def _gpos(table, t: float, y0: float) -> None:
    reach = _reach(table)
    seen = set()
    for i, lookup in enumerate(table.LookupList.Lookup):
        tags = reach.get(i, set())
        if tags and tags <= VERTICAL:
            continue
        for st in lookup.SubTable:
            ext = getattr(st, "ExtSubTable", None)
            _subtable(ext if ext is not None else st, t, y0, seen)


def _reach(table) -> dict[int, set[str]]:
    """The feature tags that reach each lookup, directly, through a feature
    variation (Noto CJK's heavier palt and vpal) or through contextual lookups."""
    reach = {}
    features = [(rec.FeatureTag, rec.Feature) for rec in table.FeatureList.FeatureRecord]
    if getattr(table, "FeatureVariations", None) is not None:
        for var in table.FeatureVariations.FeatureVariationRecord:
            for sub in var.FeatureTableSubstitution.SubstitutionRecord:
                features.append((table.FeatureList.FeatureRecord[sub.FeatureIndex].FeatureTag, sub.Feature))
    for tag, feature in features:
        for i in feature.LookupListIndex:
            reach.setdefault(i, set()).add(tag)
    calls = {i: _called(lookup) for i, lookup in enumerate(table.LookupList.Lookup)}
    changed = True
    while changed:
        changed = False
        for i, called in calls.items():
            for j in called:
                tags = reach.get(i, set()) - reach.get(j, set())
                if tags:
                    reach.setdefault(j, set()).update(tags)
                    changed = True
    return reach


def _called(lookup) -> set[int]:
    """The lookups a contextual lookup's records call."""
    out = set()

    def visit(obj) -> None:
        if isinstance(obj, list):
            for item in obj:
                visit(item)
        elif type(obj).__name__ == "PosLookupRecord":
            out.add(obj.LookupListIndex)
        elif hasattr(obj, "__dict__") and type(obj).__name__ not in ("Coverage", "ClassDef"):
            for value in vars(obj).values():
                visit(value)

    for st in lookup.SubTable:
        ext = getattr(st, "ExtSubTable", None)
        st = ext if ext is not None else st
        if type(st).__name__ in ("ContextPos", "ChainContextPos"):
            visit(st)
    return out


def _subtable(st, t: float, y0: float, seen: set) -> None:
    kind = type(st).__name__
    if kind == "SinglePos":
        st.ValueFormat = _values([st.Value] if st.Format == 1 else st.Value, st.ValueFormat, t)
    elif kind == "PairPos":
        if st.Format == 1:
            recs = [r for pair_set in st.PairSet for r in pair_set.PairValueRecord]
        else:
            recs = [r for c1 in st.Class1Record for r in c1.Class2Record]
        st.ValueFormat1 = _values([getattr(r, "Value1", None) for r in recs], st.ValueFormat1, t)
        st.ValueFormat2 = _values([getattr(r, "Value2", None) for r in recs], st.ValueFormat2, t)
    elif kind == "CursivePos":
        for r in st.EntryExitRecord:
            _anchors([r.EntryAnchor, r.ExitAnchor], t, y0, seen)
    elif kind == "MarkBasePos":
        _anchors([r.MarkAnchor for r in st.MarkArray.MarkRecord], t, y0, seen)
        _anchors([a for r in st.BaseArray.BaseRecord for a in r.BaseAnchor], t, y0, seen)
    elif kind == "MarkLigPos":
        _anchors([r.MarkAnchor for r in st.MarkArray.MarkRecord], t, y0, seen)
        _anchors([a for attach in st.LigatureArray.LigatureAttach for c in attach.ComponentRecord
                  for a in c.LigatureAnchor], t, y0, seen)
    elif kind == "MarkMarkPos":
        _anchors([r.MarkAnchor for r in st.Mark1Array.MarkRecord], t, y0, seen)
        _anchors([a for r in st.Mark2Array.Mark2Record for a in r.Mark2Anchor], t, y0, seen)


def _values(records: list, fmt: int, t: float) -> int:
    """Records whose format has a Y placement or advance take its slant in X; returns the new format."""
    if not fmt & (Y_PLACEMENT | Y_ADVANCE):
        return fmt
    if fmt & Y_DEVICES:
        raise ValueError("a value record with a Y device table")
    for v in records:
        if v is None:
            continue
        if fmt & Y_PLACEMENT:
            v.XPlacement = getattr(v, "XPlacement", 0) + otRound(getattr(v, "YPlacement", 0) * t)
        if fmt & Y_ADVANCE:
            v.XAdvance = getattr(v, "XAdvance", 0) + otRound(getattr(v, "YAdvance", 0) * t)
    return fmt | (0x0001 if fmt & Y_PLACEMENT else 0) | (0x0004 if fmt & Y_ADVANCE else 0)


def _anchors(anchors: list, t: float, y0: float, seen: set) -> None:
    for a in anchors:
        if a is None or id(a) in seen:
            continue
        seen.add(id(a))
        if a.Format == 3 and getattr(a, "YDeviceTable", None) is not None:
            raise ValueError("an anchor with a Y device table")
        a.XCoordinate = otRound(a.XCoordinate + (a.YCoordinate - y0) * t)

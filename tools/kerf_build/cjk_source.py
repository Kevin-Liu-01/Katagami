"""The CJK companions' sources, made ready for build_cjk.py: one variable font per
companion on Katagami's weight axis, 100 to 900 with Thin as its default.

SC takes Frex Sans GB, the fork of IBM Plex Sans SC that draws the shapes of
China's national standard, as released. TC, JP and KR take IBM Plex Sans TC, JP
and KR, compiled here from the masters in each release's sources.zip, because
IBM ships them only as static fonts. The sources draw Thin to Bold, and every
weight between keeps the source's own outlines and curve. Black is Bold thickened
with build_world's embolden, the rule Katagami already uses where a merged
script's Noto font stops short of Black: each glyph by BLACK_RATIO of what it
thickens from Thin to Bold, as Noto Sans CJK's Black does, with each advance
kept at the full-width em. ExtraBold falls halfway between.

A character the national standard asks for that the source does not draw comes
from the other Plex and Frex sources in LENDERS order. They share one design,
one stem system and one em box. A character none of them draws is left out.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import ufoLib2
from fontTools import subset
from fontTools.designspaceLib import DesignSpaceDocument, RuleDescriptor
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib import build as build_variable
from fontTools.varLib.instancer import OverlapMode, instantiateVariableFont
from fontTools.varLib.models import piecewiseLinearMap

ROOT = Path(__file__).resolve().parents[2]
PLEX = ROOT / "vendor" / "plex"  # the masters of IBM Plex Sans JP, KR and TC, from each release's sources.zip
FREX = ROOT / "vendor" / "frex"  # Frex Sans GB's release
WORK = ROOT / "build" / "cjk-src"
SOURCES = {
    "SC": {"name": "Frex Sans GB", "vf": FREX / "Frex Sans GB[wght].ttf"},
    "TC": {"name": "IBM Plex Sans TC", "glyphs": PLEX / "tc" / "IBM Plex Sans TC.glyphs"},
    "JP": {"name": "IBM Plex Sans JP", "glyphs": PLEX / "jp" / "IBM Plex Sans JP.glyphs"},
    # Plex KR's em box runs from -220 to 780 where the others' runs from -120 to 880, so it is raised by 100
    "KR": {"name": "IBM Plex Sans KR", "glyphs": PLEX / "kr" / "IBM Plex Sans KR.glyphs", "raise": 100},
}
# who lends a source the characters it lacks, in order: Japanese punctuation sits low in the em as
# Chinese and Korean punctuation does, so JP lends first to SC and KR; KR comes last, for the
# parenthesized and circled Hangul and the squared units only it draws
LENDERS = {"SC": ("JP", "TC", "KR"), "TC": ("JP", "SC", "KR"), "JP": ("TC", "SC", "KR"), "KR": ("JP", "TC", "SC")}
# the notices as the sources state them: IBM's license file, and Frex Sans GB's copyright name
IBM = 'Copyright 2017 IBM Corp. with Reserved Font Name "Plex"'
FREX_NOTICE = "Copyright 2025 The Frex Sans Project Authors (https://gitee.com/NightFurySL2001/flex-sc)"
# Each glyph's strokes thicken from Bold to Black by this share of what they thicken from Thin to Bold.
# It is Noto Sans CJK's rule, measured as ink area gained over half the outline's length: 0.25 to 0.27
# on 一, 丨, 口, 永, 的, 编, 器, 囊 and 爨 alike, so a dense glyph, which its designers thicken less,
# keeps its white at Black. On Frex Sans GB's 一 it adds 28 units, as Noto's 一 gains 28 from 131 to 159.
BLACK_RATIO = 0.27
TOP = 900
STYLES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium",
          600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
# a Plex instance's user weight, by name; its location in the .glyphs file is its design weight
USER = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "text": 450, "medium": 500, "semibold": 600, "bold": 700}


def _between(x: float, xs: list[float], ys: list[float]) -> float:
    """y at x on the polyline through (xs, ys); xs rises."""
    if x <= xs[0]:
        return ys[0]
    for x0, y0, x1, y1 in zip(xs, ys, xs[1:], ys[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return ys[-1]


def _plex_axis(space: Path) -> None:
    """Thin to Bold with Thin as the default, each named weight at its design weight. IBM's
    instance settings do not say this: KR leaves Thin out of the export, and JP and TC give
    two instances one weight class, so glyphsLib's axis has no default or maps one weight twice."""
    doc = DesignSpaceDocument.fromfile(space)
    axis = doc.axes[0]
    pairs = {}
    for inst in doc.instances:
        name = (inst.styleName or "").replace(" ", "").lower()
        if name in USER:
            pairs[USER[name]] = inst.designLocation[axis.name]
    pairs[100] = min(s.designLocation[axis.name] for s in doc.sources)
    pairs[700] = max(s.designLocation[axis.name] for s in doc.sources)
    axis.minimum, axis.default, axis.maximum = 100, 100, 700
    axis.map = sorted(pairs.items())
    doc.write(space)


def _turn_corners(space: Path) -> list[str]:
    """Corner components drawn from the outgoing stroke back to the incoming one, turned round.
    Glyphs places such a corner either way; glyphsLib reads a corner's first point as the incoming
    stroke's, so Plex KR's _corner.round, which runs from (19, 0) to (0, 18), put a spur on 6,384
    Hangul where IBM's fonts have a round corner. No corner in Plex KR is mirrored, which would
    reverse it again."""
    from fontTools.pens.pointPen import PointToSegmentPen, SegmentToPointPen
    from fontTools.pens.reverseContourPen import ReverseContourPen

    turned = set()
    for src in DesignSpaceDocument.fromfile(space).sources:
        font = ufoLib2.Font.open(src.path)
        changed = False
        for name in [n for n in font.keys() if n.startswith("_corner.")]:
            g = font[name]
            origin = next((a for a in g.anchors if a.name == "origin"), None)
            ox = origin.x if origin else 0
            runs = [[p for p in c if p.type] for c in g.contours if c[0].type == "move"]
            if not runs or not all(r[0].x != ox and r[-1].x == ox for r in runs):
                continue
            new = ufoLib2.objects.Glyph(name)
            g.drawPoints(PointToSegmentPen(ReverseContourPen(SegmentToPointPen(new.getPointPen()))))
            g.clearContours()
            new.drawPoints(g.getPointPen())
            turned.add(name)
            changed = True
        if changed:
            font.save(src.path, overwrite=True)
    return sorted(turned)


def _name_unicodes(space: Path) -> list[str]:
    """Each glyph named uniXXXX or uXXXXX also maps its name's code point, when no other glyph does,
    as Glyphs maps it on export. Plex TC stores only the radical U+2EC4 on 西's glyph, uni897F, and Plex JP
    stores none on 39 glyphs, 恵 and 舘 among them; IBM's own fonts map all of them by their names."""
    added = set()
    for src in DesignSpaceDocument.fromfile(space).sources:
        font = ufoLib2.Font.open(src.path)
        mapped = {u for g in font for u in g.unicodes}
        changed = False
        for g in font:
            m = re.fullmatch(r"uni([0-9A-F]{4})|u([0-9A-F]{5,6})", g.name)
            u = int(m.group(1) or m.group(2), 16) if m else None
            if u is not None and u not in mapped and not 0xD800 <= u <= 0xDFFF:
                g.unicodes = [*g.unicodes, u]
                mapped.add(u)
                added.add(chr(u))
                changed = True
        if changed:
            font.save(src.path, overwrite=True)
    return sorted(added)


def _left_of(line, p) -> bool:
    (ax, ay), (bx, by) = line
    return (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) >= 0


def _collapse_open_corners(contour) -> bool:
    """Glyphs' open corners, found as glyphsLib's eraseOpenCorners finds them, with the line between
    the two crossing strokes collapsed onto their crossing instead of deleted. The ink is the same,
    and the contour keeps every point, so masters that differ in which corners they erase still
    interpolate."""
    from fontTools.misc.bezierTools import _split_segment_at_t, segmentSegmentIntersections

    pts = list(contour)
    if not pts or pts[0].type == "move":
        return False
    on = [i for i, p in enumerate(pts) if p.type]
    if len(on) < 3:
        return False
    n = len(pts)
    # a segment is the run of point indices from one on-curve point to the next, both ends included
    segs = []
    for k, end in enumerate(on):
        start = on[k - 1]
        between = list(range(start + 1, end)) if end > start else [*range(start + 1, n), *range(0, end)]
        segs.append([start, *between, end])
    xy = lambda run: [(pts[x].x, pts[x].y) for x in run]  # noqa: E731
    changed = False
    for k, seg in enumerate(segs):
        if len(seg) != 2:
            continue
        prev, nxt = segs[k - 1], segs[(k + 1) % len(segs)]
        line = xy(seg)
        if line[0] == line[1] or _left_of(line, xy(prev)[-2]) or _left_of(line, xy(nxt)[1]):
            continue
        hits = [h for h in segmentSegmentIntersections(xy(prev), xy(nxt)) if 0 <= h.t1 <= 1 and 0 <= h.t2 <= 1]
        if not hits:
            continue
        t1, t2 = 1 - hits[0].t1, hits[0].t2
        if not (((t1 < 0.5 and t2 < 0.5) or (t1 < 0.3 and t2 < 0.99) or (t1 < 0.99 and t2 < 0.3)) and t1 > 0.001 and t2 > 0.001):
            continue
        head, _ = _split_segment_at_t(xy(prev), hits[0].t1)
        _, tail = _split_segment_at_t(xy(nxt), hits[0].t2)
        cross = head[-1]
        for x, (px, py) in zip(prev[1:], head[1:]):
            pts[x].x, pts[x].y = px, py
        pts[seg[1]].x, pts[seg[1]].y = cross
        for x, (px, py) in zip(nxt[1:-1], tail[1:-1]):
            pts[x].x, pts[x].y = px, py
        changed = True
    return changed


def _open_corners(space: Path) -> int:
    """Every master's open corners collapsed (`_collapse_open_corners`) in place of glyphsLib's
    eraseOpenCorners filter, which deletes a point where Glyphs' rule finds an open corner and so
    left 97 of Plex JP's glyphs, わ and ぁ among them, with masters that no longer interpolate."""
    count = 0
    for src in DesignSpaceDocument.fromfile(space).sources:
        font = ufoLib2.Font.open(src.path)
        filters = font.lib.get("com.github.googlei18n.ufo2ft.filters", [])
        if not any(f.get("name") == "eraseOpenCorners" for f in filters):
            continue
        font.lib["com.github.googlei18n.ufo2ft.filters"] = [f for f in filters if f.get("name") != "eraseOpenCorners"]
        for g in font:
            if sum([_collapse_open_corners(c) for c in g.contours]):
                count += 1
        font.save(src.path, overwrite=True)
    return count


def _shape(glyph) -> tuple:
    return [tuple(p.type for p in c) for c in glyph.contours], [c.baseGlyph for c in glyph.components]


def _flatten_incompatible(space: Path, names: set[str] | None = None) -> dict[str, list[int]]:
    """Glyphs whose masters do not interpolate (or the given names), as {name: code points}. Each
    takes its default master's outline in every master, so the font compiles; the source then
    counts their characters as ones it does not draw, and a lender or nobody draws them."""
    doc = DesignSpaceDocument.fromfile(space)
    default = doc.findDefault().path
    fonts = {s.path: ufoLib2.Font.open(s.path) for s in doc.sources}
    base = fonts[default]
    flat = {}
    for name in sorted(names) if names is not None else base.keys():
        shapes = [_shape(f[name]) for f in fonts.values() if name in f]
        if names is not None or len(shapes) == len(fonts) and any(s != shapes[0] for s in shapes[1:]):
            flat[name] = list(base[name].unicodes)
            for p, f in fonts.items():
                if p != default:
                    f[name].clearContours()
                    f[name].clearComponents()
                    base[name].drawPoints(f[name].getPointPen())
                    f[name].width = base[name].width
    for p, f in fonts.items():
        if p != default and flat:
            f.save(p, overwrite=True)
    return flat


def source_vf(region: str) -> tuple[Path, set[int]]:
    """The source as a variable font on its own axis, and the characters whose glyph it draws
    at one weight only: Frex Sans GB as released, each Plex font compiled once into build/cjk-src."""
    src = SOURCES[region]
    if "vf" in src:
        return src["vf"], set()
    work = WORK / region
    out = work / (src["name"].replace(" ", "") + "[wght].ttf")
    flat_file = work / "flattened.json"
    if out.exists() and flat_file.exists() and out.stat().st_mtime > src["glyphs"].stat().st_mtime:
        return out, set(json.loads(flat_file.read_text())["characters"])
    work.mkdir(parents=True, exist_ok=True)
    glyphs = work / src["glyphs"].name
    # IBM switched some of KR's intermediate layers off by naming them "Rg {400, 100off}". Glyphs passes
    # over such a name and glyphsLib cannot read it, so they become backup layers, as Glyphs treats them.
    text = src["glyphs"].read_text(encoding="utf-8")
    text = re.sub(r'^name = "(\w+) \{([^}]*off)\}";$', r'name = "\1 (\2)";', text, flags=re.M)
    glyphs.write_text(text, encoding="utf-8")
    del text
    ufos = work / "master_ufo"
    shutil.rmtree(ufos, ignore_errors=True)
    bin_dir = Path(sys.executable).parent
    # --minimal: the full conversion stops on a missing component in a background layer of KR's ga-ko
    subprocess.run([str(bin_dir / "glyphs2ufo"), str(glyphs), "-m", str(ufos), "--minimal", "--generate-GDEF"],
                   check=True, stdout=subprocess.DEVNULL)
    space = next(ufos.glob("*.designspace"))
    _plex_axis(space)
    named = _name_unicodes(space)
    turned = _turn_corners(space)
    collapsed = _open_corners(space)
    flat = _flatten_incompatible(space)
    for _ in range(3):
        # ufo2ft's filters (erasing open corners) can part two masters that matched before them;
        # fontmake names such glyphs, and they are flattened too
        run = subprocess.run([str(bin_dir / "fontmake"), "-m", str(space), "-o", "variable", "--output-path", str(out)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        late = re.search(r"incompatible glyphs: (.+)$", run.stderr, flags=re.M)
        if run.returncode == 0 or not late:
            break
        flat |= _flatten_incompatible(space, set(re.findall(r"'([^']+)'", late.group(1))))
    if run.returncode:
        sys.stderr.write(run.stderr[-4000:])
        raise RuntimeError(f"fontmake could not compile {space.name}")
    codes = sorted({u for us in flat.values() for u in us})
    flat_file.write_text(json.dumps({"glyphs": sorted(flat), "characters": codes}, indent=1))
    print(f"{out.relative_to(ROOT)}: compiled; mapped by name: {''.join(named) or 'none'}; "
          f"corner components turned round: {', '.join(turned) or 'none'}; "
          f"open corners collapsed in {collapsed} glyph masters; "
          f"{len(flat)} glyphs whose masters do not interpolate are left out ({', '.join(sorted(flat)) or 'none'})",
          flush=True)
    return out, set(codes)


def _subset(font: TTFont, unicodes: set[int], layout: bool) -> None:
    opts = subset.Options()
    opts.layout_features = ["*"] if layout else []
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = False
    opts.glyph_names = True
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=sorted(unicodes))
    sub.subset(font)


def _axis(font: TTFont):
    return next(a for a in font["fvar"].axes if a.axisTag == "wght")


def _segments(font: TTFont) -> dict:
    return font["avar"].segments.get("wght", {}) if "avar" in font else {}


def _design(font: TTFont, w: float) -> float:
    """A user weight as the source's normalized coordinate after avar, where its masters sit."""
    a = _axis(font)
    n = (w - a.defaultValue) / ((a.defaultValue - a.minValue) if w < a.defaultValue else (a.maxValue - a.defaultValue) or 1)
    seg = _segments(font)
    return piecewiseLinearMap(n, seg) if seg else n


def _user(font: TTFont, d: float) -> float:
    """The inverse of _design."""
    seg = _segments(font)
    n = piecewiseLinearMap(d, {v: k for k, v in seg.items()}) if seg else d
    a = _axis(font)
    w = a.defaultValue + n * ((a.defaultValue - a.minValue) if n < 0 else (a.maxValue - a.defaultValue))
    return float(round(w)) if abs(w - round(w)) < 0.05 else round(w, 3)  # avar keys are 2.14 fixed point


def masters(font: TTFont) -> list[float]:
    """The user weights of the source's masters: its default and every peak in gvar."""
    peaks = Counter(tv.axes["wght"][1] for tvs in font["gvar"].variations.values() for tv in tvs if "wght" in tv.axes)
    return sorted({_user(font, 0.0)} | {_user(font, p) for p in peaks})


def _axis_map(font: TTFont, weights: list[float]) -> tuple[list[tuple[float, float]], callable]:
    """User weight to design weight for the assembled font, and the function from the source's
    normalized coordinates to design weights. A master's design weight is its user weight; between
    two masters every weight sits where the source puts it, and from Bold to Black the map is straight."""
    peaks = [_design(font, w) for w in weights]
    to_design = lambda d: _between(d, peaks, weights)  # noqa: E731
    users = set(weights) | {_user(font, k_out) for k_out in _segments(font).values()}
    pairs = [(u, round(to_design(_design(font, u)), 3)) for u in sorted(users) if weights[0] <= u <= weights[-1]]
    return pairs + [(float(TOP), float(TOP))], to_design


def _take_rules(font: TTFont) -> tuple[list[tuple[float, float, dict]], str]:
    """Remove GSUB's feature variations (glyphs Plex swaps in from one weight up) and return them
    as (lowest, highest, {glyph: swapped glyph}) in the source's normalized coordinates, with the
    feature that carried them, so varLib can build them again on the new axis."""
    gsub = font["GSUB"].table if "GSUB" in font else None
    fv = getattr(gsub, "FeatureVariations", None)
    if fv is None:
        return [], "rvrn"
    lookups = gsub.LookupList.Lookup
    recs, tags = [], set()
    for rec in fv.FeatureVariationRecord:
        lo, hi = -1.0, 1.0
        for c in rec.ConditionSet.ConditionTable if rec.ConditionSet else []:  # no condition set: every weight
            lo, hi = max(lo, c.FilterRangeMinValue), min(hi, c.FilterRangeMaxValue)
        subs = {}
        for sr in rec.FeatureTableSubstitution.SubstitutionRecord:
            fr = gsub.FeatureList.FeatureRecord[sr.FeatureIndex]
            tags.add(fr.FeatureTag)
            for i in set(sr.Feature.LookupListIndex) - set(fr.Feature.LookupListIndex):
                for st in lookups[i].SubTable:
                    st = getattr(st, "ExtSubTable", st)
                    if not isinstance(st, ot.SingleSubst):
                        raise ValueError(f"a feature variation of {font['name'].getDebugName(1)} is not a single substitution")
                    subs.update(st.mapping)
        recs.append((lo, hi, subs))
    gsub.FeatureVariations = None
    gsub.Version = 0x00010000
    if len(tags) > 1:
        raise ValueError(f"feature variations on {sorted(tags)}")
    # A shaper takes the first record whose conditions hold, and glyphsLib writes one record for each
    # overlap of Plex's bracket layers. So each swap holds over the runs of weights where the first
    # record that holds has it, found by probing every bound and the middle of every gap between bounds.
    cuts = sorted({b for lo, hi, _ in recs for b in (lo, hi)} | {-1.0, 1.0})
    probes = sorted(set(cuts) | {(a + b) / 2 for a, b in zip(cuts, cuts[1:])})
    runs, before = {}, set()
    for x in probes:
        now = set(next((s for lo, hi, s in recs if lo <= x <= hi), {}).items())
        for swap in now:
            if swap in before:
                runs[swap][-1][1] = x
            else:
                runs.setdefault(swap, []).append([x, x])
        before = now
    rules = {}
    for (a, b), spans in runs.items():
        for lo, hi in spans:
            rules.setdefault((lo, hi), {})[a] = b
    return [(lo, hi, subs) for (lo, hi), subs in sorted(rules.items())], tags.pop()


def _instance(font: TTFont, w: float) -> TTFont:
    buf = io.BytesIO()
    font.save(buf)
    return instantiateVariableFont(TTFont(io.BytesIO(buf.getvalue())), {"wght": w}, overlap=OverlapMode.KEEP_AND_DONT_SET_FLAGS)


def _copy(font: TTFont) -> TTFont:
    buf = io.BytesIO()
    font.save(buf)
    return TTFont(io.BytesIO(buf.getvalue()))


def _anchors(st):
    """Every anchor of a mark, cursive or mark-to-ligature subtable."""
    if hasattr(st, "MarkArray"):
        yield from (r.MarkAnchor for r in st.MarkArray.MarkRecord)
    if hasattr(st, "BaseArray"):
        yield from (a for r in st.BaseArray.BaseRecord for a in r.BaseAnchor)
    if hasattr(st, "Mark2Array"):
        yield from (a for r in st.Mark2Array.Mark2Record for a in r.Mark2Anchor)
    if hasattr(st, "EntryExitRecord"):
        yield from (a for r in st.EntryExitRecord for a in (r.EntryAnchor, r.ExitAnchor))
    if hasattr(st, "LigatureArray"):
        yield from (a for lig in st.LigatureArray.LigatureAttach for comp in lig.ComponentRecord for a in comp.LigatureAnchor)


def _raise(font: TTFont, dy: int) -> None:
    """Every outline, top bearing and anchor up by dy, the advances as they were."""
    glyf = font["glyf"]
    for name in font.getGlyphOrder():
        g = glyf[name]
        if g.numberOfContours > 0:
            g.coordinates.translate((0, dy))
            g.recalcBounds(glyf)
    for name in font.getGlyphOrder():
        if glyf[name].isComposite():
            glyf[name].recalcBounds(glyf)
    if "vmtx" in font:
        for name, (adv, tsb) in list(font["vmtx"].metrics.items()):
            font["vmtx"].metrics[name] = (adv, tsb - dy)
    if "GPOS" in font:
        for lookup in font["GPOS"].table.LookupList.Lookup:
            for st in lookup.SubTable:
                for a in _anchors(getattr(st, "ExtSubTable", st)):
                    if a is not None:
                        a.YCoordinate += dy


def _lend(font: TTFont, lender: TTFont, suffix: str) -> None:
    """Copy every glyph the lender maps and the font does not, with its components, named as in the
    lender plus the suffix. Advances and top bearings come along; layout does not."""
    cmap = font.getBestCmap()
    give = sorted((u, n) for u, n in lender.getBestCmap().items() if u not in cmap)
    glyf, lglyf = font["glyf"], lender["glyf"]
    order = list(font.getGlyphOrder())
    names = {}

    def take(name: str) -> str:
        if name not in names:
            new = names[name] = f"{name}.{suffix}"
            g = lglyf[name]
            g.expand(lglyf)
            if g.isComposite():
                for c in g.components:
                    c.glyphName = take(c.glyphName)
            order.append(new)
            glyf.glyphs[new] = g
            font["hmtx"].metrics[new] = lender["hmtx"].metrics[name]
        return names[name]

    for u, name in give:
        new = take(name)
        for table in font["cmap"].tables:
            if table.isUnicode() and table.format != 14 and (u <= 0xFFFF or table.format in (12, 13)):
                table.cmap[u] = new
    glyf.glyphOrder = order
    font.setGlyphOrder(order)
    upm = font["head"].unitsPerEm
    for name, new in names.items():
        glyf[new].recalcBounds(glyf)
        if "vmtx" in font:
            # without the lender's own, the vertical origin is the CJK typo ascender, 0.88 em
            top = getattr(glyf[new], "yMax", 0)
            font["vmtx"].metrics[new] = lender["vmtx"].metrics[name] if "vmtx" in lender else (upm, round(0.88 * upm) - top)


def _growth(thin: TTFont, bold: TTFont) -> dict[str, float]:
    """How much each simple glyph's strokes thicken from Thin to Bold: the ink area gained over half
    the outline's length, which for a straight stroke is its gain in thickness."""
    out = {}
    for name in bold.getGlyphOrder():
        g = bold["glyf"][name]
        if g.isComposite() or g.numberOfContours <= 0:
            continue
        (a0, p0), (a1, p1) = (_area_length(f, name) for f in (thin, bold))
        if p0 + p1:
            out[name] = max(0.0, (a1 - a0) / ((p0 + p1) / 4))
    return out


def _area_length(font: TTFont, name: str) -> tuple[float, float]:
    from fontTools.pens.areaPen import AreaPen
    from fontTools.pens.perimeterPen import PerimeterPen

    glyf = font["glyf"]
    area, length = AreaPen(), PerimeterPen()
    glyf[name].draw(area, glyf)
    glyf[name].draw(length, glyf)
    return abs(area.value), length.value


def _black(thin: TTFont, bold: TTFont) -> tuple[TTFont, list[str]]:
    """Bold with each glyph thickened by BLACK_RATIO of its own growth from Thin, every advance kept,
    top bearings following the ink."""
    from build_world import embolden  # tools/ is on sys.path when build_cjk runs

    black = _copy(bold)
    glyf = black["glyf"]
    tops = {n: glyf[n].yMax for n in black.getGlyphOrder() if glyf[n].numberOfContours}
    strengths = {n: BLACK_RATIO * g for n, g in _growth(thin, bold).items()}
    limited = embolden(black, 0, fixed_advance=True, per_glyph=strengths)
    if "vmtx" in black:
        for n, top in tops.items():
            adv, tsb = black["vmtx"].metrics[n]
            black["vmtx"].metrics[n] = (adv, tsb + top - glyf[n].yMax)
    return black, limited


def assemble(region: str, chars: set[int]) -> tuple[Path, list[str]]:
    """The companion's source on Katagami's weight axis with `chars` and their layout, saved in
    build/cjk-src, and the sources it draws on."""
    src = SOURCES[region]
    path, flat = source_vf(region)
    font = TTFont(path)
    have = set(font.getBestCmap()) - flat
    _subset(font, chars & have, layout=True)
    rules, rule_feature = _take_rules(font)
    weights = masters(font)
    statics = {w: _instance(font, w) for w in weights}
    if src.get("raise"):
        for st in statics.values():
            _raise(st, src["raise"])
    used = [region]
    missing = chars - have
    for name in LENDERS[region]:
        lpath, lflat = source_vf(name)
        lender = TTFont(lpath)
        give = (missing & set(lender.getBestCmap())) - lflat
        if not give:
            continue
        _subset(lender, give, layout=False)
        _take_rules(lender)
        for w, st in statics.items():
            lent = _instance(lender, w)
            if SOURCES[name].get("raise"):
                _raise(lent, SOURCES[name]["raise"])
            _lend(st, lent, name.lower())
        missing -= give
        used.append(name)
        print(f"  {region}: {len(give)} characters from {SOURCES[name]['name']}", flush=True)
    statics[float(TOP)], limited = _black(statics[weights[0]], statics[weights[-1]])
    print(f"  {region}: masters at {', '.join(f'{w:g}' for w in weights)} and Black, Bold thickened by {BLACK_RATIO} of its growth; "
          f"{len(limited)} glyphs thicken less to keep a counter open; {len(missing)} characters no source draws",
          flush=True)
    pairs, to_design = _axis_map(font, weights)
    work = WORK / region
    work.mkdir(parents=True, exist_ok=True)
    doc = DesignSpaceDocument()
    doc.addAxisDescriptor(tag="wght", name="Weight", minimum=weights[0], default=weights[0], maximum=TOP, map=pairs)
    for w, st in statics.items():
        p = work / f"master-{w:g}.ttf"
        st.save(p)
        doc.addSourceDescriptor(path=str(p), designLocation={"Weight": w}, styleName=f"{w:g}")
    for w, style in STYLES.items():
        doc.addInstanceDescriptor(styleName=style, userLocation={"Weight": w})
    top_design = _design(font, weights[-1])
    for lo, hi, subs in rules:
        rule = RuleDescriptor(name=f"from {lo:g}")
        rule.conditionSets = [[{"name": "Weight", "minimum": weights[0] if lo <= _design(font, weights[0]) else to_design(lo),
                                "maximum": TOP if hi >= top_design else to_design(hi)}]]
        rule.subs = sorted(subs.items())
        doc.addRule(rule)
    doc.rulesProcessingLast = rule_feature == "rclt"
    vf, _, _ = build_variable(doc)
    if "MVAR" in vf:  # build_cjk sets the line, x-height and underline, and none of them varies with weight
        del vf["MVAR"]
    if "VVAR" in vf:
        # as in Noto's fonts, vertical metrics vary through gvar's phantom points alone; a VVAR would go
        # stale when build_cjk adds the Latin, which build_cjk rebuilds HVAR for
        del vf["VVAR"]
    if "BASE" not in vf:
        # the Plex fonts compile without one; Frex Sans GB's baselines (ideographic -120, character face
        # -80 to 840) hold for them, since they share its design and em box
        vf["BASE"] = TTFont(SOURCES["SC"]["vf"])["BASE"]
    out = work / f"Katagami{region}-source[wght].ttf"
    vf.save(out)
    print(f"  {region}: {out.relative_to(ROOT)}, {len(vf.getBestCmap())} characters, "
          f"{len(rules)} weight swaps", flush=True)
    return out, used


def credits(used: list[str]) -> tuple[str, str]:
    """The copyright line's credit for the sources, and their designers."""
    names = [SOURCES[r]["name"] for r in used]
    notices = ([FREX_NOTICE] if "SC" in used else []) + [IBM]
    if len(names) > 1:
        derived = ", ".join(names[:-1]) + " and " + names[-1]
    else:
        derived = names[0]
    designers = []
    for r in used:
        path, _ = source_vf(r)
        who = " ".join((TTFont(path, lazy=True)["name"].getDebugName(9) or "").split()).rstrip(";")
        designers.append(f"{SOURCES[r]['name']}: {who.removeprefix(SOURCES[r]['name'] + ': ')}")
    return f"Derived from {derived}. {'. '.join(notices)}.", "; ".join(designers)

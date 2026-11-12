"""Generate the specimen site's assets from the built fonts.

The site lives in its own repo, Katagami-Website, checked out next to this one
(or wherever KATAGAMI_SITE points). This writes into it:

    fonts/KatagamiSans.woff2 ...        each member's Latin, Greek and Cyrillic core
    fonts/KatagamiSans-Italic.woff2 ... each member's Italic (Latin, Greek and Cyrillic)
    fonts/KatagamiSans-thai.woff2 ...   one file per merged script, per member
    fonts/KatagamiSans-Italic-thai.woff2 ...  the same from the Italic
    fonts/KatagamiCJK{SC,TC,JP,KR}.woff2 and -Italic.woff2   the CJK companions
    fonts/first.js, first-rows.js, first-round.js, first-text.js, first-serif.js,
    first-features.js, kanji.js
                                    subsets of a member a page adds for its first paint
    fonts/katagami.css                  @font-face rules: each member is one family whose
                                    faces split by unicode-range, so a page downloads
                                    only the scripts it shows, in the roman or the Italic
    data.js     window.KERF: metrics, features, the hero's outlines and the Curves plate
    glyphs.js   each member's character table and the Unicode names, merged into window.KERF
    content/pages/*.json  a record per hand-written page, asset URLs stamped with hashes
    content/site.json  the numbers the header and footer print, and each asset's hash
    katagami-apply.js  its face table, between the generated-faces markers

Run after tools/build.sh, then commit and push Katagami-Website; Vercel deploys it.
After editing only a page fragment, `tools/build_site.py --pages` rewraps the pages.
After a change to the Curves plate's data, `tools/build_site.py --data` writes data.js and glyphs.js alone.
After a change to the download table's links, `tools/build_site.py --downloads` writes the zip and files.json alone.
The full build and --data stop before writing data.js when build/, where the hero and the Curves
plate read their glyphs, no longer draws them as fonts/ ships them.
"""

from __future__ import annotations

import functools
import hashlib
import html
import json
import math
import re
import subprocess
import time
import unicodedata
import zipfile
from pathlib import Path

import sys

import pathops
import ufoLib2
from fontTools import subset
from fontTools.misc.bezierTools import calcBounds, calcCubicBounds, calcCubicParameters, cubicPointAtT, quadraticPointAtT, solveCubic
from fontTools.misc.roundTools import otRound
from fontTools.pens.basePen import BasePen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from build_world import SCRIPTS  # noqa: E402
from kerf_build.cjk import latin_chars  # noqa: E402
from kerf_build.fontops import VERSION as _VERSION  # noqa: E402
from kerf_build.sitepath import PUBLIC, SITE, require_site  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONTS = {"sans": ROOT / "fonts/sans/KatagamiSans[wght].ttf", "round": ROOT / "fonts/round/KatagamiRound[wght].ttf",
         "text": ROOT / "fonts/text/KatagamiText[wght].ttf", "serif": ROOT / "fonts/serif/KatagamiSerif[wght].ttf",
         "mono": ROOT / "fonts/mono/KatagamiMono[wght].ttf"}
ITALICS = {key: path.with_name(path.name.replace("[wght]", "-Italic[wght]")) for key, path in FONTS.items()}
WOFF2 = {"sans": "KatagamiSans.woff2", "round": "KatagamiRound.woff2", "text": "KatagamiText.woff2",
         "serif": "KatagamiSerif.woff2", "mono": "KatagamiMono.woff2"}
WOFF2_ITALIC = {key: name.replace(".woff2", "-Italic.woff2") for key, name in WOFF2.items()}
VERSION = f"{_VERSION[0]}.{f'{_VERSION[1]:03d}'.rstrip('0') or '0'}"  # "1.0": 1.000 and 0.200 lose their trailing zeros but keep one digit
ZIP = f"Katagami-{VERSION}.zip"
SCRIPT_COUNT = 3 + len(SCRIPTS)  # Latin, Greek and Cyrillic drawn, the rest merged
OUTLINE_CHARS = {"K": "K", "a": "a", "t": "t", "g": "g", "m": "m", "i": "i"}
KERF_UFO = ROOT / "build/sans/KatagamiSans-Regular.ufo"
MONO_UFO = ROOT / "build/mono/KatagamiMono-Regular.ufo"
ROUND_UFO = ROOT / "build/round/KatagamiRound-Regular.ufo"
TEXT_UFO = ROOT / "build/text/KatagamiText-Regular.ufo"
SERIF_UFO = ROOT / "build/serif/KatagamiSerif-Regular.ufo"
INTER_UFO = ROOT / "build/ufo/Inter-Regular.ufo"
# the Curves plate draws and measures o and n in Inter and in each member, in this order
CURVE_SOURCES = {"inter": INTER_UFO, "sans": KERF_UFO, "round": ROUND_UFO, "text": TEXT_UFO, "serif": SERIF_UFO, "mono": MONO_UFO}
# Git ignores build/, so a release can change a glyph the site draws and leave build/ as it was.
# Before data.js is written, stale_masters compares these glyphs in every master of each member in
# build/ with the shipped font at the master's weight. DRIFT is how far an outline may lie from the
# font's, in font units. Fontmake's curve conversion allows 0.001 em (2.05 units), TrueType rounds
# each point to a whole unit, and in 1.2 each outline lies 0.1 to 2.2 units from the font's.
CHECKED = [*OUTLINE_CHARS.values(), "o", "n"]
MASTERS = {key: {"Thin": 100, "Regular": 400, **({"Bold": 700} if key == "mono" else {"Black": 900})} for key in FONTS}
DRIFT = 2.5
FAMILY = {"sans": "Katagami Sans", "round": "Katagami Round", "text": "Katagami Text", "serif": "Katagami Serif", "mono": "Katagami Mono"}
WEIGHTS = {"sans": "100 900", "round": "100 900", "text": "100 900", "serif": "100 900", "mono": "100 700"}
# Companion file -> the ranges it serves in every proportional family. Where two
# faces share a range the browser tries the one declared later first, so SC
# comes after TC: a character in both is drawn by SC, and TC draws the rest
# (traditional forms, bopomofo). TC's web file leaves out what SC already has.
HAN = [(0x2E80, 0x2FDF), (0x3000, 0x303F), (0x3200, 0x33FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
       (0xF900, 0xFAFF), (0xFF00, 0xFF60), (0xFFE0, 0xFFEF)]
CJK = {
    "KatagamiCJKTC": [*HAN, (0x3100, 0x312F), (0x31A0, 0x31BF)],
    "KatagamiCJKSC": HAN,
    "KatagamiCJKJP": [(0x3040, 0x30FF), (0x31F0, 0x31FF), (0xFF61, 0xFF9F)],
    "KatagamiCJKKR": [(0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7FF), (0xFFA0, 0xFFDC)],
}
FONT_URL = "https://katagami.kevinliu.studio/fonts/"
HERO = "Katagami"  # morphs Mono, Round, Sans, Text and Serif; all five share Inter's point structure
PAGES = {"page.html": "index.html", "about-page.html": "about.html", "map-page.html": "map.html", "convert-page.html": "convert.html",
         "glyphs-page.html": "glyphs.html", "features-page.html": "features.html", "faq-page.html": "faq.html",
         "download-page.html": "download.html"}  # hand-written fragment -> served page
# features a reader turns on or off; the rest shape scripts and work underneath
OPTIONAL = re.compile(r"^(cv\d\d|ss\d\d|calt|case|cpsp|dlig|frac|numr|dnom|ordn|pnum|tnum|salt|sinf|smcp|c2sc|subs|sups|zero|liga)$")
REPO = "https://github.com/Kevin-Liu-01/Katagami"


SCRIPT_OF = {u: name for name, ranges in SCRIPTS.items() for lo, hi in ranges for u in range(lo, hi + 1)}


def group(cp: int) -> str:
    if cp in SCRIPT_OF:
        return "scripts"
    if 0x2500 <= cp <= 0x259F:
        return "drawing"
    cat = unicodedata.category(chr(cp))
    return {"L": "letters", "N": "figures", "P": "punctuation", "S": "symbols", "M": "marks"}.get(cat[0], "other")


def feature_chars(font: TTFont, records: list, limit: int = 48) -> str:
    """The characters the single, alternate and ligature substitutions of all of
    a tag's records start from, in code point order: what turning it on changes.
    Latin, Greek and Cyrillic come alone when the tag changes any of them, since
    a merged script's record (Devanagari's ss01) would otherwise lead the sample."""
    lookups = font["GSUB"].table.LookupList.Lookup
    rev = {g: cp for cp, g in font.getBestCmap().items()}
    found = set()
    for li in {li for feature in records for li in feature.LookupListIndex}:
        lookup = lookups[li]
        for st in lookup.SubTable:
            kind = lookup.LookupType
            if kind == 7:
                kind, st = st.ExtensionLookupType, st.ExtSubTable
            keys = (st.mapping if kind == 1 else st.alternates if kind == 3 else st.ligatures if kind == 4 else {})
            found |= {rev[g] for g in keys if g in rev}
    found = {cp for cp in found if not unicodedata.category(chr(cp)).startswith(("C", "Z", "M"))}
    core = {cp for cp in found if cp not in SCRIPT_OF}
    return "".join(chr(cp) for cp in sorted(core or found))[:limit]


def features(font: TTFont) -> list[dict]:
    name = font["name"]
    records: dict[str, list] = {}
    for rec in font["GSUB"].table.FeatureList.FeatureRecord:
        records.setdefault(rec.FeatureTag, []).append(rec.Feature)
    out = []
    for tag, feats in records.items():
        label = ""
        params = feats[0].FeatureParams
        if params is not None:
            nid = getattr(params, "UINameID", None) or getattr(params, "FeatUILabelNameID", None)
            if nid:
                label = name.getDebugName(nid) or ""
        entry = {"tag": tag, "label": label}
        if OPTIONAL.match(tag):
            entry["chars"] = feature_chars(font, feats)
        out.append(entry)
    return out


def chars(font: TTFont) -> list[list]:
    hmtx = font["hmtx"]
    return [[cp, gname, hmtx[gname][0], group(cp)]
            for cp, gname in sorted(font.getBestCmap().items())
            if not unicodedata.category(chr(cp)).startswith(("C", "Z"))]


def metrics(font: TTFont) -> dict:
    os2, hhea, glyf, cmap = font["OS/2"], font["hhea"], font["glyf"], font.getBestCmap()
    def reach(ch: str, top: bool, default: int) -> int:
        """How high l reaches or how low p does at the default weight: the drawn ascender and descender."""
        if ord(ch) not in cmap:
            return default
        g = glyf[cmap[ord(ch)]]
        g.recalcBounds(glyf)
        return g.yMax if top else g.yMin
    return {"upm": font["head"].unitsPerEm, "ascender": hhea.ascent, "descender": hhea.descent,
            "capHeight": os2.sCapHeight, "xHeight": os2.sxHeight,
            "ascenderLine": reach("l", True, hhea.ascent), "descenderLine": reach("p", False, hhea.descent),
            "glyphs": len(font.getGlyphOrder()), "characters": len(font.getBestCmap()),
            "weights": [a.minValue for a in font["fvar"].axes] + [a.maxValue for a in font["fvar"].axes]}


TYPES = {"curve": "c", "line": "l", None: "o"}


def flatten(font, gname: str, xf=(1, 0, 0, 1, 0, 0)) -> list:
    """A glyph's contours with its components drawn in, in order, without
    changing the font: own contours first, then each component's."""
    g = font[gname]
    a, b, c, d, e, f = xf
    out = [[[round(a * p.x + c * p.y + e, 1), round(b * p.x + d * p.y + f, 1), TYPES.get(p.type, "l")]
             for p in cont.points] for cont in g.contours]
    for comp in g.components:
        A, B, C, D, E, F = comp.transformation
        out += flatten(font, comp.baseGlyph,
                       (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f))
    return out


def flat_plan(font, gname: str, offset: int = 0) -> list:
    """Katagami Round's rounded corners for the flattened glyph, contour indices shifted to match."""
    plans = font.lib.get("com.kerf.roundedCorners", {})
    g = font[gname]
    out = [(ci + offset, idx) for ci, idx in plans.get(gname, [])]
    n = offset + len(g.contours)
    for comp in g.components:
        out += flat_plan(font, comp.baseGlyph, n)
        n += len(flatten(font, comp.baseGlyph))
    return out


def flatten_marked(font, ref, gname: str, xf=(1, 0, 0, 1, 0, 0)) -> list:
    """flatten(), each contour paired with True when `ref`'s glyph of the same
    name has no such contour: the slabs Katagami Serif adds to Katagami Text."""
    g = font[gname]
    n = len(ref[gname].contours)
    a, b, c, d, e, f = xf
    out = [([[round(a * p.x + c * p.y + e, 1), round(b * p.x + d * p.y + f, 1), TYPES.get(p.type, "l")] for p in cont.points], k >= n)
           for k, cont in enumerate(g.contours)]
    for comp in g.components:
        A, B, C, D, E, F = comp.transformation
        out += flatten_marked(font, ref, comp.baseGlyph,
                              (a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D, a * E + c * F + e, b * E + d * F + f))
    return out


def weave(contours: list, marked: list, slabs: list) -> list:
    """Put `slabs` back between `contours` where `marked` had its slabs."""
    rest, extra = iter(contours), iter(slabs)
    return [next(extra) if slab else next(rest) for _, slab in marked]


def expand(contours: list, plan: list) -> list:
    """Split each planned corner into the four coincident points Katagami Round has there."""
    out = [list(c) for c in contours]
    for ci, idx in plan:
        c = out[ci]
        for i in sorted(idx, reverse=True):
            x, y, t = c[i]
            c[i:i + 1] = [[x, y, t], [x, y, "o"], [x, y, "o"], [x, y, "c"]]
    return out


def outlines() -> dict:
    kerf, mono, rnd, text, serif = (ufoLib2.Font.open(p) for p in (KERF_UFO, MONO_UFO, ROUND_UFO, TEXT_UFO, SERIF_UFO))
    shape = lambda o: [len(c) for c in o["contours"]]  # noqa: E731
    out = {}
    for ch, gname in OUTLINE_CHARS.items():
        out[ch] = {}
        if ch in HERO:
            # Katagami Round rounds its vertices, which adds points. Give Sans and
            # Mono the same corners at zero radius so all three still morph.
            plan = flat_plan(rnd, gname)
            sans_like = {"adv": kerf[gname].width, "contours": expand(flatten(kerf, gname), plan)}
            mono_like = {"adv": mono[gname].width, "contours": expand(flatten(mono, gname), plan)}
            rounded = {"adv": rnd[gname].width, "contours": flatten(rnd, gname)}
            # Mono's i is redrawn with a flag and a foot slab, so it cannot morph point
            # for point; that letter stays on the Sans outline toward the Mono end
            if shape(mono_like) != shape(sans_like):
                mono_like = sans_like
            assert shape(rounded) == shape(sans_like), f"{ch}: round and Katagami Sans outlines differ"
            # Serif is Text with slab rectangles added. The other four states carry
            # each slab at zero height on the edge it grows from, so it draws nothing
            # until the slider moves from Text toward Serif.
            marked = flatten_marked(serif, text, gname)
            serif_base = [c for c, slab in marked if not slab]
            # Serif's terminal facets each add a point (a foot) to Text's structure: lift them out
            # here and put them back into every state at the end, as a zero-length step at the
            # outer corner in the other four, so the facet grows from the corner toward Serif
            feet = facet_feet(serif, gname)
            for ci, k, _ in sorted(feet, reverse=True):
                serif_base[ci].pop(k)
            text_flat = flatten(text, gname)
            assert [len(c) for c in serif_base] == [len(c) for c in text_flat], f"{ch}: Serif and Text outlines differ"
            dx = serif_base[0][0][0] - text_flat[0][0][0]
            ys = [p[1] for c in serif_base for p in c]
            mid = (min(ys) + max(ys)) / 2
            slabs = [c for c, slab in marked if slab]
            flat = []
            for c in slabs:
                lo, hi = min(p[1] for p in c), max(p[1] for p in c)
                edge = lo if abs(lo - mid) > abs(hi - mid) else hi
                flat.append([[round(p[0] - dx, 1), edge, p[2]] for p in c])
            for key, o in (("hero", sans_like), ("mono", mono_like), ("round", rounded)):
                out[ch][key] = {"adv": o["adv"], "contours": weave(o["contours"], marked, flat)}
            out[ch]["text"] = {"adv": text[gname].width, "contours": weave(expand(text_flat, plan), marked, flat)}
            out[ch]["serif"] = {"adv": serif[gname].width, "contours": weave(expand(serif_base, plan), marked, slabs)}
            if feet:
                base_at = [w for w, (_, slab) in enumerate(marked) if not slab]  # base contour -> woven index
                own = flatten(serif, gname)
                for ci, k, prev in sorted(feet):
                    # k counts the feet before it; in Text's structure the foot comes before point k_text,
                    # and Round's corners before that point each grew by three
                    k_text = k - sum(1 for c2, k2, _ in feet if c2 == ci and k2 < k)
                    grown = 3 * sum(1 for pci, idx in plan if pci == ci for i in idx if i < k_text)
                    for key, state in out[ch].items():
                        c = state["contours"][base_at[ci]]
                        at = k + grown
                        if key == "serif":
                            c.insert(at, own[ci][k])
                        else:
                            x, y, _ = c[at - 1] if prev else c[at % len(c)]
                            c.insert(at, [x, y, "l"])
            assert len({tuple(len(c) for c in st["contours"]) for st in out[ch].values()}) == 1, f"{ch}: states differ in structure"
    return out


def facet_feet(font, gname: str) -> list:
    """The feet of Katagami Serif's terminal facets in a glyph's own contours, named by
    tools/build_sans.py: (contour, index, whether the outer corner is the point before it)."""
    return [(ci, k, p.name == "facet:prev") for ci, c in enumerate(font[gname].contours)
            for k, p in enumerate(c.points) if p.name in ("facet:prev", "facet:next")]


def segments(contour: list) -> list:
    """A flattened contour's segments, each its points from one on-curve point to the next."""
    s = next(i for i, p in enumerate(contour) if p[2] != "o")
    pts = contour[s:] + contour[:s]
    out, run = [], [tuple(pts[0][:2])]
    for x, y, t in pts[1:] + pts[:1]:
        run.append((x, y))
        if t != "o":
            assert len(run) in (2, 4), "the Curves plate reads lines and cubic curves only"
            out.append(run)
            run = [(x, y)]
    return out


def box(contour: list) -> tuple:
    """xMin, yMin, xMax, yMax of a contour's outline, its curves' extremes included."""
    rects = [calcCubicBounds(*s) if len(s) == 4 else calcBounds(s) for s in segments(contour)]
    return tuple(f(r[i] for r in rects) for i, f in ((0, min), (1, min), (2, max), (3, max)))


def crossings(contour: list, y: float) -> list:
    """The x of each point where a contour crosses the level line at height y, from left to right."""
    xs = []
    for s in segments(contour):
        if len(s) == 2:
            (x0, y0), (x1, y1) = s
            if min(y0, y1) <= y < max(y0, y1):
                xs.append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
            continue
        (ax, ay), (bx, by), (cx, cy), (dx, dy) = calcCubicParameters(*s)
        xs += [((ax * t + bx) * t + cx) * t + dx for t in solveCubic(ay, by, cy, dy - y) if 0 <= t < 1]
    return sorted(xs)


def superellipse_n(arc: list) -> float:
    """The exponent n of the superellipse x^n + y^n = 1 that fits a quarter arc in the unit square
    best, by least squares on the radius at 127 points along the arc."""
    pts = [cubicPointAtT(*arc, i / 128) for i in range(1, 128)]
    polar = [(math.hypot(x, y), math.atan2(y, x)) for x, y in pts]
    err = lambda n: sum((r - (abs(math.cos(a)) ** n + abs(math.sin(a)) ** n) ** (-1 / n)) ** 2 for r, a in polar)  # noqa: E731
    lo, hi, g = 1.0, 8.0, (math.sqrt(5) - 1) / 2
    for _ in range(60):
        m1, m2 = hi - g * (hi - lo), lo + g * (hi - lo)
        lo, hi = (lo, m2) if err(m1) < err(m2) else (m1, hi)
    return (lo + hi) / 2


def quarter(contour: list) -> dict:
    """A contour's top-right quarter arc: the handle fraction f, the superellipse exponent n that fits
    it, and its two handles once the arc is mapped into a unit square from (1, 0) to (0, 1)."""
    seg = max((s for s in segments(contour) if len(s) == 4), key=lambda s: s[0][0] + s[0][1] + s[3][0] + s[3][1])
    r, hr, ht, t = seg if seg[0][0] > seg[3][0] else seg[::-1]
    # k is the corner where the tangents at the right end r and the top end t meet
    (ax, ay), (bx, by) = (hr[0] - r[0], hr[1] - r[1]), (ht[0] - t[0], ht[1] - t[1])
    a = ((t[0] - r[0]) * by - (t[1] - r[1]) * bx) / (ax * by - ay * bx)
    k = (r[0] + a * ax, r[1] + a * ay)
    f = (math.dist(r, hr) / math.dist(r, k) + math.dist(t, ht) / math.dist(t, k)) / 2
    # c is the corner opposite k; the unit square runs from c to r along u and from c to t along v
    c = (r[0] + t[0] - k[0], r[1] + t[1] - k[1])
    (ux, uy), (vx, vy) = (r[0] - c[0], r[1] - c[1]), (t[0] - c[0], t[1] - c[1])
    det = ux * vy - uy * vx
    unit = [(((p[0] - c[0]) * vy - (p[1] - c[1]) * vx) / det, (ux * (p[1] - c[1]) - uy * (p[0] - c[0])) / det) for p in (r, hr, ht, t)]
    return {"f": round(f, 4), "n": round(superellipse_n(unit), 3), "arc": [[round(x, 4), round(y, 4)] for x, y in unit[1:3]]}


def merged(contours: list) -> list:
    """Flattened contours with their overlaps removed, so a drawing shows the outline a reader sees
    and none of the parts a glyph is built from (an n's arch over its stem, a separate serif)."""
    path = pathops.Path()
    pen = path.getPen()
    for c in contours:
        segs = segments(c)
        pen.moveTo(segs[0][0])
        for s in segs:
            pen.lineTo(s[1]) if len(s) == 2 else pen.curveTo(*s[1:])
        pen.closePath()
    path.simplify(fix_winding=True, keep_starting_points=True)
    rec, out = RecordingPen(), []
    path.draw(rec)
    for op, pts in rec.value:
        r = [[round(x, 1), round(y, 1)] for x, y in pts]
        if op == "moveTo":
            out.append([r[0] + ["l"]])
        elif op == "lineTo":
            out[-1].append(r[0] + ["l"])
        elif op == "curveTo":
            out[-1] += [r[0] + ["o"], r[1] + ["o"], r[2] + ["c"]]
        else:
            assert op == "closePath", f"the Curves plate draws lines and cubic curves only, not {op}"
            # the last segment closes on the first point, which the list already holds
            if len(out[-1]) > 1 and out[-1][-1][:2] == out[-1][0][:2]:
                out[-1].pop()
    return out


def curve_facts(font) -> dict:
    """The o and n of one source at Regular, drawn with their overlaps removed and measured
    on the source's own contours, in font units."""
    o, n = flatten(font, "o"), flatten(font, "n")
    size = lambda c: (lambda b: (b[2] - b[0]) * (b[3] - b[1]))(box(c))  # noqa: E731
    outer, counter = sorted(o, key=size, reverse=True)[:2]
    (ox0, oy0, ox1, oy1), (cx0, cy0, cx1, cy1) = box(outer), box(counter)
    xh = font.info.xHeight
    # n's left stem, across the level line a third of the way up the x-height
    edge = crossings(max(n, key=size), xh / 3)
    # the thinner of o's top and bottom strokes, and the thicker of its sides
    thin, thick = min(oy1 - cy1, cy0 - oy0), max(cx0 - ox0, ox1 - cx1)
    return {"o": {"adv": font["o"].width, "contours": merged(o)}, "n": {"adv": font["n"].width, "contours": merged(n)},
            "outer": quarter(outer), "counter": quarter(counter), "wh": round((ox1 - ox0) / (oy1 - oy0), 4),
            "stem": round(edge[1] - edge[0], 1), "thin": round(thin, 1), "thick": round(thick, 1), "contrast": round(thin / thick, 4),
            "over": [round(oy1 - xh, 1), round(-oy0, 1)], "xHeight": xh, "capHeight": font.info.capHeight}


def member_curves() -> dict:
    """The Curves plate: a circle's quarter arc, then Inter and each member at Regular. Mono adds its cell."""
    kappa = 4 / 3 * (math.sqrt(2) - 1)
    out = {"circle": {"f": round(kappa, 4), "n": round(superellipse_n([(1, 0), (1, kappa), (kappa, 1), (0, 1)]), 3),
                      "arc": [[1, round(kappa, 4)], [round(kappa, 4), 1]]}}
    for key, path in CURVE_SOURCES.items():
        font = ufoLib2.Font.open(path)
        out[key] = curve_facts(font)
        if key == "mono":
            out[key]["cell"] = font["zero"].width
    return out


class Pieces(BasePen):
    """An outline as straight pieces: its lines whole, its curves cut about every 4 units."""

    def __init__(self):
        super().__init__(None)
        self.out = []

    def _moveTo(self, p):
        self.start = self.cur = p

    def _lineTo(self, p):
        if p != self.cur:
            self.out.append((self.cur, p))
        self.cur = p

    def _curve(self, pts, at):
        n = max(1, math.ceil(sum(map(math.dist, pts, pts[1:])) / 4))
        run = [at(*pts, i / n) for i in range(n + 1)]
        self.out += [(p, q) for p, q in zip(run, run[1:]) if p != q]
        self.cur = pts[-1]

    def _curveToOne(self, a, b, c):
        self._curve((self.cur, a, b, c), cubicPointAtT)

    def _qCurveToOne(self, a, b):
        self._curve((self.cur, a, b), quadraticPointAtT)

    def _closePath(self):
        if self.cur != self.start:
            self.out.append((self.cur, self.start))


def pieces(glyph, glyph_set) -> list:
    """A glyph's outline with its components drawn in and its overlaps removed, as straight pieces."""
    path = pathops.Path()
    glyph.draw(path.getPen(glyphSet=glyph_set))
    path.simplify()
    pen = Pieces()
    path.draw(pen)
    return pen.out


def gap(m: tuple, piece: tuple) -> float:
    """The distance from the point m to a straight piece."""
    (x0, y0), (x1, y1) = piece
    dx, dy = x1 - x0, y1 - y0
    t = min(1, max(0, ((m[0] - x0) * dx + (m[1] - y0) * dy) / (dx * dx + dy * dy)))
    return math.hypot(m[0] - x0 - t * dx, m[1] - y0 - t * dy)


def drift(a: list, b: list) -> float:
    """How far outline a strays from outline b, both as pieces. It is 0 when the ends and middle of
    every piece of a lie within DRIFT of b; otherwise it is the distance of the furthest point that
    strays, measured on at most 100 of those points."""
    cell, cells = 16, {}
    for piece in b:
        (x0, y0), (x1, y1) = piece
        for i in range(math.floor((min(x0, x1) - DRIFT) / cell), math.floor((max(x0, x1) + DRIFT) / cell) + 1):
            for j in range(math.floor((min(y0, y1) - DRIFT) / cell), math.floor((max(y0, y1) + DRIFT) / cell) + 1):
                cells.setdefault((i, j), []).append(piece)
    # a piece within DRIFT of a point is filed under the point's own cell
    points = [m for p, q in a for m in (p, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))]
    far = [m for m in points if all(gap(m, s) > DRIFT for s in cells.get((math.floor(m[0] / cell), math.floor(m[1] / cell)), ()))]
    return max((min(gap(m, s) for s in b) for m in far[::len(far) // 100 + 1]), default=0)


def stale_masters() -> list[tuple]:
    """Each glyph in CHECKED that a master in build/ draws otherwise than the shipped font does at the
    master's weight, as (member, what differs): an outline more than DRIFT from the font's, or another advance."""
    stale = []
    for key, path in FONTS.items():
        font = TTFont(path)
        stem = path.name.removesuffix("[wght].ttf")
        for style, wght in MASTERS[key].items():
            ufo = ufoLib2.Font.open(ROOT / "build" / key / f"{stem}-{style}.ufo")
            shipped = font.getGlyphSet(location={"wght": wght})
            for gname in CHECKED:
                built, ships = pieces(ufo[gname], ufo), pieces(shipped[gname], shipped)
                far = max(drift(built, ships), drift(ships, built))
                adv = otRound(ufo[gname].width), otRound(shipped[gname].width)
                if far:
                    stale.append((key, f"{FAMILY[key]} {gname} at {wght}: the outline in build/ lies {far:.1f} units from the font's"))
                if adv[0] != adv[1]:
                    stale.append((key, f"{FAMILY[key]} {gname} at {wght}: the advance is {adv[0]} in build/ and {adv[1]} in the font"))
    return stale


def unicode_range(unicodes, avoid=frozenset()) -> str:
    """CSS unicode-range for a set of code points. Runs join across gaps that
    hold none of `avoid`, so the list stays short without claiming another
    face's characters."""
    runs = []
    for u in sorted(unicodes):
        if runs and all(g not in avoid for g in range(runs[-1][1] + 1, u)) and u - runs[-1][1] < 256:
            runs[-1][1] = u
        else:
            runs.append([u, u])
    return ",".join(f"U+{a:X}" if a == b else f"U+{a:X}-{b:X}" for a, b in runs)


def fresh(src: Path, out: Path) -> bool:
    """True when `out` was written after `src`, so a rerun can keep it."""
    return out.exists() and out.stat().st_mtime > src.stat().st_mtime


def woff2_slice(src: Path, unicodes, out: Path) -> None:
    if fresh(src, out):
        return
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.hinting = False
    font = TTFont(src)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes)
    sub.subset(font)
    font.flavor = "woff2"
    font.save(out)


def stamp(rel: str) -> str:
    return f"{rel}?v={hashlib.sha256((PUBLIC / rel).read_bytes()).hexdigest()[:10]}"


def web_fonts() -> list[list]:
    """Write every member's slices, roman and Italic, and the CJK companions'; return
    the faces as [family, file, weights, unicode-range, style] with stamped file names."""
    faces = []
    scripted = set(SCRIPT_OF)
    stamped = lambda name: stamp(f"fonts/{name}").removeprefix("fonts/")  # noqa: E731
    for key, path in FONTS.items():
        cmap = set(TTFont(path).getBestCmap())
        core = cmap - scripted
        stem = WOFF2[key].removesuffix(".woff2")
        woff2_slice(path, core, PUBLIC / "fonts" / WOFF2[key])
        faces.append([FAMILY[key], stamped(WOFF2[key]), WEIGHTS[key], unicode_range(core, avoid=scripted), "normal"])
        italic = ITALICS[key]
        if italic.exists():
            icore = set(TTFont(italic).getBestCmap()) - scripted
            woff2_slice(italic, icore, PUBLIC / "fonts" / WOFF2_ITALIC[key])
            faces.append([FAMILY[key], stamped(WOFF2_ITALIC[key]), WEIGHTS[key], unicode_range(icore, avoid=scripted), "italic"])
        for script, ranges in SCRIPTS.items():
            have = {u for lo, hi in ranges for u in range(lo, hi + 1)} & cmap
            if not have:
                continue
            name = f"{stem}-{script.lower()}.woff2"
            woff2_slice(path, have, PUBLIC / "fonts" / name)
            ur = unicode_range(have, avoid=cmap - have)
            faces.append([FAMILY[key], stamped(name), WEIGHTS[key], ur, "normal"])
            if italic.exists():
                iname = f"{stem}-Italic-{script.lower()}.woff2"
                woff2_slice(italic, have, PUBLIC / "fonts" / iname)
                faces.append([FAMILY[key], stamped(iname), WEIGHTS[key], ur, "italic"])
    latin = latin_chars()
    for name, ranges in CJK.items():
        src = ROOT / "fonts" / "cjk" / f"{name}[wght].ttf"
        if not src.exists():
            continue
        out = PUBLIC / "fonts" / f"{name}.woff2"
        # a companion's web file holds its CJK characters alone: the members set its Latin
        have = set(TTFont(src).getBestCmap()) - latin
        if name == "KatagamiCJKTC":
            have -= set(TTFont(src.with_name("KatagamiCJKSC[wght].ttf")).getBestCmap())
        woff2_slice(src, have, out)
        italic = src.with_name(f"{name}-Italic[wght].ttf")
        woff2_slice(italic, have, PUBLIC / "fonts" / f"{name}-Italic.woff2")
        css = ",".join(f"U+{a:X}-{b:X}" for a, b in ranges)
        for key in ("sans", "round", "text", "serif"):
            faces.append([FAMILY[key], stamped(f"{name}.woff2"), "100 900", css, "normal"])
            faces.append([FAMILY[key], stamped(f"{name}-Italic.woff2"), "100 900", css, "italic"])
    return faces


# The first-paint faces. Each is a small subset of a member that holds the characters a
# page shows before its fonts load. A script in the page's head adds them to the document's
# fonts from bytes it carries, and a face made from bytes is ready at once, so the first
# frame already sets that text in Katagami and no text waits or changes face. A face added
# by script is tried before the stylesheet's faces of its family, and it keeps setting its
# characters with the outlines and metrics of the full face, which a page fetches only for a
# character the subset lacks. A part of a page that needs the whole font, such as the type
# tester with its features, calls KatagamiFirst.release(family): the full face loads and the
# subsets step aside, and the full face sets the same text with the same outlines. first.js serves every page with Sans and Mono. names.js holds "Katagami Round
# Name", "Text Name" and "Serif Name", the members' names alone for the lists that set each
# name in its own face (the footer, the header's picker, the download table, the about page),
# which no full face replaces: the pages that show them first hold their first paint for it,
# and every other page loads it after it has painted. first-rows.js serves the member rows and the glyph tiles that set Round,
# Text and Serif. first-round.js, first-text.js and first-serif.js hold a member's Latin for the
# map page, which is set in Round, and for the library pages' specimens. first-features.js serves
# the feature cards with every feature.
# kanji.js holds 型紙 (pattern paper) alone, which it keeps for good: a page that shows only
# those two characters never fetches a CJK companion of megabytes, and a companion is a font
# of its own, so no text is shaped across it and a Latin face.
#
# ASCII and the few other characters the pages' first screens show: the non-breaking space,
# the copyright sign, the superscript two, the middle dot, the multiplication sign, é, ō,
# the dashes, the curly quotes, the ellipsis, the arrows and the minus sign
FIRST_LATIN = [(0x20, 0x7E), (0xA0, 0xA0), (0xA9, 0xA9), (0xB2, 0xB2), (0xB7, 0xB7), (0xD7, 0xD7), (0xE9, 0xE9),
               (0x14D, 0x14D), (0x2013, 0x2014), (0x2018, 0x201D), (0x2026, 0x2026), (0x2190, 0x2193), (0x2197, 0x2197),
               (0x2212, 0x2212)]
# the features that apply without a request, and tnum, which the site's figures ask for (tabular-nums)
FIRST_FEATURES = ["kern", "calt", "liga", "ccmp", "locl", "mark", "mkmk", "tnum"]
FIRST = {"first.js": [("latin", ["sans", "mono"])], "names.js": [("names", ["round", "text", "serif"])],
         "first-rows.js": [("rows", ["round", "text", "serif"])], "first-round.js": [("latin", ["round"])],
         "first-text.js": [("latin", ["text"])], "first-serif.js": [("latin", ["serif"])],
         "first-features.js": [("features", ["sans"])],
         "kanji.js": [("kanji", ["cjk"])]}
# every subset holds a 0: a ch unit is the width of 0 in the element's first available face
NAMES_TEXT = "Katagami Sans Round Text Serif Mono Italic 0"
KANJI_TEXT = "型紙"
# Adds the faces. KatagamiFirst.release(family) loads the full face and hands the member over
# to it; `keep` faces are never handed over.
FIRST_RUNTIME = r"""(function(){var K=window.KatagamiFirst;if(!K){K=window.KatagamiFirst={faces:[],
release:function(fam){var core=null;document.fonts.forEach(function(x){if(!core&&K.faces.indexOf(x)<0&&x.style=="normal"&&x.family.replace(/["']/g,"")==fam&&/^U\+0-/i.test(x.unicodeRange))core=x});
if(!core)return Promise.resolve();return core.load().then(function(){K.faces=K.faces.filter(function(f){if(f.family!=fam)return true;document.fonts.delete(f);return false})},function(){})}}}
K.done=K.done||{};K.add=K.add||function(fam,w,range,keep,b){try{var s=atob(b),u=new Uint8Array(s.length);for(var i=0;i<s.length;i++)u[i]=s.charCodeAt(i);
var f=new FontFace(fam,u.buffer,{weight:w,unicodeRange:range});document.fonts.add(f);if(!keep)K.faces.push(f)}catch(e){}};
"""


def rows_text(member: str) -> str:
    """The text the landing page sets in a member's own face above the fold: its row's name
    and sample line and its stop on the track, and the R the glyph tiles show."""
    page = (SITE / "page.html").read_text()
    row = re.search(rf'<button type="button" class="m-row"[^>]*data-v="{member}".*?</button>', page, re.S)
    found = re.findall(r'<span class="m-(?:name|sample)"[^>]*>(.*?)</span>', row.group(0)) if row else []
    stops = re.search(r'<span class="mt-names"[^>]*>(.*?)</span>\s*<span class="mt-bar"', page, re.S)
    if stops:
        found += [t for t in re.findall(r">([^<]+)<", stops.group(1)) if t.lower() == member]
    text = "".join(found).replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<") + "R0"
    return "".join(sorted(set(text)))


def features_text() -> str:
    """The text of /features at Katagami Sans as the build writes it: every card's samples,
    from the site's own renderer (public/render.js) run on data.js."""
    script = ("const vm=require('vm'),fs=require('fs'),p=require('path'),w={},c=vm.createContext({window:w});"
              "for(const f of ['data.js','hero.js','render.js'])vm.runInContext(fs.readFileSync(p.join(process.argv[1],f),'utf8'),c);"
              "process.stdout.write(w.KatagamiRender.features(w.KERF,'sans').replace(/<[^>]+>/g,'').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'\"').replace(/&amp;/g,'&'))")
    return subprocess.run(["node", "-e", script, str(PUBLIC)], capture_output=True, text=True, check=True).stdout


def exact_range(cps) -> str:
    runs = []
    for u in sorted(cps):
        if runs and u == runs[-1][1] + 1:
            runs[-1][1] = u
        else:
            runs.append([u, u])
    return ",".join(f"U+{a:X}" if a == b else f"U+{a:X}-{b:X}" for a, b in runs)


def subset_bytes(src: Path, have: set, features: list) -> bytes:
    import io
    font = TTFont(src)
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = features
    opts.name_IDs = []
    opts.notdef_outline = True
    opts.hinting = False
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=have)
    sub.subset(font)
    font.flavor = "woff2"
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def first_fonts() -> None:
    import base64
    latin = {u for lo, hi in FIRST_LATIN for u in range(lo, hi + 1)}
    sets = {"latin": latin, "names": {ord(c) for c in NAMES_TEXT},
            # the feature cards switch every feature on and off, so their subset keeps all of them
            "features": latin | {ord(c) for c in features_text()},
            "kanji": {ord(c) for c in KANJI_TEXT}}
    # SC draws a kanji it has, as katagami.css tries SC before TC, and TC the rest
    cjk = [ROOT / "fonts" / "cjk" / f"{n}[wght].ttf" for n in ("KatagamiCJKSC", "KatagamiCJKTC")]
    for name in [p.name for p in (PUBLIC / "fonts").glob("first*.css")] + ["kanji.css"]:
        (PUBLIC / "fonts" / name).unlink(missing_ok=True)
    for name, parts in FIRST.items():
        out = PUBLIC / "fonts" / name
        sources = [p for _, keys in parts for k in keys for p in (cjk if k == "cjk" else [FONTS[k]]) if p.exists()]
        key = hashlib.sha256(repr([(sorted(sets[kind]) if kind != "rows" else [rows_text(k) for k in keys], keys) for kind, keys in parts] + FIRST_FEATURES + [FIRST_RUNTIME]).encode()).hexdigest()[:12]
        if out.exists() and f"key {key}" in out.read_text()[:120] and all(fresh(p, out) for p in sources):
            continue
        calls = []
        for kind, k in ((kind, k) for kind, keys in parts for k in keys):
            left = {ord(c) for c in rows_text(k)} if kind == "rows" else set(sets[kind])
            for src in (cjk if k == "cjk" else [FONTS[k]]):
                have = left & set(TTFont(src).getBestCmap()) if src.exists() else set()
                if not have:
                    continue
                left -= have
                data = subset_bytes(src, have, ["*"] if kind == "features" else FIRST_FEATURES)
                family = "Katagami Sans" if k == "cjk" else FAMILY[k] + (" Name" if kind == "names" else "")
                keep = kind in ("names", "kanji")
                calls.append(f'K.add("{family}","{"100 900" if k == "cjk" else WEIGHTS[k]}","{exact_range(have)}",{str(keep).lower()},"{base64.b64encode(data).decode()}");')
                print(f"{name}: {family} {len(have)} characters, {len(data) / 1024:.1f} KB")
        out.write_text(f"/* key {key}: first-paint faces, generated by tools/build_site.py --first in the Katagami repo */\n"
                       + FIRST_RUNTIME + f'if(K.done["{name}"])return;K.done["{name}"]=1;\n' + "\n".join(calls) + "\n})();\n")


def stale_slices(faces: list[list]) -> list[str]:
    """Delete the font files in the site's fonts/ that no face uses any more."""
    used = {f[1].split("?")[0] for f in faces}
    gone = []
    for p in sorted((PUBLIC / "fonts").glob("*.woff2")):
        if p.name not in used:
            p.unlink()
            gone.append(p.name)
    return gone


def cjk_line() -> str:
    """The descriptors that set a CJK companion on Katagami Sans's line (its typo
    metrics), whatever line metrics the companion's own tables give."""
    sans = TTFont(FONTS["sans"])
    os2, upm = sans["OS/2"], sans["head"].unitsPerEm
    pct = lambda v: f"{100 * v / upm:.10g}%"  # noqa: E731
    return (f"ascent-override:{pct(os2.sTypoAscender)};descent-override:{pct(-os2.sTypoDescender)};"
            f"line-gap-override:{pct(os2.sTypoLineGap)};")


def write_faces(faces: list[list]) -> None:
    line = cjk_line()
    rule = lambda fam, file, w, ur, style, base: (f'@font-face{{font-family:"{fam}";src:url("{base}{file}") format("woff2");'  # noqa: E731
                                                  f"font-weight:{w};font-style:{style};font-display:swap;"
                                                  f"{line if file.startswith('KatagamiCJK') else ''}unicode-range:{ur}}}")
    (PUBLIC / "fonts" / "katagami.css").write_text("/* Katagami web fonts, generated by tools/build_site.py in the Katagami repo */\n"
                                              + "\n".join(rule(*f, "") for f in faces) + "\n")
    apply = PUBLIC / "katagami-apply.js"
    text = apply.read_text()
    start, end = "/* generated faces: start */", "/* generated faces: end */"
    if start in text:
        a, b = text.index(start) + len(start), text.index(end)
        text = text[:a] + "\n  const FACES = " + json.dumps(faces, separators=(",", ":")) + ";\n  " + text[b:]
        apply.write_text(text)


def git(*args: str) -> str:
    """One git command in the fonts repository: its output, or "" when git fails."""
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def same_fonts(ref: str) -> bool:
    """True when the fonts and the license at `ref` are the ones in this checkout."""
    return subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", ref, "--", "fonts", "OFL.txt"], capture_output=True).returncode == 0


def published_commit() -> str:
    """The newest commit on origin/main that this checkout builds on, which GitHub can show; "" when git cannot say."""
    return git("merge-base", "HEAD", "origin/main")


def fonts_ref() -> str:
    """The ref the download table links each font file at: the release tag, or the published commit, when it
    holds this checkout's fonts, so a link never serves a file other than the one the table describes."""
    tag = f"v{VERSION}"
    if git("rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}") and same_fonts(tag):
        return tag
    base = published_commit()
    if base and same_fonts(base):
        return base
    print(f"files.json links to main, because neither {tag} nor a commit on origin/main holds this checkout's fonts. "
          "Push the fonts, then run tools/build_site.py --downloads again.", file=sys.stderr)
    return "main"


def site_facts() -> dict:
    """Numbers the header and footer print, read from the built data and the repository."""
    facts = {"version": VERSION, "characters": 0, "glyphs": 0, "features": 0, "people": "", "commit": "", "date": time.strftime("%Y-%m-%d"), "zip": ""}
    zip_path = PUBLIC / "download" / ZIP
    if zip_path.exists():
        facts["zip"] = f"{zip_path.stat().st_size / 1048576:.1f} MB"  # the unit the download page uses
    data_js = PUBLIC / "data.js"
    if data_js.exists():
        text = data_js.read_text()
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        facts["characters"] = data["sans"]["metrics"]["characters"]
        # every glyph in the build: the five romans and their Italics
        facts["glyphs"] = sum(data[k]["metrics"]["glyphs"] + data[k].get("italic", {}).get("metrics", {}).get("glyphs", 0) for k in FONTS if k in data)
        facts["features"] = len({f["tag"] for f in data["sans"]["features"] if OPTIONAL.match(f["tag"])})
    map_json = PUBLIC / "map" / "map.json"
    if map_json.exists():
        facts["people"] = json.loads(map_json.read_text()).get("stats", {}).get("sans", {}).get("people", "")
    base = published_commit()
    facts["commit"] = git("rev-parse", "--short", base) if base else ""
    if base and base != git("rev-parse", "HEAD"):
        print(f"The footer links to {facts['commit']}, the newest commit on origin/main under this checkout. HEAD is not on origin/main.", file=sys.stderr)
    return facts


SITE_URL = "https://katagami.kevinliu.studio"
# each served page: (title, description, Open Graph image, schema.org page type)
PAGE_META = {
    "index.html": ("Katagami: a free variable type family in five members",
                   f"Katagami is a free, open-source type family with five members: Sans, Round, Text, Serif and Mono. Each member is a variable roman and Italic. Weights run from {WEIGHTS['sans'].replace(' ', ' to ')} in Sans, Round, Text and Serif and from {WEIGHTS['mono'].replace(' ', ' to ')} in Mono. The family sets {SCRIPT_COUNT} scripts plus Chinese, Japanese and Korean.",
                   "home", "WebPage"),
    "glyphs.html": ("Katagami glyphs: every character in five fonts",
                    "Search every character in Katagami Sans, Round, Text, Serif and Mono by character, Unicode name or code point, and see each glyph on its metric lines.",
                    "glyphs", "CollectionPage"),
    "features.html": ("Katagami OpenType features: figures, small capitals and alternates",
                      "This page shows every OpenType feature in Katagami off and on, from tabular figures and fractions to small capitals, stylistic sets and code ligatures. Each feature comes with the CSS that turns it on.",
                      "features", "WebPage"),
    "map.html": ("Where Katagami writes: a world map of languages in letters",
                 "The map draws the world in letters. Each land cell shows a letter of the language spoken there in Katagami, which sets the main language of every place on the map.",
                 "map", "WebPage"),
    "convert.html": ("Font-ify: see any website in Katagami",
                     "Type an address and see the page with every font swapped for Katagami, side by side with the original. The rewrite runs in your browser.",
                     "convert", "WebPage"),
    "about.html": ("About Katagami",
                   "This page explains why Katagami was made, where its name comes from and how katagami paper stencils are cut. It also lists the credits.",
                   "about", "AboutPage"),
    "faq.html": ("Katagami FAQ: license, web use, languages and features",
                 "These answers cover commercial use under the SIL Open Font License, which member to use, web fonts, OpenType features, languages and how the fonts are made.",
                 "faq", "FAQPage"),
    "download.html": ("Download Katagami: free variable fonts under the OFL",
                      f"Katagami {VERSION} has five variable TrueType fonts and four CJK companions, each with an Italic. The page has install steps for macOS, Windows and Linux and a stylesheet for the web.",
                      "download", "WebPage"),
}
MEMBER_PATHS = {"sans": "/katagami-sans", "round": "/katagami-round", "text": "/katagami-text", "serif": "/katagami-serif", "mono": "/katagami-mono"}


def asset_stamps() -> dict:
    assets = ["data.js", "glyphs.js", "hero.js", "render.js", "fontify.js", "katagami-apply.js", "katagami-paper.js", *(f"fonts/{name}" for name in FIRST), "site.css", "site.js", "library.css", "glyph-wall.js", "glyph-wall.css", "map/map.json", "download/files.json",
              "fonts/katagami.css", *(f"fonts/{name}" for name in (*WOFF2.values(), *WOFF2_ITALIC.values()))]
    return {rel: hashlib.sha256((PUBLIC / rel).read_bytes()).hexdigest()[:10] for rel in assets if (PUBLIC / rel).exists()}


def base_graph(facts: dict) -> list:
    """The site, its author and the type family: the nodes every page carries."""
    person = {"@type": "Person", "@id": f"{SITE_URL}/#kevin", "name": "Kevin Liu", "url": "https://kevinliu.studio",
              "sameAs": ["https://github.com/Kevin-Liu-01"]}
    site = {"@type": "WebSite", "@id": f"{SITE_URL}/#website", "url": f"{SITE_URL}/", "name": "Katagami", "inLanguage": "en",
            "publisher": {"@id": person["@id"]},
            "potentialAction": {"@type": "SearchAction",
                                "target": {"@type": "EntryPoint", "urlTemplate": f"{SITE_URL}/glyphs?q={{search_term_string}}"},
                                "query-input": "required name=search_term_string"}}
    family = {"@type": ["CreativeWork", "SoftwareApplication"], "@id": f"{SITE_URL}/#katagami", "name": "Katagami",
              "alternateName": ["Katagami type family", "型紙"], "additionalType": "https://www.wikidata.org/wiki/Q17451",
              "genre": "Typeface", "url": f"{SITE_URL}/",
              "description": PAGE_META["index.html"][1], "author": {"@id": person["@id"]}, "creator": {"@id": person["@id"]},
              "license": "https://openfontlicense.org/", "isAccessibleForFree": True, "softwareVersion": VERSION,
              "dateCreated": "2026-10-07", "dateModified": fonts_date(), "applicationCategory": "DesignApplication",
              "operatingSystem": "macOS, Windows, Linux, Web", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
              "downloadUrl": f"{SITE_URL}/download/{ZIP}", "sameAs": [REPO],
              "keywords": "free font, variable font, open source font, OFL font, sans serif, serif, monospace font, multilingual font",
              "hasPart": [{"@type": "CreativeWork", "name": FAMILY[k], "url": f"{SITE_URL}{MEMBER_PATHS[k]}"} for k in MEMBER_PATHS]}
    return [site, person, family]


def page_graph(meta: dict, facts: dict, crumbs: list | None = None, extra: list | None = None) -> list:
    """base_graph with the page itself, its breadcrumb trail and any page-specific nodes."""
    url = SITE_URL + meta["path"]
    page = {"@type": meta.get("schema", "WebPage"), "@id": f"{url}#page", "url": url, "name": meta["title"],
            "description": meta["description"], "inLanguage": "en", "isPartOf": {"@id": f"{SITE_URL}/#website"},
            "about": {"@id": f"{SITE_URL}/#katagami"}, "dateModified": facts["date"],
            "primaryImageOfPage": f"{SITE_URL}/og/{meta.get('image', 'home')}.png"}
    graph = [*base_graph(facts), page]
    if meta["path"] == "/":
        # the home page names the organization and its logo for search results
        graph.append({"@type": "Organization", "@id": f"{SITE_URL}/#organization", "name": "Katagami", "url": f"{SITE_URL}/",
                      "logo": f"{SITE_URL}/apple-touch-icon.png"})
    if crumbs:
        trail = [("Katagami", "/"), *crumbs]
        graph.append({"@type": "BreadcrumbList", "@id": f"{url}#crumbs", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": SITE_URL + href} for i, (name, href) in enumerate(trail)]})
        page["breadcrumb"] = {"@id": f"{url}#crumbs"}
    if extra:
        if meta.get("schema") == "FAQPage":
            page["mainEntity"] = extra
        else:
            graph += extra
    return graph


def record(page: str, meta: dict, stamps: dict) -> dict:
    """A page fragment as the Next app's record: its metadata and structured
    data, the tags from its head, the body between the header and the footer,
    and what follows the footer, with every asset URL stamped by its hash."""
    page = re.sub(r"<title>.*?</title>\n?", "", page, count=1, flags=re.S)
    page = re.sub(r'<meta name="description"[^>]*>\n?', "", page, count=1)
    for rel, digest in stamps.items():
        page = page.replace(f'"{rel}"', f'"/{rel}?v={digest}"').replace(f'"/{rel}"', f'"/{rel}?v={digest}"')
    head, _, rest = page.partition("<!-- site:nav -->")
    main, _, tail = rest.partition("<!-- site:footer -->")
    return {"path": meta["path"], "title": meta["title"], "description": meta["description"], "image": meta.get("image", "home"),
            "schema": meta.get("schema", "WebPage"), "ogType": meta.get("og_type", "website"), "graph": meta["graph"],
            "head": head.strip(), "main": main.strip(), "tail": tail.strip()}


STAMP = re.compile(r"\?v=[0-9a-f]{10}")  # an asset's content hash in its address


@functools.lru_cache(maxsize=None)
def fonts_date() -> str:
    """The day the committed fonts last changed, for the family's dateModified; today when git cannot say."""
    try:
        day = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%cs", "--", "fonts"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        day = ""
    return day or time.strftime("%Y-%m-%d")


def page_date(rec: dict) -> str:
    """The dateModified of a record's own page node, or "" when it has none."""
    return next((node.get("dateModified", "") for node in rec.get("graph", []) if str(node.get("@id", "")).endswith("#page")), "")


def content_key(rec: dict) -> str:
    """What a page says, without the hashes in its asset addresses: two records with one key are the same page."""
    return STAMP.sub("?v=", json.dumps([rec.get(k) for k in ("title", "description", "head", "main", "tail")], ensure_ascii=False))


def record_date(here: str) -> str:
    """The day the page at `here` last changed, read from its record; today for a page with no record yet."""
    out = SITE / "content" / "pages" / (("index" if here == "/" else here.strip("/")) + ".json")
    return (page_date(json.loads(out.read_text())) if out.exists() else "") or time.strftime("%Y-%m-%d")


def emit(here: str, page: str, meta: dict, facts: dict, stamps: dict) -> None:
    """Write one page as a record under content/pages/."""
    out = SITE / "content" / "pages" / (("index" if here == "/" else here.strip("/")) + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    new = record(page, meta, stamps)
    if out.exists():
        old = json.loads(out.read_text())
        if page_date(old) and content_key(old) == content_key(new):
            for node in new["graph"]:
                if str(node.get("@id", "")).endswith("#page"):
                    node["dateModified"] = page_date(old)  # the page says what it said, so it keeps its date
    out.write_text(json.dumps(new, ensure_ascii=False, separators=(",", ":")))


def write_site_facts(facts: dict, stamps: dict) -> None:
    """The numbers the Next app's header and footer print, with the asset hashes."""
    (SITE / "content").mkdir(exist_ok=True)
    (SITE / "content" / "site.json").write_text(json.dumps({**facts, "stamps": stamps}, ensure_ascii=False, indent=1))


def faq_entities(fragment: str) -> list:
    """The questions and answers of the FAQ page, as schema.org Question nodes. Tags are
    dropped and character references decoded, so a code sample reads as it does on the page."""
    text = lambda s: html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()  # noqa: E731
    out = []
    for m in re.finditer(r'<details class="q"[^>]*>.*?<h2>(.*?)</h2>.*?<div class="a">(.*?)</div>\s*</details>', fragment, re.S):
        out.append({"@type": "Question", "name": text(m.group(1)), "acceptedAnswer": {"@type": "Answer", "text": text(m.group(2))}})
    return out


def write_pages() -> None:
    stamps = asset_stamps()
    facts = site_facts()
    for source, target in PAGES.items():
        if not (SITE / source).exists():
            continue
        page = (SITE / source).read_text()
        here = "/" + target.removesuffix(".html").replace("index", "")
        title, description, image, schema = PAGE_META[target]
        meta = {"path": here, "title": title, "description": description, "image": image, "schema": schema}
        extra = faq_entities(page) if target == "faq.html" else None
        crumbs = None if here == "/" else [(title.split(":")[0], here)]
        meta["graph"] = page_graph(meta, facts, crumbs, extra)
        emit(here, page, meta, facts, stamps)
    write_site_facts(facts, stamps)


CJK_FILES = [ROOT / "fonts" / "cjk" / f"{name}{style}[wght].ttf" for name in CJK for style in ("", "-Italic")]


def write_downloads() -> None:
    """The zip of the five members and the four CJK companions, roman and Italic, and
    the license, and files.json, which the download page lists: every font file
    with its size and a link. An older version's zip is removed."""
    out = PUBLIC / "download"
    out.mkdir(exist_ok=True)
    for old in out.glob("Katagami-*.zip"):
        if old.name != ZIP:
            old.unlink()
    zpath = out / ZIP
    keys = ("sans", "round", "text", "serif", "mono")
    fonts = [path for key in keys for path in (FONTS[key], ITALICS[key]) if path.exists()]
    cjk_files = [path for path in CJK_FILES if path.exists()]
    folder = f"Katagami-{VERSION}"
    if not all(fresh(path, zpath) for path in (*fonts, *cjk_files)):
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            # fixed timestamps, so the same fonts make the same zip
            for arc, src in [*((f"{folder}/{path.name}", path) for path in fonts),
                             *((f"{folder}/cjk/{path.name}", path) for path in cjk_files),
                             (f"{folder}/OFL.txt", ROOT / "OFL.txt")]:
                info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, src.read_bytes())
    ref = fonts_ref()
    raw = lambda path: f"{REPO}/raw/{ref}/{path.relative_to(ROOT).as_posix().replace('[', '%5B').replace(']', '%5D')}"  # noqa: E731
    entry = lambda key, path, style: {"key": key, "family": FAMILY[key], "style": style, "file": path.name,  # noqa: E731
                                      "weights": WEIGHTS[key].replace(" ", " to "), "glyphs": len(TTFont(path).getGlyphOrder()),
                                      "bytes": path.stat().st_size, "url": raw(path)}
    files = [entry(key, FONTS[key], "Roman") for key in keys]
    italics = [entry(key, ITALICS[key], "Italic") for key in keys if ITALICS[key].exists()]
    cjk = [{"family": f"Katagami CJK {path.stem[11:13]}", "style": "Italic" if "-Italic" in path.name else "Roman",
            "file": path.name, "bytes": path.stat().st_size, "url": raw(path)} for path in cjk_files]
    with zipfile.ZipFile(zpath) as z:
        listing = [i.filename for i in z.infolist()]
    (out / "files.json").write_text(json.dumps({"version": VERSION, "zip": {"file": zpath.name, "bytes": zpath.stat().st_size, "files": listing},
                                                "members": files, "italics": italics, "cjk": cjk}, separators=(",", ":")))


def site_data() -> dict:
    """window.KERF: each member's metrics, characters and features, the hero's outlines and the Curves plate."""
    data = {"version": VERSION, "names": {}}
    for key, path in FONTS.items():
        font = TTFont(path)
        data[key] = {"metrics": metrics(font), "chars": chars(font), "features": features(font)}
        for cp, *_ in data[key]["chars"]:
            data["names"][cp] = unicodedata.name(chr(cp), "").title()
        if ITALICS[key].exists():
            # the Italic's metrics, and its advance where it differs from the roman's
            ifont = TTFont(ITALICS[key])
            roman = {c[0]: c[2] for c in data[key]["chars"]}
            ihmtx, icmap = ifont["hmtx"], ifont.getBestCmap()
            adv = {cp: ihmtx[g][0] for cp, g in icmap.items() if cp in roman and ihmtx[g][0] != roman[cp]}
            data[key]["italic"] = {"metrics": metrics(ifont), "adv": adv}
    data["mono"]["metrics"]["cell"] = TTFont(FONTS["mono"])["hmtx"]["zero"][0]
    data["outlines"] = outlines()
    data["curves"] = member_curves()
    return data


# glyphs.js puts its tables into window.KERF as it runs: each member's characters, the
# Unicode names and the Italic's advances. A member that shares Sans's characters
# carries only its own advances, and this rebuilds its table from Sans's.
TABLES_JS = """(function(){var T=__TABLES__,D=window.KERF||(window.KERF={});D.names=T.names;
for(var k in T.members){var m=T.members[k],o=D[k]||(D[k]={});
o.chars=m.chars||T.members[m.like].chars.map(function(c,i){return[c[0],c[1],m.adv[i],c[3]]});
if(m.italic)(o.italic||(o.italic={})).adv=m.italic}
D.tables=true;document.dispatchEvent(new Event("katagami:tables"))})();
"""


def cmap_runs(chars: list, groups: list) -> dict:
    """A member's characters as runs, small enough for data.js: the gap before each run of
    consecutive code points and its length, then each run of one group and its length."""
    runs, kinds, end = [], [], 0
    for cp, _, _, group in chars:
        if runs and cp == end:
            runs[-1] += 1
        else:
            runs += [cp - end, 1]
        end = cp + 1
        if kinds and kinds[-2] == groups.index(group):
            kinds[-1] += 1
        else:
            kinds += [groups.index(group), 1]
    return {"runs": runs, "kinds": kinds}


def split_data(data: dict) -> tuple[dict, dict]:
    """data.js keeps what a page draws from at once: the metrics, the features, the hero's
    outlines, the Curves plate, each member's characters as runs and its ASCII advances, so
    the glyph wall can set its rows and its ruler before the tables arrive. glyphs.js holds
    the character tables and the names, which the inspector, the filters' counts and
    search need."""
    core = {k: v for k, v in data.items() if k not in FONTS and k != "names"}
    members = {}
    base = data["sans"]["chars"]
    groups = sorted({c[3] for k in FONTS if k in data for c in data[k]["chars"]})
    core["cmap"] = {"groups": groups}
    for key in FONTS:
        if key not in data:
            continue
        m = data[key]
        core[key] = {"metrics": m["metrics"], "features": m["features"]}
        if "italic" in m:
            core[key]["italic"] = {"metrics": m["italic"]["metrics"]}
        chars = m["chars"]
        same = key != "sans" and len(chars) == len(base) and all(c[0] == b[0] and c[1] == b[1] and c[3] == b[3] for c, b in zip(chars, base))
        core["cmap"][key] = "sans" if same else cmap_runs(chars, groups)
        adv = {c[0]: c[2] for c in chars if c[0] < 0x7F}
        core[key]["ascii"] = [adv.get(cp) for cp in range(0x20, 0x7F)]
        entry = {"like": "sans", "adv": [c[2] for c in chars]} if same else {"chars": chars}
        if "italic" in m:
            entry["italic"] = m["italic"]["adv"]
        members[key] = entry
    return core, {"names": data["names"], "members": members}


def write_data() -> None:
    stale = stale_masters()
    if stale:
        members = [key for key in FONTS if key in {k for k, _ in stale}]
        sys.exit("build/ no longer draws what fonts/ ships, and the site reads these glyphs from build/:\n  "
                 + "\n  ".join(line for _, line in stale) + "\nRebuild build/ ("
                 + ", ".join(f"tools/build.sh {key}-roman" for key in members) + "), then run tools/build_site.py again.")
    print(f"build/ draws {' '.join(CHECKED)} as fonts/ ships them, in every master of every member")
    core, tables = split_data(site_data())
    (PUBLIC / "data.js").write_text("window.KERF = " + json.dumps(core, separators=(",", ":")) + ";\n")
    (PUBLIC / "glyphs.js").write_text(TABLES_JS.replace("__TABLES__", json.dumps(tables, separators=(",", ":"))))


def main() -> None:
    (PUBLIC / "fonts").mkdir(parents=True, exist_ok=True)
    faces = web_fonts()
    write_faces(faces)
    first_fonts()
    for name in stale_slices(faces):
        print(f"removed stale fonts/{name}")
    write_downloads()
    write_data()

    write_pages()
    for p in sorted(PUBLIC.rglob("*")):
        rel = p.relative_to(PUBLIC)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            print(f"{p.stat().st_size / 1024:8.1f} KB  {rel}")


if __name__ == "__main__":
    require_site()
    # --pages rewraps the hand-written pages only, for a change to their markup;
    # --data writes data.js and glyphs.js alone and leaves the web fonts, downloads and pages as they are
    # --first writes the first-paint faces alone
    # --downloads writes the zip and files.json alone
    write_pages() if "--pages" in sys.argv else write_data() if "--data" in sys.argv else first_fonts() if "--first" in sys.argv else write_downloads() if "--downloads" in sys.argv else main()

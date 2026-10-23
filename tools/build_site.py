"""Generate the specimen site's assets from the built fonts.

The site lives in its own repo, Katagami-Website, checked out next to this one
(or wherever KATAGAMI_SITE points). This writes into it:

    fonts/KatagamiSans.woff2 ...        each member's Latin, Greek and Cyrillic core
    fonts/KatagamiSans-Italic.woff2 ... each member's Italic (Latin, Greek and Cyrillic)
    fonts/KatagamiSans-thai.woff2 ...   one file per merged script, per member
    fonts/KatagamiCJK{SC,JP,KR}.woff2   the CJK companions
    fonts/katagami.css                  @font-face rules: each member is one family whose
                                    faces split by unicode-range, so a page downloads
                                    only the scripts it shows; the merged scripts and
                                    CJK are declared for italic too, so italic text in
                                    them sets the upright letters
    data.js     window.KERF: metrics, character tables, features, outlines
    index.html  page.html wrapped in a document, asset URLs stamped with hashes
    katagami-apply.js  its face table, between the generated-faces markers

Run after tools/build.sh, then commit and push Katagami-Website; Vercel deploys it.
After editing only a page fragment, `tools/build_site.py --pages` rewraps the pages.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import unicodedata
import zipfile
from pathlib import Path

import sys

import ufoLib2
from fontTools import subset
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from build_world import SCRIPTS  # noqa: E402
from kerf_build.fontops import VERSION as _VERSION  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("KATAGAMI_SITE", ROOT.parent / "Katagami-Website"))
# a site checkout that is a Next app serves its files from public/ and renders
# its pages from the JSON records in content/
NEXT = (SITE / "next.config.ts").exists()
PUBLIC = SITE / "public" if NEXT else SITE
FONTS = {"sans": ROOT / "fonts/sans/KatagamiSans[wght].ttf", "round": ROOT / "fonts/round/KatagamiRound[wght].ttf",
         "text": ROOT / "fonts/text/KatagamiText[wght].ttf", "serif": ROOT / "fonts/serif/KatagamiSerif[wght].ttf",
         "mono": ROOT / "fonts/mono/KatagamiMono[wght].ttf"}
ITALICS = {key: path.with_name(path.name.replace("[wght]", "-Italic[wght]")) for key, path in FONTS.items()}
WOFF2 = {"sans": "KatagamiSans.woff2", "round": "KatagamiRound.woff2", "text": "KatagamiText.woff2",
         "serif": "KatagamiSerif.woff2", "mono": "KatagamiMono.woff2"}
WOFF2_ITALIC = {key: name.replace(".woff2", "-Italic.woff2") for key, name in WOFF2.items()}
VERSION = f"{_VERSION[0]}.{_VERSION[1]:03d}".rstrip("0").rstrip(".")  # "0.2"
ZIP = f"Katagami-{VERSION}.zip"
SCRIPT_COUNT = 3 + len(SCRIPTS)  # Latin, Greek and Cyrillic drawn, the rest merged
OUTLINE_CHARS = {"K": "K", "a": "a", "t": "t", "g": "g", "m": "m", "i": "i"}
COMPARE = "on"  # the Curves plate draws these in Sans, Round and Text
KERF_UFO = ROOT / "build/sans/KatagamiSans-Regular.ufo"
MONO_UFO = ROOT / "build/mono/KatagamiMono-Regular.ufo"
ROUND_UFO = ROOT / "build/round/KatagamiRound-Regular.ufo"
TEXT_UFO = ROOT / "build/text/KatagamiText-Regular.ufo"
SERIF_UFO = ROOT / "build/serif/KatagamiSerif-Regular.ufo"
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
MARK = ('<svg class="mark" viewBox="0 0 100 100" aria-hidden="true"><path d="M0 0 L31 0 L31 100 L0 100 Z"/>'
        '<path d="M38 0 L100 0 L100 30 L38 50 Z"/><path d="M38 50 L100 70 L100 100 L38 100 Z"/></svg>')
SPARKLES = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M15.98 1.804a1 1 0 0 0-1.96 0l-.24 1.192a1 1 0 0 1-.784.785l-1.192.238a1 1 0 0 0 0 1.962l1.192.238a1 1 0 0 1 .785.785l.238 1.192a1 1 0 0 0 1.962 0l.238-1.192a1 1 0 0 1 .785-.785l1.192-.238a1 1 0 0 0 0-1.962l-1.192-.238a1 1 0 0 1-.785-.785l-.238-1.192ZM6.949 5.684a1 1 0 0 0-1.898 0l-.683 2.051a1 1 0 0 1-.633.633l-2.051.683a1 1 0 0 0 0 1.898l2.051.684a1 1 0 0 1 .633.632l.683 2.051a1 1 0 0 0 1.898 0l.683-2.051a1 1 0 0 1 .633-.633l2.051-.683a1 1 0 0 0 0-1.898l-2.051-.683a1 1 0 0 1-.633-.633L6.95 5.684ZM13.949 13.684a1 1 0 0 0-1.898 0l-.184.551a1 1 0 0 1-.632.633l-.551.183a1 1 0 0 0 0 1.898l.551.183a1 1 0 0 1 .633.633l.183.551a1 1 0 0 0 1.898 0l.184-.551a1 1 0 0 1 .632-.633l.551-.183a1 1 0 0 0 0-1.898l-.551-.184a1 1 0 0 1-.633-.632l-.183-.551Z"/></svg>')
SEARCH = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path fill-rule="evenodd" clip-rule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"/></svg>')
TRAY = ('<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10.75 2.75a.75.75 0 0 0-1.5 0v8.614L6.295 8.235a.75.75 0 1 0-1.09 1.03l4.25 4.5a.75.75 0 0 0 1.09 0l4.25-4.5a.75.75 0 0 0-1.09-1.03l-2.955 3.129V2.75Z"/>'
        '<path d="M3.5 12.75a.75.75 0 0 0-1.5 0v2.5A2.75 2.75 0 0 0 4.75 18h10.5A2.75 2.75 0 0 0 18 15.25v-2.5a.75.75 0 0 0-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5Z"/></svg>')
GITHUB = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>')
LINKS = [("/glyphs", "Glyphs"), ("/features", "Features"), ("/map", "Map"), ("/about", "About"), ("/faq", "FAQ")]


SCRIPT_OF = {u: name for name, ranges in SCRIPTS.items() for lo, hi in ranges for u in range(lo, hi + 1)}


def group(cp: int) -> str:
    if cp in SCRIPT_OF:
        return "scripts"
    if 0x2500 <= cp <= 0x259F:
        return "drawing"
    cat = unicodedata.category(chr(cp))
    return {"L": "letters", "N": "figures", "P": "punctuation", "S": "symbols", "M": "marks"}.get(cat[0], "other")


def feature_chars(font: TTFont, feature, limit: int = 48) -> str:
    """The characters a feature's single, alternate and ligature substitutions
    start from, in code point order: what turning it on changes."""
    lookups = font["GSUB"].table.LookupList.Lookup
    rev = {g: cp for cp, g in font.getBestCmap().items()}
    found = set()
    for li in feature.LookupListIndex:
        lookup = lookups[li]
        for st in lookup.SubTable:
            kind = lookup.LookupType
            if kind == 7:
                kind, st = st.ExtensionLookupType, st.ExtSubTable
            keys = (st.mapping if kind == 1 else st.alternates if kind == 3 else st.ligatures if kind == 4 else {})
            found |= {rev[g] for g in keys if g in rev}
    return "".join(chr(cp) for cp in sorted(found) if not unicodedata.category(chr(cp)).startswith(("C", "Z", "M")))[:limit]


def features(font: TTFont) -> list[dict]:
    name = font["name"]
    out, seen = [], set()
    for rec in font["GSUB"].table.FeatureList.FeatureRecord:
        tag = rec.FeatureTag
        if tag in seen:
            continue
        seen.add(tag)
        label = ""
        params = rec.Feature.FeatureParams
        if params is not None:
            nid = getattr(params, "UINameID", None) or getattr(params, "FeatUILabelNameID", None)
            if nid:
                label = name.getDebugName(nid) or ""
        entry = {"tag": tag, "label": label}
        if OPTIONAL.match(tag):
            entry["chars"] = feature_chars(font, rec.Feature)
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
    return out


def member_outlines() -> dict:
    """The COMPARE letters at Regular in Sans, Round and Text."""
    fonts = {k: ufoLib2.Font.open(p) for k, p in (("sans", KERF_UFO), ("round", ROUND_UFO), ("text", TEXT_UFO))}
    return {ch: {k: {"adv": f[ch].width, "contours": flatten(f, ch)} for k, f in fonts.items()} for ch in COMPARE}


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
    """Write every member's slices, its Italic and the CJK companions; return the
    faces as [family, file, weights, unicode-range, style] with stamped file names.

    The Italics carry Latin, Greek and Cyrillic. Each merged script's slice and
    each CJK companion is declared a second time with font-style: italic, so
    italic text in those scripts sets the upright letters instead of falling to
    another family or being slanted by the browser."""
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
                faces.append([FAMILY[key], stamped(name), WEIGHTS[key], ur, "italic"])
    for name, ranges in CJK.items():
        src = ROOT / "fonts" / "cjk" / f"{name}[wght].ttf"
        if not src.exists():
            continue
        out = PUBLIC / "fonts" / f"{name}.woff2"
        if name == "KatagamiCJKTC":
            sc = set(TTFont(src.with_name("KatagamiCJKSC[wght].ttf")).getBestCmap())
            woff2_slice(src, set(TTFont(src).getBestCmap()) - sc, out)
        elif not fresh(src, out):
            font = TTFont(src)
            font.flavor = "woff2"
            font.save(out)
        css = ",".join(f"U+{a:X}-{b:X}" for a, b in ranges)
        for key in ("sans", "round", "text", "serif"):
            for style in ("normal", "italic"):
                faces.append([FAMILY[key], stamped(f"{name}.woff2"), "100 900", css, style])
    return faces


def stale_slices(faces: list[list]) -> list[str]:
    """Delete the font files in the site's fonts/ that no face uses any more."""
    used = {f[1].split("?")[0] for f in faces}
    gone = []
    for p in sorted((PUBLIC / "fonts").glob("*.woff2")):
        if p.name not in used:
            p.unlink()
            gone.append(p.name)
    return gone


def write_faces(faces: list[list]) -> None:
    rule = lambda fam, file, w, ur, style, base: (f'@font-face{{font-family:"{fam}";src:url("{base}{file}") format("woff2");'  # noqa: E731
                                                  f"font-weight:{w};font-style:{style};font-display:swap;unicode-range:{ur}}}")
    (PUBLIC / "fonts" / "katagami.css").write_text("/* Katagami web fonts, generated by tools/build_site.py in the Katagami repo */\n"
                                              + "\n".join(rule(*f, "") for f in faces) + "\n")
    apply = PUBLIC / "katagami-apply.js"
    text = apply.read_text()
    start, end = "/* generated faces: start */", "/* generated faces: end */"
    if start in text:
        a, b = text.index(start) + len(start), text.index(end)
        text = text[:a] + "\n  const FACES = " + json.dumps(faces, separators=(",", ":")) + ";\n  " + text[b:]
        apply.write_text(text)


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
    try:
        facts["commit"] = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    return facts


def nav_html(here: str, facts: dict) -> str:
    """The header every page shares, with the current page marked."""
    cur = lambda href: ' aria-current="page"' if href == here else ""  # noqa: E731
    links = "".join(f'<a href="{h}"{cur(h)}>{t}</a>' for h, t in LINKS)
    hints = {"/glyphs": f"{facts['characters']:,} characters", "/features": f"{facts['features']} features",
             "/map": f"{facts['people']}% of people" if facts["people"] else "", "/about": "Why I made it", "/faq": "",
             "/convert": "Any site in Katagami", "/download": f"v{VERSION} under the OFL"}
    sheet = "".join(f'<a href="{h}"{cur(h)}>{t}<span>{hints.get(h, "")}</span></a>'
                    for h, t in [*LINKS, ("/convert", "Font-ify"), ("/download", "Download")])
    keys = ("sans", "round", "text", "serif", "mono")
    picks = "".join(f'<button type="button" data-member="{k}" aria-pressed="{str(k == "sans").lower()}"><b style="font-family:\'{FAMILY[k]}\'">{FAMILY[k]}</b><span>{"100 to 700" if k == "mono" else "100 to 900"}</span></button>' for k in keys)
    menu_members = "".join(f'<button type="button" data-member="{k}" aria-pressed="{str(k == "sans").lower()}">{FAMILY[k].split()[1]}</button>' for k in keys)
    modes = '<button type="button" data-mode="human" aria-pressed="true">Human</button><button type="button" data-mode="machine" aria-pressed="false">Machine</button>'
    return f"""<header class="top">
  <div class="wrap">
    <a class="brand" href="/">{MARK}<b>Katagami</b><span>v{VERSION}</span></a>
    <nav aria-label="Pages">
      <div class="links">{links}</div>
      <button type="button" class="find" data-cmdk aria-label="Search pages, glyphs and actions" aria-keyshortcuts="Meta+K Control+K">{SEARCH}<span>Search</span><kbd>⌘K</kbd></button>
      <details class="pick">
        <summary aria-label="Set the whole site in a member"><b>Aa</b><span>Sans</span></summary>
        <div class="pick-menu" role="group" aria-label="Member">{picks}</div>
      </details>
      <div class="seg mode" role="group" aria-label="View">{modes}</div>
      <a class="pill fontify" href="/convert"{cur("/convert")}>{SPARKLES}<span>Font-ify</span></a>
      <a class="pill dl" href="/download"{cur("/download")}>{TRAY}<span>Download</span></a>
      <a class="gh" href="{REPO}" target="_blank" rel="noopener" aria-label="Katagami on GitHub">{GITHUB}</a>
      <details class="menu">
        <summary aria-label="Menu"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="shut" d="M4 7h16M4 12h16M4 17h16"/><path class="open" d="M6 6l12 12M18 6L6 18"/></svg></summary>
        <div class="sheet-menu"><div class="menu-tools"><div class="seg mode" role="group" aria-label="View">{modes}</div><div class="seg menu-members" role="group" aria-label="Member">{menu_members}</div></div>{sheet}<a href="{REPO}" target="_blank" rel="noopener">GitHub<span>Source and issues</span></a></div>
      </details>
    </nav>
  </div>
</header>"""


def footer_html(facts: dict) -> str:
    """The footer every page shares: how to use the fonts, the page index, the
    name as a live specimen, and the build, the author and the theme."""
    weights = {"mono": "100 to 700"}
    members = "".join(f'<a href="{MEMBER_PATHS[k]}" style="font-family:\'{FAMILY[k]}\'">{FAMILY[k]}<small>{weights.get(k, "100 to 900")}</small></a>'
                      for k in ("sans", "round", "text", "serif", "mono"))
    hints = {"/glyphs": f"{facts['characters']:,} characters", "/features": f"{facts['features']} features",
             "/map": f"{facts['people']}% of people" if facts["people"] else "", "/convert": "Any site in Katagami"}
    explore = "".join(f'<a href="{h}">{t}<small>{hints[h]}</small></a>' for h, t in
                      (("/glyphs", "Glyphs"), ("/features", "Features"), ("/map", "Map"), ("/convert", "Font-ify")))
    commit = f'<a href="{REPO}/commit/{facts["commit"]}">{facts["commit"]}</a>' if facts["commit"] else ""
    css = f"{SITE_URL}/fonts/katagami.css"
    seg = "".join(f'<button type="button" data-k="{i}" aria-pressed="{str(k == "sans").lower()}">{FAMILY[k].split()[1]}</button>'
                  for i, k in enumerate(("sans", "round", "text", "serif", "mono")))
    return f"""<footer class="site">
  <div class="wrap">
    <section class="f-use" aria-label="Use Katagami">
      <div class="f-say">
        <h2>Katagami is free for any project</h2>
        <p>The SIL Open Font License 1.1 lets you use, change and ship the fonts in any product, paid or free.</p>
      </div>
      <div class="f-acts">
        <a class="f-dl" href="/download">{TRAY}<span>Download v{VERSION}</span><small>{facts["zip"]}</small></a>
        <div class="f-css"><code>&lt;link rel="stylesheet" href="{css}"&gt;</code><button type="button" data-copy='<link rel="stylesheet" href="{css}">'>Copy</button></div>
      </div>
    </section>
    <div class="f-grid">
      <nav class="f-col f-members" aria-label="Members"><h3>Members</h3>{members}</nav>
      <nav class="f-col f-hinted" aria-label="Explore"><h3>Explore</h3>{explore}</nav>
      <nav class="f-col" aria-label="Project"><h3>Project</h3><a href="/about">About</a><a href="/faq">FAQ</a><a href="/download">Download</a><a href="/library">Library</a><a href="{REPO}">GitHub</a><a href="{REPO}/blob/main/OFL.txt">License</a></nav>
      <div class="f-col f-build"><h3>This build</h3><p>Version {VERSION}</p><p>{facts["glyphs"]:,} glyphs</p><p>Built {facts["date"]}</p>{commit}</div>
    </div>
    <div class="f-type">
      <div class="f-controls">
        <div class="seg" role="group" aria-label="Member">{seg}</div>
        <label class="f-weight">Weight <input type="range" min="100" max="900" step="1" value="800"><output>800</output></label>
      </div>
      <div class="f-word" aria-hidden="true"><b>Katagami</b></div>
    </div>
    <div class="f-bar">
      <p>Made by <a href="https://kevinliu.studio">Kevin Liu</a></p>
      <div class="seg f-theme" role="group" aria-label="Theme"><button type="button" data-theme-set="auto">Auto</button><button type="button" data-theme-set="light">Light</button><button type="button" data-theme-set="dark">Dark</button></div>
      <button type="button" class="f-top">Back to top</button>
    </div>
  </div>
</footer>"""


SITE_URL = "https://katagami.kevinliu.studio"
# each served page: (title, description, Open Graph image, schema.org page type)
PAGE_META = {
    "index.html": ("Katagami: a free variable type family in five members",
                   f"Katagami is a free, open-source type family with five members: Sans, Round, Text, Serif and Mono. Each member is a variable roman and Italic with weights from 100 to 900, and the family sets {SCRIPT_COUNT} scripts plus Chinese, Japanese and Korean.",
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
                      f"Katagami {VERSION} has five variable TrueType fonts, each with an Italic, and four CJK companions. The page has install steps for macOS, Windows and Linux and a stylesheet for the web.",
                      "download", "WebPage"),
}
MEMBER_PATHS = {"sans": "/katagami-sans", "round": "/katagami-round", "text": "/katagami-text", "serif": "/katagami-serif", "mono": "/katagami-mono"}


def asset_stamps() -> dict:
    assets = ["data.js", "katagami-apply.js", "site.css", "site.js", "library.css", "glyph-wall.js", "glyph-wall.css", "map/map.json", "download/files.json",
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
              "dateCreated": "2026-10-07", "dateModified": facts["date"], "applicationCategory": "DesignApplication",
              "operatingSystem": "macOS, Windows, Linux, Web", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
              "downloadUrl": f"{SITE_URL}/download/{ZIP}", "sameAs": [REPO],
              "keywords": "free font, variable font, open source font, OFL font, sans serif, serif, monospace font, multilingual font",
              "hasPart": [{"@type": "CreativeWork", "name": FAMILY[k], "url": f"{SITE_URL}{MEMBER_PATHS[k]}"} for k in MEMBER_PATHS]}
    return [site, person, family]


def head_html(meta: dict, stamps: dict) -> str:
    """The head of a page: title, description, canonical address, social cards,
    its Markdown twin and its structured data."""
    esc = lambda t: t.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")  # noqa: E731
    url = SITE_URL + meta["path"]
    image = f"{SITE_URL}/og/{meta.get('image', 'home')}.png"
    graph = json.dumps({"@context": "https://schema.org", "@graph": meta["graph"]}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    md = meta["path"].rstrip("/") + ".md" if meta["path"] != "/" else "/index.md"
    return "".join([
        '<meta charset="utf-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n',
        # the theme the footer's switch saved, set before the first paint
        '<script>try{var t=localStorage.getItem("katagami-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t;if(localStorage.getItem("katagami-mode")==="machine")document.documentElement.dataset.mode="machine"}catch(e){}</script>\n',
        f"<title>{esc(meta['title'])}</title>\n",
        f'<meta name="description" content="{esc(meta["description"])}">\n',
        f'<link rel="canonical" href="{url}">\n',
        '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">\n',
        '<meta name="author" content="Kevin Liu">\n',
        '<meta name="theme-color" content="#f1f2ef" media="(prefers-color-scheme: light)">\n',
        '<meta name="theme-color" content="#0e0f10" media="(prefers-color-scheme: dark)">\n',
        '<meta property="og:site_name" content="Katagami">\n',
        f'<meta property="og:type" content="{meta.get("og_type", "website")}">\n',
        f'<meta property="og:title" content="{esc(meta["title"])}">\n',
        f'<meta property="og:description" content="{esc(meta["description"])}">\n',
        f'<meta property="og:url" content="{url}">\n',
        f'<meta property="og:image" content="{image}">\n',
        '<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n',
        f'<meta property="og:image:alt" content="{esc(meta["title"])}">\n',
        '<meta name="twitter:card" content="summary_large_image">\n',
        f'<meta name="twitter:title" content="{esc(meta["title"])}">\n',
        f'<meta name="twitter:description" content="{esc(meta["description"])}">\n',
        f'<meta name="twitter:image" content="{image}">\n',
        f'<link rel="alternate" type="text/markdown" href="{md}" title="This page in Markdown">\n',
        '<link rel="alternate" type="text/plain" href="/llms.txt" title="llms.txt">\n',
        '<link rel="sitemap" type="application/xml" href="/sitemap.xml">\n',
        '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n',
        '<link rel="icon" href="/favicon.png" type="image/png" sizes="64x64">\n',
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n',
        '<link rel="manifest" href="/site.webmanifest">\n',
        f'<link rel="preload" href="/fonts/KatagamiSans.woff2?v={stamps.get("fonts/KatagamiSans.woff2", "")}" as="font" type="font/woff2" crossorigin>\n',
        f'<link rel="stylesheet" href="/site.css?v={stamps.get("site.css", "")}">\n',
        f'<script type="application/ld+json">{graph}</script>\n',
    ])


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


def wrap(page: str, here: str, meta: dict, facts: dict, stamps: dict) -> str:
    """A page fragment as a whole document: the shared head, header and footer,
    with every asset URL stamped by its content hash, so a changed file gets a
    new URL and the cache headers in vercel.json never pair a new page with old data."""
    page = re.sub(r"<title>.*?</title>\n?", "", page, count=1, flags=re.S)
    page = re.sub(r'<meta name="description"[^>]*>\n?', "", page, count=1)
    page = page.replace("<!-- site:nav -->", nav_html(here, facts)).replace("<!-- site:footer -->", footer_html(facts))
    for rel, digest in stamps.items():
        page = page.replace(f'"{rel}"', f'"{rel}?v={digest}"').replace(f'"/{rel}"', f'"/{rel}?v={digest}"')
    return ('<!doctype html>\n<html lang="en">\n<head>\n' + head_html(meta, stamps) + "</head>\n<body>\n" + page
            + f'\n<script src="/site.js?v={stamps.get("site.js", "")}" defer></script>\n</body>\n</html>\n')


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


def emit(here: str, page: str, meta: dict, facts: dict, stamps: dict) -> None:
    """Write one page: an HTML document beside the others for the static site, a
    record under content/pages/ for the Next app."""
    if NEXT:
        out = SITE / "content" / "pages" / (("index" if here == "/" else here.strip("/")) + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record(page, meta, stamps), ensure_ascii=False, separators=(",", ":")))
        return
    out = SITE / (("index" if here == "/" else here.strip("/")) + ".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(wrap(page, here, meta, facts, stamps))


def write_site_facts(facts: dict, stamps: dict) -> None:
    """The numbers the Next app's header and footer print, with the asset hashes."""
    if NEXT:
        (SITE / "content").mkdir(exist_ok=True)
        (SITE / "content" / "site.json").write_text(json.dumps({**facts, "stamps": stamps}, ensure_ascii=False, indent=1))


def faq_entities(fragment: str) -> list:
    """The questions and answers of the FAQ page, as schema.org Question nodes."""
    out = []
    for m in re.finditer(r'<details class="q"[^>]*>.*?<h2>(.*?)</h2>.*?<div class="a">(.*?)</div>\s*</details>', fragment, re.S):
        answer = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        out.append({"@type": "Question", "name": m.group(1), "acceptedAnswer": {"@type": "Answer", "text": answer}})
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


CJK_FILES = [ROOT / "fonts" / "cjk" / f"{name}[wght].ttf" for name in CJK]


def write_downloads() -> None:
    """The zip of the five members, roman and Italic, the four CJK companions and
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
    raw = lambda path: f"{REPO}/raw/main/{path.relative_to(ROOT).as_posix().replace('[', '%5B').replace(']', '%5D')}"  # noqa: E731
    entry = lambda key, path, style: {"key": key, "family": FAMILY[key], "style": style, "file": path.name,  # noqa: E731
                                      "weights": WEIGHTS[key].replace(" ", " to "), "glyphs": len(TTFont(path).getGlyphOrder()),
                                      "bytes": path.stat().st_size, "url": raw(path)}
    files = [entry(key, FONTS[key], "Roman") for key in keys]
    italics = [entry(key, ITALICS[key], "Italic") for key in keys if ITALICS[key].exists()]
    cjk = [{"family": f"Katagami CJK {path.stem[11:13]}", "file": path.name, "bytes": path.stat().st_size, "url": raw(path)}
           for path in cjk_files]
    with zipfile.ZipFile(zpath) as z:
        listing = [i.filename for i in z.infolist()]
    (out / "files.json").write_text(json.dumps({"version": VERSION, "zip": {"file": zpath.name, "bytes": zpath.stat().st_size, "files": listing},
                                                "members": files, "italics": italics, "cjk": cjk}, separators=(",", ":")))


def main() -> None:
    (PUBLIC / "fonts").mkdir(parents=True, exist_ok=True)
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
    faces = web_fonts()
    write_faces(faces)
    for name in stale_slices(faces):
        print(f"removed stale fonts/{name}")
    data["mono"]["metrics"]["cell"] = TTFont(FONTS["mono"])["hmtx"]["zero"][0]
    write_downloads()
    data["outlines"] = outlines()
    data["members"] = member_outlines()
    (PUBLIC / "data.js").write_text("window.KERF = " + json.dumps(data, separators=(",", ":")) + ";\n")

    write_pages()
    for p in sorted(PUBLIC.rglob("*")):
        rel = p.relative_to(PUBLIC)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            print(f"{p.stat().st_size / 1024:8.1f} KB  {rel}")


if __name__ == "__main__":
    # --pages rewraps the hand-written pages only, for a change to their markup
    write_pages() if "--pages" in sys.argv else main()

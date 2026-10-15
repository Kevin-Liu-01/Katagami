"""Generate the specimen site's assets from the built fonts.

The site lives in its own repo, Katagami-Website, checked out next to this one
(or wherever KATAGAMI_SITE points). This writes into it:

    fonts/KatagamiSans.woff2 ...        each member's Latin, Greek and Cyrillic core
    fonts/KatagamiSans-thai.woff2 ...   one file per merged script, per member
    fonts/KatagamiCJK{SC,JP,KR}.woff2   the CJK companions
    fonts/katagami.css                  @font-face rules: each member is one family whose
                                    faces split by unicode-range, so a page downloads
                                    only the scripts it shows
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

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("KATAGAMI_SITE", ROOT.parent / "Katagami-Website"))
FONTS = {"sans": ROOT / "fonts/sans/KatagamiSans[wght].ttf", "round": ROOT / "fonts/round/KatagamiRound[wght].ttf",
         "text": ROOT / "fonts/text/KatagamiText[wght].ttf", "serif": ROOT / "fonts/serif/KatagamiSerif[wght].ttf",
         "mono": ROOT / "fonts/mono/KatagamiMono[wght].ttf"}
WOFF2 = {"sans": "KatagamiSans.woff2", "round": "KatagamiRound.woff2", "text": "KatagamiText.woff2",
         "serif": "KatagamiSerif.woff2", "mono": "KatagamiMono.woff2"}
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
    os2, hhea = font["OS/2"], font["hhea"]
    return {"upm": font["head"].unitsPerEm, "ascender": hhea.ascent, "descender": hhea.descent,
            "capHeight": os2.sCapHeight, "xHeight": os2.sxHeight,
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
    return f"{rel}?v={hashlib.sha256((SITE / rel).read_bytes()).hexdigest()[:10]}"


def web_fonts() -> list[list]:
    """Write every member's slices and the CJK companions; return the faces
    as [family, file, weights, unicode-range] with stamped file names."""
    faces = []
    scripted = set(SCRIPT_OF)
    for key, path in FONTS.items():
        cmap = set(TTFont(path).getBestCmap())
        core = cmap - scripted
        stem = WOFF2[key].removesuffix(".woff2")
        woff2_slice(path, core, SITE / "fonts" / WOFF2[key])
        faces.append([FAMILY[key], stamp(f"fonts/{WOFF2[key]}").removeprefix("fonts/"), WEIGHTS[key],
                      unicode_range(core, avoid=scripted)])
        for script, ranges in SCRIPTS.items():
            have = {u for lo, hi in ranges for u in range(lo, hi + 1)} & cmap
            if not have:
                continue
            name = f"{stem}-{script.lower()}.woff2"
            woff2_slice(path, have, SITE / "fonts" / name)
            faces.append([FAMILY[key], stamp(f"fonts/{name}").removeprefix("fonts/"), WEIGHTS[key],
                          unicode_range(have, avoid=cmap - have)])
    for name, ranges in CJK.items():
        src = ROOT / "fonts" / "cjk" / f"{name}[wght].ttf"
        if not src.exists():
            continue
        out = SITE / "fonts" / f"{name}.woff2"
        if name == "KatagamiCJKTC":
            sc = set(TTFont(src.with_name("KatagamiCJKSC[wght].ttf")).getBestCmap())
            woff2_slice(src, set(TTFont(src).getBestCmap()) - sc, out)
        elif not fresh(src, out):
            font = TTFont(src)
            font.flavor = "woff2"
            font.save(out)
        css = ",".join(f"U+{a:X}-{b:X}" for a, b in ranges)
        for key in ("sans", "round", "text", "serif"):
            faces.append([FAMILY[key], stamp(f"fonts/{name}.woff2").removeprefix("fonts/"), "100 900", css])
    return faces


def write_faces(faces: list[list]) -> None:
    rule = lambda fam, file, w, ur, base: (f'@font-face{{font-family:"{fam}";src:url("{base}{file}") format("woff2");'  # noqa: E731
                                           f"font-weight:{w};font-display:swap;unicode-range:{ur}}}")
    (SITE / "fonts" / "katagami.css").write_text("/* Katagami web fonts, generated by tools/build_site.py in the Katagami repo */\n"
                                              + "\n".join(rule(*f, "") for f in faces) + "\n")
    apply = SITE / "katagami-apply.js"
    text = apply.read_text()
    start, end = "/* generated faces: start */", "/* generated faces: end */"
    if start in text:
        a, b = text.index(start) + len(start), text.index(end)
        text = text[:a] + "\n  const FACES = " + json.dumps(faces, separators=(",", ":")) + ";\n  " + text[b:]
        apply.write_text(text)


def site_facts() -> dict:
    """Numbers the header and footer print, read from the built data and the repository."""
    facts = {"characters": 0, "glyphs": 0, "features": 0, "people": "", "commit": "", "date": time.strftime("%Y-%m-%d")}
    data_js = SITE / "data.js"
    if data_js.exists():
        text = data_js.read_text()
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
        facts["characters"] = data["sans"]["metrics"]["characters"]
        facts["glyphs"] = sum(data[k]["metrics"]["glyphs"] for k in FONTS if k in data)
        facts["features"] = len({f["tag"] for f in data["sans"]["features"] if OPTIONAL.match(f["tag"])})
    map_json = SITE / "map" / "map.json"
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
             "/convert": "Any site, set in Katagami", "/download": "v0.1, OFL"}
    sheet = "".join(f'<a href="{h}"{cur(h)}>{t}<span>{hints.get(h, "")}</span></a>'
                    for h, t in [*LINKS, ("/convert", "Font-ify"), ("/download", "Download")])
    return f"""<header class="top">
  <div class="wrap">
    <a class="brand" href="/">{MARK}<b>Katagami</b><span>v0.1</span></a>
    <nav aria-label="Pages">
      <div class="links">{links}</div>
      <a class="pill fontify" href="/convert"{cur("/convert")}>{SPARKLES}<span>Font-ify</span></a>
      <a class="pill dl" href="/download"{cur("/download")}>{TRAY}<span>Download</span></a>
      <a class="gh" href="{REPO}" target="_blank" rel="noopener" aria-label="Katagami on GitHub">{GITHUB}</a>
      <details class="menu">
        <summary aria-label="Menu"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="shut" d="M4 7h16M4 12h16M4 17h16"/><path class="open" d="M6 6l12 12M18 6L6 18"/></svg></summary>
        <div class="sheet-menu">{sheet}<a href="{REPO}" target="_blank" rel="noopener">GitHub<span>Source and issues</span></a></div>
      </details>
    </nav>
  </div>
</header>"""


def footer_html(facts: dict) -> str:
    """The footer every page shares."""
    members = "".join(f'<a href="/#{k}">{FAMILY[k]}</a>' for k in ("sans", "round", "text", "serif", "mono"))
    commit = f'<a href="{REPO}/commit/{facts["commit"]}">{facts["commit"]}</a>' if facts["commit"] else ""
    return f"""<footer class="site">
  <div class="wrap">
    <div class="f-grid">
      <div class="f-lede">
        <p>Katagami is a free type family in five members, Sans, Round, Text, Serif and Mono, under the SIL Open Font License 1.1. You can use it, change it and ship it in any product.</p>
        <p class="f-meta"><span>v0.1</span><span>{facts["glyphs"]:,} glyphs</span><span>built {facts["date"]}</span>{commit}</p>
      </div>
      <nav class="f-col" aria-label="Members"><h3>Members</h3>{members}</nav>
      <nav class="f-col" aria-label="Explore"><h3>Explore</h3><a href="/glyphs">Glyphs</a><a href="/features">Features</a><a href="/map">Map</a><a href="/convert">Font-ify</a></nav>
      <nav class="f-col" aria-label="Project"><h3>Project</h3><a href="/about">About</a><a href="/faq">FAQ</a><a href="/download">Download</a><a href="{REPO}">GitHub</a><a href="{REPO}/blob/main/OFL.txt">License</a></nav>
    </div>
    <div class="f-word" aria-hidden="true"><b>Katagami</b><span></span></div>
  </div>
</footer>"""


def write_pages() -> None:
    # Each hand-written page fragment is wrapped in a document. Asset URLs are
    # stamped with a content hash, so a changed file gets a new URL and the
    # cache headers in vercel.json never pair a new page with old data.
    assets = ["data.js", "katagami-apply.js", "site.css", "site.js", "map/map.json", "download/files.json", "fonts/katagami.css", *(f"fonts/{name}" for name in WOFF2.values())]
    stamps = {rel: hashlib.sha256((SITE / rel).read_bytes()).hexdigest()[:10]
              for rel in assets if (SITE / rel).exists()}
    facts = site_facts()
    for source, target in PAGES.items():
        if not (SITE / source).exists():
            continue
        page = (SITE / source).read_text()
        here = "/" + target.removesuffix(".html").replace("index", "")
        page = page.replace("<!-- site:nav -->", nav_html(here, facts)).replace("<!-- site:footer -->", footer_html(facts))
        for rel, digest in stamps.items():
            page = page.replace(f'"{rel}"', f'"{rel}?v={digest}"')
        (SITE / target).write_text(
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
            '<link rel="icon" href="/favicon.png" type="image/png" sizes="64x64">\n'
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
            f'<link rel="stylesheet" href="/site.css?v={stamps.get("site.css", "")}">\n'
            "</head>\n<body>\n" + page + f'\n<script src="/site.js?v={stamps.get("site.js", "")}" defer></script>\n</body>\n</html>\n'
        )


CJK_FILES = [ROOT / "fonts" / "cjk" / f"{name}[wght].ttf" for name in CJK]


def write_downloads() -> None:
    """The zip of the five members with the license, and files.json, which the
    download page lists: every font file with its size and a link."""
    out = SITE / "download"
    out.mkdir(exist_ok=True)
    zpath = out / "Katagami-0.1.zip"
    members = [(key, FONTS[key]) for key in ("sans", "round", "text", "serif", "mono")]
    if not all(fresh(path, zpath) for _, path in members):
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            # fixed timestamps, so the same fonts make the same zip
            for arc, src in [*((f"Katagami-0.1/{path.name}", path) for _, path in members),
                             ("Katagami-0.1/OFL.txt", ROOT / "OFL.txt")]:
                info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, src.read_bytes())
    raw = lambda path: f"{REPO}/raw/main/{path.relative_to(ROOT).as_posix().replace('[', '%5B').replace(']', '%5D')}"  # noqa: E731
    files = [{"key": key, "family": FAMILY[key], "file": path.name, "weights": WEIGHTS[key].replace(" ", " to "),
              "glyphs": len(TTFont(path).getGlyphOrder()), "bytes": path.stat().st_size, "url": raw(path)} for key, path in members]
    cjk = [{"family": f"Katagami CJK {path.stem[11:13]}", "file": path.name, "bytes": path.stat().st_size, "url": raw(path)}
           for path in CJK_FILES if path.exists()]
    (out / "files.json").write_text(json.dumps({"version": "0.1", "zip": {"file": zpath.name, "bytes": zpath.stat().st_size},
                                                "members": files, "cjk": cjk}, separators=(",", ":")))


def main() -> None:
    (SITE / "fonts").mkdir(parents=True, exist_ok=True)
    data = {"version": "0.1", "names": {}}
    for key, path in FONTS.items():
        font = TTFont(path)
        data[key] = {"metrics": metrics(font), "chars": chars(font), "features": features(font)}
        for cp, *_ in data[key]["chars"]:
            data["names"][cp] = unicodedata.name(chr(cp), "").title()
    write_faces(web_fonts())
    data["mono"]["metrics"]["cell"] = TTFont(FONTS["mono"])["hmtx"]["zero"][0]
    write_downloads()
    data["outlines"] = outlines()
    data["members"] = member_outlines()
    (SITE / "data.js").write_text("window.KERF = " + json.dumps(data, separators=(",", ":")) + ";\n")

    write_pages()
    for p in sorted(SITE.rglob("*")):
        rel = p.relative_to(SITE)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            print(f"{p.stat().st_size / 1024:8.1f} KB  {rel}")


if __name__ == "__main__":
    # --pages rewraps the hand-written pages only, for a change to their markup
    write_pages() if "--pages" in sys.argv else main()

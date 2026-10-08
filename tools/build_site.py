"""Generate the specimen site's assets from the built fonts.

The site lives in its own repo, Kerf-Website, checked out next to this one
(or wherever KERF_SITE points). This writes into it:

    fonts/KerfSans.woff2, fonts/KerfRound.woff2, fonts/KerfMono.woff2
    data.js     window.KERF: metrics, character tables, features, outlines
    index.html  page.html wrapped in a document, asset URLs stamped with hashes

Run after tools/build.sh, then commit and push Kerf-Website; Vercel deploys it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import unicodedata
from pathlib import Path

import sys

import ufoLib2
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import decompose  # noqa: E402
from kerf_build.outline import round_corners  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get("KERF_SITE", ROOT.parent / "Kerf-Website"))
FONTS = {"sans": ROOT / "fonts/sans/KerfSans[wght].ttf", "round": ROOT / "fonts/round/KerfRound[wght].ttf",
         "text": ROOT / "fonts/text/KerfText[wght].ttf", "mono": ROOT / "fonts/mono/KerfMono[wght].ttf"}
WOFF2 = {"sans": "KerfSans.woff2", "round": "KerfRound.woff2", "text": "KerfText.woff2", "mono": "KerfMono.woff2"}
OUTLINE_CHARS = {"K": "K", "e": "e", "r": "r", "f": "f", "O": "O", "o": "o"}
INTER_UFO = ROOT / "build/ufo/Inter-Regular.ufo"
KERF_UFO = ROOT / "build/sans/KerfSans-Regular.ufo"
MONO_UFO = ROOT / "build/mono/KerfMono-Regular.ufo"
ROUND_UFO = ROOT / "build/round/KerfRound-Regular.ufo"
HERO = "Kerf"  # morphs Kerf Mono <- Kerf Sans -> Kerf Round; all three share Inter's point structure
PAGES = {"page.html": "index.html", "map-page.html": "map.html", "convert-page.html": "convert.html"}  # hand-written fragment -> served page


def group(cp: int) -> str:
    if 0x2500 <= cp <= 0x259F:
        return "drawing"
    cat = unicodedata.category(chr(cp))
    return {"L": "letters", "N": "figures", "P": "punctuation", "S": "symbols", "M": "marks"}.get(cat[0], "other")


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
        out.append({"tag": tag, "label": label})
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


def contours(font, ch: str, corners=()) -> dict:
    """A glyph's outline as [x, y, type] lists; `corners` adds zero-radius
    rounded corners (same points as Kerf Round's, same shape)."""
    g = font[ch]
    if g.components:
        decompose(font, [ch])
    if corners:
        g = copy.deepcopy(g)
        round_corners(g, [(ci, idx) for ci, idx in corners], 0.0)
    return {"adv": g.width,
            "contours": [[[round(p.x, 1), round(p.y, 1), {"curve": "c", "line": "l", None: "o"}.get(p.type, "l")]
                          for p in c.points] for c in g.contours]}


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
    """Kerf Round's rounded corners for the flattened glyph, contour indices shifted to match."""
    plans = font.lib.get("com.kerf.roundedCorners", {})
    g = font[gname]
    out = [(ci + offset, idx) for ci, idx in plans.get(gname, [])]
    n = offset + len(g.contours)
    for comp in g.components:
        out += flat_plan(font, comp.baseGlyph, n)
        n += len(flatten(font, comp.baseGlyph))
    return out


def expand(contours: list, plan: list) -> list:
    """Split each planned corner into the four coincident points Kerf Round has there."""
    out = [list(c) for c in contours]
    for ci, idx in plan:
        c = out[ci]
        for i in sorted(idx, reverse=True):
            x, y, t = c[i]
            c[i:i + 1] = [[x, y, t], [x, y, "o"], [x, y, "o"], [x, y, "c"]]
    return out


def outlines() -> dict:
    inter, kerf, mono, rnd = (ufoLib2.Font.open(p) for p in (INTER_UFO, KERF_UFO, MONO_UFO, ROUND_UFO))
    shape = lambda o: [len(c) for c in o["contours"]]  # noqa: E731
    out = {}
    for ch, gname in OUTLINE_CHARS.items():
        a, b = contours(inter, gname), contours(kerf, gname)
        assert shape(a) == shape(b), ch
        out[ch] = {"inter": a, "kerf": b}
        if ch in HERO:
            # Kerf Round rounds its vertices, which adds points. Give Sans and
            # Mono the same corners at zero radius so all three still morph.
            plan = flat_plan(rnd, gname)
            sans_like = {"adv": kerf[gname].width, "contours": expand(flatten(kerf, gname), plan)}
            mono_like = {"adv": mono[gname].width, "contours": expand(flatten(mono, gname), plan)}
            rounded = {"adv": rnd[gname].width, "contours": flatten(rnd, gname)}
            for key, o in (("mono", mono_like), ("round", rounded)):
                assert shape(o) == shape(sans_like), f"{ch}: {key} and Kerf Sans outlines differ"
            out[ch]["hero"] = sans_like
            out[ch]["mono"] = mono_like
            out[ch]["round"] = rounded
    return out


def main() -> None:
    (SITE / "fonts").mkdir(parents=True, exist_ok=True)
    data = {"version": "0.1", "names": {}}
    for key, path in FONTS.items():
        font = TTFont(path)
        data[key] = {"metrics": metrics(font), "chars": chars(font), "features": features(font)}
        for cp, *_ in data[key]["chars"]:
            data["names"][cp] = unicodedata.name(chr(cp), "").title()
        font.flavor = "woff2"
        font.save(SITE / "fonts" / WOFF2[key])
    data["mono"]["metrics"]["cell"] = TTFont(FONTS["mono"])["hmtx"]["zero"][0]
    data["outlines"] = outlines()
    (SITE / "data.js").write_text("window.KERF = " + json.dumps(data, separators=(",", ":")) + ";\n")

    # Each hand-written page fragment is wrapped in a document. Asset URLs are
    # stamped with a content hash, so a changed file gets a new URL and the
    # cache headers in vercel.json never pair a new page with old data.
    assets = ["data.js", "kerf-apply.js", "map/map.json", *(f"fonts/{name}" for name in WOFF2.values())]
    stamps = {rel: hashlib.sha256((SITE / rel).read_bytes()).hexdigest()[:10]
              for rel in assets if (SITE / rel).exists()}
    for source, target in PAGES.items():
        if not (SITE / source).exists():
            continue
        page = (SITE / source).read_text()
        for rel, digest in stamps.items():
            page = page.replace(f'"{rel}"', f'"{rel}?v={digest}"')
        (SITE / target).write_text(
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            "</head>\n<body>\n" + page + "\n</body>\n</html>\n"
        )
    for p in sorted(SITE.rglob("*")):
        rel = p.relative_to(SITE)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts):
            print(f"{p.stat().st_size / 1024:8.1f} KB  {rel}")


if __name__ == "__main__":
    main()

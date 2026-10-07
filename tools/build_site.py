"""Generate the specimen site's assets from the built fonts.

    site/fonts/KerfSans.woff2, site/fonts/KerfMono.woff2
    site/data.js     window.KERF: metrics, character tables, features, outlines
    site/index.html  site/page.html wrapped in a document

Run after tools/build.sh.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import sys

import ufoLib2
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import decompose  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
FONTS = {"sans": ROOT / "fonts/sans/KerfSans[wght].ttf", "round": ROOT / "fonts/round/KerfRound[wght].ttf",
         "mono": ROOT / "fonts/mono/KerfMono[wght].ttf"}
WOFF2 = {"sans": "KerfSans.woff2", "round": "KerfRound.woff2", "mono": "KerfMono.woff2"}
OUTLINE_CHARS = {"K": "K", "e": "e", "r": "r", "f": "f", "O": "O", "o": "o"}
INTER_UFO = ROOT / "build/ufo/Inter-Regular.ufo"
KERF_UFO = ROOT / "build/sans/KerfSans-Regular.ufo"
MONO_UFO = ROOT / "build/mono/KerfMono-Regular.ufo"
HERO = "Kerf"  # morphs between Kerf Mono and Kerf Sans; the mono is fitted point for point


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


def contours(font, ch: str) -> dict:
    g = font[ch]
    if g.components:
        decompose(font, [ch])
    return {"adv": g.width,
            "contours": [[[round(p.x, 1), round(p.y, 1), {"curve": "c", "line": "l", None: "o"}.get(p.type, "l")]
                          for p in c.points] for c in g.contours]}


def outlines() -> dict:
    inter, kerf, mono = (ufoLib2.Font.open(p) for p in (INTER_UFO, KERF_UFO, MONO_UFO))
    shape = lambda o: [len(c) for c in o["contours"]]  # noqa: E731
    out = {}
    for ch, gname in OUTLINE_CHARS.items():
        a, b = contours(inter, gname), contours(kerf, gname)
        assert shape(a) == shape(b), ch
        out[ch] = {"inter": a, "kerf": b}
        if ch in HERO:
            m = contours(mono, gname)
            assert shape(m) == shape(b), f"{ch}: Kerf Mono and Kerf Sans outlines differ"
            out[ch]["mono"] = m
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

    page = (SITE / "page.html").read_text()
    (SITE / "index.html").write_text(
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        "</head>\n<body>\n" + page + "\n</body>\n</html>\n"
    )
    for p in sorted(SITE.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size / 1024:8.1f} KB  {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

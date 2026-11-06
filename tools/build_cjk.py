"""Build Katagami CJK SC, TC, JP and KR: Chinese, Japanese and Korean companions to
the Katagami members, from Google's Noto Sans SC, TC, JP and KR (SIL OFL 1.1).

    python tools/build_cjk.py [SC TC JP KR] [--roman|--italic]

These stay separate from the members, as Pretendard JP does, so a page fetches a
CJK file only when it shows CJK text. Each is Noto's variable font subset to a
national character standard:

    SC  GB 2312: 6,763 hanzi and its CJK symbols
    TC  Big5: 13,053 hanzi, its CJK symbols and bopomofo
    JP  JIS X 0208: 6,355 kanji, hiragana, katakana and its symbols
    KR  all 11,172 Hangul syllables and the jamo

plus CJK punctuation and the full-width forms. In place of Noto's Latin each
file has Katagami Sans's: Google Fonts' Latin core, the auxiliary letters of its
languages and the dotted circle, with Sans's kerning, marks, composition,
language forms and contextual punctuation, so Latin in a CJK file sets as it
does in Katagami Sans at every weight. The website serves the CJK characters
alone and sets Latin, Greek and Cyrillic in the members.

The Latin is merged at Katagami's 2048-unit em and each file is saved at
Noto's 1000-unit em, because at 2048 Katagami CJK TC is over Google Fonts'
9 MiB limit. Its hhea and win metrics hold Katagami's line (1984 and -494 on
2048, no gap), so apps space its lines as Katagami's,
and its typo metrics follow Google's CJK rule (0.88 and -0.12 em, no gap,
USE_TYPO_METRICS off). The website sets a CJK file in the same CSS family as a
Katagami member with unicode-range, and its @font-face rules give it the same
line with ascent-override, descent-override and line-gap-override.

Each companion has a roman and an Italic. The Italic is Noto's letters slanted
by Katagami Sans Italic's angle about its half x-height (`kerf_build.slant`),
as the members' Italics slant their letters, with Sans Italic's Latin.

Each file also has chws and vchw from googlefonts' chws_tool, carets for its
ligatures, glyph names (post format 2), clockwise outer contours, contours
repaired where two share a segment, and no glyph that nothing reaches.
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.hvar import add_HVAR

sys.path.insert(0, str(Path(__file__).parent))
from finish import prune_unreachable, stat, unhinted  # noqa: E402
from chws_tool import add_chws  # noqa: E402
from kerf_build.cjk import (build_latin, glyph_names, lig_carets, ligatures, merge_latin,  # noqa: E402
                            reverse_ccw_outers, unicode_marks)
from kerf_build.contours import fix_shared_segments  # noqa: E402
from kerf_build.fontops import VENDOR, VERSION, italic_style  # noqa: E402
from kerf_build.slant import slant  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOTO = ROOT / "vendor" / "noto"
SANS = ROOT / "fonts" / "sans" / "KatagamiSans[wght].ttf"
SANS_ITALIC = ROOT / "fonts" / "sans" / "KatagamiSans-Italic[wght].ttf"
OUT = ROOT / "fonts" / "cjk"
UPM = 2048  # the em the Latin is merged at, Katagami's
FILE_UPM = 1000  # the em the files are saved at, Noto's: at 2048 Katagami CJK TC passes Google Fonts' 9 MiB limit
KERF_LINE = {"ascender": 1984, "descender": -494, "lineGap": 0}  # Katagami Sans's line, here in hhea and win
# Google's CJK rule: typo metrics at 0.88 and -0.12 em with no gap, USE_TYPO_METRICS off,
# hhea equal to win. The typo ascender is also the vertical origin of Noto's glyphs.
CJK_TYPO = {"ascender": round(0.88 * UPM), "descender": round(-0.12 * UPM), "lineGap": 0}
SCRIPT = {"SC": "Hans", "TC": "Hant", "JP": "Jpan", "KR": "Kore"}  # the meta table's script tags
SHARED = [(0x3000, 0x303F), (0xFF00, 0xFFEF), (0x3200, 0x32FF), (0x3300, 0x33FF)]  # punctuation, full width, enclosed


def euc_chars(codec: str) -> set[int]:
    """Every character of a two-byte EUC code set (GB 2312, JIS X 0208)."""
    out = set()
    for hi in range(0xA1, 0xFF):
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode(codec)
            except UnicodeDecodeError:
                continue
            if len(ch) == 1:
                out.add(ord(ch))
    return out


def big5_chars() -> set[int]:
    """Every character of Big5: lead bytes A1 to F9, trail bytes 40 to 7E and A1 to FE."""
    out = set()
    for hi in range(0xA1, 0xFA):
        for lo in (*range(0x40, 0x7F), *range(0xA1, 0xFF)):
            try:
                ch = bytes([hi, lo]).decode("big5")
            except UnicodeDecodeError:
                continue
            if len(ch) == 1:
                out.add(ord(ch))
    return out


def charset(region: str) -> set[int]:
    """The characters taken from Noto. Katagami Sans supplies the space and the rest of the Latin."""
    shared = {u for lo, hi in SHARED for u in range(lo, hi + 1)}
    if region == "SC":
        return {u for u in euc_chars("gb2312") if u >= 0x2E80} | shared
    if region == "TC":
        bopomofo = {u for lo, hi in ((0x3100, 0x312F), (0x31A0, 0x31BF)) for u in range(lo, hi + 1)}
        return {u for u in big5_chars() if u >= 0x2E80} | bopomofo | shared
    if region == "JP":
        kana = {u for lo, hi in ((0x3040, 0x30FF), (0x31F0, 0x31FF)) for u in range(lo, hi + 1)}
        return {u for u in euc_chars("euc_jp") if u >= 0x2E80} | kana | shared
    hangul = {u for lo, hi in ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xD7B0, 0xD7FF))
              for u in range(lo, hi + 1)}
    return hangul | shared


def rename(font: TTFont, family: str, italic: bool) -> None:
    """Names the default instance, Thin in Noto's variable fonts, as Google Fonts
    names it, and in an Italic every named instance as an Italic (Thin Italic)."""
    ps = family.replace(" ", "")
    name = font["name"]
    version = f"{VERSION[0]}.{VERSION[1]:03d}"
    font["head"].fontRevision = float(version)
    if italic:
        for inst in font["fvar"].instances:
            inst.subfamilyNameID = name.addName(italic_style(name.getDebugName(inst.subfamilyNameID)),
                                                platforms=((3, 1, 0x409),), minNameID=256)
    default = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
    style = next(name.getDebugName(i.subfamilyNameID) for i in font["fvar"].instances if i.coordinates == default)
    weight = style.removesuffix("Italic").strip() or "Regular"
    for rec in list(name.names):
        if rec.nameID == 1:
            rec.string = family if weight == "Regular" else f"{family} {weight}"
        elif rec.nameID == 4:
            rec.string = f"{family} {style}"
        elif rec.nameID == 2:
            rec.string = "Italic" if italic else "Regular"
        elif rec.nameID == 16:
            rec.string = family
        elif rec.nameID == 17:
            rec.string = style
        elif rec.nameID == 6:
            rec.string = f"{ps}-{style.replace(' ', '')}"
        elif rec.nameID == 3:
            rec.string = f"{version};{VENDOR};{ps}-{style.replace(' ', '')}"
        elif rec.nameID == 5:
            rec.string = f"Version {version}"
        elif rec.nameID == 25:
            rec.string = ps + ("Italic" if italic else "")
        elif rec.nameID == 13:
            rec.string = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
                          "This license is available with a FAQ at: https://openfontlicense.org")
        elif rec.nameID == 14:
            rec.string = "https://openfontlicense.org"
    for rec in name.names:
        if rec.nameID == 0:
            noto = rec.toUnicode().replace("(c)", "Copyright")
            rec.string = ("Copyright 2026 The Katagami Project Authors (https://github.com/Kevin-Liu-01/Katagami). "
                          f"Derived from Noto Sans CJK, {noto}")


def style_bits(font: TTFont, sans: TTFont, italic: bool) -> None:
    """REGULAR or ITALIC in fsSelection and macStyle, and in an Italic the Latin's
    italic angle and caret slope. A roman keeps Noto's upright caret."""
    os2, head = font["OS/2"], font["head"]
    os2.fsSelection = os2.fsSelection & ~(1 << 0 | 1 << 5 | 1 << 6) | (1 << 0 if italic else 1 << 6)
    head.macStyle = (head.macStyle & ~0b11) | (0b10 if italic else 0)
    if italic:
        font["post"].italicAngle = sans["post"].italicAngle
        font["hhea"].caretSlopeRise, font["hhea"].caretSlopeRun = sans["hhea"].caretSlopeRise, sans["hhea"].caretSlopeRun


def set_metrics(font: TTFont, sans: TTFont) -> None:
    """Katagami's line in hhea and win, Google's CJK typo metrics, and the OS/2
    fields that the Latin changes."""
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = KERF_LINE["ascender"], KERF_LINE["descender"], KERF_LINE["lineGap"]
    os2.usWinAscent, os2.usWinDescent = hhea.ascent, -hhea.descent
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = CJK_TYPO["ascender"], CJK_TYPO["descender"], CJK_TYPO["lineGap"]
    os2.fsSelection &= ~(1 << 7)
    # the Latin is Sans's, so are its x-height and cap height
    os2.sxHeight, os2.sCapHeight = sans["OS/2"].sxHeight, sans["OS/2"].sCapHeight
    # code pages are read from a few test characters each, so Noto's CJK pages are kept as well
    pages = os2.ulCodePageRange1, os2.ulCodePageRange2
    os2.recalcUnicodeRanges(font)
    os2.recalcCodePageRanges(font)
    os2.ulCodePageRange1 |= pages[0]
    os2.ulCodePageRange2 |= pages[1]
    os2.recalcAvgCharWidth(font)


def latin_font(sans_path: Path, cjk: TTFont, cache: dict) -> TTFont:
    """Katagami Sans's (or Sans Italic's) Latin on the CJK file's axis, a fresh copy
    for each merge. It is built once per avar; Noto's four files share one."""
    key = (sans_path, repr(cjk["avar"].segments))
    if key not in cache:
        buf = io.BytesIO()
        build_latin(sans_path, cjk).save(buf)
        cache[key] = buf.getvalue()
    return TTFont(io.BytesIO(cache[key]))


def build(region: str, cache: dict, italic: bool = False) -> Path:
    noto = NOTO / f"NotoSans{region}[wght].ttf"
    chars = charset(region)
    font = TTFont(noto)
    font.setGlyphOrder(glyph_names(TTFont(noto), chars))  # before any table is read, so every table takes the names
    have = font.getBestCmap()
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = False
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=[u for u in chars if u in have])
    sub.subset(font)
    scale_upem(font, UPM)
    reversed_ = reverse_ccw_outers(font)
    sans_path = SANS_ITALIC if italic else SANS
    sans = TTFont(sans_path, lazy=True)
    if italic:
        slant(font, math.tan(math.radians(-sans["post"].italicAngle)), sans["OS/2"].sxHeight / 2)
    marks = unicode_marks(font)
    added = merge_latin(font, latin_font(sans_path, font, cache), CJK_TYPO["ascender"], marks)
    add_HVAR(font)  # from every glyph's phantom-point deltas, so it covers the Latin
    lig_carets(font, ligatures(font))
    set_metrics(font, sans)
    rename(font, f"Katagami CJK {region}", italic)
    style_bits(font, sans, italic)
    stat(font, italic)
    font["OS/2"].achVendID = VENDOR
    unhinted(font)
    scale_upem(font, FILE_UPM)
    shared, _, left = fix_shared_segments(font)
    reversed_ += reverse_ccw_outers(font)  # a repair can leave a counter-clockwise contour outermost
    pruned = prune_unreachable(font)  # Latin parts whose letters the subset left out
    meta = newTable("meta")
    meta.data = {"dlng": SCRIPT[region], "slng": f"{SCRIPT[region]},Latn"}
    font["meta"] = meta
    post = font["post"]  # glyph names, so text in a PDF made from the font stays searchable
    post.formatType, post.extraNames, post.mapping = 2.0, [], {}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"KatagamiCJK{region}{'-Italic' if italic else ''}[wght].ttf"
    font.save(path)
    add_chws(path, path)  # adds the chws and vchw lookups to the file in place
    font = TTFont(path)
    print(f"{path.relative_to(ROOT)}: {len(font.getGlyphOrder())} glyphs ({len(added)} Latin), "
          f"{len(font.getBestCmap())} characters, {path.stat().st_size / 1e6:.1f} MB; contours reversed in {reversed_}; "
          f"shared segments repaired in {len(shared)}, left in {left}; {pruned} unreachable glyphs dropped")
    return path


if __name__ == "__main__":
    cache = {}
    only = next((a[2:] for a in sys.argv[1:] if a in ("--roman", "--italic")), None)
    for region in [a for a in sys.argv[1:] if not a.startswith("--")] or ("SC", "TC", "JP", "KR"):
        for italic in (False, True):
            if only in (None, "italic" if italic else "roman"):
                build(region, cache, italic)

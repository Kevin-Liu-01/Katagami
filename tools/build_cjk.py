"""Build Katagami CJK SC, JP and KR: Chinese, Japanese and Korean companions to
the Katagami members, from Google's Noto Sans SC, JP and KR (SIL OFL 1.1).

    python tools/build_cjk.py

A CJK font with Katagami's Latin in it would pass the 65,535-glyph limit and be
too heavy for the web, so these stay separate files, as Pretendard JP does.
Each is Noto's variable font subset to a national character standard:

    SC  GB 2312: 6,763 hanzi and its CJK symbols
    JP  JIS X 0208: 6,355 kanji, hiragana, katakana and its symbols
    KR  all 11,172 Hangul syllables and the jamo

plus CJK punctuation and the full-width forms. Latin, Greek and Cyrillic
are left out so a page sets them in Katagami. Each file is scaled to Katagami's
2048-unit em and takes Katagami's line metrics, so it can sit in the same CSS
family as a Katagami member (the website does this with unicode-range).
"""

from __future__ import annotations

from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem

ROOT = Path(__file__).resolve().parents[1]
NOTO = ROOT / "vendor" / "noto"
OUT = ROOT / "fonts" / "cjk"
KERF_LINE = {"ascender": 1984, "descender": -494, "lineGap": 0}  # Katagami Sans's hhea and typo metrics
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


def charset(region: str) -> set[int]:
    shared = {u for lo, hi in SHARED for u in range(lo, hi + 1)}
    if region == "SC":
        return {u for u in euc_chars("gb2312") if u >= 0x2E80} | shared
    if region == "JP":
        kana = {u for lo, hi in ((0x3040, 0x30FF), (0x31F0, 0x31FF)) for u in range(lo, hi + 1)}
        return {u for u in euc_chars("euc_jp") if u >= 0x2E80} | kana | shared
    hangul = {u for lo, hi in ((0xAC00, 0xD7A3), (0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xD7B0, 0xD7FF))
              for u in range(lo, hi + 1)}
    return hangul | shared


def rename(font: TTFont, family: str) -> None:
    ps = family.replace(" ", "")
    name = font["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 16):
            rec.string = family
        elif rec.nameID == 4:
            rec.string = f"{family} {name.getDebugName(2) or 'Regular'}"
        elif rec.nameID == 6:
            rec.string = f"{ps}-{(name.getDebugName(2) or 'Regular').replace(' ', '')}"
        elif rec.nameID == 3:
            rec.string = f"{ps};{font['head'].fontRevision:.3f}"
        elif rec.nameID == 25:
            rec.string = ps
    for rec in name.names:
        if rec.nameID == 0:
            rec.string = rec.toUnicode() + " Katagami CJK: subset and rescaled from Noto Sans CJK."


def build(region: str) -> Path:
    font = TTFont(NOTO / f"NotoSans{region}[wght].ttf")
    have = font.getBestCmap()
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = False
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=[u for u in charset(region) if u in have])
    sub.subset(font)
    scale_upem(font, 2048)
    hhea, os2 = font["hhea"], font["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = KERF_LINE["ascender"], KERF_LINE["descender"], KERF_LINE["lineGap"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = hhea.ascent, hhea.descent, hhea.lineGap
    os2.fsSelection |= 1 << 7  # use the typo metrics, as Katagami does
    rename(font, f"Katagami CJK {region}")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"KatagamiCJK{region}[wght].ttf"
    font.save(path)
    font = TTFont(path)
    head = font["head"]
    font["OS/2"].usWinAscent, font["OS/2"].usWinDescent = max(head.yMax, 0), max(-head.yMin, 0)
    font.save(path)
    print(f"{path.relative_to(ROOT)}: {len(font.getGlyphOrder())} glyphs, {len(font.getBestCmap())} characters, "
          f"{path.stat().st_size / 1e6:.1f} MB")
    return path


if __name__ == "__main__":
    for region in ("SC", "JP", "KR"):
        build(region)

"""Finish a member's built fonts: version, naming, STAT, style bits, line metrics
and the tables an unhinted font needs.

    python tools/finish.py sans|round|text|serif|mono [...] [--roman|--italic]

Runs on fonts/<member>/<Stem>[wght].ttf and fonts/<member>/<Stem>-Italic[wght].ttf
in place, after fontmake (and, for the roman, the script merge):

  1. Version: head.fontRevision, the version string (name 5) and the unique ID
     (name 3) all read VERSION. The script merge otherwise leaves Noto's
     revision in the head table.
  2. Names: the default instance is Regular or Italic; every named instance
     has a PostScript name, and the variations PostScript prefix (name 25) is set.
  3. Style bits: fsSelection has REGULAR or ITALIC and USE_TYPO_METRICS, and
     macStyle matches.
  4. STAT: a weight axis value for every named weight (Regular elidable and
     linked to Bold) and an ital axis whose value is 0 (Roman, elidable,
     linked to Italic) or 1 (Italic), so a roman and its Italic link as one family.
  5. Line metrics: the Italic takes the roman's hhea and typo metrics, so both
     set the same line height, and both files clip at the tallest and deepest
     glyph of the two.
  6. Unhinted: a gasp table that asks for smoothing at every size, and a prep
     program that turns on smart dropout control (as gftools fix-unhinted does).
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import VERSION  # noqa: E402
from kerf_build.profiles import PROFILES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STEMS = {key: p.file_stem for key, p in PROFILES.items()} | {"mono": "KatagamiMono"}
WEIGHTS = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
           700: "Bold", 800: "ExtraBold", 900: "Black"}


def version(font: TTFont, ps: str) -> None:
    major, minor = VERSION
    text = f"{major}.{minor:03d}"
    font["head"].fontRevision = float(text)
    name = font["name"]
    name.setName(f"Version {text}", 5, 3, 1, 0x409)
    name.setName(f"{text};KERF;{ps}", 3, 3, 1, 0x409)


def names(font: TTFont, family: str, italic: bool) -> str:
    """Family and default style names, and a PostScript name for every instance."""
    name = font["name"]
    style = "Italic" if italic else "Regular"
    ps_family = family.replace(" ", "")
    ps = f"{ps_family}-{style}"
    for nid in (16, 17, 21, 22):
        name.removeNames(nameID=nid)
    name.setName(family, 1, 3, 1, 0x409)
    name.setName(style, 2, 3, 1, 0x409)
    name.setName(f"{family} {style}", 4, 3, 1, 0x409)
    name.setName(ps, 6, 3, 1, 0x409)
    name.setName(ps_family + ("Italic" if italic else ""), 25, 3, 1, 0x409)
    for inst in font["fvar"].instances:
        sub = name.getDebugName(inst.subfamilyNameID)
        inst.postscriptNameID = name.addName(f"{ps_family}-{sub.replace(' ', '')}", platforms=((3, 1, 0x409),), minNameID=256)
    # only Windows English names: the Mac records fontmake writes duplicate them
    name.names = [r for r in name.names if r.platformID == 3]
    return ps


def style_bits(font: TTFont, italic: bool) -> None:
    os2, head = font["OS/2"], font["head"]
    sel = os2.fsSelection & ~(1 << 0 | 1 << 5 | 1 << 6)
    sel |= (1 << 0) if italic else (1 << 6)
    os2.fsSelection = sel | 1 << 7  # USE_TYPO_METRICS
    head.macStyle = (head.macStyle & ~0b11) | (0b10 if italic else 0)


def stat(font: TTFont, italic: bool) -> None:
    axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
    values = []
    for w, label in WEIGHTS.items():
        if axis.minValue <= w <= axis.maxValue:
            v = {"value": w, "name": label}
            if w == 400:
                v |= {"flags": 0x2, "linkedValue": 700}
            values.append(v)
    ital = ({"value": 1, "name": "Italic"} if italic
            else {"value": 0, "name": "Roman", "flags": 0x2, "linkedValue": 1})
    buildStatTable(font, [
        {"tag": "wght", "name": "Weight", "values": values},
        {"tag": "ital", "name": "Italic", "values": [ital]},
    ], elidedFallbackName=2)


def metrics_from(font: TTFont, roman: TTFont) -> None:
    """The roman's line spacing (hhea and typo), so both set the same line height."""
    hhea, os2, src_hhea, src_os2 = font["hhea"], font["OS/2"], roman["hhea"], roman["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = src_hhea.ascent, src_hhea.descent, src_hhea.lineGap
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = src_os2.sTypoAscender, src_os2.sTypoDescender, src_os2.sTypoLineGap


def clipping(font: TTFont, family: list[TTFont]) -> None:
    """The Windows clipping box covers the tallest and deepest glyph of the
    roman and the Italic together, and never less than the typo metrics, so
    both files of a member have the same vertical metrics. USE_TYPO_METRICS
    keeps it out of the line spacing."""
    os2 = font["OS/2"]
    os2.usWinAscent = max([f["head"].yMax for f in family] + [os2.sTypoAscender])
    os2.usWinDescent = max([-f["head"].yMin for f in family] + [-os2.sTypoDescender])


def prune_names(font: TTFont) -> None:
    """Drop name records from 256 up that nothing points at any more. Only the
    tables that hold name IDs here are read (fvar, STAT and the feature labels
    in GSUB and GPOS), so glyf and gvar stay compiled and the font saves quickly."""
    used = set()
    fvar = font["fvar"]
    used |= {a.axisNameID for a in fvar.axes}
    used |= {i.subfamilyNameID for i in fvar.instances} | {i.postscriptNameID for i in fvar.instances}
    stat = font["STAT"].table
    used |= {a.AxisNameID for a in stat.DesignAxisRecord.Axis} | {v.ValueNameID for v in stat.AxisValueArray.AxisValue}
    used.add(stat.ElidedFallbackNameID)
    records = [rec for tag in ("GSUB", "GPOS") if tag in font for rec in font[tag].table.FeatureList.FeatureRecord]
    for rec in records:
        params = rec.Feature.FeatureParams
        for attr in ("UINameID", "FeatUILabelNameID", "FeatUITooltipTextNameID", "SampleTextNameID"):
            if params is not None and getattr(params, attr, None):
                used.add(getattr(params, attr))
        if params is not None and getattr(params, "FirstParamUILabelNameID", None):
            used |= set(range(params.FirstParamUILabelNameID, params.FirstParamUILabelNameID + params.NumNamedParameters))
    font["name"].names = [r for r in font["name"].names if r.nameID < 256 or r.nameID in used]


def unhinted(font: TTFont) -> None:
    gasp = newTable("gasp")
    gasp.gaspRange = {0xFFFF: 0x000F}  # grid-fit and smooth, symmetric, at every size
    font["gasp"] = gasp
    prep = newTable("prep")
    program = ttProgram.Program()
    program.fromAssembly(["PUSHW[]", "511", "SCANCTRL[]", "PUSHB[]", "4", "SCANTYPE[]"])
    prep.program = program
    font["prep"] = prep


def finish(key: str, only: str | None = None) -> None:
    stem = STEMS[key]
    family = PROFILES[key].family if key in PROFILES else "Katagami Mono"
    roman_path = ROOT / "fonts" / key / f"{stem}[wght].ttf"
    italic_path = ROOT / "fonts" / key / f"{stem}-Italic[wght].ttf"
    roman = TTFont(roman_path) if roman_path.exists() else None
    family_fonts = [TTFont(p) for p in (roman_path, italic_path) if p.exists()]
    for path, italic in ((roman_path, False), (italic_path, True)):
        if not path.exists() or only and only != ("italic" if italic else "roman"):
            continue
        font = roman if not italic else TTFont(path)
        ps = names(font, family, italic)
        version(font, ps)
        style_bits(font, italic)
        stat(font, italic)
        if italic and roman is not None:
            metrics_from(font, roman)
        clipping(font, family_fonts)
        unhinted(font)
        prune_names(font)  # what an earlier STAT or a second run left behind
        font.save(path)
        print(f"{path.relative_to(ROOT)}: finished")


if __name__ == "__main__":
    only = next((a[2:] for a in sys.argv[1:] if a in ("--roman", "--italic")), None)
    for key in (a for a in sys.argv[1:] if not a.startswith("--")):
        finish(key, only)

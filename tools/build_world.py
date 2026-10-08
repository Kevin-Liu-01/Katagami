"""Merge other scripts into a Katagami member, the way Pretendard joins Inter
and Source Han Sans.

    python tools/build_world.py sans|round|text [--only Devanagari,Thai]

Katagami draws Latin, Greek and Cyrillic. For 19 more scripts this takes the
outlines and OpenType layout of Google's Noto Sans fonts (SIL OFL 1.1,
vendor/noto, fetched by tools/build.sh), so one Katagami file sets them all:

  1. Each Noto font is subset to its script's Unicode blocks with its layout
     closure, so it adds no Latin, digits or punctuation of its own.
  2. It is instanced at Katagami's three master weights (100, 400, 900) and
     scaled from Noto's 1000-unit em to Katagami's 2048, times Katagami's x-height
     over Noto Sans's (536), so its letters sit at Katagami's size.
  3. Each Katagami master (instanced from fontmake's variable font) is merged
     with the scripts at the same weight.
  4. The three merged masters are built back into one variable font with
     Katagami's weight axis and named instances.

Katagami's own line spacing is kept; the Windows clipping box grows to the
tallest script. The glyphs added here are Noto's design at Katagami's size and
weight, not redrawn in Katagami's style.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fontTools import subset
from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.merge import Merger, Options
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib import build as build_variable
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.profiles import PROFILES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOTO = ROOT / "vendor" / "noto"
NOTO_XHEIGHT = 536  # Noto Sans, per 1000
MASTERS = {"Thin": 100, "Regular": 400, "Black": 900}
INSTANCES = ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black"]

# Noto file stem -> the Unicode blocks taken from it
SCRIPTS = {
    "Devanagari": [(0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x1CD0, 0x1CFF)],
    "Arabic": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x0870, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "Bengali": [(0x0980, 0x09FF)],
    "Gurmukhi": [(0x0A00, 0x0A7F)],
    "Gujarati": [(0x0A80, 0x0AFF)],
    "Oriya": [(0x0B00, 0x0B7F)],
    "Tamil": [(0x0B80, 0x0BFF), (0x11FC0, 0x11FFF)],
    "Telugu": [(0x0C00, 0x0C7F)],
    "Kannada": [(0x0C80, 0x0CFF)],
    "Malayalam": [(0x0D00, 0x0D7F)],
    "Sinhala": [(0x0D80, 0x0DFF), (0x111E0, 0x111FF)],
    "Thai": [(0x0E00, 0x0E7F)],
    "Lao": [(0x0E80, 0x0EFF)],
    "Myanmar": [(0x1000, 0x109F), (0xA9E0, 0xA9FF), (0xAA60, 0xAA7F)],
    "Ethiopic": [(0x1200, 0x139F), (0x2D80, 0x2DDF), (0xAB00, 0xAB2F), (0x1E7E0, 0x1E7FF)],
    "Hebrew": [(0x0590, 0x05FF), (0xFB1D, 0xFB4F)],
    "Armenian": [(0x0530, 0x058F), (0xFB13, 0xFB17)],
    "Georgian": [(0x10A0, 0x10FF), (0x2D00, 0x2D2F), (0x1C90, 0x1CBF)],
    "Khmer": [(0x1780, 0x17FF), (0x19E0, 0x19FF)],
}


def noto_file(script: str) -> Path:
    found = sorted(NOTO.glob(f"NotoSans{script}[[]*.ttf"))
    if not found:
        raise FileNotFoundError(f"{NOTO}/NotoSans{script}[...].ttf; run tools/build.sh to fetch Noto")
    return found[0]


def script_masters(script: str, factor: float, have: set[int], work: Path) -> dict[str, Path]:
    """Noto's script at Katagami's three master weights, at Katagami's units and size."""
    font = TTFont(noto_file(script))
    cmap = font.getBestCmap()
    unicodes = [u for lo, hi in SCRIPTS[script] for u in range(lo, hi + 1) if u in cmap and u not in have]
    opts = subset.Options()
    opts.layout_features = ["*"]
    opts.layout_scripts = ["*"]
    opts.glyph_names = True
    opts.name_IDs = ["*"]
    opts.notdef_outline = False
    opts.hinting = False
    # vertical metrics (Ethiopic has them), hinting and metadata: Katagami has none of these
    opts.drop_tables += ["STAT", "vhea", "vmtx", "VVAR", "gasp", "prep", "meta"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes)
    sub.subset(font)
    # Some Noto fonts swap glyphs by weight (FeatureVariations). Instancing applies the swap
    # at one master and not another, so the masters' feature lists would differ; drop it.
    for tag in ("GSUB", "GPOS"):
        if tag in font and getattr(font[tag].table, "FeatureVariations", None) is not None:
            font[tag].table.FeatureVariations = None
            font[tag].table.Version = 0x00010000
    axes = {a.axisTag for a in font["fvar"].axes}
    out = {}
    for style, wght in MASTERS.items():
        location = {"wght": wght} | ({"wdth": 100} if "wdth" in axes else {})
        static = instantiateVariableFont(TTFont(_save(font, work / f"{script}.ttf")), location)
        scale_upem(static, round(2048 * factor))  # Noto's units times 2048 / its em, times factor
        static["head"].unitsPerEm = 2048
        out[style] = _save(static, work / f"{script}-{style}.ttf")
    return out


def _save(font: TTFont, path: Path) -> Path:
    font.save(path)
    return path


def merge_master(kerf: Path, parts: list[Path], out: Path) -> Path:
    base = TTFont(kerf)
    keep = {
        "hhea": (base["hhea"].ascent, base["hhea"].descent, base["hhea"].lineGap),
        "typo": (base["OS/2"].sTypoAscender, base["OS/2"].sTypoDescender, base["OS/2"].sTypoLineGap),
    }
    merged = Merger(options=Options(drop_tables=["DSIG", "STAT", "meta", "vhea", "vmtx", "VVAR", "gasp", "prep"])).merge([str(kerf)] + [str(p) for p in parts])
    hhea, os2 = merged["hhea"], merged["OS/2"]
    hhea.ascent, hhea.descent, hhea.lineGap = keep["hhea"]
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = keep["typo"]
    merged["name"] = base["name"]
    merged["head"].unitsPerEm = 2048
    merged.save(out)
    merged = TTFont(out)
    # the Windows clipping box covers the tallest script
    head = merged["head"]
    merged["OS/2"].usWinAscent = max(merged["OS/2"].usWinAscent, head.yMax)
    merged["OS/2"].usWinDescent = max(merged["OS/2"].usWinDescent, -head.yMin)
    merged.save(out)
    return out


NOTICE = " Merged scripts: Copyright 2022 The Noto Project Authors (https://github.com/notofonts)."


def stamp_copyright(path: Path) -> None:
    """Add Noto's copyright to the merged font's notice, as the OFL asks."""
    font = TTFont(path)
    for rec in font["name"].names:
        if rec.nameID == 0 and "Noto" not in rec.toUnicode():
            rec.string = rec.toUnicode() + NOTICE
    font.save(path)


def build(key: str, only: list[str] | None = None) -> Path:
    p = PROFILES[key]
    core = ROOT / "build" / key / f"{p.file_stem}-core[wght].ttf"
    target = ROOT / "fonts" / key / f"{p.file_stem}[wght].ttf"
    vf = TTFont(core)
    factor = vf["OS/2"].sxHeight / vf["head"].unitsPerEm * 1000 / NOTO_XHEIGHT
    have = set(vf.getBestCmap())
    scripts = only or list(SCRIPTS)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        kerf = {style: _save(instantiateVariableFont(TTFont(core), {"wght": w}), work / f"kerf-{style}.ttf")
                for style, w in MASTERS.items()}
        parts = {style: [] for style in MASTERS}
        for script in scripts:
            for style, path in script_masters(script, factor, have, work).items():
                parts[style].append(path)
            print(f"  {script}")
        merged = {style: merge_master(kerf[style], parts[style], work / f"merged-{style}.ttf") for style in MASTERS}

        ds = DesignSpaceDocument()
        ax = AxisDescriptor()
        ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 100, 400, 900
        ax.map = list(p.weight_map)
        ds.addAxis(ax)
        design = dict(p.weight_map)
        for style, w in MASTERS.items():
            s = SourceDescriptor()
            s.path, s.styleName, s.familyName = str(merged[style]), style, p.family
            s.location = {"Weight": design[w]}
            ds.addSource(s)
        for i, style in enumerate(INSTANCES):
            inst = InstanceDescriptor()
            inst.familyName, inst.styleName = p.family, style
            inst.location = {"Weight": design[(i + 1) * 100]}
            ds.addInstance(inst)
        ds.write(work / "world.designspace")
        font, _, _ = build_variable(str(work / "world.designspace"))
        font.save(target)
    stamp_copyright(target)
    out = TTFont(target)
    print(f"{target.relative_to(ROOT)}: {len(out.getGlyphOrder())} glyphs, {len(out.getBestCmap())} characters, "
          f"{target.stat().st_size / 1e6:.1f} MB")
    return target


if __name__ == "__main__":
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].split(",")
    build(sys.argv[1], only)

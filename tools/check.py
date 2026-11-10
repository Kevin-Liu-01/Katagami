#!/usr/bin/env python3
"""Check that the committed fonts are what README.md and SPEC.md say they are.

    .venv/bin/python -B tools/check.py

It reads fonts/, README.md and SPEC.md, tests a few pure helpers of the build
code, and writes nothing. It builds nothing and takes about twenty seconds.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from kerf_build.fontops import VERSION  # noqa: E402
from kerf_build.outline import inside_out, polygon_area, sound  # noqa: E402

MEMBERS = ("sans", "round", "text", "serif", "mono")
WIDE, MONO, CJK = (100, 400, 900), (100, 400, 700), (100, 100, 900)  # the weight axis: lowest, default, highest
# file under fonts/ -> glyphs, characters, weight axis, named instances
EXPECT = {
    "sans/KatagamiSans[wght].ttf": (15211, 8346, WIDE, 9), "sans/KatagamiSans-Italic[wght].ttf": (15212, 8346, WIDE, 9),
    "round/KatagamiRound[wght].ttf": (15211, 8346, WIDE, 9), "round/KatagamiRound-Italic[wght].ttf": (15212, 8346, WIDE, 9),
    "text/KatagamiText[wght].ttf": (15212, 8346, WIDE, 9), "text/KatagamiText-Italic[wght].ttf": (15212, 8346, WIDE, 9),
    "serif/KatagamiSerif[wght].ttf": (15212, 8346, WIDE, 9), "serif/KatagamiSerif-Italic[wght].ttf": (15212, 8346, WIDE, 9),
    "mono/KatagamiMono[wght].ttf": (4123, 3378, MONO, 7), "mono/KatagamiMono-Italic[wght].ttf": (4123, 3378, MONO, 7),
    "cjk/KatagamiCJKSC[wght].ttf": (8865, 8138, CJK, 9), "cjk/KatagamiCJKSC-Italic[wght].ttf": (8866, 8138, CJK, 9),
    "cjk/KatagamiCJKTC[wght].ttf": (15239, 14524, CJK, 9), "cjk/KatagamiCJKTC-Italic[wght].ttf": (15240, 14524, CJK, 9),
    "cjk/KatagamiCJKJP[wght].ttf": (9107, 7729, CJK, 9), "cjk/KatagamiCJKJP-Italic[wght].ttf": (9108, 7729, CJK, 9),
    "cjk/KatagamiCJKKR[wght].ttf": (15195, 12792, CJK, 9), "cjk/KatagamiCJKKR-Italic[wght].ttf": (15196, 12792, CJK, 9),
}


def roman(key: str) -> str:
    return f"{key}/Katagami{key.title()}[wght].ttf"


def italic(key: str) -> str:
    return f"{key}/Katagami{key.title()}-Italic[wght].ttf"


def fonts() -> list[str]:
    """Every file in fonts/ against EXPECT and the version in kerf_build/fontops.py."""
    bad = []
    on_disk = {p.relative_to(ROOT / "fonts").as_posix() for p in (ROOT / "fonts").glob("*/*.ttf")}
    bad += [f"fonts/{name}: it is in fonts/ or in EXPECT, and not in both" for name in sorted(on_disk ^ set(EXPECT))]
    version = {"name 5": f"Version {VERSION[0]}.{VERSION[1]:03d}", "head.fontRevision": VERSION[0] + VERSION[1] / 1000}
    for name in sorted(on_disk & set(EXPECT)):
        glyphs, characters, axis, instances = EXPECT[name]
        with TTFont(ROOT / "fonts" / name, lazy=True) as font:
            axes = font["fvar"].axes
            got = {"glyphs": font["maxp"].numGlyphs, "characters": len(font.getBestCmap()), "axes": [a.axisTag for a in axes],
                   "weight axis": (axes[0].minValue, axes[0].defaultValue, axes[0].maxValue), "named instances": len(font["fvar"].instances),
                   "name 5": font["name"].getDebugName(5), "head.fontRevision": round(font["head"].fontRevision, 3)}
        want = {"glyphs": glyphs, "characters": characters, "axes": ["wght"], "weight axis": axis, "named instances": instances, **version}
        bad += [f"fonts/{name}: {k} is {got[k]!r}, expected {want[k]!r}" for k in want if got[k] != want[k]]
    return bad


def documents() -> list[str]:
    """Every count README.md and SPEC.md give, against EXPECT."""
    bad = []
    readme, spec = (ROOT / "README.md").read_text(), (ROOT / "SPEC.md").read_text()
    num = lambda s: int(s.replace(",", ""))  # noqa: E731

    def check(where: str, pattern: str, text: str, expected: tuple) -> None:
        m = re.search(pattern, text)
        if not m:
            bad.append(f"{where}: the sentence or table row this check reads is gone or reworded")
        elif tuple(num(g) for g in m.groups()) != expected:
            bad.append(f"{where}: the document says {tuple(num(g) for g in m.groups())}, the fonts have {expected}")

    for key in MEMBERS:
        r, i = EXPECT[roman(key)], EXPECT[italic(key)]
        check(f"README.md Members, Katagami {key.title()}", rf"\| \*\*Katagami {key.title()}\*\* \|[^|]*\| (\d+) to (\d+) \| ([\d,]+) and ([\d,]+) \|",
              readme, (r[2][0], r[2][2], r[0], i[0]))
    check("README.md, characters of a proportional member", r"Each proportional member maps ([\d,]+) characters", readme, (EXPECT[roman("sans")][1],))
    check("README.md, characters of the CJK companions", r"Katagami CJK SC \(([\d,]+) characters\), TC \(([\d,]+)\), JP \(([\d,]+)\) and KR \(([\d,]+)\)",
          readme, tuple(EXPECT[f"cjk/KatagamiCJK{c}[wght].ttf"][1] for c in ("SC", "TC", "JP", "KR")))
    check("SPEC.md Coverage, Glyphs", r"\| Glyphs \| ([\d,]+) in Sans and Round and ([\d,]+) in Text and Serif[^|]*\| ([\d,]+) each \| ([\d,]+) each",
          spec, (EXPECT[roman("sans")][0], EXPECT[roman("text")][0], EXPECT[italic("sans")][0], EXPECT[roman("mono")][0]))
    check("SPEC.md Coverage, Characters", r"\| Characters \| ([\d,]+) \| ([\d,]+) \| ([\d,]+) each \|",
          spec, (EXPECT[roman("sans")][1], EXPECT[italic("sans")][1], EXPECT[roman("mono")][1]))
    return bad


SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]  # counter-clockwise, area 10,000
INNER = [(10, 10), (90, 10), (90, 90), (10, 90)]   # the same square drawn in by 10 units


class Outline(unittest.TestCase):
    """kerf_build/outline.py: the tests that decide whether a thinned or emboldened contour is kept."""

    def test_polygon_area_is_signed(self):
        self.assertEqual(polygon_area(SQUARE), 10000.0)
        self.assertEqual(polygon_area(SQUARE[::-1]), -10000.0)
        self.assertEqual(polygon_area([(0, 0), (1, 1)]), 0.0)

    def test_inside_out_is_the_area_wound_the_other_way(self):
        self.assertAlmostEqual(inside_out(SQUARE), 0.0, places=3)
        self.assertAlmostEqual(inside_out(SQUARE[::-1]), 0.0, places=3)
        # a corner pulled through itself: two triangles of 400 units, one wound each way
        lobed = [(0, 0), (100, 0), (100, 100), (140, 140), (140, 100), (100, 140), (100, 100), (0, 100)]
        self.assertAlmostEqual(inside_out(lobed), 400.0, places=3)

    def test_sound_keeps_a_contour_that_stays_inside_itself(self):
        self.assertTrue(sound(SQUARE, INNER))
        self.assertTrue(sound(SQUARE, [(20, 20), (70, 20), (70, 70), (20, 70)]))  # a quarter of the area
        self.assertTrue(sound([(0, 0), (1, 1)], INNER))  # nothing to compare with

    def test_sound_refuses_a_contour_that_turned_shrank_or_left(self):
        self.assertFalse(sound(SQUARE, INNER[::-1]))  # turned the other way round
        self.assertFalse(sound(SQUARE, [(40, 40), (60, 40), (60, 60), (40, 60)]))  # under a fifth of the area
        self.assertFalse(sound(SQUARE, [(60, 60), (140, 60), (140, 140), (60, 140)]))  # moved outside itself
        self.assertFalse(sound(SQUARE, INNER, floor=7000))  # under the floor
        self.assertFalse(sound(SQUARE, [(10, 10), (90, 10), (90, 90), (120, 120), (120, 90), (90, 120), (90, 90), (10, 90)]))  # a new lobe


class SiteHelpers(unittest.TestCase):
    """tools/build_site.py: the code point runs the web stylesheet and the glyph tables are written from."""

    @classmethod
    def setUpClass(cls):
        try:
            import build_site
        except (Exception, SystemExit) as error:
            raise unittest.SkipTest(f"tools/build_site.py did not import here: {error!r}")
        cls.site = build_site

    @staticmethod
    def points(css: str) -> set[int]:
        out = set()
        for run in filter(None, css.split(",")):
            lo, _, hi = run.removeprefix("U+").partition("-")
            out |= set(range(int(lo, 16), int(hi or lo, 16) + 1))
        return out

    def test_unicode_range_joins_runs(self):
        self.assertEqual(self.site.unicode_range({0x41, 0x42, 0x43, 0x61}), "U+41-61")
        self.assertEqual(self.site.unicode_range({0x41, 0x140}), "U+41-140")
        self.assertEqual(self.site.unicode_range({0x41, 0x141}), "U+41,U+141")  # a gap of 256 or more is not joined
        self.assertEqual(self.site.unicode_range(set()), "")

    def test_unicode_range_never_claims_another_face(self):
        avoid = set(range(0x900, 0x980))
        css = self.site.unicode_range({0x8FE, 0x8FF, 0x980, 0x981}, avoid=avoid)
        self.assertEqual(css, "U+8FE-8FF,U+980-981")
        self.assertFalse(self.points(css) & avoid)
        self.assertEqual(self.site.unicode_range({0x41, 0x42, 0x43, 0x61}, avoid={0x50}), "U+41-43,U+61")

    def test_cmap_runs_round_trip(self):
        chars = [(65, "A", 1200, "a"), (66, "B", 1200, "a"), (70, "F", 1100, "b"), (71, "G", 1300, "a")]
        packed = self.site.cmap_runs(chars, ["a", "b"])
        self.assertEqual(packed, {"runs": [65, 2, 3, 2], "kinds": [0, 2, 1, 1, 0, 1]})
        cps, end = [], 0
        for gap, length in zip(packed["runs"][::2], packed["runs"][1::2]):
            cps += range(end + gap, end + gap + length)
            end += gap + length
        self.assertEqual(cps, [c[0] for c in chars])
        self.assertEqual(self.site.cmap_runs([], ["a"]), {"runs": [], "kinds": []})


class DottedCircle(unittest.TestCase):
    """tools/build_sans.py: Katagami Serif's dotted circle takes its dots from the stem kept before the serifs."""

    @classmethod
    def setUpClass(cls):
        try:
            import build_sans
            import ufoLib2
        except (Exception, SystemExit) as error:
            raise unittest.SkipTest(f"tools/build_sans.py did not import here: {error!r}")
        cls.build_sans, cls.ufoLib2 = build_sans, ufoLib2

    def master(self, serifed_i: float, kept_stem: float):
        """A master with an x-height of 1020, an o, and an i that measures `serifed_i` with its serifs."""
        f = self.ufoLib2.Font()
        f.info.unitsPerEm, f.info.xHeight = 2048, 1020
        for name, x0, x1, width in (("idotless", 60, 60 + serifed_i, serifed_i + 120), ("o", 80, 1080, 1160)):
            g = f.newGlyph(name)
            g.width = width
            c = self.ufoLib2.objects.Contour()
            for x, y in ((x0, 0), (x1, 0), (x1, 1020), (x0, 1020)):
                c.points.append(self.ufoLib2.objects.Point(x, y, "line"))
            g.appendContour(c)
        f.lib[self.build_sans.SERIF_STEM_KEY] = kept_stem  # what cut_serifs keeps, before scale_outlines
        return f

    def test_dots_follow_the_stem_before_the_serifs(self):
        fonts = {"Thin": self.master(239, 44 / 0.96), "Regular": self.master(467, 173 / 0.96), "Black": self.master(680, 386 / 0.96)}
        self.build_sans.dotted_circle(fonts, 0.96)
        for style, dot in (("Thin", 61), ("Regular", 121), ("Black", 181)):
            g = fonts[style]["uni25CC"]
            xs = [p.x for p in g.contours[0].points]
            bounds = g.getBounds(fonts[style])
            self.assertAlmostEqual(max(xs) - min(xs), dot, delta=1, msg=style)
            self.assertAlmostEqual(bounds.yMax - bounds.yMin, 1020, delta=1, msg=style)

def main() -> int:
    bad = fonts() + documents()
    for line in bad:
        print("FAIL", line, flush=True)
    print(f"fonts and documents: {len(EXPECT)} files checked, {len(bad)} mismatches", flush=True)
    tests = unittest.main(module=__name__, argv=[sys.argv[0]], exit=False).result
    return 0 if not bad and tests.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

"""Build a proportional Katagami member from Inter's Thin, Regular and Black masters.

    python tools/build_sans.py sans|round|text|serif [--italic]

With --italic the member's Italic is built from Inter Italic's masters. They
are stood upright first (sheared back by Inter's 9.4 degrees about half the
x-height), so every transform below meets vertical stems as it does in the
roman. Every glyph whose design then differs from the roman's takes the
roman's (`romanize`), and the masters are slanted again at the end about the
member's own half x-height.

Inter -> profile, in order (each step only where the profile asks for it):
  1. Inter alternates promoted to the default (square punctuation, profile picks)
  2. quarter arcs squared or rounded (planned on Regular)
  3. bowl-to-stem notches and m's dip filled, g, y and t ends redrawn
  4. per-glyph widths changed with stems held, composites re-seated
  5. sidebearings adjusted
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import sys
import unicodedata
from pathlib import Path

from ufoLib2.objects import Contour, Point

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import (  # noqa: E402
    ITALIC_MATCH, MASTERS, ROOT, assign_categories, combining_double_acute, decompose_transformed, design_distances,
    dot_size, dotted_circle_anchors, draw_dotted_circle, erase_open_corners, italic_style, load_inter_masters, promote_alternates, reflow_composites,
    resize_glyph, respace, romanize, set_names, shear, slant_tangent, snapshot, stem, swap_glyph_outlines,
)
from kerf_build.outline import (  # noqa: E402
    XMap,
    apply_squaring, embolden_x, embolden_y, handles, keep_stroke, plan_corners, plan_squaring, round_corners, straighten_runs,
)
from kerf_build.profiles import PROFILES, Profile  # noqa: E402

FEATURES = ROOT / "vendor" / "inter" / "src" / "features"
KEEP_ROUND = ("circle", "circled", "ring", "degree", "bullet", "dotted")
# Share of each join fill a master gets. Inter's Thin joins barely notch, so
# moving their corners leaves a lump where the curve meets the stem; the fill
# grows from nothing at Thin to its full share at Regular and Black.
JOIN_BY_MASTER = {"Thin": 0.0, "Regular": 1.0, "Black": 1.0}
# Squaring moves a counter further than the edge outside it, and eases curves
# into stems; at Thin the stroke between them can fall to a few units. Thin's
# squared arcs give back what they must to keep this share of its stem.
THIN_FLOOR = 0.8
TIGHT_RADIUS = 1.6  # in stems: arcs tighter than this square in proportion to their radius

# After an alternate becomes the default, its feature switches back to
# Inter's original, so its label has to say so.
SWAPPED_LABELS = {
    "cv01-one.fea": ("Alternate one", "Short-flag one"),
    "cv02-four.fea": ("Open four", "Closed four"),
    "cv03-six.fea": ("Open six", "Curved six"),
    "cv04-nine.fea": ("Open nine", "Curved nine"),
    "cv09-three.fea": ("Flat-top three", "Round-top three"),
    "cv10-g-spur.fea": ("Capital G with spur", "Capital G without spur"),
    "cv12-compact-f.fea": ("Compact f", "Wide f"),
    "cv16-a-tail.fea": ("Lower-case a with tail", "Lower-case a without tail"),
    "cv05-l-tail.fea": ("Lower-case L with tail", "Lower-case L without tail"),
    "cv08-i-serif.fea": ("Upper-case i with serif", "Upper-case i without serif"),
}
DIGIT_FILES = {"cv02-four.fea", "cv03-six.fea", "cv04-nine.fea", "cv09-three.fea"}


def relabel_features(fonts, promoted) -> None:
    for f in fonts.values():
        text = f.features.text
        for fea in promoted:
            if fea in SWAPPED_LABELS:
                old, new = SWAPPED_LABELS[fea]
                text = text.replace(f'name "{old}";', f'name "{new}";')
        if DIGIT_FILES <= set(promoted):
            text = text.replace('name "Open digits";', 'name "Curved digits";')
        f.features.text = text
INSTANCES = ["Thin", "ExtraLight", "Light", "Regular", "Medium", "SemiBold", "Bold", "ExtraBold", "Black"]


def is_upper(font, name: str) -> bool:
    g = font[name]
    if g.unicodes:
        return unicodedata.category(chr(g.unicodes[0])) == "Lu"
    return name[:1].isupper()


def keeps_round(font, name: str) -> bool:
    if any(k in name.lower() for k in KEEP_ROUND):
        return True
    g = font[name]
    return any(0x25A0 <= u <= 0x25FF or 0x2460 <= u <= 0x24FF for u in g.unicodes)


def promote_square_punctuation(fonts) -> None:
    ref = fonts["Regular"]
    pairs = [(g.name[: -len(".ss07")], g.name) for g in ref if g.name.endswith(".ss07")]
    pairs = [(a, b) for a, b in pairs if a in ref]
    for f in fonts.values():
        for a, b in pairs:
            swap_glyph_outlines(f, a, b)
        f.features.text = f.features.text.replace('name "Square punctuation";', 'name "Round punctuation";')


def shape_curves(fonts, p: Profile) -> None:
    ref = fonts["Regular"]
    floor = THIN_FLOOR * stem(fonts["Thin"])
    for g in ref:
        if not g.contours or keeps_round(ref, g.name):
            continue
        plan = plan_squaring(g, TIGHT_RADIUS * stem(ref))
        if not plan:
            continue
        s = p.square_upper if is_upper(ref, g.name) else p.square_lower
        for style, f in fonts.items():
            before = handles(f[g.name], plan) if style == "Thin" else None
            apply_squaring(f[g.name], plan, s, min(0.9, s * p.counter_boost), p.join_ease)
            if before is not None:
                keep_stroke(f[g.name], plan, before, floor)


def _meet(a, b, y: float) -> tuple[float, float]:
    """Where the line through a and b reaches height y."""
    return a.x + (b.x - a.x) * (y - a.y) / (b.y - a.y), y


def _turn_fraction(p: Profile) -> float:
    """Handle fraction of a redrawn quarter turn: Inter's 0.60, squared like the lowercase."""
    return min(0.85, 0.60 + 0.40 * p.square_lower * p.counter_boost)


def _set(pt, xy) -> None:
    pt.x, pt.y = xy


def _thirds(pts, a: int, c1: int, c2: int, b: int) -> None:
    """Handles c1 and c2 at a third and two thirds of the way from a to b: a straight curve."""
    A, B = pts[a], pts[b]
    _set(pts[c1], (A.x + (B.x - A.x) / 3, A.y + (B.y - A.y) / 3))
    _set(pts[c2], (A.x + 2 * (B.x - A.x) / 3, A.y + 2 * (B.y - A.y) / 3))


G_REACH = 0.95  # how far the g tail reaches left of the bottom's centre, as a share of the right side's reach


def redraw_tails(fonts, p: Profile) -> None:
    """Redraw the ends of g, y and t (and a's foot where it has one). Point counts never change.

    g: the tail is the right side's turn into the bottom, mirrored about the
    bottom's centre, drawn in to G_REACH of its width so the end sits inside
    the bowl, and cut level at Inter's terminal height. The curl matches the
    bowl side's squaring and the cut is square to the stroke. The stroke
    keeps its width to the cut.

    y: the tail comes down the diagonal, turns through a quarter turn and
    runs level to a vertical cut. t: the hook runs level from its bottom
    to a vertical cut. Both ends keep Inter's position and thickness.

    The y turns' handles sit at the profile's squaring, so Sans turns
    square, Round less so and Text round.
    """
    k = _turn_fraction(p)
    ref = fonts["Regular"]

    # g: the level cut between the inner end (a curve corner) and the outer end (a line)
    pts = ref["g"].contours[0].points
    n = len(pts)
    cut = next(i for i, q in enumerate(pts) if q.type == "line" and pts[i - 1].type == "curve"
               and not q.smooth and not pts[i - 1].smooth and q.y < 0 and pts[i - 1].y < 0)
    for f in fonts.values():
        pts = f["g"].contours[0].points
        P = lambda i: pts[i % n]  # noqa: E731
        y = (P(cut - 1).y + P(cut).y) / 2
        y += p.g_rise * (P(cut + 6).y - y)  # toward the top of the curl
        # outer edge: the right side's turn into the bottom, mirrored about the bottom's centre
        # and cut where it reaches the terminal height
        bottom = P(cut + 3)
        mirror = lambda q, c: (c.x - G_REACH * (q.x - c.x), q.y)  # noqa: E731
        arc = [mirror(P(cut + 6), bottom), mirror(P(cut + 5), bottom), mirror(P(cut + 4), bottom), (bottom.x, bottom.y)]
        t = _crossing(arc, lambda q: q[1] - y, 0.5, 0.0, 1.0)
        _, low = _split(arc, t)
        for i, xy in zip((cut, cut + 1, cut + 2), low[:3]):
            _set(P(i), xy)
        # inner edge: the counter's turn, mirrored the same way, from its bottom up to the cut
        floor = P(cut - 4)
        arc = [(floor.x, floor.y), mirror(P(cut - 5), floor), mirror(P(cut - 6), floor), mirror(P(cut - 7), floor)]
        t = _crossing(arc, lambda q: q[1] - y, 0.5, 0.0, 1.0)
        high, _ = _split(arc, t)
        for i, xy in zip((cut - 3, cut - 2, cut - 1), high[1:]):
            _set(P(i), xy)

    # y: the cut runs from a line point (inner end) to the next line point (outer end)
    pts = ref["y"].contours[0].points
    n = len(pts)
    o = next(i for i, q in enumerate(pts) if q.type == "line" and pts[i - 1].type == "line"
             and pts[i - 2].type == "curve" and pts[(i + 3) % n].type == "curve" and q.y < 0 and pts[i - 1].y < 0)
    for f in fonts.values():
        pts = f["y"].contours[0].points
        P = lambda i: pts[i % n]  # noqa: E731
        end_out, end_in, bottom = P(o), P(o - 1), P(o + 3)
        x_end = (end_out.x + end_in.x) / 2
        thick = math.hypot(end_out.x - end_in.x, end_out.y - end_in.y)
        y_b, y_in = bottom.y, bottom.y + thick
        # outer edge: down the right arm's diagonal, a quarter turn, level to the cut
        arm_top, arm_end = P(o + 7), P(o + 6)
        kx, ky = _meet(arm_top, arm_end, y_b)
        reach = math.hypot(kx - arm_end.x, ky - arm_end.y)
        bx = max(kx - reach, x_end + 0.3 * (kx - x_end))
        _set(bottom, (bx, y_b))
        _set(P(o + 4), (bx + k * (kx - bx), y_b))
        _set(P(o + 5), (arm_end.x + k * (kx - arm_end.x), arm_end.y + k * (ky - arm_end.y)))
        _set(end_out, (x_end, y_b))
        _thirds(pts, o % n, (o + 1) % n, (o + 2) % n, (o + 3) % n)
        # inner edge: down the tail's upper edge, a quarter turn, level to the cut
        upper_top, upper_end = P(o - 6), P(o - 5)
        kx, ky = _meet(upper_top, upper_end, y_in)
        reach = math.hypot(kx - upper_end.x, ky - upper_end.y)
        ix = max(kx - reach, x_end + 0.3 * (kx - x_end))
        _set(P(o - 4), (upper_end.x + k * (kx - upper_end.x), upper_end.y + k * (ky - upper_end.y)))
        _set(P(o - 3), (ix + k * (kx - ix), y_in))
        _set(P(o - 2), (ix, y_in))
        _set(end_in, (x_end, y_in))

    # t, and a where it has a foot: the hook's cut runs from a curve corner (outer end)
    # to a line point (inner end) low on the right
    base = next(c.baseGlyph for c in ref["t"].components) if ref["t"].components else "t"
    for name in (base, "a"):
        pts = ref[name].contours[0].points
        n = len(pts)
        e = next((i for i, q in enumerate(pts) if q.type == "curve" and not q.smooth and pts[(i + 1) % n].type == "line"
                  and pts[(i + 2) % n].type is None and q.y < ref.info.xHeight * 0.3
                  and q.x > ref[name].getBounds(ref).xMax - 0.5 * stem(ref)), None)
        if e is None:
            continue
        for f in fonts.values():
            pts = f[name].contours[0].points
            P = lambda i: pts[i % n]  # noqa: E731
            end_out, end_in = P(e), P(e + 1)
            x_end = (end_out.x + end_in.x) / 2
            _set(end_out, (x_end, P(e - 3).y))
            _set(end_in, (x_end, P(e + 4).y))
            _thirds(pts, (e - 3) % n, (e - 2) % n, (e - 1) % n, e % n)
            _thirds(pts, (e + 1) % n, (e + 2) % n, (e + 3) % n, (e + 4) % n)


def lowercase_names(font) -> set[str]:
    """Lowercase letters and the unencoded parts only lowercase letters are built from."""
    cat = lambda g: unicodedata.category(chr(g.unicodes[0])) if g.unicodes else ""  # noqa: E731
    lower = {g.name for g in font if g.contours and cat(g) == "Ll"}
    used_by = {}
    for g in font:
        for c in g.components:
            used_by.setdefault(c.baseGlyph, set()).add(cat(g))
    return lower | {name for name, cats in used_by.items()
                    if cats - {"", "Co"} == {"Ll"} and not font[name].unicodes and font[name].contours}


def lower_xheight(fonts, k: float) -> None:
    """Scale the lowercase between the baseline and the x-height by k.

    Everything above the x-height (ascenders, dots, overshoots) moves down by
    the same amount, so curves that cross the x-height stay whole; descenders
    stay. Accents on a lowered letter move down with its top anchor.
    """
    if k == 1:
        return
    ref = fonts["Regular"]
    lower = lowercase_names(ref)
    for f in fonts.values():
        xh = f.info.xHeight
        drop = (1 - k) * xh
        y_of = lambda y: y * k if 0 <= y <= xh else (y - drop if y > xh else y)  # noqa: E731
        moved: dict[str, float] = {}
        for name in lower:
            g = f[name]
            for c in g.contours:
                for pt in c.points:
                    pt.y = y_of(pt.y)
            for a in g.anchors:
                old = a.y
                a.y = y_of(a.y)
                if a.name == "top":
                    moved[name] = a.y - old
        for g in f:
            if not g.components or g.contours or g.components[0].baseGlyph not in moved:
                continue
            for comp in g.components[1:]:
                t = list(comp.transformation)
                if f[comp.baseGlyph].width == 0 and t[5] >= 0:
                    t[5] += moved[g.components[0].baseGlyph]
                    comp.transformation = tuple(t)
        f.info.xHeight = round(xh * k)


def slant_t(fonts, share: float) -> None:
    """Cut the top of t's stem at a slant: its left corner drops `share` stems."""
    if not share:
        return
    ref = fonts["Regular"]
    base = next(c.baseGlyph for c in ref["t"].components) if ref["t"].components else "t"
    pts = ref[base].contours[0].points
    top = max(p.y for p in pts)
    i = min((k for k, p in enumerate(pts) if p.type and abs(p.y - top) < 1), key=lambda k: pts[k].x)
    for f in fonts.values():
        f[base].contours[0].points[i].y -= share * stem(f)


TWO_NAMES = ("two", "two.sups", "two.subs", "two.numr", "two.dnom", "two.sinf")


def square_two(fonts, share: float) -> None:
    """Square the 2 further: its bowl and the spine that turns from the bowl
    into the diagonal move `share` more of the way toward their corners. The
    spine is not a quarter turn, so it is planned with a wider angle than other
    arcs; the plan is made on Regular, as every squaring is."""
    if not share:
        return
    ref = fonts["Regular"]
    for name in TWO_NAMES:
        if name not in ref or not ref[name].contours:
            continue
        plan = plan_squaring(ref[name], 0.0, max_cos=0.8)
        for f in fonts.values():
            apply_squaring(f[name], plan, share, share, 1.0)


def straighten_q(fonts) -> None:
    """Q's tail is straight: the two points where each side of the tail crosses
    the bowl go back onto the line between the tail's ends, which the width
    transforms had bent by up to 7 degrees."""
    for f in fonts.values():
        for name in ("Q",):
            if name in f:
                for c in f[name].contours:
                    straighten_runs(c)


SMALL_CAP_TRACK = 0.03  # of the em, added around each small capital


def small_caps(fonts) -> None:
    """Small capitals for every lowercase letter with a capital, as smcp and c2sc.

    Inter has none (its 13 .sc glyphs are phonetic letters). Each small cap is
    its capital scaled to the x-height, emboldened back to the lowercase stem
    (and 0.4 of that on horizontal strokes), and tracked a little wider.
    Accented small caps are built like the accented lowercase: the small-cap
    base with the same marks, moved by the difference in top anchors.
    """
    ref = fonts["Regular"]
    cmap = {u: g.name for g in ref for u in g.unicodes}
    pairs = {}
    for g in ref:
        if not g.unicodes or unicodedata.category(chr(g.unicodes[0])) != "Ll":
            continue
        up = chr(g.unicodes[0]).upper()
        if len(up) == 1 and ord(up) in cmap and cmap[ord(up)] != g.name:
            pairs[g.name] = cmap[ord(up)]
    drawn = [lc for lc, uc in pairs.items() if ref[uc].contours and not ref[uc].components]
    built = [lc for lc in pairs if lc not in drawn and ref[lc].components and ref[lc].components[0].baseGlyph in drawn
             and all(not ref[c.baseGlyph].width for c in ref[lc].components[1:])]
    anchor = lambda g, name: next(((a.x, a.y) for a in g.anchors if a.name == name), None)  # noqa: E731
    for f in fonts.values():
        upm, xh, cap = f.info.unitsPerEm, f.info.xHeight, f.info.capHeight
        lc_stem = stem(f)
        b = f["I"].getBounds(f)
        uc_stem = b.xMax - b.xMin
        dx = lc_stem - uc_stem * xh / cap
        dy = 0.4 * dx  # less on horizontals, or Black's bars close the counters of E and S
        k = (xh - dy) / cap
        track = SMALL_CAP_TRACK * upm
        for lc in drawn:
            src = f[pairs[lc]]
            g = f.newGlyph(f"{lc}.smcp")
            for c in src.contours:
                g.appendContour(copy.deepcopy(c))
            for c in g.contours:
                for pt in c.points:
                    pt.x, pt.y = pt.x * k, pt.y * k
            embolden_x(g, dx)
            embolden_y(g, dy)
            for c in g.contours:
                for pt in c.points:
                    pt.x, pt.y = pt.x + dx / 2 + track / 2, pt.y + dy / 2
            for a in src.anchors:
                g.appendAnchor({"name": a.name, "x": a.x * k + dx / 2 + track / 2, "y": a.y * k + dy / 2})
            g.width = round(src.width * k + dx + track)
        for lc in built:
            src = f[lc]
            base = src.components[0].baseGlyph
            g = f.newGlyph(f"{lc}.smcp")
            g.width = f[f"{base}.smcp"].width
            old, new = anchor(f[base], "top"), anchor(f[f"{base}.smcp"], "top")
            shift = (new[0] - old[0]) if old and new else (g.width - f[base].width) / 2
            for i, c in enumerate(src.components):
                comp = copy.deepcopy(c)
                if i == 0:
                    comp.baseGlyph = f"{base}.smcp"
                else:
                    t = list(comp.transformation)
                    t[4] += shift
                    comp.transformation = tuple(t)
                g.components.append(comp)
    made = drawn + built
    lc_names = " ".join(made)
    sc_names = " ".join(f"{lc}.smcp" for lc in made)
    # one small cap per capital: dotless i, long s and final sigma share theirs with i, s and sigma
    upper = {}
    for lc in made:
        upper.setdefault(pairs[lc], f"{lc}.smcp")
    uc_names = " ".join(upper)
    uc_sc_names = " ".join(upper.values())
    for f in fonts.values():
        f.features.text += f"""

# Small capitals, generated by tools/build_sans.py
@kerfLowerSC = [{lc_names}];
@kerfSmallCaps = [{sc_names}];
@kerfUpperSC = [{uc_names}];
@kerfUpperSmallCaps = [{uc_sc_names}];
feature smcp {{
  sub @kerfLowerSC by @kerfSmallCaps;
}} smcp;
feature c2sc {{
  sub @kerfUpperSC by @kerfUpperSmallCaps;
}} c2sc;
"""


def scale_outlines(fonts, k: float) -> None:
    """Scale every glyph, advance, anchor, offset and kerning value by k about the origin.

    The vertical metrics that set the line height stay, so the letters get
    smaller on the same line spacing.
    """
    if k == 1:
        return
    for f in fonts.values():
        for g in f:
            for c in g.contours:
                for pt in c.points:
                    pt.x, pt.y = pt.x * k, pt.y * k
            for a in g.anchors:
                a.x, a.y = a.x * k, a.y * k
            for comp in g.components:
                t = list(comp.transformation)
                t[4], t[5] = t[4] * k, t[5] * k
                comp.transformation = tuple(t)
            g.width = round(g.width * k)
        for pair, value in list(f.kerning.items()):
            f.kerning[pair] = round(value * k)
        f.info.xHeight = round(f.info.xHeight * k)
        f.info.capHeight = round(f.info.capHeight * k)


def find_valleys(glyph, xheight: float) -> list[tuple[int, int, int]]:
    """Dips between two arches below the x-height: m's, where its second arch leaves the middle stem.

    A dip is a curve corner, a short level step, and a curve rising again on
    the other side. Returns (contour, corner, step end).
    """
    out = []
    for ci, c in enumerate(glyph.contours):
        pts = c.points
        n = len(pts)
        for i, q in enumerate(pts):
            r = pts[(i + 1) % n]
            if q.type != "curve" or q.smooth or r.type != "line" or pts[(i + 2) % n].type is not None:
                continue
            if abs(q.y - r.y) > 2 or abs(q.x - r.x) > 80 or not 0.5 * xheight < q.y < 0.95 * xheight:
                continue
            if pts[(i - 1) % n].y > q.y and pts[(i + 2) % n].y > r.y:
                out.append((ci, i, (i + 1) % n))
    return out


def fill_valleys(fonts, amount: float) -> None:
    """Raise each dip `amount` of the way to the x-height.

    The curves on both sides are squashed vertically into the shorter span,
    so their handles keep their direction and the arches stay smooth.
    """
    if not amount:
        return
    ref = fonts["Regular"]
    plans = {g.name: find_valleys(g, ref.info.xHeight) for g in ref
             if g.contours and g.unicodes and unicodedata.category(chr(g.unicodes[0])) == "Ll"}
    plans = {k: v for k, v in plans.items() if v}
    for style, f in fonts.items():
        xh = f.info.xHeight
        for name, valleys in plans.items():
            for ci, a, b in valleys:
                pts = f[name].contours[ci].points
                n = len(pts)
                old = pts[a].y
                new = old + (xh - old) * amount * JOIN_BY_MASTER[style]
                for corner, handle, far in ((a, (a - 1) % n, (a - 3) % n), (b, (b + 1) % n, (b + 3) % n)):
                    top = pts[far].y
                    h = pts[handle]
                    h.y = new + (h.y - old) * (top - new) / (top - old)
                    pts[corner].y = new


def find_notches(glyph, xheight: float) -> list[tuple[int, int, list[int], float, int]]:
    """Corners where a bowl meets a stem through a notch.

    A notch is a corner where a curve arrives, followed by at most one short
    step, then a near-vertical stem edge running to the baseline or the
    x-height (Inter's bowl-to-stem joins in a, u, n, h and the rest). Returns
    (contour, corner, points to move with the handle last, baseline or
    x-height, the curve's other end).
    """
    out = []
    for ci, c in enumerate(glyph.contours):
        pts = c.points
        n = len(pts)
        for i, p in enumerate(pts):
            if p.type != "curve" or p.smooth:
                continue
            for direction in (1, -1):
                # walk along line segments away from the curve
                chain, k = [i], i
                for _ in range(2):
                    j = (k + direction) % n
                    seg_end_type = pts[j].type if direction == 1 else pts[k].type
                    if pts[j].type is None or seg_end_type != "line":
                        break
                    chain.append(j)
                    k = j
                if len(chain) < 2:
                    continue
                end = pts[chain[-1]]
                prev = pts[chain[-2]]
                vertical = abs(end.x - prev.x) < 0.1 * abs(end.y - prev.y)
                # the stem edge runs down past the baseline or up past the x-height
                ref = 0.0 if end.y < p.y else xheight
                reaches = end.y <= 2 if ref == 0.0 else end.y >= xheight - 2
                step_ok = len(chain) == 2 or abs(pts[chain[1]].y - p.y) < 2
                # a stem edge ends in the stem's flat end; a terminal (the arm of r) ends in a curve
                cap = pts[(chain[-1] + direction) % n]
                capped = cap.type is not None and abs(cap.y - end.y) < 2 and (direction == 1 and cap.type == "line" or direction == -1 and end.type == "line")
                if vertical and reaches and step_ok and capped and abs(ref - p.y) > 20:
                    handle = (i - direction) % n  # the curve's handle at the corner
                    far = (i - 3 * direction) % n  # the curve's other end
                    out.append((ci, i, chain[:-1] + [handle], ref, far))
    return out


def fill_notches(fonts, amount: float) -> None:
    """Move each notch corner part of the way toward its stem's end.

    Inter's heavy weights cut deep notches where bowls join stems, which
    leaves a hairline in bold a and u. Moving the corner, its step and its
    handle a share of the way toward the baseline (or x-height) shortens the
    notch and thickens the join, in proportion at every weight.
    """
    ref = fonts["Regular"]
    plans = {g.name: find_notches(g, ref.info.xHeight) for g in ref
             if g.contours and g.unicodes and unicodedata.category(chr(g.unicodes[0])) == "Ll"}
    for style, f in fonts.items():
        for name, notches in plans.items():
            g = f[name]
            share = amount * JOIN_BY_MASTER[style]
            for ci, corner, moving, ref, far in notches:
                pts = g.contours[ci].points
                dy = (ref - pts[corner].y) * share
                for k in moving:
                    pts[k].y += dy
                # the handle stays between the corner and the curve's far end,
                # so the bowl flattens into the join instead of sagging past it
                h, lo, hi = pts[moving[-1]], *sorted((pts[far].y, pts[corner].y))
                h.y = min(max(h.y, lo), hi)


def find_terminals(glyph, stem_w: float, lo: float = 6, hi: float = 30) -> list[tuple[int, int, int]]:
    """Straight cuts between two curves, angled lo..hi degrees from horizontal.

    These are the stroke ends of c, e, s, a, g and the rest. Vertical cuts
    (the arm of r) are excluded.
    Returns (contour, first end, second end).
    """
    out = []
    for ci, c in enumerate(glyph.contours):
        pts = c.points
        n = len(pts)
        for j, q in enumerate(pts):
            i = (j - 1) % n
            p = pts[i]
            if q.type != "line" or p.type != "curve" or p.smooth or q.smooth or pts[(j + 1) % n].type is not None:
                continue
            dx, dy = q.x - p.x, q.y - p.y
            if math.hypot(dx, dy) > 1.6 * stem_w or abs(dx) < 1:
                continue
            if lo <= abs(math.degrees(math.atan2(dy, dx))) % 180 <= hi or lo <= 180 - abs(math.degrees(math.atan2(dy, dx))) <= hi:
                out.append((ci, i, j))
    return out


def _point(c, t):
    """A cubic at t (t may run past 0 or 1: the curve's own continuation)."""
    u = 1 - t
    return (u**3 * c[0][0] + 3 * u * u * t * c[1][0] + 3 * u * t * t * c[2][0] + t**3 * c[3][0],
            u**3 * c[0][1] + 3 * u * u * t * c[1][1] + 3 * u * t * t * c[2][1] + t**3 * c[3][1])


def _split(c, t):
    """de Casteljau: the cubic's control points before and after t."""
    lerp = lambda a, b: (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)  # noqa: E731
    p01, p12, p23 = lerp(c[0], c[1]), lerp(c[1], c[2]), lerp(c[2], c[3])
    p012, p123 = lerp(p01, p12), lerp(p12, p23)
    m = lerp(p012, p123)
    return (c[0], p01, p012, m), (m, p123, p23, c[3])


def _crossing(c, side, near: float, lo: float, hi: float):
    """The parameter nearest `near` in lo..hi where the cubic crosses the line."""
    steps = 80
    ts = [lo + (hi - lo) * k / steps for k in range(steps + 1)]
    vals = [side(_point(c, t)) for t in ts]
    best = None
    for k in range(steps):
        if vals[k] == 0 or vals[k] * vals[k + 1] < 0:
            a, b = ts[k], ts[k + 1]
            for _ in range(50):
                mid = (a + b) / 2
                if side(_point(c, a)) * side(_point(c, mid)) <= 0:
                    b = mid
                else:
                    a = mid
            t = (a + b) / 2
            if best is None or abs(t - near) < abs(best - near):
                best = t
    return best


def level_terminals(fonts, angle: float) -> None:
    """Cut each angled terminal again, along a line at `angle` degrees.

    The new cut line passes through the old cut's midpoint, tilted the same
    way as the old cut. Each edge of the stroke is split where it crosses the
    line (de Casteljau): the edge that runs past it is trimmed, the edge that
    stops short is extended along its own curve. Both handles of each edge
    move with the split, so the edges stay pieces of their original curves
    and the stroke is not warped. An end whose curve never crosses the line
    near the old cut is left as it was.
    """
    ref = fonts["Regular"]
    sw = stem(ref)
    plans = {g.name: find_terminals(g, sw, hi=40 if g.name == "g" else 30) for g in ref
             if g.contours and g.width and g.unicodes and unicodedata.category(chr(g.unicodes[0]))[0] in "LN"}
    plans = {k: v for k, v in plans.items() if v}
    for f in fonts.values():
        for name, terms in plans.items():
            for ci, i, j in terms:
                recut(f[name].contours[ci].points, i, j, angle)


def recut(pts, i: int, j: int, angle: float, through=None) -> bool:
    """Cut the stroke end from point i to point j again, along a line at `angle`
    degrees through its midpoint (or the point `through`), tilted the way the
    old cut was: each edge is split where it crosses the line, so it stays a
    piece of its own curve. Returns False, changing nothing, where an edge is
    not a curve or does not cross the line near the old cut."""
    n = len(pts)
    P = lambda k: pts[k % n]  # noqa: E731
    if P(i - 3).type is None or P(j + 2).type is not None or P(j + 3).type != "curve":
        return False
    p, q = P(i), P(j)
    mid = through or ((p.x + q.x) / 2, (p.y + q.y) / 2)
    dx, dy = q.x - p.x, q.y - p.y
    a = math.radians(angle) * (1 if dx * dy >= 0 else -1)
    direction = (math.cos(a), math.sin(a))
    side = lambda pt: (pt[0] - mid[0]) * direction[1] - (pt[1] - mid[1]) * direction[0]  # noqa: E731
    into = [P(i - 3), P(i - 2), P(i - 1), p]  # the edge arriving at the cut
    out = [q, P(j + 1), P(j + 2), P(j + 3)]  # the edge leaving it
    ca = [(pt.x, pt.y) for pt in into]
    cb = [(pt.x, pt.y) for pt in out]
    ta = _crossing(ca, side, 1.0, 0.6, 1.4)
    tb = _crossing(cb, side, 0.0, -0.4, 0.4)
    if ta is None or tb is None:
        return False
    left, _ = _split(ca, ta)
    _, right = _split(cb, tb)
    for pt, (x, y) in zip(into[1:], left[1:]):
        pt.x, pt.y = x, y
    for pt, (x, y) in zip(out[:3], right[:3]):
        pt.x, pt.y = x, y
    return True


def find_stem_ends(font, g, sw: float, letters: set[str]) -> list[tuple]:
    """Where a straight stroke ends flat on a vertical metric line, and which sides take a serif.

    A stem end is a straight horizontal segment at the baseline, the x-height, the
    cap height or the glyph's own top or bottom. The ink is above a segment
    travelled left to right and below one travelled right to left, so the
    direction tells a foot from a top. A side takes a serif when the straight
    segment arriving at that corner is a stroke: at least 1.2 stems long and
    steeper than 45 degrees. Where two diagonals meet (the apex of A, the
    bottom of v) nothing is added. A lowercase vertical stem gets one head serif,
    to the left. A bar (E, L, B) takes one serif, on the side of its stem.
    Returns (contour, i, j, left, right, top, width, head) per end.
    """
    b = g.getBounds(font)
    if b is None:
        return []
    xh = font["x"].getBounds(font).yMax if "x" in font else font.info.xHeight
    cap = font["H"].getBounds(font).yMax if "H" in font else font.info.capHeight
    lower = unicodedata.category(chr(g.unicodes[0])) == "Ll" if g.unicodes else g.name.split(".")[0] in letters and g.name[:1].islower()
    tops = [h for h in (xh, cap, b.yMax) if h is not None]
    bottoms = [0, b.yMin]
    out = []
    for ci, c in enumerate(g.contours):
        pts = c.points
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            a, q = pts[i], pts[j]
            if a.type is None or q.type != "line" or abs(a.y - q.y) > 0.5:
                continue
            top = q.x < a.x
            if not any(abs(a.y - h) < 3 for h in (tops if top else bottoms)):
                continue
            prev, nxt = pts[(i - 1) % n], pts[(j + 1) % n]
            def stroke(p0, p1):
                length = math.hypot(p1.x - p0.x, p1.y - p0.y)
                return length >= 1.2 * sw and abs(p1.y - p0.y) >= abs(p1.x - p0.x)
            arrive = a.type == "line" and prev.type is not None and stroke(prev, a)
            leave = nxt.type == "line" and stroke(q, nxt)
            # the arriving side is the stroke's left side on a foot and its right side on a top
            left, right = (arrive, leave) if not top else (leave, arrive)
            if not (left or right):
                continue
            length = abs(q.x - a.x)
            vertical = lambda p0, p1: abs(p1.x - p0.x) < 2  # noqa: E731
            head = False
            if length > 2.6 * sw:
                # a bar: a serif only where a vertical stem stands at its end
                left = left and vertical(*((prev, a) if not top else (q, nxt)))
                right = right and vertical(*((q, nxt) if not top else (prev, a)))
                if not (left or right):
                    continue
            else:
                xs = sorted((a.x, q.x))
                lx = (prev if not top else nxt).x
                rx = (nxt if not top else prev).x
                if not vertical(prev, a) and not vertical(q, nxt) and lx < xs[0] and rx > xs[1]:
                    continue  # the sides spread away from the flat end: an apex or a vertex
                if top and lower and vertical(prev, a) and vertical(q, nxt):
                    right, head = False, True  # a head serif points left
            out.append((ci, i, j, left, right, top, min(length, SERIF_WIDTH_CAP * sw), head))
    return out


def find_arm_ends(font, g, sw: float) -> list[tuple]:
    """The free ends of horizontal bars that lie on a metric line (the arms of E,
    F, L, T and Z): a short vertical segment between two horizontal ones that
    both run away from it. Returns (contour, i, j, side, way) per end, where
    side is 1 for an end at the bar's right and way is -1 when the bar is at the
    top, so its wedge hangs down, and 1 when it sits on the baseline."""
    b = g.getBounds(font)
    if b is None:
        return []
    xh = font["x"].getBounds(font).yMax if "x" in font else font.info.xHeight
    cap = font["H"].getBounds(font).yMax if "H" in font else font.info.capHeight
    out = []
    for ci, c in enumerate(g.contours):
        pts = c.points
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            a, q = pts[i], pts[j]
            if a.type != "line" or q.type != "line" or abs(a.x - q.x) > 2 or not 0.3 * sw < abs(a.y - q.y) < 2 * sw:
                continue
            prev, nxt = pts[(i - 1) % n], pts[(j + 1) % n]
            if nxt.type != "line" or abs(prev.y - a.y) > 0.5 or abs(nxt.y - q.y) > 0.5:
                continue
            if (prev.x - a.x) * (nxt.x - q.x) <= 0 or min(abs(prev.x - a.x), abs(nxt.x - q.x)) < sw:
                continue
            lo, hi = sorted((a.y, q.y))
            if any(abs(hi - h) < 3 for h in (xh, cap, b.yMax)):
                way = -1
            elif any(abs(lo - h) < 3 for h in (0, b.yMin)):
                way = 1
            else:
                continue
            out.append((ci, i, j, 1 if prev.x < a.x else -1, way))
    return out


ARMS = set("EFLTZzΓΕΖΤГЕТ")
SERIF_WIDTH_CAP = 1.1  # stems: a serif's reach is measured on its stroke end, at most this wide
def plan_serifs(fonts) -> dict:
    """Where Katagami Serif's serifs go, found on Regular before any of them is cut:
    stem ends and the free ends of arms, in letters, their alternates and the
    stems f and t are built from."""
    ref = fonts["Regular"]
    sw = stem(ref)
    letters = {g.name for g in ref if g.unicodes and unicodedata.category(chr(g.unicodes[0]))[0] == "L"}
    base = lambda g: g.name if g.unicodes else g.name.split(".")[0]  # noqa: E731
    char = {g.name: chr(g.unicodes[0]) for g in ref if g.unicodes}
    names = [g.name for g in ref if g.contours and g.width and (g.name in letters or (not g.unicodes and base(g) in letters))]
    names += sorted(serif_parts(ref) - set(names))
    plan = {}
    for name in names:
        g = ref[name]
        ch = char.get(base(g), "")
        ends = find_stem_ends(ref, g, sw, letters)
        arms = find_arm_ends(ref, g, sw) if ch in ARMS else []
        if ends or arms:
            plan[name] = (ends, arms)
    return plan


def fit_serifs(fonts, plan: dict, reach: float, share: float) -> None:
    """Narrow the letters whose serifs would reach past their own ink.

    A serif on a stroke end at the edge of a letter (the tops of v, w and y,
    the feet of A, K and X) reaches past its sidebearing by most of its length,
    and widening the letter for all of it opens a hole beside it: in a sans
    skeleton the diagonals already run to the edges. So each such letter is
    narrowed, its stems kept, by `share` of the widening its serifs would need
    (measured on Regular, applied to every master); the rest is spacing.
    """
    if not share:
        return
    ref = fonts["Regular"]
    clear = TIP_CLEAR * stem(ref)
    scales = {}
    for name, (ends, _) in plan.items():
        g = ref[name]
        ink = g.getBounds(ref)
        if ink is None or not g.width:
            continue
        over_l = over_r = 0.0  # how far the letter would widen on each side
        for ci, i, j, left, right, top, width, head in ends:
            pts = g.contours[ci].points
            xs = (pts[i].x, pts[j].x)
            o = reach * width
            if left:
                over_l = max(over_l, clear - (min(xs) - o))
            if right and not head:
                over_r = max(over_r, max(xs) + o + clear - g.width)
        over = share * (over_l + over_r)
        if over > 1:
            scales[name] = (ink.xMax - ink.xMin - over) / (ink.xMax - ink.xMin)
    for f in fonts.values():
        before = snapshot(f)
        sw = stem(f)
        maps = {name: resize_glyph(f, name, k, sw) for name, k in scales.items()}
        reflow_composites(f, maps, before)


def add_contrast(fonts, amounts: dict) -> None:
    """Thin the horizontal strokes. Every point keeps its x and moves `amounts[style]` of
    the way from its y to the same point's y in the next lighter master (Regular
    toward Thin, Black toward Regular), so vertical stems keep their width and
    horizontal strokes take part of the lighter master's. A neighbouring master
    keeps the joins of diagonals close to where they were. Thin is unchanged."""
    order = [s for s in ("Thin", "Regular", "Black") if s in fonts]
    lighter = {heavy: fonts[light] for light, heavy in zip(order, order[1:])}
    snap = {style: {g.name: ([[pt.y for pt in c.points] for c in g.contours], [a.y for a in g.anchors],
                             [c.transformation[5] for c in g.components]) for g in f} for style, f in fonts.items()}
    for style, f in fonts.items():
        amount = amounts.get(style, 0.0)
        if style not in lighter or not amount:
            continue
        light = {name: snap[order[order.index(style) - 1]][name] for name in snap[style]}
        for g in f:
            ys, ays, cys = light[g.name]
            for c, cy in zip(g.contours, ys):
                for pt, y in zip(c.points, cy):
                    pt.y += amount * (y - pt.y)
            for an, y in zip(g.anchors, ays):
                an.y += amount * (y - an.y)
            for comp, y in zip(g.components, cys):
                xx, xy, yx, yy, dx, dy = comp.transformation
                comp.transformation = (xx, xy, yx, yy, dx, dy + amount * (y - dy))


SERIF_TIP = 0.3  # the flat end of a head serif, as a share of its thickness
# A serif's bracket: how far it runs along the serif, as a share of the serif's
# reach, and how far it climbs the stroke, as a share of the serif's thickness.
BRACKET = (0.35, 0.45)
BRACKET_SIDE = 0.5  # the most of a short stroke side (inside x, A, K) a bracket may climb
ARM_WIDTH = 0.4  # an arm's serif, in stems
# Serif thickness per master, times serif_depth's share of the H crossbar: Thin's
# serifs as thick as its hairlines, so they hold at text sizes; Black's a little
# lighter than Regular's, so the heavy weights stay a text face and not a slab.
SERIF_DEPTH_SCALE = (1.65, 1.0, 0.8)  # Thin, Regular, Black
SERIF_REACH_POWER = 0.3  # toward Thin and Black a serif's reach scales with the stem to this power
TIP_CLEAR = 0.15  # stems (Regular) a serif tip keeps from the edge of the advance
SERIF_FIT = 0.75  # share of the serifs' reach past a letter's ink taken back by narrowing the letter, stems kept
HEAD_BY_REACH = True  # a head serif's drop follows the reach (Regular stem times the reach scale), not the master's stem


def _contour(nodes) -> Contour:
    """A closed contour from (x, y, on) nodes in path order: an on-curve point
    that follows off-curve points ends a curve, any other ends a line."""
    c = Contour()
    for k, (x, y, on) in enumerate(nodes):
        kind = None if not on else ("curve" if not nodes[k - 1][2] else "line")
        c.points.append(Point(round(x, 1), round(y, 1), kind))
    return c


def _side_x(side, y: float) -> float:
    """Where a straight stroke side, given as (corner, far end), reaches height y,
    held at its ends."""
    (x0, y0), (x1, y1) = side
    if abs(y1 - y0) < 1e-6:
        return x0
    u = min(1.0, max(0.0, (y - y0) / (y1 - y0)))
    return x0 + u * (x1 - x0)


def _bracket(side, y: float, s: int, t: float, tip: float, way: int) -> list:
    """One side of a rectangular serif, from its square end to the stroke: the
    end at `tip`, the flat back at y + s * t, and a bracket that leaves the back
    level and meets the stroke's side along it. way is 1 for a serif right of
    the stroke and -1 for one left of it."""
    back = y + s * t
    sx = _side_x(side, back)
    run = max(0.0, BRACKET[0] * way * (tip - sx))
    room = abs(side[1][1] - back)  # how much of the stroke's side stands above the serif's back
    top = back + s * min(BRACKET[1] * t, BRACKET_SIDE * room)
    return [(tip, y, True), (tip, back, True), (sx + way * run, back, True), (sx + way * 0.45 * run, back, False),
            (_side_x(side, back + 0.55 * (top - back)), back + 0.55 * (top - back), False), (_side_x(side, top), top, True)]


def _serif_nodes(y, s, left, right, ol, orr, t, has_l, has_r):
    """A rectangular serif on the stroke end at height y, growing into the
    stroke in the direction s (1 for a foot, -1 for a top). Each side that has
    one runs out along the line, ends square at its full thickness t, and comes
    back flat to a short bracket into the stroke's side. has_l and has_r come
    from the plan, so every master gets the same points even where a counter
    leaves a side no reach."""
    if has_r:
        nodes = _bracket(right, y, s, t, right[0][0] + orr, 1)
    else:
        nodes = [(right[0][0], y, True), (_side_x(right, y + s * t), y + s * t, True)]
    if has_l:
        nodes = _bracket(left, y, s, t, left[0][0] - ol, -1)[::-1] + nodes
    else:
        nodes = [(_side_x(left, y + s * t), y + s * t, True), (left[0][0], y, True)] + nodes
    # a top is a foot mirrored, which turns the contour the other way
    return nodes if s > 0 else nodes[::-1]


def _arm_nodes(xe, lo, hi, side, way, w, length):
    """A rectangular serif at the free end xe of a bar from lo to hi: an outer
    edge flush with the end, a square end `length` past the bar, `w` wide, and a
    straight inner edge that brackets into the bar. It hangs below the bar when
    way is -1 and stands above it when way is 1."""
    rise, run = BRACKET[0] * length, BRACKET[1] * w
    nodes = [(xe - w, lo - length, True), (xe, lo - length, True), (xe, hi, True), (xe - w - run, hi, True),
             (xe - w - run, lo, True), (xe - w - 0.45 * run, lo, False), (xe - w, lo - 0.55 * rise, False), (xe - w, lo - rise, True)]
    nodes = [(xe + side * (x - xe), y if way < 0 else lo + hi - y, on) for x, y, on in nodes]
    # mirrored once, the contour turns the other way
    return nodes if (side > 0) == (way < 0) else nodes[::-1]


def cut_serifs(fonts, plan: dict, reach: float, depth: float, head_drop: float, beak: float) -> None:
    """Cut rectangular serifs onto the ends plan_serifs found.

    A serif runs out along its line `reach` of the stroke's width at Regular,
    ends square, `depth` of the master's H crossbar thick, and comes back flat
    to a short bracket into the stroke's own side, so a diagonal's serif meets
    the diagonal. Toward Thin and Black the reach scales with the stem to the
    power 0.15. The head of a lowercase stem is a triangle: its tip drops
    `head_drop` stems below the line and the stem's top left corner moves down
    onto the cut. The free end of an arm takes a vertical serif `beak` stems
    long. Every serif is its own contour, added in the same order to every
    master, so the masters stay compatible.
    """
    sw_ref = stem(fonts["Regular"])
    def crossbar(font) -> float:
        ys = sorted({round(pt.y) for c in font["H"].contours for pt in c.points if 0 < round(pt.y) < round(font["H"].getBounds(font).yMax)})
        return ys[-1] - ys[0] if len(ys) >= 2 else stem(font)
    gap = 0.5 * sw_ref  # the least white left between two serifs, inside a letter or between two
    parts = serif_parts(fonts["Regular"])
    for style, f in fonts.items():
        sw = stem(f)
        k = (sw / sw_ref) ** SERIF_REACH_POWER
        t = depth * crossbar(f) * dict(zip(("Thin", "Regular", "Black"), SERIF_DEPTH_SCALE)).get(style, 1.0)
        before = snapshot(f)
        widened = {}
        for name, (ends, arms) in plan.items():
            g = f[name]
            ink = g.getBounds(f)
            spans = []
            for ci, i, j, left, right, top, width, head in ends:
                pts = g.contours[ci].points
                n = len(pts)
                a, q, prev, nxt = pts[i], pts[j], pts[(i - 1) % n], pts[(j + 1) % n]
                # a foot is travelled left to right and a top right to left
                lc, lf, rc, rf = (a, prev, q, nxt) if not top else (q, nxt, a, prev)
                lside, rside = ((lc.x, lc.y), (lf.x, lf.y)), ((rc.x, rc.y), (rf.x, rf.y))
                if rc.x - lc.x > 2.6 * sw:  # a bar: the serif sits under the stem only
                    if left:
                        rside = ((lc.x + sw, lc.y), (lc.x + sw, lc.y + 1000))
                    else:
                        lside = ((rc.x - sw, rc.y), (rc.x - sw, rc.y + 1000))
                o = reach * width * k
                spans.append([lside[0][0], rside[0][0], a.y, top, o if left else 0, o if right else 0, head, lc, o, lside, rside, left, right])
            # serifs that face each other on one line share the counter between them
            for s1 in spans:
                for s2 in spans:
                    if s1 is s2 or s1[3] != s2[3] or abs(s1[2] - s2[2]) > 2 or s2[0] < s1[1]:
                        continue
                    room = s2[0] - s1[1] - gap
                    if s1[5] and s2[4]:
                        s1[5] = min(s1[5], max(0, room / 2)); s2[4] = min(s2[4], max(0, room / 2))
                    elif s1[5]:
                        s1[5] = min(s1[5], max(0, room))
                    elif s2[4]:
                        s2[4] = min(s2[4], max(0, room))
            shapes = []
            for x0, x1, y, top, ol, orr, head, corner, o, lside, rside, has_l, has_r in spans:
                if head:
                    d = head_drop * (sw_ref * k if HEAD_BY_REACH else sw)
                    yq = y - d * (x1 - x0) / (ol + x1 - x0)
                    corner.y = yq
                    tip, e, low = x0 - ol, SERIF_TIP * t, yq - t
                    bottom = y - d - e
                    shapes.append([(_side_x(lside, low), low, True), (_side_x(rside, low), low, True), (x1, y, True), (tip, y - d, True),
                                   (tip, bottom, True), (tip + 0.5 * (x0 - tip), bottom, False),
                                   (_side_x(lside, low + 0.55 * (bottom - low)), low + 0.55 * (bottom - low), False)])
                else:
                    shapes.append(_serif_nodes(y, -1 if top else 1, lside, rside, ol, orr, t, has_l, has_r))
            length = beak * sw_ref * k
            for ci, i, j, side, way in arms:
                pts = g.contours[ci].points
                lo, hi = sorted((pts[i].y, pts[j].y))
                shapes.append(_arm_nodes(pts[i].x, lo, hi, side, way, ARM_WIDTH * sw, length))
            for nodes in shapes:
                g.appendContour(_contour(nodes))
            # the serifs overlap their strokes; the flag tells rasterizers to fill the union
            g.lib["public.truetype.overlap"] = True
            # a side whose serif reaches past the letter's ink widens until the
            # serif's tip keeps half the gap from the edge of the advance
            out = g.getBounds(f)
            clear = TIP_CLEAR * sw_ref
            dl = max(0.0, clear - out.xMin) if out.xMin < ink.xMin - 1 else 0.0
            dr = max(0.0, clear - (g.width - out.xMax)) if out.xMax > ink.xMax + 1 else 0.0
            if (dl or dr) and name not in parts:  # a part sits inside its letter's advance
                for c in g.contours:
                    for pt in c.points:
                        pt.x += dl
                for an in g.anchors:
                    an.x += dl
                g.width = round(g.width + dl + dr)
                widened[name] = XMap(0, dl, 1)
        reflow_composites(f, widened, before)
        flag_overlaps(f)


def flag_overlaps(font) -> None:
    """fontmake flattens components, so a composite of a serifed glyph overlaps too."""
    def wedged(name: str) -> bool:
        g = font[name]
        return bool(g.lib.get("public.truetype.overlap")) or any(wedged(c.baseGlyph) for c in g.components)
    for g in font:
        if g.components and wedged(g.name):
            g.lib["public.truetype.overlap"] = True



def serif_parts(font) -> set[str]:
    """The stems f and t are drawn from (unencoded parts): their ends take
    serifs and terminal slabs as a letter's do."""
    return {font[n].components[0].baseGlyph for n in ("f", "t") if n in font and font[n].components}


TERMINAL_FACE = (0.45, 1.6)  # stems (Regular): how long a cut across a stroke may be to count as its end
TERMINAL_REF = 1.0  # stems: a terminal cut this long or longer takes a full slab; shorter ones (superiors) a thinner one
TERMINAL_SYMBOLS = set("?¿&§$¢€£@‽")  # symbols drawn with the letters' curved strokes


def _ink_side(font, g, a, q) -> tuple[bool, bool]:
    """Whether the ink lies on the left of the cut from a to q and not on its right,
    a quarter stem from its midpoint: the cut is an end the stroke stops at."""
    from fontTools.pens.pointInsidePen import PointInsidePen
    mx, my = (a.x + q.x) / 2, (a.y + q.y) / 2
    d = math.hypot(q.x - a.x, q.y - a.y)
    nx, ny = -(q.y - a.y) / d, (q.x - a.x) / d  # left of travel
    r = 0.25 * stem(font)
    def inside(x, y):
        pen = PointInsidePen(font, (x, y))
        g.draw(pen)
        return pen.getResult()
    return inside(mx + r * nx, my + r * ny), not inside(mx - r * nx, my - r * ny)


def plan_terminals(fonts, plan: dict) -> dict:
    """Where Katagami Serif's terminals take a flat slab, found on Regular: every
    stroke end the serif plan leaves bare in letters, figures, their
    alternates, the stems of f and t and the symbols drawn like letters.

    A stroke end is a straight cut 0.45 to 1.6 stems long between two
    corners whose sides run back the way they came, with ink on one side of
    it and none on the other. A level cut (within 30 degrees of horizontal)
    between two curves is the end of a curved stroke (c, s, a, C, S, G, the
    figures), and so is one on a short straight stroke that hooks back up
    (J); its slab must lie within the letter's height. An upright cut (within 30
    degrees of vertical) is the end of a hook, an arm or a tail (r, f, t, y,
    j), unless it ends a stub in the middle third of the letter (the waist of
    3) or a stroke that lies on the baseline, x-height or cap height. A bar's
    end, with a straight side 1.8 stems or longer (the crossbars of f and t,
    the foot of 2), is not a terminal. Returns
    {glyph: [(kind, contour, i, j, outer, way, scale)]}: for a level cut the
    corner on the outside of the letter and whether the cut faces up (1)
    or down (-1); for an upright cut the corner below or above it; scale is
    the cut's length over TERMINAL_REF stems, at most 1.
    """
    ref = fonts["Regular"]
    sw = stem(ref)
    cat = lambda g: unicodedata.category(chr(g.unicodes[0])) if g.unicodes else ""  # noqa: E731
    drawn = {g.name for g in ref if g.unicodes and (cat(g)[0] in "LN" or chr(g.unicodes[0]) in TERMINAL_SYMBOLS)}
    names = [g.name for g in ref if g.contours and g.width and (g.name in drawn or (not g.unicodes and g.name.split(".")[0] in drawn))]
    names += sorted(serif_parts(ref) - set(names))
    metrics = (ref["x"].getBounds(ref).yMax, ref["H"].getBounds(ref).yMax)
    out = {}
    for name in names:
        g = ref[name]
        ends, arms = plan.get(name, ([], []))
        taken = {(e[0], k) for e in ends + arms for k in (e[1], e[2])}
        b = g.getBounds(ref)
        found = []
        for ci, c in enumerate(g.contours):
            pts = c.points
            n = len(pts)
            for i in range(n):
                j = (i + 1) % n
                a, q = pts[i], pts[j]
                if a.type is None or q.type != "line" or a.smooth or q.smooth or (ci, i) in taken or (ci, j) in taken:
                    continue
                length = math.hypot(q.x - a.x, q.y - a.y)
                if not TERMINAL_FACE[0] * sw <= length <= TERMINAL_FACE[1] * sw:
                    continue
                prev, nxt = pts[(i - 1) % n], pts[(j + 1) % n]
                din, dout = (a.x - prev.x, a.y - prev.y), (nxt.x - q.x, nxt.y - q.y)
                li, lo = math.hypot(*din), math.hypot(*dout)
                if li < 1 or lo < 1 or (din[0] * dout[0] + din[1] * dout[1]) / (li * lo) > -0.5:
                    continue
                into_curve, out_curve = a.type == "curve", nxt.type is None
                # a bar's end: a straight side at least 1.8 stems long runs from it (f, t, Z, the foot of 2)
                bar = (not into_curve and li >= 1.8 * sw) or (nxt.type == "line" and lo >= 1.8 * sw)
                angle = abs(math.degrees(math.atan2(q.y - a.y, q.x - a.x))) % 180
                angle = min(angle, 180 - angle)
                mid_x, mid_y, cut_y = (b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2, (a.y + q.y) / 2
                if angle <= 30:
                    # a cut left at a slant (Inter's a.2, which the level cuts do not reach) keeps it
                    if angle > SLAB_ANGLE:
                        continue
                    kind = "level"
                    # the ink is left of travel, so the bare side faces up when the cut runs right to left
                    way = 1 if q.x < a.x else -1
                    # a slab stays within the letter's height, never on its top or foot (the arms of ω)
                    if (way > 0) != (cut_y < mid_y):
                        continue
                    # the end of a curved stroke, or of a straight one that hooks back up (J)
                    if not (into_curve and out_curve or not bar and way > 0):
                        continue
                elif angle >= 60 and not bar:
                    kind = "upright"
                    lo_y, hi_y = sorted((a.y, q.y))
                    # a stroke lying on a metric line ends in a bar's end (the foot of 2, the top of Z)
                    if abs(lo_y) < 3 or any(abs(hi_y - m) < 3 for m in metrics):
                        continue
                    # a stub in the middle of a letter (the waist of 3) is not a terminal
                    if abs(cut_y - mid_y) < (b.yMax - b.yMin) / 6:
                        continue
                    way = -1 if cut_y > mid_y else 1
                else:
                    continue
                ink_left, bare_right = _ink_side(ref, g, a, q)
                if not (ink_left and bare_right):
                    continue
                # a curved stroke that ends rising at the foot of the letter's right side (the exits of c,
                # C and e) ends plain: its slab would run under the one above it, a second jaw (t's hook
                # takes one, as a foot)
                if not SLAB_EXITS and kind == "level" and way > 0 and (a.x + q.x) / 2 > mid_x:
                    continue
                scale = min(1.0, length / (TERMINAL_REF * sw))
                if kind == "level":
                    outer = i if abs(a.x - mid_x) > abs(q.x - mid_x) else j
                else:
                    lo_k, hi_k = (i, j) if a.y < q.y else (j, i)
                    outer = lo_k if way < 0 else hi_k
                found.append((kind, ci, i, j, outer, way, scale))
        found = [term for term in found if not _jaw(ref, g, term, found, mid_x)]
        if found:
            out[name] = found
    return out


def _jaw(font, g, term, found, mid_x: float) -> bool:
    """Whether the slab at the foot of an opening would sit under the slab above
    it across that opening, a second jaw, as in ɔ and Ↄ (the mirrored c): both
    cuts on the same side of the letter and nothing between them (the white at
    their mid-height reaches the letter's middle, where 3 has its waist). The
    upper slab stays."""
    from fontTools.pens.pointInsidePen import PointInsidePen
    kind, ci, i, j, outer, way, _ = term
    if kind != "level" or way < 0:
        return False
    pts = g.contours[ci].points
    side = 1 if pts[outer].x > mid_x else -1
    y = (pts[i].y + pts[j].y) / 2
    for k2, c2, i2, j2, o2, w2, _ in found:
        if k2 != "level" or w2 > 0:
            continue
        p2 = g.contours[c2].points
        if (p2[o2].x > mid_x) != (side > 0) or (p2[i2].y + p2[j2].y) / 2 <= y:
            continue
        mid_y = (y + (p2[i2].y + p2[j2].y) / 2) / 2
        x0 = (pts[outer].x + p2[o2].x) / 2
        ink = False
        for t in range(1, 21):
            pen = PointInsidePen(font, (x0 + (mid_x - x0) * t / 20, mid_y))
            g.draw(pen)
            if pen.getResult():
                ink = True
                break
        if not ink:
            return True
    return False


def _walk_to_x(pts, k: int, step: int, x: float) -> float:
    """The height where the outline, followed from point k in direction step
    (away from a cut), first reaches x; the height of point k if it does not
    within three segments."""
    n = len(pts)
    cur = k
    for _ in range(3):
        seg = [pts[cur]]
        nk = cur
        while True:
            nk = (nk + step) % n
            seg.append(pts[nk])
            if pts[nk].type is not None:
                break
        xy = [(q.x, q.y) for q in seg]
        samples = []
        for t in [m / 32 for m in range(33)]:
            if len(xy) == 4:
                samples.append(_point(xy, t))
            else:
                samples.append((xy[0][0] + (xy[-1][0] - xy[0][0]) * t, xy[0][1] + (xy[-1][1] - xy[0][1]) * t))
        for (x0, y0), (x1, y1) in zip(samples, samples[1:]):
            if (x0 - x) * (x1 - x) <= 0 and x0 != x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        cur = nk
    return pts[k].y


def _upright(pts, i: int, j: int, outer: int) -> bool:
    """Cut the stroke end from point i to point j exactly upright: through its
    midpoint, or, where an edge cannot reach that line (the hook of f),
    through the corner nearer the stroke. Returns False where neither works."""
    a, q = pts[i], pts[j]
    if abs(q.x - a.x) <= 1:
        return True
    side = 1 if pts[(outer + (-1 if outer == i else 1)) % len(pts)].x > (a.x + q.x) / 2 else -1
    near = max((a, q), key=lambda pt: side * pt.x)
    return recut(pts, i, j, 90) or recut(pts, i, j, 90, (near.x, near.y))


def _contour_x(pts, k: int, step: int, y: float) -> float | None:
    """Where the outline, followed from point k in direction step (away from a
    cut), first reaches height y, within three segments; None if it does not."""
    n = len(pts)
    cur = k
    for _ in range(3):
        seg = [pts[cur]]
        nk = cur
        while True:
            nk = (nk + step) % n
            seg.append(pts[nk])
            if pts[nk].type is not None:
                break
        xy = [(q.x, q.y) for q in seg]
        samples = [_point(xy, m / 32) if len(xy) == 4 else
                   (xy[0][0] + (xy[-1][0] - xy[0][0]) * m / 32, xy[0][1] + (xy[-1][1] - xy[0][1]) * m / 32) for m in range(33)]
        for (x0, y0), (x1, y1) in zip(samples, samples[1:]):
            if (y0 - y) * (y1 - y) <= 0 and y0 != y1:
                return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
        cur = nk
    return None


SLAB_REACH = 0.7  # a terminal slab's reach past the stroke, as a share of the stem serifs' reach
SLAB_INWARD = 0.4  # share of the reach a terminal's slab also runs inward, past the cut's inner corner
SLAB_MIN = 0.45  # a slab a neighbouring stroke would cut shorter than this share of its reach is left off
SLAB_ANGLE = 6  # degrees: a cut further from level than this keeps its plain cut
SLAB_EXITS = False  # whether the rising exits at a letter's right foot (c, C, e, t) take a slab
SLAB_CLEAR = 0.85  # share of a side's own white a letter keeps past a terminal slab that reaches beyond its ink


def _inked(font, g, x: float, y: float) -> bool:
    from fontTools.pens.pointInsidePen import PointInsidePen
    pen = PointInsidePen(font, (x, y))
    g.draw(pen)
    return pen.getResult()


def _free(font, g, x: float, y: float, way: int, most: float) -> float:
    """How far the white runs from (x, y) along x (way 1 right, -1 left) before it meets ink, up to `most`."""
    from fontTools.pens.pointInsidePen import PointInsidePen
    d = 4.0
    while d < most:
        pen = PointInsidePen(font, (x + way * d, y))
        g.draw(pen)
        if pen.getResult():
            return d
        d += 4.0
    return most


def _slab(font, g, term, t: float, o: float, gap: float, inward_part: bool = False) -> list | None:
    """A flat terminal serif in this master: a slab as thick as the serifs (t),
    its outer face flush with the end of the stroke and level, reaching `o`
    past the stroke's outer side and ending square, its back meeting that side
    in the serifs' bracket. A level cut (c, s, a, S, the figures) takes it on
    the cut: flush with the cut's level, outward past the outer corner. An
    upright cut (r, f, j, y, t) is cut upright first and takes it on the
    stroke's outer edge: flush with the arm's top (r, f) or the tail's foot
    (j, y, t), outward past the cut. None where a neighbouring part of the
    letter leaves less than SLAB_MIN of the reach, with `gap` of white kept."""
    kind, ci, i, j, outer, way, scale = term
    pts = g.contours[ci].points
    n = len(pts)
    a, q = pts[i], pts[j]
    if kind == "level":
        o_pt, i_pt = (a, q) if outer == i else (q, a)
        out_step, in_step = (-1, 1) if outer == i else (1, -1)
        k_out, k_in = outer, (j if outer == i else i)
        s = -way  # the serif grows into the stroke: up from a cut the stroke stands on (the top of c), down from one it hangs from
        y = o_pt.y
        h = 1 if o_pt.x > i_pt.x else -1  # outward
        back = y + s * t
        # the stroke's outer side up to where the bracket ends (a short arch, as in Black's a, may not reach as far)
        far = next(((x, f) for f in (2.0, 1.6, 1.3) if (x := _contour_x(pts, k_out, out_step, y + s * f * t)) is not None), None)
        in_back = _contour_x(pts, k_in, in_step, back)
        if in_back is None and _inked(font, g, i_pt.x, back):
            in_back = i_pt.x  # a counter shorter than the slab (Black's s): the stroke above the inner corner is solid
        if far is None or in_back is None:
            return None
        far_out, far_f = far
        # the white beyond the stroke's outer side, through the slab's height and a gap beyond its face
        x_side = [_contour_x(pts, k_out, out_step, y + s * f * t) for f in (0.1, 0.5, 0.95)]
        if any(x is None for x in x_side):
            return None
        free = min([_free(font, g, x + h, y + s * f * t, h, o + 2 * gap) for x, f in zip(x_side, (0.1, 0.5, 0.95))] +
                   [_free(font, g, o_pt.x + h, y - s * gap * f, h, o + 2 * gap) for f in (0.25, 0.75)])
        reach = min(o, free - gap)
        if reach < SLAB_MIN * o:
            return None
        outer_side = ((o_pt.x, y), (far_out, y + s * far_f * t))
        inner_side = ((i_pt.x, y), (in_back, back))
        # a small part inward too, as a foot serif runs both ways, where the counter has room for it
        inward = 0.0
        if inward_part:
            in_far = _contour_x(pts, k_in, in_step, y + s * 2 * t)
            x_in = [_contour_x(pts, k_in, in_step, y + s * f * t) for f in (0.1, 0.5, 0.95)]
            if in_far is None or any(x is None for x in x_in):
                return None
            room = min([_free(font, g, x - h, y + s * f * t, -h, o + 2 * gap) for x, f in zip(x_in, (0.1, 0.5, 0.95))] +
                       [_free(font, g, i_pt.x - h, y - s * gap * f, -h, o + 2 * gap) for f in (0.25, 0.75)])
            inward = min(SLAB_INWARD * reach, room - gap)
            if inward < 0.5 * SLAB_INWARD * reach:
                return None
            inner_side = ((i_pt.x, y), (in_far, y + s * 2 * t))
        left, right = (inner_side, outer_side) if h > 0 else (outer_side, inner_side)
        ol, orr = (inward, reach) if h > 0 else (reach, inward)
        return _serif_nodes(y, s, left, right, ol, orr, t, h < 0 or inward > 0, h > 0 or inward > 0)
    # an upright cut: the slab on the stroke's outer edge, past the cut
    if not _upright(pts, i, j, outer):
        return None
    xe = (a.x + q.x) / 2
    for pt in (a, q):
        pt.x = xe
    lo_k, hi_k = (i, j) if a.y < q.y else (j, i)
    edge = hi_k if way < 0 else lo_k  # the arm's top (r, f), the tail's foot (j, y, t)
    other = lo_k if edge == hi_k else hi_k
    step = -1 if edge == i else 1
    away = pts[(edge + step) % n]
    h = -1 if away.x > xe else 1  # outward, past the cut
    y = pts[edge].y
    s = -1 if edge == hi_k else 1  # into the stroke
    face = abs(pts[hi_k].y - pts[lo_k].y)
    t = min(t, 0.75 * face)  # never deeper than the end it caps (Thin's serifs are thicker than its hairlines)
    free = min(_free(font, g, xe + h, y + s * f * t, h, o + 2 * gap) for f in (0.1, 0.5, 0.95))
    reach = min(o, free - gap)
    if reach < SLAB_MIN * o:
        return None
    tip, backy = xe + h * reach, y + s * t
    run = BRACKET[0] * reach
    climb = min(BRACKET[1] * t, BRACKET_SIDE * (face - t))
    top = backy + s * climb
    lip = min(0.3 * t, 0.5 * abs(xe - away.x))
    nodes = [(xe - h * lip, y, True), (tip, y, True), (tip, backy, True), (xe + h * run, backy, True),
             (xe + h * 0.45 * run, backy, False), (xe, backy + s * 0.55 * climb, False), (xe, top, True),
             (xe - h * lip, top, True)]
    # outer contours run counter-clockwise: the turn follows from which way the slab reaches and grows
    return nodes if h * s > 0 else nodes[::-1]


def cut_terminals(fonts, plan: dict, depth: float, reach: float) -> None:
    """Give every terminal plan_terminals found a flat serif in the stem
    serifs' system (`_slab`): as thick as the master's serifs
    (SERIF_DEPTH_SCALE, so Thin's hold and Black's stay light), reaching
    `reach` of the Regular cut past the stroke, scaled with the stem as the
    serifs' reach is, square-ended, with the serifs' bracket. Every slab is
    its own contour, the same in every master; a terminal takes one only
    where every master can draw it. A letter whose slab reaches past its
    ink widens until the tip keeps TIP_CLEAR stems from the edge of its
    advance, as the stem serifs do."""
    ref = fonts["Regular"]
    sw_ref = stem(ref)
    gap = 0.5 * sw_ref
    def crossbar(font) -> float:
        ys = sorted({round(pt.y) for c in font["H"].contours for pt in c.points if 0 < round(pt.y) < round(font["H"].getBounds(font).yMax)})
        return ys[-1] - ys[0] if len(ys) >= 2 else stem(font)
    width = {}
    for name, terms in plan.items():
        for term in terms:
            pts = ref[name].contours[term[1]].points
            a, q = pts[term[2]], pts[term[3]]
            width[(name, term[1], term[2])] = min(math.hypot(q.x - a.x, q.y - a.y), SERIF_WIDTH_CAP * sw_ref)
    sizes = {}
    for style, f in fonts.items():
        k = (stem(f) / sw_ref) ** SERIF_REACH_POWER
        sizes[style] = (depth * crossbar(f) * dict(zip(("Thin", "Regular", "Black"), SERIF_DEPTH_SCALE)).get(style, 1.0), k)
    def shape(style, g, term, inward_part):
        t, k = sizes[style]
        return _slab(fonts[style], g, term, t * term[6] ** 0.5, SLAB_REACH * reach * width[(g.name, term[1], term[2])] * k, gap,
                     inward_part)
    parts = serif_parts(ref)
    # a terminal takes a slab, and its inward part, only where every master can draw it, so the masters stay compatible
    kept = {}
    for name, terms in plan.items():
        for term in terms:
            for inward_part in ((True, False) if SLAB_INWARD and term[0] == "level" else (False,)):
                if all(shape(style, copy.deepcopy(f[name]), term, inward_part) is not None for style, f in fonts.items()):
                    kept.setdefault(name, []).append((term, inward_part))
                    break
    # two slabs of one letter never come within `gap` of each other (the facing ends of ȣ): both are left off
    def box(nodes):
        xs, ys = [x for x, _, _ in nodes], [y for _, y, _ in nodes]
        return min(xs), min(ys), max(xs), max(ys)
    def near(b, c):
        return b[0] < c[2] + gap and c[0] < b[2] + gap and b[1] < c[3] + gap and c[1] < b[3] + gap
    for name, terms in kept.items():
        if len(terms) < 2:
            continue
        clashing = set()
        for style, f in fonts.items():
            g = copy.deepcopy(f[name])
            boxes = [box(shape(style, g, term, inward_part)) for term, inward_part in terms]
            for x in range(len(boxes)):
                for y in range(x + 1, len(boxes)):
                    if near(boxes[x], boxes[y]):
                        clashing |= {x, y}
        kept[name] = [t for k, t in enumerate(terms) if k not in clashing]
    plan = kept
    clear = TIP_CLEAR * sw_ref
    for style, f in fonts.items():
        before = snapshot(f)
        widened = {}
        for name, terms in plan.items():
            g = f[name]
            ink = g.getBounds(f)
            for nodes in [shape(style, g, term, inward_part) for term, inward_part in terms]:
                g.appendContour(_contour(nodes))
            g.lib["public.truetype.overlap"] = True
            out = g.getBounds(f)
            # a slab beyond the letter's ink keeps SLAB_CLEAR of the side's own white past its tip (at
            # least the stem serifs' TIP_CLEAR): a terminal sits beside the next letter's stem, not its serif
            keep_l = max(clear, SLAB_CLEAR * ink.xMin)
            keep_r = max(clear, SLAB_CLEAR * (g.width - ink.xMax))
            dl = max(0.0, keep_l - out.xMin) if out.xMin < ink.xMin - 1 else 0.0
            dr = max(0.0, keep_r - (g.width - out.xMax)) if out.xMax > ink.xMax + 1 else 0.0
            if (dl or dr) and name not in parts:
                for c in g.contours:
                    for pt in c.points:
                        pt.x += dl
                for an in g.anchors:
                    an.x += dl
                g.width = round(g.width + dl + dr)
                widened[name] = XMap(0, dl, 1)
        reflow_composites(f, widened, before)
        flag_overlaps(f)


def close_c(fonts, share: float) -> None:
    """Bring c's two terminals toward each other by `share` of the gap between
    them, half each. Each cut moves along the stroke, parallel to itself (Thin
    keeps Inter's angled cuts; the other masters are level): both edges are
    extended along their own curves to the moved line, as level_terminals
    extends them, so the curves stay whole."""
    for f in fonts.values():
        pts = f["c"].contours[0].points
        n = len(pts)
        P = lambda k: pts[k % n]  # noqa: E731
        cuts = [((j - 1) % n, j) for j in range(n)
                if P(j).type == "line" and P(j - 1).type == "curve" and not P(j - 1).smooth and not P(j).smooth]
        if len(cuts) != 2:
            continue
        mids = [((P(i).x + P(j).x) / 2, (P(i).y + P(j).y) / 2) for i, j in cuts]
        lo, hi = min(m[1] for m in mids), max(m[1] for m in mids)
        for (i, j), (mx, my) in zip(cuts, mids):
            my += share * (hi - lo) / 2 * (1 if my == lo else -1)
            length = math.hypot(P(j).x - P(i).x, P(j).y - P(i).y)
            dx, dy = (P(j).x - P(i).x) / length, (P(j).y - P(i).y) / length
            side = lambda q, mx=mx, my=my, dx=dx, dy=dy: (q[0] - mx) * dy - (q[1] - my) * dx  # noqa: E731
            into = [P(i - 3), P(i - 2), P(i - 1), P(i)]
            out = [P(j), P(j + 1), P(j + 2), P(j + 3)]
            ca, cb = [(q.x, q.y) for q in into], [(q.x, q.y) for q in out]
            ta = _crossing(ca, side, 1.0, 0.6, 1.4)
            tb = _crossing(cb, side, 0.0, -0.4, 0.4)
            if ta is None or tb is None:
                # A curve that reaches its end steeply on a short handle (Inter's
                # Thin c) bends back when extended; move its end and last handle
                # instead, so the cut moves the same distance with its angle kept.
                dy = my - (P(i).y + P(j).y) / 2
                for q in (into[2], into[3], out[0], out[1]):
                    q.y += dy
                continue
            left, _ = _split(ca, ta)
            _, right = _split(cb, tb)
            for q, xy in zip(into[1:], left[1:]):
                _set(q, xy)
            for q, xy in zip(out[:3], right[:3]):
                _set(q, xy)


def f_crossbar_overhang(fonts, overhang: float) -> None:
    """Let the f's crossbar reach `overhang` Regular stems past the stem's left edge.

    The compact f's bar starts at or inside its stem. Its left end moves out to
    the same distance from the stem in every master, so the bar shows the same
    length on the left at every weight. The glyph shifts right by half the gain
    and its advance grows by the same half, so its spacing stays balanced.
    """
    if not overhang:
        return
    reach = overhang * stem(fonts["Regular"])
    for f in fonts.values():
        g = f["f"]
        bars = [c for c in g.contours if len(c.points) == 4]
        if len(bars) != 1 or not g.components:
            continue
        part = g.components[0]
        stem_left = f[part.baseGlyph].getBounds(f).xMin + part.transformation[4]
        target = stem_left - reach
        bar = bars[0]
        left = min(p.x for p in bar.points)
        if target >= left:
            continue
        for p in bar.points:
            if abs(p.x - left) < 1:
                p.x = target
        shift = (left - target) / 2
        for c in g.contours:
            for p in c.points:
                p.x += shift
        t = list(part.transformation)
        t[4] += shift
        part.transformation = tuple(t)
        for a in g.anchors:
            a.x += shift
        g.width = round(g.width + shift)


def lift_ascenders(fonts, lift: float) -> None:
    """Stretch lowercase strokes above the x-height so ascenders rise by `lift`.

    Points above the x-height scale away from it; accents sitting on a lifted
    base move up with the base's top anchor.
    """
    if not lift:
        return
    ref = fonts["Regular"]
    cat = lambda g: unicodedata.category(chr(g.unicodes[0])) if g.unicodes else ""  # noqa: E731
    lower = {g.name for g in ref if g.contours and cat(g) == "Ll"}
    # unencoded parts that only lowercase letters are built from (the stems of f and t);
    # unencoded and private-use alternates do not count as other users
    used_by = {}
    for g in ref:
        for c in g.components:
            used_by.setdefault(c.baseGlyph, set()).add(cat(g))
    lower |= {name for name, cats in used_by.items() if cats - {"", "Co"} == {"Ll"} and not ref[name].unicodes and ref[name].contours}
    for f in fonts.values():
        xh = f.info.xHeight
        top = f["l"].getBounds(f).yMax
        k = (top + lift - xh) / (top - xh)
        moved: dict[str, float] = {}
        for name in lower:
            g = f[name]
            if g.getBounds(f).yMax <= xh + 20:
                continue
            for c in g.contours:
                for pt in c.points:
                    if pt.y > xh:
                        pt.y = xh + (pt.y - xh) * k
            for a in g.anchors:
                if a.name == "top":
                    old = a.y
                    a.y = xh + (a.y - xh) * k if a.y > xh else a.y
                    moved[name] = a.y - old
        for g in f:
            if not g.components or g.contours or g.components[0].baseGlyph not in moved:
                continue
            for comp in g.components[1:]:
                t = list(comp.transformation)
                if f[comp.baseGlyph].width == 0 and t[5] >= 0:
                    t[5] += moved[g.components[0].baseGlyph]
                    comp.transformation = tuple(t)


def set_space(fonts, width: int | None) -> None:
    if width is None:
        return
    for f in fonts.values():
        old = f["space"].width
        for g in f:
            if g.width == old and g.unicodes and unicodedata.category(chr(g.unicodes[0])) == "Zs" and not g.contours:
                g.width = width


def soften_vertices(fonts, radius: float) -> dict:
    """Round every sharp vertex by `radius` stems (decided on Regular)."""
    if not radius:
        return {}
    ref = fonts["Regular"]
    plans = {g.name: plan_corners(g) for g in ref if g.contours}
    plans = {k: v for k, v in plans.items() if v}
    for f in fonts.values():
        r = radius * stem(f)
        for name, plan in plans.items():
            round_corners(f[name], plan, r)
    return {k: [[ci, idx] for ci, idx in v] for k, v in plans.items()}


def letters_and_figures(font) -> set[str]:
    """Drawn letters and figures, their unencoded alternates (a.1, g.cv10)
    and the unencoded parts only they are built from."""
    # Lm, modifier letters, are left out: marks such as commasuprevcomb are built from them
    cat = lambda g: unicodedata.category(chr(g.unicodes[0])) if g.unicodes else ""  # noqa: E731
    letter = lambda c: c[:1] in ("L", "N") and c != "Lm"  # noqa: E731
    encoded = {g.name for g in font if g.contours and g.width and letter(cat(g))}
    used_by = {}  # base parts only: the marks on accented letters keep their widths
    for g in font:
        if g.components:
            used_by.setdefault(g.components[0].baseGlyph, set()).add(cat(g))
    alternates = {g.name for g in font if g.contours and g.width and not g.unicodes and g.name.split(".")[0] in encoded}
    parts = {name for name, cats in used_by.items()
             if cats - {""} and all(letter(c) for c in cats - {""})
             and not font[name].unicodes and font[name].contours and font[name].width}
    return encoded | alternates | parts


def adjust_widths(fonts, widths: dict[str, float], condense: float = 1.0) -> None:
    """Scale glyphs' ink horizontally, stems kept: each glyph in `widths` by
    its factor, and every letter and figure by `condense` as well."""
    scales = dict(widths)
    if condense != 1:
        for name in letters_and_figures(fonts["Regular"]):
            scales[name] = scales.get(name, 1.0) * condense
    for f in fonts.values():
        old = snapshot(f)
        sw = stem(f)
        # in name order: a glyph drawn over a part that is resized too (Ґ over Г) measures
        # the part as it stands, so the order must be the same in every run
        maps = {name: resize_glyph(f, name, k, sw) for name, k in sorted(scales.items())
                if name in f and k != 1 and all(m[name].width > 0 for m in fonts.values())}
        reflow_composites(f, maps, old)


def dotted_circle(fonts) -> None:
    """U+25CC DOTTED CIRCLE, drawn after every transform so none reshapes its
    dots: a ring as tall as the x-height, spaced as o is, its dots sized from
    each master's stem (fontops.draw_dotted_circle)."""
    sw_ref = stem(fonts["Regular"])
    anchors = dotted_circle_anchors(fonts["Regular"])
    for f in fonts.values():
        o = f["o"]
        b = o.getBounds(f)
        d = f.info.xHeight
        draw_dotted_circle(f, dot_size(stem(f), sw_ref), d, d + b.xMin + (o.width - b.xMax), anchors)


def write_designspace(p: Profile, out_dir: Path, paths: dict[str, Path], italic: bool = False) -> Path:
    name = italic_style if italic else (lambda style: style)
    ds = DesignSpaceDocument()
    ax = AxisDescriptor()
    ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 100, 400, 900
    ax.map = list(p.weight_map)
    ds.addAxis(ax)
    design = dict(p.weight_map)
    for style, w in MASTERS.items():
        s = SourceDescriptor()
        s.path = str(paths[style])
        s.familyName, s.styleName = p.family, name(style)
        s.location = {"Weight": design[w]}
        ds.addSource(s)
    for i, style in enumerate(INSTANCES):
        inst = InstanceDescriptor()
        inst.familyName, inst.styleName = p.family, name(style)
        inst.location = {"Weight": design[(i + 1) * 100]}
        ds.addInstance(inst)
    out = out_dir / f"{p.file_stem}{'-Italic' if italic else ''}.designspace"
    ds.write(out)
    return out


def transform(p: Profile, italic: bool = False) -> tuple[dict, dict]:
    """Inter's Thin, Regular and Black (an Italic's stood upright) through
    every transform of the profile. Returns the masters and the corners
    `soften_vertices` rounded."""
    fonts = load_inter_masters(italic)
    if italic:
        decompose_transformed(fonts)
        shear(fonts, -slant_tangent(fonts["Regular"]), fonts["Regular"].info.xHeight / 2)
    if p.square_punctuation:
        promote_square_punctuation(fonts)
    if p.promote:
        promote_alternates(fonts, p.promote, FEATURES)
        relabel_features(fonts, p.promote)
    shape_curves(fonts, p)
    square_two(fonts, p.two_square)
    if p.terminal_angle is not None:
        level_terminals(fonts, p.terminal_angle)
    if p.c_close:
        close_c(fonts, p.c_close)
    f_crossbar_overhang(fonts, p.f_overhang)
    if p.notch_fill:
        fill_notches(fonts, p.notch_fill)
    fill_valleys(fonts, p.valley_fill)
    if p.tails:
        redraw_tails(fonts, p)
    slant_t(fonts, p.t_slant)
    adjust_widths(fonts, p.widths, p.condense)
    lift_ascenders(fonts, p.ascender_lift)
    lower_xheight(fonts, p.xheight_scale)
    if p.serif_reach:
        plan = plan_serifs(fonts)
        fit_serifs(fonts, plan, p.serif_reach, SERIF_FIT)
        plan = plan_serifs(fonts)  # the same ends, where the narrowed letters now have them
        terminals = plan_terminals(fonts, plan)
        add_contrast(fonts, dict(p.serif_contrast))
        # before the serifs, which would count in the stems and crossbars the slabs are measured on
        cut_terminals(fonts, terminals, p.serif_depth, p.serif_reach)
        cut_serifs(fonts, plan, p.serif_reach, p.serif_depth, p.serif_head, p.serif_beak)
    straighten_q(fonts)
    small_caps(fonts)
    respace(fonts, p.spacing)
    set_space(fonts, p.space_width)
    scale_outlines(fonts, p.scale)
    if not italic:
        # the Italic takes both from the roman (romanize), so they are the roman's slanted
        dotted_circle(fonts)
        for f in fonts.values():
            combining_double_acute(f)
    return fonts, soften_vertices(fonts, p.corner_radius)


def build(p: Profile, italic: bool = False) -> Path:
    fonts, corners = transform(p, italic)
    if italic:
        # each glyph is the roman's design, slanted: Inter Italic's drawing
        # stays only where it matches the roman's
        roman, roman_corners = transform(p)
        distances = design_distances(fonts, roman)
        replaced = sorted(name for name, d in distances.items() if d > ITALIC_MATCH)
        romanize(fonts, roman, replaced)
        corners = {name: plan for name, plan in corners.items() if name in roman["Regular"] and name not in replaced}
        corners |= {name: roman_corners[name] for name in replaced if name in roman_corners}
        shear(fonts, slant_tangent(fonts["Regular"]), fonts["Regular"].info.xHeight / 2)
    erase_open_corners(fonts)

    out = ROOT / "build" / (f"{p.key}-italic" if italic else p.key)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(FEATURES, out / "features")
    paths = {}
    for style, f in fonts.items():
        set_names(f, p.family, italic_style(style) if italic else style, MASTERS[style])
        if italic:
            f.info.styleMapStyleName = "italic" if style == "Regular" else None
        assign_categories(f)
        if corners:
            # which corners were rounded, so the site can give Sans and Mono the
            # same corners at zero radius and morph between them point for point
            f.lib["com.kerf.roundedCorners"] = corners
        path = out / f"{p.file_stem}-{(italic_style(style) if italic else style).replace(' ', '')}.ufo"
        f.save(path, overwrite=True)
        paths[style] = path
    if italic:
        # which glyphs took the roman's drawing, and how far every glyph was from it
        (out / "romanized.json").write_text(json.dumps(
            {"limit": ITALIC_MATCH, "replaced": replaced,
             "distances": {name: (None if math.isinf(d) else round(d, 1)) for name, d in distances.items()}}, indent=0))
    return write_designspace(p, out, paths, italic)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print(build(PROFILES[args[0] if args else "sans"], "--italic" in sys.argv))

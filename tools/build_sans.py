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

from ufoLib2.objects import Component, Contour, Point

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.basePen import BasePen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen

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
from kerf_build.missing import add_missing, complete_anchors, declare_scripts, dot_marks, soft_dotted_modifiers, patch_ccmp, turned_small_f, unseat_marks  # noqa: E402
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
            mark = f[a].width == 0
            swap_glyph_outlines(f, a, b)
            if mark:
                f[a].width = 0  # Inter's dotbelow.ss07 has an advance; the combining dot below must not
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
SMALL_CAP_MARKS = ("_top", "_bottom", "_ogonek", "_cedilla")  # the anchors a mark attaches by
SMALL_CAP_FLAT = (0x044D, 0x0454)  # э and є, whose openings close at Black when their bars are emboldened
# A capital's bar, dot, tail or stroke emboldened with it closes the small capital's counters at Black,
# so these small capitals are their base's small capital with the parts set apart. A "scaled" part is
# the capital's, scaled and placed as the capital's outline is but not emboldened, so it keeps the
# capital's room ("full" keeps its size, "thick" its thickness; "middle" centres it in the white it
# crosses near its top, "cross" the white at its own centre, "clip" keeps it 0.3 stem off the walls, and "retract" ends a bar that would leave less than
# that each side at the stem it crosses); any other part is the lowercase's,
# at its own size, and keeps its place against the base: x against the ink's left, right or centre
# or after the advance, y as drawn or centred. A "fit" part shrinks to under 0.45 of the white it
# sits in and moves to where that white is widest.
SMALL_CAP_PARTS = {
    0x0140: ("left", "keep"),  # ŀ: L and ŀ's dot
    0x0180: ("scaled", "retract"),  # ƀ: B and Ƀ's bar, which ends at the stem where B's counter is too small for it
    0x01E5: ("scaled", "full", "clip"),  # ǥ: G and Ǥ's bar, at its own size so it reaches past the jaw, clear of the bowl
    0x2C65: ("scaled", "thick", "cross"),  # ⱥ: A and Ⱥ's stroke, as thick as the capital's, across the middle of A's counter
    0x04B9: ("scaled", "thick", "middle"),  # ҹ: Ч and Ҹ's stroke, as thick as the capital's, in the middle of the white
    0x047F: ("center", "keep"),  # ѿ: Ѡ and ѿ's т
    0x048B: ("right", "keep"),  # ҋ: Й and ҋ's tail
    0x0479: ("after", "keep"),  # ѹ: О and ѹ's у, as Ѹ is О and у
    0x0298: ("center", "center", "fit"),  # ʘ: O and ʘ's dot; ʘ has no capital
    0x037D: ("center", "center", "fit"),  # ͽ: Ͻ and ͽ's dot, set back from the mouth where Black's terminals curl in
    0x01F0: ("center", "keep"),  # ǰ: J and ǰ's caron; ǰ has no capital
    0x1E96: ("center", "keep"),  # ẖ: H and ẖ's line; ẖ has no capital
}
# Black's emboldening closes these small capitals' counters (ß's channel, ω's legs, ỿ's loop,
# the hook of ʕ, A's triangle, Ч's bowl): at Black they are drawn this much wider and emboldened
# this share of the way back to the lowercase stem across, and this share of the horizontal strokes' way up
SMALL_CAP_OPEN = {
    0x00DF: (1.14, 0.3, 1),
    0x03C9: (1.10, 0.3, 1),
    0x1EFF: (1.12, 0.5, 0.4),
    0x0295: (1.10, 1, 1),
    0x0061: (1.14, 0.45, 1),
    0x0250: (1.14, 0.45, 1),
    0x0447: (1.12, 0.6, 1),
}
SMALL_CAP_SELF = (0x0295,)  # ʕ is drawn at the cap height and has no capital: its small capital is ʕ redrawn
# Ɤ is ɤ with its arms drawn up and Ʝ is ʝ's tail under a stem, so their small capitals are ɤ and dotless ʝ, tracked
SMALL_CAP_LOWER = {0x0264: None, 0x029D: "jcrosstail.ccmp"}


def letter_marks(f, name):
    """The glyph under name's marks and each mark component with the anchor it attaches to,
    or None unless name is a letter set from an unmoved component and marks. A glyph that is
    one unmoved component (ӓ is ä) is followed, and a base that is itself a letter with marks
    is opened, so į, a dotless i with an ogonek under i's dot, gives the dotless i with the
    ogonek; the dot of i or j is dropped."""
    g = f[name]
    if g.contours or not g.components or tuple(g.components[0].transformation) != (1, 0, 0, 1, 0, 0):
        return None
    if len(g.components) == 1:
        return letter_marks(f, g.components[0].baseGlyph)
    marks = []
    for c in g.components[1:]:
        attach = next((a.name[1:] for a in f[c.baseGlyph].anchors if a.name in SMALL_CAP_MARKS), None)
        if attach is None:
            return None
        marks.append((c, attach))
    base = g.components[0].baseGlyph
    inner = letter_marks(f, base)
    if inner:
        base, marks = inner[0], inner[1] + marks
    if base in ("idotless", "jdotless"):
        marks = [(c, a) for c, a in marks if not c.baseGlyph.startswith("dotaccentcomb")]
    return base, marks


def _contour_points(font, glyph, transform=(1, 0, 0, 1, 0, 0), steps: int = 8) -> list[list[tuple[float, float]]]:
    """Each contour of glyph, components drawn in and curves flattened, as points."""
    rec = DecomposingRecordingPen(font)
    glyph.draw(rec)
    xx, xy, yx, yy, dx, dy = transform
    contours, cur = [], []
    for op, args in rec.value:
        if op == "moveTo":
            cur = [args[0]]
            contours.append(cur)
        elif op == "curveTo":
            (ax, ay), ((bx, by), (cx, cy), (ex, ey)) = cur[-1], args
            cur += [((1 - t) ** 3 * ax + 3 * (1 - t) ** 2 * t * bx + 3 * (1 - t) * t * t * cx + t**3 * ex,
                     (1 - t) ** 3 * ay + 3 * (1 - t) ** 2 * t * by + 3 * (1 - t) * t * t * cy + t**3 * ey)
                    for t in (j / steps for j in range(1, steps + 1))]
        elif args:
            cur.append(args[-1])
    return [[(xx * x + yx * y + dx, xy * x + yy * y + dy) for x, y in c] for c in contours]


def _gap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    return min(math.dist(p, q) for p in a for q in b)


def _spans(font, glyph, x: float, y: float):
    """The nearest ink left, right, below and above (x, y), each None where there is none."""
    xs, ys = [], []
    for c in _contour_points(font, glyph):
        for (x0, y0), (x1, y1) in zip(c, c[1:] + c[:1]):
            if (y0 <= y < y1) or (y1 <= y < y0):
                xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            if (x0 <= x < x1) or (x1 <= x < x0):
                ys.append(y0 + (x - x0) * (y1 - y0) / (x1 - x0))
    return (max((v for v in xs if v < x), default=None), min((v for v in xs if v > x), default=None),
            max((v for v in ys if v < y), default=None), min((v for v in ys if v > y), default=None))


def _room(font, glyph, x: float, y: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """The white around (x, y) along the horizontal and the vertical through it. A side open
    to the outside (ͽ's mouth) closes where the ink above and below it ends."""
    left, right, low, high = _spans(font, glyph, x, y)
    b = glyph.getBounds(font)
    for side, step in (("left", -8), ("right", 8)):
        if (left if side == "left" else right) is None:
            edge = x
            while b.xMin <= edge <= b.xMax and all(v is not None for v in _spans(font, glyph, edge + step, y)[2:]):
                edge += step
            if side == "left":
                left = edge
            else:
                right = edge
    return (left, right), (b.yMin if low is None else low, b.yMax if high is None else high)


def _widest_white(font, glyph, x: float, y: float) -> tuple[float, float, float]:
    """Along the horizontal through (x, y), inside the white it lies in, the point whose
    white is widest both ways, and that width: a dot there clears the walls on every side.
    An open side (ͽ's mouth) does not count as a wall."""
    left, right, _, _ = _spans(font, glyph, x, y)
    lo = left if left is not None else glyph.getBounds(font).xMin
    hi = right if right is not None else glyph.getBounds(font).xMax
    best = (x, y, 0.0)
    for i in range(1, 64):
        cx = lo + (hi - lo) * i / 64
        _, _, low, high = _spans(font, glyph, cx, y)
        if low is None or high is None:
            continue
        across = 2 * min(cx - left if left is not None else math.inf, right - cx if right is not None else math.inf)
        room = min(across, high - low)
        if room > best[2]:
            best = (cx, (low + high) / 2, room)
    return best


def fit_part(font, base, part, rule, gap: float) -> None:
    """Seat a small capital's bar or stroke in the white of its base: "middle" and "cross" centre it
    across the white it crosses, "clip" keeps its far end and top `gap` off the walls of
    the counter its left end sits in, and "retract" ends a bar at the wall it crosses
    when the counter beyond leaves it less than `gap` above, below or after it."""
    b = part.getBounds(font)
    cy = (b.yMin + b.yMax) / 2
    points = [p for c in part.contours for p in c.points]
    if "middle" in rule or "cross" in rule:  # "middle" measures near its top, clear of the stroke it crosses
        y = b.yMax - 0.2 * (b.yMax - b.yMin) if "middle" in rule else cy
        (x0, x1), _ = _room(font, base, (b.xMin + b.xMax) / 2, y)
        for p in points:
            p.x += (x0 + x1 - b.xMin - b.xMax) / 2
    if "clip" in rule:
        (x0, x1), (y0, y1) = _room(font, base, b.xMin + 0.25 * (b.xMax - b.xMin), cy)
        down = max(min(0, y1 - gap - b.yMax), y0 + gap - b.yMin)
        for p in points:
            p.x, p.y = max(p.x, x0 + gap), p.y + down
    if "retract" in rule:
        (x0, x1), (y0, y1) = _room(font, base, b.xMax - 1, cy)
        if x1 - b.xMax < gap or b.yMin - y0 < gap or y1 - b.yMax < gap:
            for p in points:
                p.x = min(p.x, x0)


def clear_horns(f, letters: dict[str, tuple[str, str]]) -> None:
    """The accents above a horned small capital (ữ, ớ) clear the horn by as
    much as the lowercase's do at the same weight: they move left by up to
    48 units, then up, because the small capital's horn rises nearer them.
    letters maps each to its lowercase base and its small capital base."""
    for lc, (b, base) in letters.items():
        g = f[f"{lc}.smcp"]
        above = lambda comps: [c for c in comps if any(a.name == "_top" for a in f[c.baseGlyph].anchors)]  # noqa: E731
        horn = lambda name: max(_contour_points(f, f[name]), key=lambda c: max(x for x, _ in c))  # noqa: E731
        ink = lambda comps: [p for c in comps for contour in _contour_points(f, f[c.baseGlyph], c.transformation) for p in contour]  # noqa: E731
        marks, h = above(g.components), horn(f"{base}.smcp")
        if not marks or not above(f[lc].components):  # ự has only a dot below
            continue
        want = _gap(horn(b), ink(above(f[lc].components)))
        shift = lift = 0
        while shift + lift < 200 and _gap(h, [(x - shift, y + lift) for x, y in ink(marks)]) < want:
            if shift < 48:
                shift += 8
            else:
                lift += 8
        for c in marks:
            t = list(c.transformation)
            t[4], t[5] = t[4] - shift, t[5] + lift
            c.transformation = tuple(t)


def small_caps(fonts) -> None:
    """Small capitals for every lowercase letter with a capital, as smcp and c2sc.

    Inter has none (its 13 .sc glyphs are phonetic letters). Each small cap is
    its capital scaled to the x-height, emboldened back to the lowercase stem
    (and 0.4 of that on horizontal strokes), and tracked a little wider.
    Accented small caps are built like the accented lowercase: the small cap of
    the capital's base with the lowercase's marks, each moved by the difference
    in the anchor it attaches to, and the capital's ogonek scaled with the letter,
    because the lowercase shapes its own to its letter. A capital set from other capitals (Ĳ, Ы) is set
    from their small caps. Every other letter (ø, ł, ď, and α, whose capital is
    a component of A) is drawn from its capital, components drawn in. The
    letters in SMALL_CAP_PARTS are their base's small cap with the capital's
    bar or stroke scaled, or the lowercase's own dot, tail or mark; ʕ is
    redrawn from itself, ɤ is ɤ tracked, and the accents of ữ and the other
    horned letters clear the horn as the lowercase's do.
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
    if 0x00DF in cmap and 0x1E9E in cmap:
        pairs[cmap[0x00DF]] = cmap[0x1E9E]  # ß capitalises to SS; its small capital is ẞ
    for u in SMALL_CAP_SELF:
        if u in cmap:
            pairs[cmap[u]] = cmap[u]
    capital = dict(pairs)
    anchor = lambda g, name: next(((a.x, a.y) for a in g.anchors if a.name == name), None)  # noqa: E731

    def part_shape(f, lc):
        """lc's base and its other parts, or None unless lc is a base, moved at most, with other parts."""
        g = f[lc]
        if not g.components or tuple(g.components[0].transformation)[:4] != (1, 0, 0, 1):
            return None
        return g.components[0].baseGlyph, [c.baseGlyph for c in g.components[1:]], len(g.contours)

    # every master must set the letter from the same parts
    source = lambda lc, rule: capital.get(lc) if rule[0] == "scaled" else lc  # noqa: E731
    parted = {cmap[u]: rule for u, rule in SMALL_CAP_PARTS.items()
              if u in cmap and source(cmap[u], rule) and part_shape(ref, source(cmap[u], rule))
              and all(part_shape(f, source(cmap[u], rule)) == part_shape(ref, source(cmap[u], rule)) for f in fonts.values())}
    lowered = {cmap[u]: src or cmap[u] for u, src in SMALL_CAP_LOWER.items() if u in cmap and (src or cmap[u]) in ref}
    for lc in [*parted, *lowered]:
        pairs.pop(lc, None)
    shape = lambda m: m and (m[0], [(c.baseGlyph, a) for c, a in m[1]])  # noqa: E731
    drawn = [lc for lc, uc in pairs.items() if ref[uc].contours and not ref[uc].components]
    marked = {lc: letter_marks(ref, lc) for lc in pairs if lc not in drawn}
    marked = {lc: m for lc, m in marked.items() if m and m[1]}  # ј is j, its dot dropped: a letter with no marks

    def parts(uc):
        """The capitals a capital is set from side by side (Ĳ is I and J), or None."""
        g = ref[uc]
        if g.contours or len(g.components) < 2 or any(tuple(c.transformation[:4]) != (1, 0, 0, 1) for c in g.components):
            return None
        names = [c.baseGlyph for c in g.components]
        letters = all(ref[n].unicodes and unicodedata.category(chr(ref[n].unicodes[0])) == "Lu" for n in names)
        return names if letters else None

    # the rest (ø, ł, ď, œ, ư with its horn, and α, в and the other letters whose
    # capital is a component) are drawn from their capitals' outlines, components drawn in
    redrawn = [lc for lc in pairs if lc not in drawn and lc not in marked]
    small = {}  # capital -> the lowercase whose small capital draws it
    for lc in drawn + redrawn:
        small.setdefault(pairs[lc], lc)
    have = set(drawn) | set(redrawn)

    def plan(f, lc):
        """The base lowercase, the small capital it sits on, its marks and the capital's marks."""
        b, marks = letter_marks(f, lc)
        cap = letter_marks(f, pairs[lc])
        if not cap:  # Ἀ moves its A to make room for the breathing
            return b, b if b in have else None, marks, []
        # ӱ is ÿ with a dieresis, and its small capital is У's
        return b, b if pairs.get(b) == cap[0] and b in have else small.get(cap[0]), marks, cap[1]

    # an accented letter is set when every master has the same marks, the capital's base
    # has a small capital, and each mark has its anchor on both
    built = []
    for lc, m in marked.items():
        if not all(shape(letter_marks(f, lc)) == shape(m) for f in fonts.values()):
            continue
        b, base, marks, _ = plan(ref, lc)
        if base and all(anchor(ref[b], a) and anchor(ref[pairs[base]], a) for _, a in marks):
            built.append(lc)
    for lc in built:
        small.setdefault(pairs[lc], lc)
    # an accented letter that cannot be built (ɉ's capital is J with a bar, ʝ's is drawn) is drawn
    # from its capital, unless the capital carries marks, which emboldening would fuse
    has_marks = lambda uc: any(anchor(ref[c.baseGlyph], a) for c in ref[uc].components for a in SMALL_CAP_MARKS)  # noqa: E731
    unbuilt = [lc for lc in marked if lc not in built and not has_marks(pairs[lc])]
    redrawn += unbuilt
    for lc in unbuilt:
        small.setdefault(pairs[lc], lc)
    compound = [lc for lc in redrawn if parts(pairs[lc]) and all(n in small and small[n] != lc for n in parts(pairs[lc]))]
    redrawn = [lc for lc in redrawn if lc not in compound]
    flat = {cmap[u] for u in SMALL_CAP_FLAT if u in cmap}
    opened = {cmap[u]: v for u, v in SMALL_CAP_OPEN.items() if u in cmap}
    for style, f in fonts.items():
        upm, xh, cap = f.info.unitsPerEm, f.info.xHeight, f.info.capHeight
        lc_stem = stem(f)
        b = f["I"].getBounds(f)
        uc_stem = b.xMax - b.xMin
        dx = lc_stem - uc_stem * xh / cap
        dy = 0.4 * dx  # less on horizontals, or Black's bars close the counters of E and S
        k = (xh - dy) / cap
        track = SMALL_CAP_TRACK * upm
        for lc in drawn + redrawn:
            src = f[pairs[lc]]
            g = f.newGlyph(f"{lc}.smcp")
            pen = DecomposingRecordingPen(f, reverseFlipped=True)  # И is N mirrored; emboldening needs its contours the right way round
            src.draw(pen)
            pen.replay(g.getPen())
            kk, ddy = (xh / cap, 0) if lc in flat else (k, dy)
            wide, share, up = opened.get(lc, (1, 1, 1)) if style == "Black" else (1, 1, 1)
            kx, ddx, ddy = kk * wide, dx * share, ddy * up
            for c in g.contours:
                for pt in c.points:
                    pt.x, pt.y = pt.x * kx, pt.y * kk
            embolden_x(g, ddx)
            embolden_y(g, ddy)
            for c in g.contours:
                for pt in c.points:
                    pt.x, pt.y = pt.x + ddx / 2 + track / 2, pt.y + ddy / 2
            for a in src.anchors:
                g.appendAnchor({"name": a.name, "x": a.x * kx + ddx / 2 + track / 2, "y": a.y * kk + ddy / 2})
            g.width = round(src.width * kx + ddx + track)
            if SERIFS_KEY in src.lib:  # drawn from the capital in order, so its serifs keep their indices
                g.lib[SERIFS_KEY] = list(src.lib[SERIFS_KEY])
        for lc in compound:
            src = f[pairs[lc]]
            g = f.newGlyph(f"{lc}.smcp")
            for i, c in enumerate(src.components):
                x = c.transformation[4] * k + i * (dx + track)
                g.components.append(Component(f"{small[c.baseGlyph]}.smcp", (1, 0, 0, 1, round(x), round(c.transformation[5] * k))))
            for a in src.anchors:
                g.appendAnchor({"name": a.name, "x": a.x * k + dx / 2 + track / 2, "y": a.y * k + dy / 2})
            g.width = round(src.width * k + len(src.components) * (dx + track))
        for lc in built:
            b, base, marks, cap_marks = plan(f, lc)
            sc = f[f"{base}.smcp"]
            g = f.newGlyph(f"{lc}.smcp")
            g.width = sc.width
            g.components.append(Component(sc.name))
            ogonek = next((c for c, a in cap_marks if a == "ogonek"), None)
            for c, a in marks:
                # the capital's ogonek scaled with the letter: the lowercase's is shaped to its letter (ę's hangs from the bowl)
                if a == "ogonek" and ogonek:
                    (x1, y1), (mx, my) = anchor(sc, a), anchor(f[ogonek.baseGlyph], "_ogonek")
                    g.components.append(Component(ogonek.baseGlyph, (k, 0, 0, k, round(x1 - k * mx), round(y1 - k * my))))
                    continue
                (x0, y0), (x1, y1) = anchor(f[b], a), anchor(sc, a)
                t = list(c.transformation)
                t[4], t[5] = t[4] + x1 - x0, t[5] + y1 - y0
                g.components.append(Component(c.baseGlyph, tuple(t)))
            for a in sc.anchors:
                g.appendAnchor({"name": a.name, "x": a.x, "y": a.y})
        clear_horns(f, {lc: plan(f, lc)[:2] for lc in built if plan(f, lc)[1] in ("uhorn", "ohorn")})
        for lc, rule in parted.items():
            scaled = rule[0] == "scaled"
            src = f[source(lc, rule)]
            base = src.components[0].baseGlyph
            lower = small.get(base, {"idotless": "i", "jdotless": "j"}.get(base, base))
            sc = f[f"{lower}.smcp"]
            lb, sb = f[base].getBounds(f), sc.getBounds(f)
            g = f.newGlyph(f"{lc}.smcp")
            g.components.append(Component(sc.name))
            right = sb.xMax
            ox, oy = src.components[0].transformation[4:]  # Black's Ƀ sets its B 80 units in
            pieces = [(c.baseGlyph, c) for c in src.components[1:]] + ([(None, src)] if src.contours else [])
            for name, c in pieces:
                a = name and next((a.name[1:] for a in f[name].anchors if a.name in SMALL_CAP_MARKS), None)
                if not scaled and a and anchor(f[base], a) and anchor(sc, a):  # a mark moves as its anchor does
                    (x0, y0), (x1, y1) = anchor(f[base], a), anchor(sc, a)
                    t = list(c.transformation)
                    t[4], t[5] = round(t[4] + x1 - x0), round(t[5] + y1 - y0)
                    g.components.append(Component(name, tuple(t)))
                    continue
                piece = f.newGlyph("_smcp_piece")
                if name:
                    piece.components.append(Component(name, c.transformation))
                else:
                    for contour in src.contours:
                        contour.drawPoints(piece.getPointPen())
                pb = piece.getBounds(f)
                pcx, pcy = (pb.xMin + pb.xMax) / 2, (pb.yMin + pb.yMax) / 2
                if scaled:
                    t = (k, 0, 0, k, dx / 2 + track / 2 - k * ox, dy / 2 - k * oy)
                    if "full" in rule:
                        t = (1, 0, 0, 1, (k - 1) * pcx + dx / 2 + track / 2 - k * ox, (k - 1) * pcy + dy / 2 - k * oy)
                else:
                    xrule, yrule = rule[:2]
                    sx = {"left": sb.xMin - lb.xMin, "right": sb.xMax - lb.xMax,
                          "center": (sb.xMin + sb.xMax - lb.xMin - lb.xMax) / 2, "after": sc.width - f[base].width}[xrule] - ox
                    sy = {"keep": 0, "center": (sb.yMin + sb.yMax - lb.yMin - lb.yMax) / 2}[yrule] - oy
                    t = (1, 0, 0, 1, round(sx), round(sy))
                    if "fit" in rule:
                        cx, cy, room = _widest_white(f, sc, pcx + sx, pcy + sy)
                        z = min(1, 0.45 * room / max(pb.xMax - pb.xMin, pb.yMax - pb.yMin))
                        t = (z, 0, 0, z, cx - z * pcx, cy - z * pcy)
                if name and not scaled and "fit" not in rule:  # every master sets it the same way
                    t0 = c.transformation
                    g.components.append(Component(name, (1, 0, 0, 1, t0[4] + t[4], t0[5] + t[5])))
                else:
                    pen = DecomposingRecordingPen(f)
                    piece.draw(pen)
                    drawn_piece = f.newGlyph("_smcp_drawn")
                    pen.replay(TransformPen(drawn_piece.getPen(), t))
                    if "thick" in rule:  # back to the capital's thickness: its area over its length
                        area = AreaPen(f)
                        piece.draw(area)
                        e = abs(area.value) / math.hypot(pb.xMax - pb.xMin, pb.yMax - pb.yMin) * (1 - k)
                        embolden_x(drawn_piece, e)
                        embolden_y(drawn_piece, e)
                    fit_part(f, sc, drawn_piece, rule, 0.3 * lc_stem)
                    for contour in drawn_piece.contours:
                        contour.drawPoints(g.getPointPen())
                    del f["_smcp_drawn"]
                right = max(right, t[0] * pb.xMax + t[4])
                del f["_smcp_piece"]
            g.width = round(sc.width + src.width - f[base].width) if rule[0] == "after" else round(sc.width + right - sb.xMax)
            for a in sc.anchors:
                g.appendAnchor({"name": a.name, "x": a.x, "y": a.y})
        for lc, src in lowered.items():
            g = f.newGlyph(f"{lc}.smcp")
            g.components.append(Component(src, (1, 0, 0, 1, round(track / 2), 0)))
            g.width = round(f[src].width + track)
            for a in f[src].anchors:
                g.appendAnchor({"name": a.name, "x": a.x + round(track / 2), "y": a.y})
    settle_facing_serifs(fonts, [f"{lc}.smcp" for lc in drawn + redrawn])
    made = drawn + redrawn + compound + built + list(parted) + list(lowered)
    lc_names = " ".join(made)
    sc_names = " ".join(f"{lc}.smcp" for lc in made)
    # one small cap per capital: dotless i, long s and final sigma share theirs with i, s and sigma
    upper = {}
    for lc in made:
        if capital.get(lc, lc) != lc:  # c2sc has nothing to do for ʕ, ʘ, ǰ and ẖ, which have no capital
            upper.setdefault(capital[lc], f"{lc}.smcp")
    uc_names = " ".join(upper)
    uc_sc_names = " ".join(upper.values())
    # Turkish and Azerbaijani i keeps its dot in small capitals, as İ does
    dotted = "i.smcp" in ref and 0x0130 in cmap
    for f in fonts.values():
        if dotted:
            sc, dot = f["i.smcp"], f["dotaccentcomb"]
            top = next(a for a in sc.anchors if a.name == "top")
            mark = next(a for a in dot.anchors if a.name == "_top")
            g = f.newGlyph("i.smcp.TRK")
            g.width = sc.width
            g.components.append(Component("i.smcp"))
            g.components.append(Component("dotaccentcomb", (1, 0, 0, 1, round(top.x - mark.x), round(top.y - mark.y))))
    turkic = f"""
feature smcp {{
  script latn;
  language TRK;
  sub i.smcp by i.smcp.TRK;
  language AZE;
  sub i.smcp by i.smcp.TRK;
}} smcp;
feature c2sc {{
  sub {cmap[0x0130]} by i.smcp.TRK;
}} c2sc;
""" if dotted else ""
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
""" + turkic


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
    keeps the joins of diagonals close to where they were. A dot keeps its shape
    and moves with its centre. Thin is unchanged."""
    order = [s for s in ("Thin", "Regular", "Black") if s in fonts]
    lighter = {heavy: fonts[light] for light, heavy in zip(order, order[1:])}
    snap = {style: {g.name: ([[pt.y for pt in c.points] for c in g.contours], [a.y for a in g.anchors],
                             [c.transformation[5] for c in g.components]) for g in f} for style, f in fonts.items()}
    dots = _dots(fonts["Regular"])
    for style, f in fonts.items():
        amount = amounts.get(style, 0.0)
        if style not in lighter or not amount:
            continue
        light = {name: snap[order[order.index(style) - 1]][name] for name in snap[style]}
        for g in f:
            ys, ays, cys = light[g.name]
            for ci, (c, cy) in enumerate(zip(g.contours, ys)):
                if ci in dots.get(g.name, ()):
                    shift = amount * (min(cy) + max(cy) - min(pt.y for pt in c.points) - max(pt.y for pt in c.points)) / 2
                    for pt in c.points:
                        pt.y += shift
                    continue
                for pt, y in zip(c.points, cy):
                    pt.y += amount * (y - pt.y)
            for an, y in zip(g.anchors, ays):
                an.y += amount * (y - an.y)
            for comp, y in zip(g.components, cys):
                xx, xy, yx, yy, dx, dy = comp.transformation
                comp.transformation = (xx, xy, yx, yy, dx, dy + amount * (y - dy))


DOT_SIZE = 1.8  # stems (Regular): the most a dot measures across


def _dots(font) -> dict[str, set[int]]:
    """Each glyph's dots, by contour index: outer contours at most DOT_SIZE stems
    across, about as wide as tall, whose boxes touch no other contour's (the dots
    of i, j, ! and ?, periods, diaereses)."""
    sw = stem(font)
    out = {}
    for g in font:
        boxes = [(min(p.x for p in c.points), min(p.y for p in c.points), max(p.x for p in c.points), max(p.y for p in c.points))
                 for c in g.contours]
        for i, c in enumerate(g.contours):
            x0, y0, x1, y1 = boxes[i]
            w, h = x1 - x0, y1 - y0
            pts = [(p.x, p.y) for p in c.points]
            outer = sum(xa * yb - xb * ya for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1])) > 0
            if not (outer and 0 < w <= DOT_SIZE * sw and 0 < h <= DOT_SIZE * sw and 0.75 <= w / h <= 1.33):
                continue
            if all(b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1 for j, b in enumerate(boxes) if j != i):
                out.setdefault(g.name, set()).add(i)
    return out


SERIF_TIP = 0.3  # the flat end of a head serif, as a share of its thickness
# A serif's bracket: how far it runs along the serif, as a share of the serif's
# reach, and how far it climbs the stroke, as a share of the serif's thickness.
BRACKET = (0.35, 0.45)
BRACKET_SIDE = 0.5  # the most of a short stroke side (inside x, A, K) a bracket may climb
ARM_WIDTH = 0.4  # an arm's serif, in stems
# Serif thickness per master, times serif_depth's share of the H crossbar: Thin's
# serifs as thick as its hairlines, so they hold at text sizes; Black's a little
# lighter than Regular's, so the heavy weights stay a text face and not a slab.
SERIF_DEPTH_SCALE = (1.24, 1.0, 0.6)  # Thin, Regular, Black
SERIF_REACH_POWER = (0.3, 0.0)  # toward Thin and toward Black, a serif's reach scales with the stem to this power
TIP_CLEAR = 0.23  # stems (Regular) a serif tip keeps from the edge of the advance, before the profile's spacing
SERIF_CLEAR = 0.25  # stems (Regular) of white a serif leaves to other ink it does not join
SERIF_GAP = 0.5  # stems (Regular): the least white between two serifs that face each other, inside a letter or between two
SERIF_HAIR = 0.1  # stems (Regular): white narrower than this between two facing serifs reads as a crack
SERIFS_KEY = "com.kerf.serifs"  # a glyph's foot and top serif contours, by index
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


def _ink_runs(font, g, y: float) -> list[tuple[float, float]]:
    """The spans of g's ink along height y, left to right, overlapping contours merged."""
    class Flat(BasePen):
        def __init__(self):
            super().__init__(font)
            self.segs, self.cur, self.start = [], None, None
        def _moveTo(self, p):
            self.cur = self.start = p
        def _lineTo(self, p):
            self.segs.append((self.cur, p))
            self.cur = p
        def _curveToOne(self, a, b, c):
            p0 = self.cur
            for k in range(1, 17):
                s = k / 16
                m = 1 - s
                q = tuple(m ** 3 * p0[i] + 3 * m * m * s * a[i] + 3 * m * s * s * b[i] + s ** 3 * c[i] for i in (0, 1))
                self.segs.append((self.cur, q))
                self.cur = q
        def _closePath(self):
            if self.cur != self.start:
                self.segs.append((self.cur, self.start))
            self.cur = self.start
    pen = Flat()
    g.draw(pen)
    cross = sorted((x0 + (y - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1)
                   for (x0, y0), (x1, y1) in pen.segs if min(y0, y1) <= y < max(y0, y1))
    out, wind, start = [], 0, 0.0
    for x, d in cross:
        if not wind:
            start = x
        wind += d
        if not wind:
            out.append((start, x))
    return out


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
    gap = SERIF_GAP * sw_ref
    ink_clear = SERIF_CLEAR * sw_ref
    parts = serif_parts(fonts["Regular"])
    for style, f in fonts.items():
        sw = stem(f)
        k = (sw / sw_ref) ** SERIF_REACH_POWER[sw > sw_ref]
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
            # a serif that does not run SERIF_CLEAR into other ink on its line stops SERIF_CLEAR short of it
            # (the foot of ß, the arm of a narrowed k)
            for sp in spans:
                if sp[6]:
                    continue
                band = [sp[2] + (-u if sp[3] else u) * t for u in (0.1, 0.5, 0.9)]
                lines = [_ink_runs(f, g, yb) for yb in band]
                for side in (4, 5):
                    if not sp[side]:
                        continue
                    if side == 4:
                        tip = sp[0] - sp[4]
                        edges = [max(near) for yb, line in zip(band, lines)
                                 if (near := [b for a, b in line if b < _side_x(sp[9], yb) - 1])]
                        if edges and not all(e >= tip + ink_clear for e in edges):
                            sp[4] = min(sp[4], max(0.0, sp[0] - max(edges) - ink_clear))
                    else:
                        tip = sp[1] + sp[5]
                        edges = [min(near) for yb, line in zip(band, lines)
                                 if (near := [a for a, b in line if a > _side_x(sp[10], yb) + 1])]
                        if edges and not all(e <= tip - ink_clear for e in edges):
                            sp[5] = min(sp[5], max(0.0, min(edges) - sp[1] - ink_clear))
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
            first = len(g.contours)
            for nodes in shapes:
                g.appendContour(_contour(nodes))
            g.lib[SERIFS_KEY] = [first + i for i, sp in enumerate(spans) if not sp[6]]
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


def settle_facing_serifs(fonts, names: list[str]) -> None:
    """Two serifs that face each other on one line and stand less than SERIF_HAIR
    apart in a master (a small capital, scaled and emboldened after its capital's
    serifs were cut) take Regular's arrangement there: joined, they overlap by
    SERIF_HAIR; apart, each facing end is cut back toward SERIF_GAP between them,
    no further than its bracket."""
    ref = fonts["Regular"]
    sw_ref = stem(ref)
    hair, gap = SERIF_HAIR * sw_ref, SERIF_GAP * sw_ref
    def box(c):
        xs, ys = [p.x for p in c.points], [p.y for p in c.points]
        return min(xs), max(xs), min(ys), max(ys)
    for name in names:
        if name not in ref:
            continue
        serifs = ref[name].lib.get(SERIFS_KEY, [])
        if len(serifs) < 2 or max(serifs) >= len(ref[name].contours):
            continue
        rb = {i: box(ref[name].contours[i]) for i in serifs}
        # i faces j from the left: one line (feet or tops), with i's ink left of j's
        pairs = [(i, j) for i in serifs for j in serifs
                 if i != j and rb[i][0] < rb[j][0] and (abs(rb[i][2] - rb[j][2]) <= 2 or abs(rb[i][3] - rb[j][3]) <= 2)
                 and not any(rb[i][1] < rb[m][0] and rb[m][1] < rb[j][0] for m in serifs if m not in (i, j))]
        for i, j in pairs:
            joined = rb[j][0] - rb[i][1] <= 0
            for f in fonts.values():
                g = f[name]
                (l0, l1, _, _), (r0, r1, _, _) = box(g.contours[i]), box(g.contours[j])
                white = r0 - l1
                if not 0 < white < hair:
                    continue
                want = -(white + hair) / 2 if joined else (gap - white) / 2
                for c, edge, way in ((g.contours[i], l1, -1), (g.contours[j], r0, 1)):
                    rest = [p.x for p in c.points if abs(p.x - edge) >= 0.5]
                    room = (edge - max(rest) if way < 0 else min(rest) - edge) - 1
                    cut = want if joined else min(want, max(0.0, room))
                    for p in c.points:
                        if abs(p.x - edge) < 0.5:
                            p.x += way * cut


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
    serifs and terminal faces as a letter's do."""
    return {font[n].components[0].baseGlyph for n in ("f", "t") if n in font and font[n].components}


TERMINAL_FACE = (0.45, 1.6)  # stems (Regular): how long a cut across a stroke may be to count as its end
TERMINAL_REF = 1.0  # stems: a terminal cut shorter than this (the superiors) is planned with its share of a full one
TERMINAL_SYMBOLS = set("?¿&§$¢€£@‽")  # symbols drawn with the letters' curved strokes
LEVEL_FACE_ANGLE = 6  # degrees: a cut further from level than this (Inter's a.2, £, §) ends plain
FACETS_KEY = "com.kerf.facets"
FACET_PREV, FACET_NEXT = "facet:prev", "facet:next"  # a facet's foot, its outer corner the point before it or after it
FACET = 0.45  # the facet's height, as a share of the cut's length (about a stem serif's thickness at Regular and Black)
RIGHT_EXITS = False  # whether a stroke rising out at the foot of a letter's right side (c, C, e, t) takes a facet
# letters whose curved ends both stay a level cut, the way C's foot already ends: C, S, c, s and G,
# the letters and signs drawn the same way, and the reversed C; their alternates and small capitals follow
PLAIN_ENDS = set("CSСЅЄЭϹ€" "csєᶜˢʗ" "Gɢ" "Ↄↄɔ")

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
    """Where Katagami Serif's terminals take a facet, found on Regular: every
    stroke end the serif plan leaves bare in letters, figures, their
    alternates, the stems of f and t and the symbols drawn like letters.

    A stroke end is a straight cut 0.45 to 1.6 stems long between two
    corners whose sides run back the way they came, with ink on one side of
    it and none on the other. A level cut (within LEVEL_FACE_ANGLE of
    horizontal) between two curves is the end of a curved stroke (C, G, S,
    a, c, s, the figures); it faces into the letter. An upright cut
    (within 30 degrees of vertical) ends a hook, an arm or a tail (r, f, j,
    y), unless it ends a stub in the middle third of the letter (the waist
    of 3) or a stroke lying on the baseline, x-height or cap height. A bar's
    end (the crossbars of f and t, the foot of 2) is not a terminal. The
    stroke rising out at the foot of a letter's right side (c, C, e, ε, the
    hook of t) ends plain, as in a text face, and so does the lower end of
    an opening whose upper end has a face on the same side (ɔ, Ↄ). The
    letters in PLAIN_ENDS end plain at both ends.
    Returns {glyph: [(kind, contour, i, j, outer, way, scale)]}: for a
    level cut the corner on the outside of the letter, for an upright cut
    the corner below or above it; way is 1 where the cut faces up and -1
    where it faces down; scale is the cut's length over TERMINAL_REF stems,
    at most 1.
    """
    ref = fonts["Regular"]
    sw = stem(ref)
    cat = lambda g: unicodedata.category(chr(g.unicodes[0])) if g.unicodes else ""  # noqa: E731
    drawn = {g.name for g in ref if g.unicodes and (cat(g)[0] in "LN" or chr(g.unicodes[0]) in TERMINAL_SYMBOLS)}
    names = [g.name for g in ref if g.contours and g.width and (g.name in drawn or (not g.unicodes and g.name.split(".")[0] in drawn))]
    names += sorted(serif_parts(ref) - set(names))
    metrics = (ref["x"].getBounds(ref).yMax, ref["H"].getBounds(ref).yMax)
    def plain(name):
        base = name.split(".")[0]
        if ref[name].unicodes:
            return chr(ref[name].unicodes[0]) in PLAIN_ENDS
        if base not in ref or not ref[base].unicodes:
            return False
        ch = chr(ref[base].unicodes[0])
        return (ch.upper() if name.endswith(".smcp") else ch) in PLAIN_ENDS
    out = {}
    for name in names:
        if plain(name):
            continue
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
                bar = (not into_curve and li >= 1.8 * sw) or (nxt.type == "line" and lo >= 1.8 * sw)
                angle = abs(math.degrees(math.atan2(q.y - a.y, q.x - a.x))) % 180
                angle = min(angle, 180 - angle)
                mid_x, mid_y, cut_y = (b.xMin + b.xMax) / 2, (b.yMin + b.yMax) / 2, (a.y + q.y) / 2
                if angle <= 30:
                    if angle > LEVEL_FACE_ANGLE:
                        continue
                    kind = "level"
                    # the ink is left of travel, so the bare side faces up when the cut runs right to left
                    way = 1 if q.x < a.x else -1
                    # the end faces into the letter, never past its top or foot (the arms of ω)
                    if (way > 0) != (cut_y < mid_y):
                        continue
                    # only the end of a curved stroke can be cut back to a face its stroke meets at a slant
                    if not (into_curve and out_curve):
                        continue
                elif angle >= 60 and not bar:
                    kind = "upright"
                    lo_y, hi_y = sorted((a.y, q.y))
                    if abs(lo_y) < 3 or any(abs(hi_y - m) < 3 for m in metrics):
                        continue
                    if abs(cut_y - mid_y) < (b.yMax - b.yMin) / 6:
                        continue
                    way = -1 if cut_y > mid_y else 1
                else:
                    continue
                ink_left, bare_right = _ink_side(ref, g, a, q)
                if not (ink_left and bare_right):
                    continue
                if not RIGHT_EXITS and way > 0 and (a.x + q.x) / 2 > mid_x:
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
    """Whether the end at the foot of an opening would face the end above it
    across that opening, a second jaw, as in ɔ and Ↄ: both cuts on the same
    side of the letter and nothing between them (the white at their
    mid-height reaches the letter's middle, where 3 has its waist). The
    upper end keeps its face."""
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
        for t in range(1, 21):
            pen = PointInsidePen(font, (x0 + (mid_x - x0) * t / 20, mid_y))
            g.draw(pen)
            if pen.getResult():
                break
        else:
            return True
    return False


def _edges(pts, i: int, j: int, outer: int):
    """The cubics on either side of the cut from i to j, each as its four
    points' indices from the cut's corner outward: (outer edge, inner edge).
    None where one side is not a single curve."""
    n = len(pts)
    into = [i, (i - 1) % n, (i - 2) % n, (i - 3) % n]  # from corner i back along the arriving edge
    out = [j, (j + 1) % n, (j + 2) % n, (j + 3) % n]
    for side in (into, out):
        if pts[side[1]].type is not None or pts[side[2]].type is not None or pts[side[3]].type is None:
            return None
    return (into, out) if outer == i else (out, into)


def _trim(pts, side, t: float) -> None:
    """Cut the cubic `side` at t (from its corner), keeping the part away from
    the corner: the corner moves to the cut and both handles shrink with it,
    so the edge stays a piece of its own curve."""
    c = [(pts[k].x, pts[k].y) for k in side]
    _, rest = _split(c, t)
    for k, (x, y) in zip(side[:3], rest[:3]):
        pts[k].x, pts[k].y = x, y


def _side_curve(pts, side):
    return [(pts[k].x, pts[k].y) for k in side]


def _first_crossing(c, fn, lo: float, hi: float):
    """The first parameter from lo toward hi where the cubic c crosses fn's zero, or None."""
    steps = 120
    prev = fn(_point(c, lo))
    for k in range(1, steps + 1):
        t = lo + (hi - lo) * k / steps
        cur = fn(_point(c, t))
        if prev == 0 or prev * cur < 0:
            a, b = t - (hi - lo) / steps, t
            for _ in range(50):
                m = (a + b) / 2
                if fn(_point(c, a)) * fn(_point(c, m)) <= 0:
                    b = m
                else:
                    a = m
            return (a + b) / 2
        prev = cur
    return None


def _facet(pts, term) -> bool:
    """A small square facet at the cut's outer corner: the outer edge is trimmed where
    it stands FACET of the cut's length from the cut's line (split by de Casteljau, so it
    stays a piece of its own curve), and the corner becomes a short face square to the
    cut, its foot a new point on the cut. Returns False, changing nothing, where the
    edge is not a single curve or does not reach that far."""
    kind, ci, i, j, outer, way, scale = term
    if kind == "upright":
        outer = j if outer == i else i  # an upright term records the corner below or above the outer edge
    sides = _edges(pts, i, j, outer)
    if sides is None:
        return False
    o_side, n_side = sides
    ox, oy = pts[o_side[0]].x, pts[o_side[0]].y
    nc = pts[n_side[0]]
    length = math.hypot(nc.x - ox, nc.y - oy)
    ux, uy = (nc.x - ox) / length, (nc.y - oy) / length  # along the cut, outer to inner
    nx, ny = -uy, ux  # square to the cut, into the stroke: toward the outer edge's far end
    far = pts[o_side[3]]
    if (far.x - ox) * nx + (far.y - oy) * ny < 0:
        nx, ny = -nx, -ny
    h = FACET * length
    t = _first_crossing(_side_curve(pts, o_side), lambda p: (p[0] - ox) * nx + (p[1] - oy) * ny - h, 0.0, 0.95)
    if t is None:
        return False
    _trim(pts, o_side, t)
    top = pts[o_side[0]]
    d = (top.x - ox) * ux + (top.y - oy) * uy
    lo, hi = sorted((i, j))
    wrap = (lo, hi) == (0, len(pts) - 1)
    # named for the site's morph, which grows the facet out of the outer corner: the one before the foot or after it
    before = o_side[0] == (hi if wrap else lo)
    foot = Point(ox + d * ux, oy + d * uy, "line", name=FACET_PREV if before else FACET_NEXT)
    if wrap:
        pts.append(foot)
    else:
        pts.insert(hi, foot)
    return True


def small_cap_terminals(fonts, plan: dict) -> dict:
    """The terminals of each drawn small capital: its capital's, where the small capital
    keeps the capital's contours point for point (small_caps copies them in order)."""
    ref = fonts["Regular"]
    cmap = {u: g.name for g in ref for u in g.unicodes}
    out = {}
    for g in ref:
        if not g.name.endswith(".smcp") or not g.contours:
            continue
        lc = g.name[: -len(".smcp")]
        if lc not in ref or not ref[lc].unicodes:
            continue
        up = chr(ref[lc].unicodes[0]).upper()
        cap = cmap.get(ord(up)) if len(up) == 1 else None
        if cap in plan and [len(c.points) for c in ref[cap].contours] == [len(c.points) for c in g.contours]:
            out[g.name] = plan[cap]
    return out


def cut_terminals(fonts, plan: dict) -> None:
    """Give every terminal plan_terminals found a small square facet at its outer
    corner (`_facet`), on Text's own curve: Text's cut stays where it is, the outer
    edge is only trimmed along itself, and no other point moves. A terminal takes a
    facet only where every master can cut it. The facet adds a point, so this runs
    after the stem serifs, whose plan holds point numbers, and each contour's later
    terminals are cut first, so the earlier numbers stay valid."""
    kept = {name: [term for term in terms if all(_facet(copy.deepcopy(f[name].contours[term[1]].points), term)
                                                 for f in fonts.values())] for name, terms in plan.items()}
    for f in fonts.values():
        # which glyphs took facets, so an Italic can take the roman's design where the two differ (build pops it)
        f.lib[FACETS_KEY] = sorted(name for name, terms in kept.items() if terms)
        for name, terms in kept.items():
            for term in sorted(terms, key=lambda tm: (tm[1], -max(tm[2], tm[3]))):
                _facet(f[name].contours[term[1]].points, term)


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
    add_missing(fonts)
    declare_scripts(fonts)
    if p.square_punctuation:
        promote_square_punctuation(fonts)
    if p.promote:
        promote_alternates(fonts, p.promote, FEATURES)
        relabel_features(fonts, p.promote)
    dot_marks(fonts)
    soft_dotted_modifiers(fonts)
    # after the swaps, which carry each alternate's own anchors into the default
    complete_anchors(fonts)
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
        cut_serifs(fonts, plan, p.serif_reach, p.serif_depth, p.serif_head, p.serif_beak)
    straighten_q(fonts)
    small_caps(fonts)
    turned_small_f(fonts)
    if p.serif_reach:
        # after the serifs (a facet adds a point, and their plan holds point numbers) and after the
        # small capitals, so each takes its own facets on its own curve, not its capital's re-emboldened
        cut_terminals(fonts, terminals | small_cap_terminals(fonts, terminals))
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
        # and where the Italic's own drawing takes terminal facets the roman's does not (or the other
        # way round: Inter Italic's J ends in a curve the facets can cut, the roman's in a straight stub)
        faceted = set(fonts["Regular"].lib.get(FACETS_KEY, [])) ^ set(roman["Regular"].lib.get(FACETS_KEY, []))
        replaced = sorted(name for name, d in distances.items() if d > ITALIC_MATCH or name in faceted)
        romanize(fonts, roman, replaced)
        for f in fonts.values():
            f["notequal"].width = f["equal"].width  # ≠ takes the roman's a unit narrower than the Italic's other math signs
        corners = {name: plan for name, plan in corners.items() if name in roman["Regular"] and name not in replaced}
        corners |= {name: roman_corners[name] for name in replaced if name in roman_corners}
        decompose_transformed(fonts)  # the scaled and turned parts built since the Italic was stood upright
        shear(fonts, slant_tangent(fonts["Regular"]), fonts["Regular"].info.xHeight / 2)
    for f in fonts.values():
        f.lib.pop(FACETS_KEY, None)
    erase_open_corners(fonts)
    unseat_marks(fonts["Regular"])

    out = ROOT / "build" / (f"{p.key}-italic" if italic else p.key)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(FEATURES, out / "features")
    patch_ccmp(out / "features")
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

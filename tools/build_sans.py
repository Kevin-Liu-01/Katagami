"""Build a proportional Katagami member from Inter's Thin, Regular and Black masters.

    python tools/build_sans.py [sans|round]

Inter -> profile, in order (each step only where the profile asks for it):
  1. Inter alternates promoted to the default (square punctuation, profile picks)
  2. quarter arcs squared or rounded (planned on Regular)
  3. bowl-to-stem notches and m's dip filled, g, y and t ends redrawn
  4. per-glyph widths changed with stems held, composites re-seated
  5. sidebearings adjusted
"""

from __future__ import annotations

import copy
import math
import shutil
import sys
import unicodedata
from pathlib import Path

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import (  # noqa: E402
    MASTERS, ROOT, assign_categories, erase_open_corners, load_inter_masters, promote_alternates, reflow_composites, resize_glyph, respace,
    set_names, snapshot, stem, swap_glyph_outlines,
)
from kerf_build.outline import (  # noqa: E402
    apply_squaring, embolden_x, embolden_y, handles, keep_stroke, plan_corners, plan_squaring, round_corners,
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
    "cv01-one.fea": ("Alternate one", "Inter one"),
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
            text = text.replace('name "Open digits";', 'name "Inter digits";')
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


G_REACH = 0.9  # how far the g tail reaches left of the bottom's centre, as a share of the right side's reach


def redraw_tails(fonts, p: Profile) -> None:
    """Redraw the ends of g, y and t (and a's foot where it has one). Point counts never change.

    g: the tail is the right side's turn into the bottom, mirrored about the
    bottom's centre, drawn in to G_REACH of its width so the end sits inside
    the bowl, and cut level at Inter's terminal height. The curl matches the
    bowl side's squaring and the cut is square to the stroke.
    The inner edge then leans toward the outer one, by nothing at the
    counter's floor and by enough at the cut to leave it `g_tip` as wide, so
    the stroke thins as it rises instead of ending as heavy as the stem.

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
        d = (1 - p.g_tip) * (high[3][0] - P(cut).x)
        lean = lambda q: (q[0] - d * (floor.x - q[0]) / (floor.x - high[3][0]), q[1])  # noqa: E731
        for i, xy in zip((cut - 3, cut - 2, cut - 1), high[1:]):
            _set(P(i), lean(xy))

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


def is_bowl_letter(glyph) -> bool:
    """b, d, p and q and their drawn variants (with stroke, hook, and so on)."""
    if not glyph.unicodes:
        return False
    name = unicodedata.name(chr(glyph.unicodes[0]), "")
    return any(name == f"LATIN SMALL LETTER {c}" or name.startswith(f"LATIN SMALL LETTER {c} WITH ") for c in "BDPQ")


def fill_notches(fonts, amount: float, bowl_amount: float | None = None) -> None:
    """Move each notch corner part of the way toward its stem's end.

    Inter's heavy weights cut deep notches where bowls join stems, which
    leaves a hairline in bold a and u. Moving the corner, its step and its
    handle a share of the way toward the baseline (or x-height) shortens the
    notch and thickens the join, in proportion at every weight.
    """
    ref = fonts["Regular"]
    plans = {g.name: find_notches(g, ref.info.xHeight) for g in ref
             if g.contours and g.unicodes and unicodedata.category(chr(g.unicodes[0])) == "Ll"}
    bowls = {name for name in plans if is_bowl_letter(fonts["Regular"][name])}
    for style, f in fonts.items():
        for name, notches in plans.items():
            g = f[name]
            share = (bowl_amount if bowl_amount is not None and name in bowls else amount) * JOIN_BY_MASTER[style]
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
                pts = f[name].contours[ci].points
                n = len(pts)
                P = lambda k: pts[k % n]  # noqa: E731
                if P(i - 3).type is None or P(j + 2).type is not None or P(j + 3).type != "curve":
                    continue
                p, q = P(i), P(j)
                mid = ((p.x + q.x) / 2, (p.y + q.y) / 2)
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
                    continue
                left, _ = _split(ca, ta)
                _, right = _split(cb, tb)
                for pt, (x, y) in zip(into[1:], left[1:]):
                    pt.x, pt.y = x, y
                for pt, (x, y) in zip(out[:3], right[:3]):
                    pt.x, pt.y = x, y


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
    """Let the f's crossbar reach `overhang` stems past the stem's left edge.

    The compact f's bar starts inside its stem, so nothing shows on the left.
    The bar's left end moves out; the glyph shifts right by half the gain and
    its advance grows by the same half, so its spacing stays balanced.
    """
    if not overhang:
        return
    for f in fonts.values():
        g = f["f"]
        bars = [c for c in g.contours if len(c.points) == 4]
        if len(bars) != 1 or not g.components:
            continue
        part = g.components[0]
        stem_left = f[part.baseGlyph].getBounds(f).xMin + part.transformation[4]
        target = stem_left - overhang * stem(f)
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
        maps = {name: resize_glyph(f, name, k, sw) for name, k in scales.items()
                if name in f and k != 1 and all(m[name].width > 0 for m in fonts.values())}
        reflow_composites(f, maps, old)


def write_designspace(p: Profile, out_dir: Path, paths: dict[str, Path]) -> Path:
    ds = DesignSpaceDocument()
    ax = AxisDescriptor()
    ax.tag, ax.name, ax.minimum, ax.default, ax.maximum = "wght", "Weight", 100, 400, 900
    ax.map = list(p.weight_map)
    ds.addAxis(ax)
    design = dict(p.weight_map)
    for style, w in MASTERS.items():
        s = SourceDescriptor()
        s.path = str(paths[style])
        s.familyName, s.styleName = p.family, style
        s.location = {"Weight": design[w]}
        ds.addSource(s)
    for i, style in enumerate(INSTANCES):
        inst = InstanceDescriptor()
        inst.familyName, inst.styleName = p.family, style
        inst.location = {"Weight": design[(i + 1) * 100]}
        ds.addInstance(inst)
    out = out_dir / f"{p.file_stem}.designspace"
    ds.write(out)
    return out


def build(p: Profile) -> Path:
    fonts = load_inter_masters()
    if p.square_punctuation:
        promote_square_punctuation(fonts)
    if p.promote:
        promote_alternates(fonts, p.promote, FEATURES)
        relabel_features(fonts, p.promote)
    shape_curves(fonts, p)
    if p.terminal_angle is not None:
        level_terminals(fonts, p.terminal_angle)
    if p.c_close:
        close_c(fonts, p.c_close)
    f_crossbar_overhang(fonts, p.f_overhang)
    if p.notch_fill:
        fill_notches(fonts, p.notch_fill, p.bowl_fill)
    fill_valleys(fonts, p.valley_fill)
    if p.tails:
        redraw_tails(fonts, p)
    slant_t(fonts, p.t_slant)
    adjust_widths(fonts, p.widths, p.condense)
    lift_ascenders(fonts, p.ascender_lift)
    lower_xheight(fonts, p.xheight_scale)
    small_caps(fonts)
    respace(fonts, p.spacing)
    set_space(fonts, p.space_width)
    scale_outlines(fonts, p.scale)
    corners = soften_vertices(fonts, p.corner_radius)
    erase_open_corners(fonts)

    out = ROOT / "build" / p.key
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(FEATURES, out / "features")
    paths = {}
    for style, f in fonts.items():
        set_names(f, p.family, style, MASTERS[style])
        assign_categories(f)
        if corners:
            # which corners were rounded, so the site can give Sans and Mono the
            # same corners at zero radius and morph between them point for point
            f.lib["com.kerf.roundedCorners"] = corners
        path = out / f"{p.file_stem}-{style}.ufo"
        f.save(path, overwrite=True)
        paths[style] = path
    return write_designspace(p, out, paths)


if __name__ == "__main__":
    print(build(PROFILES[sys.argv[1] if len(sys.argv) > 1 else "sans"]))

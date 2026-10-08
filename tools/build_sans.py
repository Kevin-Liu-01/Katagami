"""Build a proportional Kerf member from Inter's Thin, Regular and Black masters.

    python tools/build_sans.py [sans|round]

Inter -> profile, in order (each step only where the profile asks for it):
  1. Inter alternates promoted to the default (square punctuation, profile picks)
  2. quarter arcs squared or rounded (planned on Regular)
  3. bowl-to-stem notches filled, g tail redrawn
  4. per-glyph widths changed with stems held, composites re-seated
  5. sidebearings adjusted
"""

from __future__ import annotations

import math
import shutil
import sys
import unicodedata
from pathlib import Path

from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, InstanceDescriptor, SourceDescriptor

sys.path.insert(0, str(Path(__file__).parent))
from kerf_build.fontops import (  # noqa: E402
    MASTERS, ROOT, assign_categories, load_inter_masters, promote_alternates, reflow_composites, resize_glyph, respace,
    set_names, snapshot, stem, swap_glyph_outlines,
)
from kerf_build.outline import apply_squaring, plan_squaring  # noqa: E402
from kerf_build.profiles import PROFILES, Profile  # noqa: E402

FEATURES = ROOT / "vendor" / "inter" / "src" / "features"
G_TAIL_STROKE = 0.94  # width of the g tail's rising stroke, in stems
G_TAIL_HANDLE = 0.72  # handle fraction of the g tail's turn, matching the squared lowercase
KEEP_ROUND = ("circle", "circled", "ring", "degree", "bullet", "dotted")
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
    for g in ref:
        if not g.contours or keeps_round(ref, g.name):
            continue
        plan = plan_squaring(g, TIGHT_RADIUS * stem(ref))
        if not plan:
            continue
        s = p.square_upper if is_upper(ref, g.name) else p.square_lower
        for f in fonts.values():
            apply_squaring(f[g.name], plan, s, min(0.9, s * p.counter_boost), p.join_ease)


def redraw_g_tail(fonts) -> None:
    """Redraw the tail of g so it ends in a level cut.

    The bottom stroke runs left, turns up through one squared quarter curve,
    and rises vertically into a horizontal cut. The cut sits at the height
    and left edge Inter gives the terminal at that weight, and the rising
    stroke is as wide as the stem, so the end is a clean rectangle. The point
    count is unchanged, so the masters stay compatible.
    """
    ref = fonts["Regular"]["g"]
    for ci, contour in enumerate(ref.contours):
        pts = contour.points
        found = [i for i, p in enumerate(pts)
                 if p.type == "line" and pts[i - 1].type and not p.smooth and not pts[i - 1].smooth and p.y < 0 and pts[i - 1].y < 0]
        if found:
            b_i = found[0]
            a_i = b_i - 1  # inner end of the hook; b_i is the outer end
            break
    else:
        raise ValueError("g terminal not found")
    for f in fonts.values():
        pts = f["g"].contours[ci].points
        n = len(pts)
        P = lambda k: pts[k % n]  # noqa: E731
        inner_end, outer_end, inner_bot, outer_bot = P(a_i), P(b_i), P(a_i - 3), P(b_i + 3)
        y = (inner_end.y + outer_end.y) / 2
        x_out = outer_end.x
        x_in = x_out + stem(f) * G_TAIL_STROKE
        k = G_TAIL_HANDLE
        # outer edge: down from the cut, around to the bottom of the bowl
        outer_end.x, outer_end.y = x_out, y
        P(b_i + 1).x, P(b_i + 1).y = x_out, y - k * (y - outer_bot.y)
        P(b_i + 2).x, P(b_i + 2).y = outer_bot.x - k * (outer_bot.x - x_out), outer_bot.y
        # inner edge: from the bottom of the counter, around and up to the cut
        P(a_i - 2).x, P(a_i - 2).y = inner_bot.x - k * (inner_bot.x - x_in), inner_bot.y
        P(a_i - 1).x, P(a_i - 1).y = x_in, inner_bot.y + k * (y - inner_bot.y)
        inner_end.x, inner_end.y = x_in, y


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
    for f in fonts.values():
        for name, notches in plans.items():
            g = f[name]
            for ci, corner, moving, ref, far in notches:
                pts = g.contours[ci].points
                dy = (ref - pts[corner].y) * amount
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


def adjust_widths(fonts, widths: dict[str, float]) -> None:
    for f in fonts.values():
        old = snapshot(f)
        sw = stem(f)
        maps = {name: resize_glyph(f, name, k, sw) for name, k in widths.items()}
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
    f_crossbar_overhang(fonts, p.f_overhang)
    if p.notch_fill:
        fill_notches(fonts, p.notch_fill)
    if p.g_tail:
        redraw_g_tail(fonts)
    adjust_widths(fonts, p.widths)
    lift_ascenders(fonts, p.ascender_lift)
    respace(fonts, p.spacing)
    set_space(fonts, p.space_width)

    out = ROOT / "build" / p.key
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(FEATURES, out / "features")
    paths = {}
    for style, f in fonts.items():
        set_names(f, p.family, style, MASTERS[style])
        assign_categories(f)
        path = out / f"{p.file_stem}-{style}.ufo"
        f.save(path, overwrite=True)
        paths[style] = path
    return write_designspace(p, out, paths)


if __name__ == "__main__":
    print(build(PROFILES[sys.argv[1] if len(sys.argv) > 1 else "sans"]))

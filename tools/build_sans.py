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
        plan = plan_squaring(g)
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
    shape_curves(fonts, p)
    if p.notch_fill:
        fill_notches(fonts, p.notch_fill)
    if p.g_tail:
        redraw_g_tail(fonts)
    adjust_widths(fonts, p.widths)
    respace(fonts, p.spacing)

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

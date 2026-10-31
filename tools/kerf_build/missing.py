"""The characters Inter has no glyph for that Google Fonts' case and language
checks ask for, built from Inter's own parts on its masters before any
transform, so every member draws them in its own style; the anchors the
shaper needs to set accents on the letters Inter leaves without them; and the
soft-dotted rule that drops the dot of i under every accent above it.

Each master is built by the same rule from its own parts, which have the same
points in every master, so the masters stay compatible. A glyph whose parts a master set lacks (Inter's Italic has no
_part.lambdabar) is left out of that set."""

from __future__ import annotations

import copy
import re
import unicodedata
from pathlib import Path

import ufoLib2
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from ufoLib2.objects import Anchor, Component

from kerf_build.fontops import stem
from kerf_build.outline import embolden_x, embolden_y

# the marks above that a copy moved under the baseline makes; its top sits as deep as Inter's dot below
BELOW_MARKS = (
    (0x0331, "macroncomb"),
    (0x0330, "tildecomb"),
    (0x032D, "circumflexcomb"),
    (0x032E, "brevecomb"),
    (0x0324, "dieresiscomb"),
    (0x0325, "ringcomb"),
)
# the accents above that the soft-dotted rule must also see
ABOVE_MARKS = ("uni0311", "uni030D", "hungarumlautcomb", "threedotsabovecomb", "fourdotsabovecomb")
# the joiners and direction marks Arabic and Persian text uses: invisible, with no advance
CONTROLS = (0x200C, 0x200D, 0x200E, 0x200F)
# ⁱ ʲ ᵢ ⱼ ᶤ: soft dotted, so an accent above drops their dot; superiors before the glyphs built from them
SOFT_DOTTED_MODIFIERS = ("i.sups", "j.sups", "i.subs", "j.subs", "uni1DA4")


def _new(font, unicode: int, width: float):
    """A new glyph named uniXXXX; Inter has none by that name."""
    name = f"uni{unicode:04X}"
    if name in font:
        raise ValueError(f"{name} is already in {font.info.styleName}")
    g = font.newGlyph(name)
    g.unicodes = [unicode]
    g.width = round(width)
    order = font.lib.get("public.glyphOrder")
    if order is not None and name not in order:
        order.append(name)
    return g


def _bounds(font, name: str):
    return font[name].getBounds(font)


def _anchor(font, name: str, anchor: str):
    return next(((a.x, a.y) for a in font[name].anchors if a.name == anchor), None)


def _draw(font, src: str, dst, transform=(1, 0, 0, 1, 0, 0)) -> None:
    """src's outline, its components drawn in, appended to dst."""
    pen = DecomposingRecordingPen(font)
    font[src].draw(pen)
    pen.replay(TransformPen(dst.getPen(), transform))


def _runs(font, name: str, y: float, step: int = 2) -> list[tuple[float, float]]:
    """The spans of ink a horizontal line at y crosses, left to right."""
    b = _bounds(font, name)
    runs, start = [], None
    x = b.xMin - step
    while x <= b.xMax + step:
        pen = PointInsidePen(font, (x, y))
        font[name].draw(pen)
        if pen.getResult() and start is None:
            start = x
        elif not pen.getResult() and start is not None:
            runs.append((start, x - step))
            start = None
        x += step
    return runs


def _rect(g, x0: float, y0: float, x1: float, y1: float) -> None:
    """A rectangle contour, counter-clockwise like Inter's outer contours."""
    pen = g.getPen()
    pen.moveTo((round(x0), round(y0)))
    pen.lineTo((round(x1), round(y0)))
    pen.lineTo((round(x1), round(y1)))
    pen.lineTo((round(x0), round(y1)))
    pen.closePath()


def _feet(font, name: str, y: float) -> list[float]:
    """The x of a glyph's on-curve points at height y, left to right, its
    components drawn in."""
    scratch = ufoLib2.objects.Glyph()
    _draw(font, name, scratch)
    return sorted(p.x for c in scratch.contours for p in c.points if round(p.y) == round(y) and p.type)


def _thickness(font, name: str) -> float:
    b = _bounds(font, name)
    return b.yMax - b.yMin


def _resized(font, unicode: int, src: str, k: float, dx: float, dy: float, ink_left: float, ink_bottom: float, right: float):
    """src scaled by k and emboldened by dx and dy, its ink placed at
    (ink_left, ink_bottom) with `right` units after it."""
    g = _new(font, unicode, 0)
    _draw(font, src, g, (k, 0, 0, k, 0, 0))
    embolden_x(g, dx)
    embolden_y(g, dy)
    b = g.getBounds(font)
    for c in g.contours:
        for p in c.points:
            p.x, p.y = round(p.x + ink_left - b.xMin), round(p.y + ink_bottom - b.yMin)
    g.width = round(ink_left + b.xMax - b.xMin + right)
    return g


def _stretch(dst, pivot: float, top_from: float, top_to: float) -> None:
    """Points above `pivot` move up so `top_from` lands on `top_to`, in
    proportion to their height above the pivot; points below it stay."""
    k = (top_to - pivot) / (top_from - pivot)
    for c in dst.contours:
        for p in c.points:
            if p.y > pivot:
                p.y = round(pivot + (p.y - pivot) * k)


def _marks(font, below_top: float) -> None:
    xh = font.info.xHeight
    for u, src in BELOW_MARKS:
        b = _bounds(font, src)
        x = _anchor(font, src, "_top")[0]
        dy = below_top - b.yMax
        g = _new(font, u, 0)
        g.components.append(Component(src, (1, 0, 0, 1, 0, round(dy))))
        g.appendAnchor({"name": "_bottom", "x": x, "y": 0})
        g.appendAnchor({"name": "bottom", "x": x, "y": round(b.yMin + dy)})
    # the inverted breves: the breve turned over in place, and below the baseline
    b = _bounds(font, "brevecomb")
    x = _anchor(font, "brevecomb", "_top")[0]
    g = _new(font, 0x0311, 0)
    g.components.append(Component("brevecomb", (1, 0, 0, -1, 0, round(b.yMin + b.yMax))))
    g.appendAnchor({"name": "_top", "x": x, "y": xh})
    g.appendAnchor({"name": "top", "x": x, "y": round(b.yMax)})
    dy = below_top - b.yMax
    g = _new(font, 0x032F, 0)
    g.components.append(Component("brevecomb", (1, 0, 0, -1, 0, round(b.yMin + b.yMax + dy))))
    g.appendAnchor({"name": "_bottom", "x": x, "y": 0})
    g.appendAnchor({"name": "bottom", "x": x, "y": round(b.yMin + dy)})
    # the vertical lines: Inter's spacing linevert as a mark, above as far from
    # the letter as the acute, and below
    b = _bounds(font, "linevert")
    x = round((b.xMin + b.xMax) / 2)
    up = _bounds(font, "acutecomb").yMin - b.yMin
    g = _new(font, 0x030D, 0)
    g.components.append(Component("linevert", (1, 0, 0, 1, 0, round(up))))
    g.appendAnchor({"name": "_top", "x": x, "y": xh})
    g.appendAnchor({"name": "top", "x": x, "y": round(b.yMax + up)})
    dy = below_top - b.yMax
    g = _new(font, 0x0329, 0)
    g.components.append(Component("linevert", (1, 0, 0, 1, 0, round(dy))))
    g.appendAnchor({"name": "_bottom", "x": x, "y": 0})
    g.appendAnchor({"name": "bottom", "x": x, "y": round(b.yMin + dy)})
    # the low line runs under the letter before it, as wide as the underscore
    g = _new(font, 0x0332, 0)
    g.components.append(Component("underscore", (1, 0, 0, 1, -font["underscore"].width, 0)))


def _saltillos(font) -> None:
    """Ꞌ and ꞌ: Inter's straight quote drawn longer and with straight sides,
    as wide as the quote at its middle, down to a quarter of the cap height
    for the capital and to 0.46 of it for the small letter."""
    cap = font.info.capHeight
    for u, foot in ((0xA78B, 0.25), (0xA78C, 0.46)):
        g = _new(font, u, font["quotesingle"].width)
        _draw(font, "quotesingle", g)
        pts = g.contours[0].points
        cx = sum(p.x for p in pts) / len(pts)
        half = sum(abs(p.x - cx) for p in pts) / len(pts)
        low = min(p.y for p in pts)
        for p in pts:
            p.x = round(cx - half if p.x < cx else cx + half)
            if p.y == low:
                p.y = round(cap * foot)


def _letters(font) -> None:
    xh, cap = font.info.xHeight, font.info.capHeight

    # Ǆ: D and Ž, as Inter sets ǅ from D and ž
    g = _new(font, 0x01C4, font["D"].width + font["Zcaron"].width)
    g.components.append(Component("D"))
    g.components.append(Component("Zcaron", (1, 0, 0, 1, font["D"].width, 0)))

    # ⱥ and ⱦ: the stroke of ø through a and through the stem of t
    cx, cy = _anchor(font, "_part.oslash", "_center")
    b = _bounds(font, "a")
    g = _new(font, 0x2C65, font["a"].width)
    g.components.append(Component("a"))
    g.components.append(Component("_part.oslash", (1, 0, 0, 1, round((b.xMin + b.xMax) / 2 - cx), round(xh / 2 - cy))))
    g = _new(font, 0x2C66, font["t"].width)
    g.components.append(Component("t"))
    g.components.append(Component("_part.oslash", (1, 0, 0, 1, round(_anchor(font, "t", "top")[0] - cx), round(xh / 2 - cy))))

    # Ɤ: ɤ with its arms drawn up to the cap height; the loop keeps its size
    b = _bounds(font, "babygamma")
    g = _new(font, 0xA7CB, font["babygamma"].width)
    _draw(font, "babygamma", g)
    _stretch(g, 0.4 * xh, b.yMax, b.yMax + cap - xh)

    # Ɥ: the turned h at the cap height, u with its stems drawn up
    b = _bounds(font, "u")
    g = _new(font, 0xA78D, font["u"].width)
    _draw(font, "u", g)
    _stretch(g, 0.75 * xh, b.yMax, b.yMax + cap - xh)

    # Ɦ: H whose left stem ends in ɦ's hook. The stem stops inside the hook's
    # straight part, and the hook is widened to the capital stem.
    h = _bounds(font, "H")
    hook = _bounds(font, "_part.top_r_hook")
    g = _new(font, 0xA7AA, font["H"].width)
    _draw(font, "H", g)
    left = sorted((p for p in g.contours[0].points if p.y == h.yMax), key=lambda p: p.x)[:2]
    stem_l, stem_r = left[0].x, left[1].x
    foot = sorted(p.x for c in font["_part.top_r_hook"].contours for p in c.points if p.y == hook.yMin)
    sx = (stem_r - stem_l) / (foot[-1] - foot[0])
    for p in left:
        p.y = round(hook.yMin + 100)
    g.components.append(Component("_part.top_r_hook", (sx, 0, 0, 1, round(stem_l - foot[0] * sx), 0)))

    # Ɪ: the capital I with serifs that cv08 sets
    g = _new(font, 0xA7AE, font["I.1"].width)
    g.components.append(Component("I.1"))

    # Ɬ: ɬ's belt where ɬ has it, and L moved under it so its stem takes the
    # place of ɬ's; the glyph keeps ɬ's left margin
    belt = max(font["lbelt"].contours, key=lambda c: len(c.points))
    stem = min(font["lbelt"].contours, key=lambda c: len(c.points))
    dx = round((min(p.x for p in stem.points) + max(p.x for p in stem.points)) / 2 - _anchor(font, "L", "top")[0])
    g = _new(font, 0xA7AD, font["L"].width + dx)
    g.components.append(Component("L", (1, 0, 0, 1, dx, 0)))
    belt.draw(g.getPen())

    # Ʝ: ʝ's crossed tail under the stem of l, which reaches the cap height
    src = font["jcrosstail.ccmp"]
    g = _new(font, 0xA7B2, src.width)
    for c in src.contours:
        c.draw(g.getPen())
    dx = next(c.transformation[4] for c in src.components if c.baseGlyph == "idotless")
    g.components.append(Component("l", (1, 0, 0, 1, dx, 0)))

    # Ƛ: Λ with ƛ's bar across its right leg, which runs the way ƛ's long
    # stroke does, 0.62 of the cap height up
    if "_part.lambdabar" in font:
        bx, by = _anchor(font, "_part.lambdabar", "_bar")
        y = 0.62 * cap
        leg = _runs(font, "Lambda", y)[-1]
        g = _new(font, 0xA7DC, font["Lambda"].width)
        g.components.append(Component("Lambda"))
        g.components.append(Component("_part.lambdabar", (1, 0, 0, 1, round((leg[0] + leg[1]) / 2 - bx), round(y - by))))

    # ͷ and ϻ: Inter sets Ͷ as И and Ϻ as M, so the small letters are и and м
    for u, src in ((0x0377, "iicyrillic"), (0x03FB, "emcyrillic")):
        g = _new(font, u, font[src].width)
        g.components.append(Component(src))

    # Ԯ: Л with the descender of ԯ at Л's own descender anchor
    ax = _anchor(font, "afii10029", "cyrtic")[0] - _anchor(font, "_part.cyrtic", "_cyrtic")[0]
    g = _new(font, 0x052E, font["afii10029"].width)
    g.components.append(Component("afii10029"))
    g.components.append(Component("_part.cyrtic", (1, 0, 0, 1, round(ax), 0)))


def _more_letters(fonts) -> None:
    """The letters the language check asks for next, mostly Church Slavonic,
    Africanist and phonetic, built the same way: from Inter's own parts, bars
    and ticks drawn at Inter's own thicknesses, and letters redrawn at another
    size the way the small capitals are."""
    ref = fonts["Regular"]
    cx = lambda f, n: (_bounds(f, n).xMin + _bounds(f, n).xMax) / 2  # noqa: E731
    # the top of the middle stem of Ѡ and ѡ, which broad omega lowers
    tops = {}
    for n, h in (("Omegacyrillic", ref.info.capHeight), ("omegacyrillic", ref.info.xHeight)):
        mid = cx(ref, n)
        tops[n] = [i for i, p in enumerate(ref[n].contours[0].points) if abs(p.x - mid) < 2 * stem(ref) and p.y >= 0.8 * h]
    for f in fonts.values():
        xh, cap = f.info.xHeight, f.info.capHeight
        lc, uc = stem(f), _bounds(f, "I").xMax - _bounds(f, "I").xMin
        bar = _thickness(f, "crossbar_short.uc")
        o_k = (_bounds(f, "O").yMax - _bounds(f, "O").yMin) / (_bounds(f, "o").yMax - _bounds(f, "o").yMin)

        # ɽ and Ɽ: r and R with Inter's retroflex tail at the foot of the stem
        for u, base, part in ((0x027D, "r", "_part.bottom_rthook_r"), (0x2C64, "R", "_part.bottom_rthook_uc")):
            g = _new(f, u, f[base].width)
            g.components.append(Component(base))
            g.components.append(Component(part, (1, 0, 0, 1, round(_feet(f, base, 0)[1] - _anchor(f, part, "_bottomr")[0]), 0)))

        # ᵽ: p with a bar through the stem and the bowl at half the x-height
        g = _new(f, 0x1D7D, f["p"].width)
        g.components.append(Component("p"))
        left = _feet(f, "p", _bounds(f, "p").yMin)[0]
        _rect(g, left - 0.9 * lc, (xh - bar) / 2, _bounds(f, "p").xMax, (xh + bar) / 2)
        # Ᵽ: P with a short bar across the stem only, 0.7 of the cap height up
        foot = _feet(f, "P", 0)[:2]
        mid = (foot[0] + foot[1]) / 2
        shift = max(0, foot[0] / 2 - (mid - 1.5 * uc))
        g = _new(f, 0x2C63, f["P"].width + shift)
        g.components.append(Component("P", (1, 0, 0, 1, round(shift), 0)))
        _rect(g, shift + mid - 1.5 * uc, 0.7 * cap - bar / 2, shift + mid + 1.5 * uc, 0.7 * cap + bar / 2)

        # Ɑ and Ꞷ: ɑ and ω at the capital's height, emboldened back to the capital stem
        for u, src in ((0x2C6D, "ascript"), (0xA7B6, "omega")):
            b = _bounds(f, src)
            d = uc - lc * o_k
            _resized(f, u, src, o_k, d, d, b.xMin * o_k, _bounds(f, "O").yMin, f[src].width * o_k - b.xMax * o_k)
        g = _new(f, 0xA7B7, f["omega"].width)
        g.components.append(Component("omega"))
        # ꞵ is β, and Ꞵ is β with its stem cut at the baseline: β's bowls close on
        # the baseline and its top is at the capital height already
        g = _new(f, 0xA7B5, f["beta"].width)
        g.components.append(Component("beta"))
        g = _new(f, 0xA7B4, f["beta"].width)
        _draw(f, "beta", g)
        for c in g.contours:
            for p in c.points:
                if p.y < -0.5 * lc:
                    p.y = 0
        # Ɐ is A turned, as ɐ is a turned
        g = _new(f, 0x2C6F, f["A"].width)
        g.components.append(Component("A", (-1, 0, 0, -1, f["A"].width, cap)))
        # ⓐ to ⓩ: in the circle Ⓐ to Ⓩ are set in, each letter at 0.92 of its height,
        # centred across it and all on one baseline that puts the x-height in the middle
        circle = _bounds(f, "largeCircle")
        for letter in "abcdefghijklmnopqrstuvwxyz":
            if f"{letter.upper()}.circled" not in f:
                continue
            b = _bounds(f, letter)
            g = _new(f, 0x24D0 + ord(letter) - ord("a"), f["largeCircle"].width)
            g.components.append(Component("largeCircle"))
            z = 0.92  # ascenders and descenders clear the ring at Black; the stems keep their weight
            g.components.append(Component(letter, (1, 0, 0, z, round((circle.xMin + circle.xMax - b.xMin - b.xMax) / 2), round((circle.yMin + circle.yMax - z * xh) / 2))))
        for u in CONTROLS:
            _new(f, u, 0)

        # Ⱳ and ⱳ: W and w whose last stroke turns right at the top into a flag
        for u, base, top, s in ((0x2C72, "W", cap, uc), (0x2C73, "w", xh, lc)):
            right = _feet(f, base, top)[-1]
            g = _new(f, u, f[base].width + 1.2 * s)
            g.components.append(Component(base))
            _rect(g, right - s / 2, top - bar, right + 1.2 * s, top)

        # ꞉ is the colon, and ꞊ is the equals sign at 0.55 of its width
        g = _new(f, 0xA789, f["colon"].width)
        g.components.append(Component("colon"))
        b = _bounds(f, "equal")
        cut = 0.45 * (b.xMax - b.xMin)
        g = _new(f, 0xA78A, f["equal"].width - cut)
        _draw(f, "equal", g)
        for c in g.contours:
            for p in c.points:
                p.x = round(b.xMin + (p.x - b.xMin) * 0.55)

        # ᵋ and ᵓ: ɛ and ɔ at the superscripts' size and weight, on ᵉ's line
        sups = _bounds(f, "e.sups")
        k = (sups.yMax - sups.yMin) / (_bounds(f, "e").yMax - _bounds(f, "e").yMin)
        sup_stem = _bounds(f, "l.sups").xMax - _bounds(f, "l.sups").xMin
        d = sup_stem - lc * k
        for u, src in ((0x1D4B, "epsilon"), (0x1D53, "oopen")):
            _resized(f, u, src, k, d, 0.6 * d, sups.xMin, sups.yMin, f["e.sups"].width - sups.xMax)
        # ᶤ and ᶶ: ⁱ and ᵘ with a bar as thick as the superscript minus, at ⁱ's cross anchor
        t = _thickness(f, "minus.sups")
        x, y = _anchor(f, "i.sups", "cross")
        half = 1.1 * sup_stem
        shift = max(0, half + 0.25 * sup_stem - x)  # the bar stays inside the glyph's own advance
        g = _new(f, 0x1DA4, f["i.sups"].width + 2 * shift)
        g.components.append(Component("i.sups", (1, 0, 0, 1, round(shift), 0)))
        _rect(g, shift + x - half, y - t / 2, shift + x + half, y + t / 2)
        b = _bounds(f, "u.sups")
        g = _new(f, 0x1DB6, f["u.sups"].width)
        g.components.append(Component("u.sups"))
        _rect(g, b.xMin - 0.4 * sup_stem, y - t / 2, b.xMax + 0.4 * sup_stem, y + t / 2)

        # Ꟈ and ꟈ: D and d with a short bar across the stem, at the middle of D
        # and at the height of đ's bar
        mid = _bounds(f, "D").xMin + uc / 2
        g = _new(f, 0xA7C7, f["D"].width)
        g.components.append(Component("D"))
        _rect(g, mid - 1.1 * uc, (cap - bar) / 2, mid + 1.1 * uc, (cap + bar) / 2)
        top = _feet(f, "d", _bounds(f, "d").yMax)[-2:]
        y = _anchor(f, "crossbar", "_cross")[1] + f["dcroat"].components[1].transformation[5]  # where đ's bar is
        g = _new(f, 0xA7C8, f["d"].width)
        g.components.append(Component("d"))
        _rect(g, (top[0] + top[1]) / 2 - 1.1 * lc, y - bar / 2, (top[0] + top[1]) / 2 + 1.1 * lc, y + bar / 2)

        # Ѻ and ѻ: O and o with a stem-wide tick through the top and the bottom of the bowl
        for u, base, s in ((0x047A, "O", uc), (0x047B, "o", lc)):
            b = _bounds(f, base)
            x = _anchor(f, base, "top")[0]
            g = _new(f, u, f[base].width)
            g.components.append(Component(base))
            _rect(g, x - s / 2, b.yMax - 0.95 * s, x + s / 2, b.yMax + 0.63 * s)
            _rect(g, x - s / 2, b.yMin - 0.63 * s, x + s / 2, b.yMin + 0.95 * s)

        # Ѽ and ѽ: Ѡ and ѡ under the combining titlo; Ѿ and ѿ under a small т
        # drawn as three legs hanging from a bar, half the letter wide
        titlo = _bounds(f, "titlocyrilliccmb")
        for u, base, s, h in ((0x047C, "Omegacyrillic", uc, cap), (0x047D, "omegacyrillic", lc, xh)):
            g = _new(f, u, f[base].width)
            g.components.append(Component(base))
            g.components.append(Component("titlocyrilliccmb", (1, 0, 0, 1, round(cx(f, base) - (titlo.xMin + titlo.xMax) / 2), round(h - xh))))
        for u, base, s, h in ((0x047E, "Omegacyrillic", uc, cap), (0x047F, "omegacyrillic", lc, xh)):
            b = _bounds(f, base)
            mid, half = cx(f, base), (b.xMax - b.xMin) / 4
            # the legs are as long as the bar is thick plus 0.08 of the cap height, so they show at Black
            low = h + 0.07 * cap
            joint = low + 0.08 * cap + 0.4 * s
            high = joint + 0.5 * s
            g = _new(f, u, f[base].width)
            g.components.append(Component(base))
            _rect(g, mid - half, joint, mid + half, high)
            # the legs thin where a stem would close the gaps between them to under 0.45 stem
            leg = min(0.65 * s, (2 * half - 0.9 * s) / 3)
            for x in (mid - half, mid - leg / 2, mid + half - leg):
                _rect(g, x, low, x + leg, joint + 0.2 * s)

        # Ꙍ and ꙍ: Ѡ and ѡ with the middle stem starting 0.43 of the way down
        for u, base, h in ((0xA64C, "Omegacyrillic", cap), (0xA64D, "omegacyrillic", xh)):
            g = _new(f, u, f[base].width)
            _draw(f, base, g)
            for i in tops[base]:
                g.contours[0].points[i].y = round(0.57 * h)

        # Ꙁ ꙁ are Ȥ ȥ, and Ꙃ ꙃ add Ƶ's and ƶ's bar to them
        for u, base in ((0xA640, "Zhook"), (0xA641, "zhook")):
            g = _new(f, u, f[base].width)
            g.components.append(Component(base))
        for u, base, barred in ((0xA642, "Zhook", "Zbar"), (0xA643, "zhook", "zbar")):
            g = _new(f, u, f[base].width)
            g.components.append(Component(base))
            g.components.append(Component(f[barred].components[1].baseGlyph, f[barred].components[1].transformation))

        # Ꙋ is Ȣ, and ꙋ is ȣ moved down so its loop descends below the baseline
        g = _new(f, 0xA64A, f["uni0222"].width)
        g.components.append(Component("uni0222"))
        g = _new(f, 0xA64B, f["uni0223"].width)
        g.components.append(Component("uni0223", (1, 0, 0, 1, 0, round(_bounds(f, "o").yMax - _bounds(f, "uni0223").yMax))))

        # Ꙗ and ꙗ: І and A, ı and a, a stem apart, joined by Ѥ's and ѥ's bar
        for u, iota, letter, e, s in ((0xA656, "I", "A", "Eiotifiedcyrillic", uc), (0xA657, "idotless", "a", "eiotifiedcyrillic", lc)):
            joint = min((c for c in f[e].contours if len(c.points) == 4), key=lambda c: max(p.y for p in c.points) - min(p.y for p in c.points))
            y0, y1 = min(p.y for p in joint.points), max(p.y for p in joint.points)
            if letter == "a":
                # the bar runs into the top of a's bowl, from just inside its counter
                counter = min(f["a"].contours, key=lambda c: len(c.points))
                top = max(p.y for p in counter.points)
                y0, y1 = top - 0.1 * (y1 - y0), top + 0.9 * (y1 - y0)
            right = _bounds(f, iota).xMax
            dx = right + s - _bounds(f, letter).xMin
            g = _new(f, u, f[letter].width + dx)
            g.components.append(Component(iota))
            g.components.append(Component(letter, (1, 0, 0, 1, round(dx), 0)))
            leg = _runs(f, letter, (y0 + y1) / 2)[0]
            _rect(g, right - s / 2, y0, dx + (leg[0] + leg[1]) / 2, y1)


def turned_small_f(fonts) -> None:
    """ⅎ: the small capital F turned over, as Ⅎ is F turned. Runs after the
    small capitals are drawn."""
    for f in fonts.values():
        if "f.smcp" not in f:
            continue
        b = _bounds(f, "f.smcp")
        g = _new(f, 0x214E, f["f.smcp"].width)
        g.components.append(Component("f.smcp", (-1, 0, 0, -1, f["f.smcp"].width, round(b.yMin + b.yMax))))


def _plan_anchors(font) -> dict[str, list[tuple[str, str]]]:
    """Which anchors each glyph takes and where: (name, rule). A letter
    without a top or bottom anchor takes one at its ink's centre, on the cap
    height or x-height above and on the baseline or its descender below. A
    letter on the baseline without a cedilla anchor takes one at its bottom
    anchor, and one without an ogonek anchor takes one a fifth of its ink's
    width in from the right. The dotless forms Inter's ccmp sets under an
    accent (uni0268.ccmp for ɨ) count as their letters. A combining mark
    without an attaching anchor takes one at its ink's centre."""
    xh, cap = font.info.xHeight, font.info.capHeight
    plan = {}
    for g in font:
        unicodes = g.unicodes
        if g.name.endswith(".ccmp"):  # Inter gives some of them a private-use code point
            base = g.name.removesuffix(".ccmp")
            named = re.fullmatch(r"uni([0-9A-F]{4,6})", base)
            unicodes = [int(named.group(1), 16)] if named else font[base].unicodes if base in font else []
        b = g.getBounds(font) if unicodes else None
        if b is None:
            continue
        cat = unicodedata.category(chr(unicodes[0]))
        names = {a.name for a in g.anchors}
        if any(n.startswith("_") for n in names):
            continue
        add = []
        if cat.startswith("L"):
            if "top" not in names:
                add.append(("top", "cap" if b.yMax > (xh + cap) / 2 else "xh"))
            if "bottom" not in names:
                add.append(("bottom", "base" if b.yMin > -100 else "ink"))
            on_base = "bottom" not in names and b.yMin > -100 or any(a.name == "bottom" and a.y == 0 for a in g.anchors)
            if "cedilla" not in names and on_base:
                add.append(("cedilla", "bottom"))
            if "ogonek" not in names and on_base:
                add.append(("ogonek", "right"))
        elif cat == "Mn" and g.width == 0:
            if b.yMin >= 0.8 * xh:
                add += [("_top", "xh"), ("top", "ink")]
            elif b.yMax <= 0:
                add += [("_bottom", "base"), ("bottom", "ink")]
        if add:
            plan[g.name] = add
    return plan


def complete_anchors(fonts) -> None:
    """The anchors planned on Regular, placed in each master from its own ink,
    so every master has the same anchors."""
    plan = _plan_anchors(fonts["Regular"])
    for f in fonts.values():
        xh, cap = f.info.xHeight, f.info.capHeight
        for name, add in plan.items():
            g = f[name]
            b = g.getBounds(f)
            cx = round((b.xMin + b.xMax) / 2)
            for anchor, rule in add:
                if rule == "bottom":
                    x, y = next((a.x, 0) for a in g.anchors if a.name == "bottom")
                elif rule == "right":
                    x, y = round(b.xMax - (b.xMax - b.xMin) / 5), 0
                else:
                    x = cx
                    y = {"cap": cap, "xh": xh, "base": 0}.get(rule, round(b.yMax if anchor in ("top", "_top") else b.yMin))
                g.appendAnchor({"name": anchor, "x": x, "y": y})


def dot_marks(fonts) -> None:
    """⃛ and ⃜: the dieresis's dots at the dieresis's spacing, centred where its
    two are. Runs after the alternates are promoted, so they take the dots the
    dieresis has then."""
    for f in fonts.values():
        pair = f["dieresiscomb"].components
        if len(pair) != 2 or f["dieresiscomb"].contours:
            continue
        step = pair[1].transformation[4] - pair[0].transformation[4]
        middle = (pair[0].transformation[4] + pair[1].transformation[4]) / 2
        for name, n in (("threedotsabovecomb", 3), ("fourdotsabovecomb", 4)):
            if name in f:
                g = f[name]
                g.clearComponents()
                g.clearContours()
                g.clearAnchors()
                # Inter's Black dieresis sets its dots smaller than the dot accent's, by its components' scale
                xx, xy, yx, yy = pair[0].transformation[:4]
                for i in range(n):
                    g.components.append(Component(pair[0].baseGlyph, (xx, xy, yx, yy, round(middle + (i - (n - 1) / 2) * step), round(pair[0].transformation[5]))))


def soft_dotted_modifiers(fonts) -> None:
    """name.ccmp for each of SOFT_DOTTED_MODIFIERS, the form ccmp sets under an
    accent above. A superior loses the contour that sits highest, its dot; a
    glyph built from a superior takes the superior's dotless form. The top
    anchor comes down to the ink's top, where idotless has it. Inter's own
    uni2071.ccmp is the dotless i.numr, which sits lower than ⁱ."""
    default = fonts["Regular"]
    for f in fonts.values():
        categories = f.lib.setdefault("public.openTypeCategories", {})
        order = f.lib.get("public.glyphOrder")
        for name in SOFT_DOTTED_MODIFIERS:
            if name not in f:
                continue
            src, new = f[name], f"{name}.ccmp"
            if new in f:
                del f[new]
            g = f.newGlyph(new)
            g.width = src.width
            dot = None
            if src.contours and not src.components:
                ref = default[name].contours
                dot = max(range(len(ref)), key=lambda i: ref[i].getBounds().yMin)
            for i, c in enumerate(src.contours):
                if i != dot:
                    g.contours.append(copy.deepcopy(c))
            for c in src.components:
                base = f"{c.baseGlyph}.ccmp" if c.baseGlyph in SOFT_DOTTED_MODIFIERS else c.baseGlyph
                g.components.append(Component(base, c.transformation))
            top = g.getBounds(f).yMax
            for a in src.anchors:
                g.anchors.append(Anchor(x=a.x, y=top if a.name == "top" else a.y, name=a.name))
            categories[new] = categories.get(name, "base")
            if order is not None and new not in order:
                order.append(new)


def unseat_marks(font) -> None:
    """A base anchor where a mark already sits unmoved (ɛ's top in Round
    Italic, under U+1DC7) moves 1 unit right: a shaper's zero offset reads as
    a mark that never attached. Runs on the default master after its last change."""
    pairs = (("top", "_top"), ("bottom", "_bottom"), ("cedilla", "_cedilla"), ("ogonek", "_ogonek"))
    rest = {}
    for g in font:
        if g.width == 0:
            for a in g.anchors:
                rest.setdefault(a.name, set()).add((round(a.x), round(a.y)))
    for g in font:
        if g.width == 0:
            continue
        for a in g.anchors:
            for base, mark in pairs:
                if a.name == base and (round(a.x) - round(g.width), round(a.y)) in rest.get(mark, ()):
                    a.x = round(a.x) + 1


def add_missing(fonts) -> None:
    """The missing marks, saltillos and letters on every master. Runs before
    the promoted alternates are swapped in, so it uses Inter's own parts."""
    for f in fonts.values():
        _marks(f, _bounds(f, "dotbelow").yMax)
        _saltillos(f)
        _letters(f)
    _more_letters(fonts)


def declare_scripts(fonts) -> None:
    """Inter declares language systems for Latin and the default script only,
    and its kerning adds Cyrillic and Greek script records that hold nothing
    else, so a shaper finds no ccmp, mark or mkmk for them and an accent after
    а or α is never placed. Declaring both scripts registers every feature for
    them. Turkish and Azerbaijani are declared for the dotted small-capital i."""
    for f in fonts.values():
        text = f.features.text
        last = list(re.finditer(r"^languagesystem [^;]+;\n", text, re.M))[-1]
        f.features.text = text[: last.end()] + "languagesystem latn TRK;\nlanguagesystem latn AZE;\nlanguagesystem cyrl dflt;\nlanguagesystem grek dflt;\n" + text[last.end():]


def patch_ccmp(features_dir: Path) -> None:
    """Inter's soft-dotted rule (i before an accent above becomes dotless i)
    sees the accents above that Katagami adds, and skips the marks below
    between them, so í̧ loses its dot too."""
    path = features_dir / "ccmp.fea"
    text = path.read_text()
    text = re.sub(r"(@CCMP_ACC = \[.*?)(\n\];)", lambda m: m.group(1) + "\n  " + " ".join(ABOVE_MARKS) + m.group(2), text, count=1, flags=re.S)
    text = text.replace("lookup ccmp02 {\n", "lookup ccmp02 {\n  lookupflag UseMarkFilteringSet @CCMP_ACC;\n", 1)
    rules = "".join(f"  sub {name}' @CCMP_ACC by {name}.ccmp;\n" for name in SOFT_DOTTED_MODIFIERS)
    text = text.replace("} ccmp02;", rules + "} ccmp02;", 1)
    path.write_text(text)

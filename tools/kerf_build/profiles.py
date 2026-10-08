"""Design profiles: each proportional Katagami member is Inter run through the same
transforms with its own parameters. Every number here is explained in SPEC.md."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    key: str  # build/<key>, fonts/<key>
    family: str
    file_stem: str
    # Curve shape: share of the way each quarter-arc handle moves toward its
    # corner. Positive squares the curve, negative rounds it toward a circle.
    square_upper: float
    square_lower: float
    counter_boost: float = 1.25  # counters move further so corner strokes keep their weight
    join_ease: float = 0.3  # share of the change a handle gets where a curve meets a stem
    notch_fill: float = 0.45  # share of the way a bowl-to-stem notch corner moves toward the stem's end
    bowl_fill: float = 0.7  # the same, for the bowls of b, d, p and q
    valley_fill: float = 0.5  # share of the way the dip between m's arches rises toward the x-height
    square_punctuation: bool = False  # Inter's ss07 becomes the default
    tails: bool = True  # g's tail mirrors its bowl into a level cut; y and t end in vertical cuts
    t_slant: float = 0.0  # stems the top-left corner of t's stem drops, cutting its top at a slant
    xheight_scale: float = 1.0  # the lowercase from baseline to x-height scaled; ascenders move down with it
    scale: float = 1.0  # every glyph scaled about the origin; the line height stays
    promote: tuple[str, ...] = ()  # Inter feature files whose alternates become the default
    widths: dict[str, float] = field(default_factory=dict)  # horizontal ink scale per glyph
    spacing: int = 0  # units added to each sidebearing; negative tightens
    space_width: int | None = None  # advance of the space; None keeps Inter's
    terminal_angle: float | None = None  # degrees from horizontal for cut terminals; None keeps Inter's
    ascender_lift: int = 0  # units the lowercase ascenders rise above the cap height
    f_overhang: float = 0.0  # stems the f crossbar reaches past the stem's left edge
    corner_radius: float = 0.0  # stems; rounds every sharp vertex of the outline
    weight_map: tuple[tuple[int, int], ...] = ((100, 100), (200, 200), (300, 300), (400, 400), (500, 500),
                                               (600, 580), (700, 670), (800, 780), (900, 900))


DIGITS = ("cv01-one.fea", "cv02-four.fea", "cv03-six.fea", "cv04-nine.fea", "cv09-three.fea")

SANS = Profile(
    key="sans",
    family="Katagami Sans",
    file_stem="KatagamiSans",
    square_upper=0.36,
    square_lower=0.32,
    square_punctuation=True,
    # flat-top 3, open 4, straight-stem 6 and 9, long-flag 1, compact f
    promote=DIGITS + ("cv12-compact-f.fea",),
    terminal_angle=0.0,  # Camber cuts c, e, s, a and g level
    f_overhang=0.4,
    widths={
        "O": 0.90, "Q": 0.90, "C": 0.92, "G": 0.92, "D": 0.96,
        "o": 0.92, "c": 0.94, "e": 0.94,
        "b": 0.96, "d": 0.96, "p": 0.96, "q": 0.96, "g": 0.96,
        "E": 1.04, "F": 1.04, "L": 1.03, "S": 1.02,
    },
    # heavier than Inter from SemiBold up (Camber Bold ~ Inter 780)
    weight_map=((100, 100), (200, 200), (300, 300), (400, 400), (500, 500),
                (600, 620), (700, 740), (800, 840), (900, 900)),
)

# Inter's proportions and spacing with geometric, squared bowls, and every
# sharp vertex rounded. Katagami's figures and f, a few Mori and Geist touches.
# SPEC.md, Katagami Round.
ROUND = Profile(
    key="round",
    family="Katagami Round",
    file_stem="KatagamiRound",
    # geometric bowls, softer than Katagami Sans (0.36 / 0.32)
    square_upper=0.24,
    square_lower=0.22,
    notch_fill=0.35,
    # Katagami's figures and compact f, and G with spur (Mori, Geist, DM Sans, Nacelle)
    promote=DIGITS + ("cv10-g-spur.fea", "cv12-compact-f.fea"),
    spacing=-3,
    space_width=552,  # 270 per 1000 (Inter 281)
    terminal_angle=0.0,  # c, e, s, a and g cut level, as in Katagami Sans
    f_overhang=0.4,
    corner_radius=0.22,  # round only at the vertices
)

# Inter moved toward PP Mori and away from Inter's own tells: a lower
# x-height, smaller overall, tighter, wider capitals and round letters, a
# compact f, an l with a tail, a t cut at a slant, no squaring. SPEC.md,
# Katagami Text.
TEXT = Profile(
    key="text",
    family="Katagami Text",
    file_stem="KatagamiText",
    # superellipse about 2.13 (Mori 2.12) from Inter's 2.15
    square_upper=-0.02,
    square_lower=-0.02,
    counter_boost=1.0,
    notch_fill=0.35,
    # Katagami's long-flag 1, G with a spur, l with a tail, compact f
    promote=("cv01-one.fea", "cv05-l-tail.fea", "cv10-g-spur.fea", "cv12-compact-f.fea"),
    t_slant=0.45,  # the top of t's stem cut at about 20 degrees, as Mori's is
    xheight_scale=0.95,  # x-height 0.71 of the cap height (Inter 0.75)
    # halfway from Inter to Mori's ink proportions (Mori O/H 1.19, H 0.768 em, a 0.581 em)
    widths={
        "O": 1.05, "Q": 1.05, "C": 1.04, "G": 1.04, "D": 1.02,
        "o": 1.03, "c": 1.02, "e": 1.025, "s": 1.025, "a": 1.03,
        "E": 1.06, "F": 1.05, "L": 1.03, "S": 1.03,
        "H": 1.04, "N": 1.03, "U": 1.03, "A": 1.03, "B": 1.03, "K": 1.03, "P": 1.03, "R": 1.03,
        "T": 1.03, "V": 1.03, "X": 1.03, "Y": 1.03, "Z": 1.03,
    },
    spacing=-14,  # o sidebearing about 42 per 1000 after scaling (Inter 51, Mori 41)
    space_width=512,  # 240 per 1000 after scaling (Inter 281, Mori 225)
    terminal_angle=0.0,  # level cuts, as Mori cuts them
    scale=0.96,  # caps 0.699 em (Mori 0.70, Inter 0.728); x-height 0.498 em after the lower x-height
    # a lighter bold than Inter's, as Mori's is
    weight_map=((100, 100), (200, 200), (300, 300), (400, 400), (500, 480),
                (600, 560), (700, 640), (800, 760), (900, 900)),
)

PROFILES = {p.key: p for p in (SANS, ROUND, TEXT)}

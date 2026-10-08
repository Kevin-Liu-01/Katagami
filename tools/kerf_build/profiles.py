"""Design profiles: each proportional Kerf member is Inter run through the same
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
    square_punctuation: bool = False  # Inter's ss07 becomes the default
    g_tail: bool = False  # redraw the g tail into a level cut
    promote: tuple[str, ...] = ()  # Inter feature files whose alternates become the default
    widths: dict[str, float] = field(default_factory=dict)  # horizontal ink scale per glyph
    spacing: int = 0  # units added to each sidebearing; negative tightens
    space_width: int | None = None  # advance of the space; None keeps Inter's
    terminal_angle: float | None = None  # degrees from horizontal for cut terminals; None keeps Inter's
    ascender_lift: int = 0  # units the lowercase ascenders rise above the cap height
    weight_map: tuple[tuple[int, int], ...] = ((100, 100), (200, 200), (300, 300), (400, 400), (500, 500),
                                               (600, 580), (700, 670), (800, 780), (900, 900))


DIGITS = ("cv01-one.fea", "cv02-four.fea", "cv03-six.fea", "cv04-nine.fea", "cv09-three.fea")

SANS = Profile(
    key="sans",
    family="Kerf Sans",
    file_stem="KerfSans",
    square_upper=0.36,
    square_lower=0.32,
    square_punctuation=True,
    # flat-top 3, open 4, straight-stem 6 and 9, long-flag 1, compact f
    promote=DIGITS + ("cv12-compact-f.fea",),
    terminal_angle=0.0,  # Camber cuts c, e, s and a level
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

# Inter with Kerf's figures and f, a light squaring and a few Mori and Geist
# touches. Kept close to Inter's proportions, spacing and terminals.
# SPEC.md, Kerf Round.
ROUND = Profile(
    key="round",
    family="Kerf Round",
    file_stem="KerfRound",
    # a light squaring: superellipse about 2.23 from Inter's 2.15
    square_upper=0.05,
    square_lower=0.04,
    notch_fill=0.35,
    # Kerf's figures and compact f, and G with spur (Mori, Geist, DM Sans, Nacelle)
    promote=DIGITS + ("cv10-g-spur.fea", "cv12-compact-f.fea"),
    spacing=-3,
    space_width=552,  # 270 per 1000 (Inter 281)
    terminal_angle=0.0,  # c, e, s and a cut level, as in Kerf Sans
)

PROFILES = {p.key: p for p in (SANS, ROUND)}

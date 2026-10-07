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


SANS = Profile(
    key="sans",
    family="Kerf Sans",
    file_stem="KerfSans",
    square_upper=0.36,
    square_lower=0.32,
    square_punctuation=True,
    g_tail=True,
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

# Inter + PP Mori + Geist, measured against DM Sans and Nacelle (SPEC.md, Kerf Round).
ROUND = Profile(
    key="round",
    family="Kerf Round",
    file_stem="KerfRound",
    # superellipse 2.13 (Mori 2.12, DM Sans 2.13) from Inter's 2.16
    square_upper=-0.02,
    square_lower=-0.02,
    counter_boost=1.0,
    notch_fill=0.35,
    # G with spur, compact f, a with a foot spur
    promote=("cv10-g-spur.fea", "cv12-compact-f.fea", "cv16-a-tail.fea"),
    # toward the mean of Inter, Mori and Geist ink proportions
    widths={
        "O": 1.045, "Q": 1.045, "C": 1.035, "G": 1.035, "D": 1.02,
        "o": 1.02, "c": 1.02, "e": 1.015, "s": 1.03, "a": 1.10,
        "E": 1.055, "F": 1.05, "L": 1.03, "S": 1.025,
    },
    spacing=-11,  # o sidebearing 51 -> about 45 per 1000
    space_width=512,  # 250 per 1000 (Inter 281, Mori 225, Geist 250)
    terminal_angle=3.0,  # Inter 16 degrees, Mori and DM Sans 0, Geist 2-4
    ascender_lift=45,  # ascenders 3 percent above the caps, like Mori
)

PROFILES = {p.key: p for p in (SANS, ROUND)}

# Kerf design spec

Kerf is a type family with three members built from one source:

- **Kerf Sans**, a squared proportional sans serif for interfaces and display.
- **Kerf Round**, a rounder, universal sans serif for interfaces and text.
- **Kerf Mono**, a monospace for code, terminals and tables, fitted from Kerf Sans.

Kerf Sans starts from the outlines of [Inter](https://github.com/rsms/inter) (SIL OFL 1.1) and moves them toward the squared geometry of Camber (Eduardo Manso, Emtype Foundry). Kerf Mono is built from Kerf Sans and takes its approach to the monospace cell from the machine-readable faces of the 1970s, the same tradition Berkeley Mono (US Graphics) draws on.

Camber and Berkeley Mono are commercial fonts. Kerf contains none of their outlines. They were measured as references: Camber from the webfont on its foundry's specimen page, Berkeley Mono from a licensed copy. Every outline in Kerf is either a transformed Inter outline or drawn by the build scripts in `tools/`.

## Principles

1. **One skeleton.** Both members share units per em, vertical metrics, curve shape, terminals and punctuation. Text set in Kerf Sans with code in Kerf Mono must look like one family.
2. **Square curves, straight cuts.** Bowls are superellipses, not circles. Terminals are cut horizontally. Dots and punctuation are square.
3. **Round letters as wide as straight ones.** In Inter, O is wider than H. In Kerf, rounds are condensed so O, H, o and n read as the same width.
4. **Every glyph distinct in code.** In the mono, i, l, 1, I and | are distinguished by shape, not only by position. 0 and O differ by a centre bar in 0.
5. **Reproducible.** The fonts are generated from Inter's pinned sources by deterministic scripts. Every number below is a constant in the build code.

## Metrics

All values are in font units at 2048 units per em, inherited from Inter.

| Metric | Value | em |
|---|---|---|
| Units per em | 2048 | 1.000 |
| Cap height | 1490 | 0.728 |
| x-height | 1118 | 0.546 |
| Ascender | 1984 | 0.969 |
| Descender | -494 | -0.241 |
| Mono cell (advance) | 1232 | 0.602 |

The mono cell is 0.6 em rounded up to a multiple of 8.

## Curve shape

Each quarter arc in a cubic outline runs from an on-curve point P0 to P3, with handles C1 and C2 on the tangents. K is where the two tangents meet. The handle fraction f = |C1 - P0| / |K - P0| sets the shape: a circle is 0.552, and a superellipse with exponent n has f = (2^(-1/n) - 0.5) / 0.375.

| Source | Measured f | Superellipse n |
|---|---|---|
| Inter | about 0.60 | about 2.16 |
| Camber, lowercase | about 0.73 | about 2.68 |
| Camber, caps | about 0.76 | about 2.84 |

The build moves each handle fraction a share s of the way toward 1:

- Caps: s = 0.36, which takes f from 0.60 to about 0.74 (n about 2.8).
- Lowercase and everything else: s = 0.32, which takes f to about 0.73 (n about 2.7).
- Counters move 1.25 times as far, so the stroke at a 45 degree corner does not get heavier.
- Where a curve meets a stem at a corner point (the shoulders of n, h, m and r, the joins of b, d, p and q), the handle on that corner gets 30 percent of the squaring. The curve stays square through its middle and eases into the stem, so the notch at the join stays as shallow as Inter's.
- Arcs qualify when their tangents are within 60 degrees of perpendicular and both handle fractions are between 0.35 and 0.85. Circled forms, the degree sign, bullets and the Geometric Shapes block stay round.

Which arcs to square is decided on the Regular master and applied to every master, so the masters stay compatible for interpolation.

## Widths

Horizontal ink scale per glyph in Kerf Sans. Sidebearings are kept, and vertical stems are restored to their original thickness after scaling.

| Glyphs | Scale |
|---|---|
| O Q | 0.90 |
| C G | 0.92 |
| D | 0.96 |
| o | 0.92 |
| c e | 0.94 |
| b d p q g | 0.96 |
| E F | 1.04 |
| L | 1.03 |
| S | 1.02 |

Accented and composite glyphs are re-seated on their changed bases, and their marks keep their position relative to the base.

## Terminals

The tail of g is redrawn on every master. The bottom stroke runs left, turns up through one squared quarter curve (handle fraction 0.72), and rises vertically into a horizontal cut. The rising stroke is 0.94 stems wide, and the cut sits at the height and left edge Inter gives the terminal at that weight, which keeps it clear of the bowl in Black.

## Joins

Inter's heavy weights cut deep notches where bowls join stems, which leaves a hairline in bold a and u. Each such notch (a corner where a curve meets a stem edge that runs to the baseline or x-height: a, u, n, m, h, b, p, r) moves 45 percent of the way toward the baseline or x-height, with its step and handle. The handle stays between the corner and the far end of its curve, so the bowl flattens into the join instead of dipping below the baseline.

## Punctuation

Inter's square punctuation (its `ss07` set) is Kerf's default. Inter's round punctuation is available under `ss07`.

## Weight

The weight axis runs 100 to 900 in Kerf Sans and 100 to 700 in Kerf Mono. From SemiBold up, Kerf is heavier than Inter at the same weight value, because Camber's Bold is about 20 percent heavier than Inter's:

| Weight | Inter master value | Kerf master value |
|---|---|---|
| 600 SemiBold | 580 | 620 |
| 700 Bold | 670 | 740 |
| 800 ExtraBold | 780 | 840 |

## Kerf Mono

### Fitting glyphs to the cell

Every outline is scaled horizontally about its centre, then centred in the 1232-unit cell. The scale is decided on the Regular master and used for all masters.

- **Wide glyphs** are condensed to at most 76 percent of the cell (caps, symbols) or 72 percent (lowercase).
- **Stem compensation.** Condensing thins vertical stems. Glyphs scaled to 0.85 or more get their full stem weight back. Narrower glyphs (m, w, M, W) get back only part of it, down to 45 percent at a scale of 0.55, so their counters keep room.
- **Narrow letters** are stretched to a minimum share of the cell: f, s, c and z to 66 percent, t and J to 62 percent, r to 60 percent, dotless j to 50 percent.
- Glyphs built from parts, such as the colon or t, are decomposed first and fitted as one outline. Accented letters keep their components and marks follow their base.

### Disambiguation

| Glyph | Form |
|---|---|
| i | flag at the top left, slab across the foot (60 percent of the cell) |
| l | flag at the top left, tail to the right |
| j | flag at the top left |
| I | serifs top and bottom |
| 1 | flag and foot |
| 0 | vertical bar in the centre of the counter; slashed zero under `zero` |

Flags are 20 percent of the cell long and as thick as the hyphen.

### Box drawing and blocks

U+2500 to U+259F are drawn by `tools/kerf_build/boxdraw.py`, not taken from Inter. Each box-drawing character is read from its Unicode name into four arms (up, right, down, left) with a weight of light, heavy or double, so the whole block follows one rule set.

- Lines span the full line height, from the descender to the ascender, so they join across lines when the line height is 1.21 em.
- Light lines are 0.9 times the hyphen thickness. Heavy lines are twice light. Double lines are two light lines with a gap equal to one light line.
- Rounded corners use a radius of 0.42 cell and the same handle fraction (0.73) as the squared letters.
- Shades are square dot grids at 25, 50 and 75 percent coverage.

## Coverage in v0.1

| | Kerf Sans | Kerf Mono |
|---|---|---|
| Glyphs | Inter's full set | about 1,140 |
| Scripts | Latin, Greek, Cyrillic (from Inter) | Latin |
| Features | Inter's full feature set | mark positioning, `zero` |

## Kerf Round

Kerf Round is Inter moved toward a fusion of PP Mori (Pangram Pangram) and Geist (Vercel), with DM Sans and Nacelle as secondary references. All five were measured from their own webfonts at 1000 px, as Camber was; none of their outlines is used. The parameters live in `tools/kerf_build/profiles.py` as the `round` profile and run through the same transforms as Kerf Sans.

| Measure (per 1000 em, Regular) | Inter | PP Mori | Geist | Kerf Round |
|---|---|---|---|---|
| Superellipse, O | 2.15 | 2.12 | 2.23 | about 2.13 |
| O ink width ÷ H ink width | 1.14 | 1.19 | 1.23 | about 1.19 |
| Terminal angle, c e s a | 16° | 0° | 2–4° | 3° |
| o sidebearing | 51 | 41 | 44 | 45 |
| Space | 281 | 225 | 250 | 250 |
| Ascender ÷ cap height | 1.00 | 1.06 | 1.00 | 1.03 |

- **Curves:** handles move 2 percent of the way toward a circle (rounding is negative squaring).
- **Widths:** O and Q 1.045, C and G 1.035, D 1.02, o and c 1.02, e 1.015, s 1.03, a 1.10, E 1.055, F 1.05, L 1.03, S 1.025, with stems held.
- **Terminals:** each angled cut between two curves is turned to 3 degrees. Both ends slide along their own curve's tangent with their handle. Inter's capitals and figures are already cut level.
- **Ascenders:** lowercase strokes above the x-height stretch so ascenders rise 45 units (3 percent of the cap height) above the caps; accents on those letters rise with them.
- **Letterforms:** Inter's G with spur (cv10), compact f (cv12) and a with a foot spur (cv16) become the defaults. Round dots and round punctuation stay.
- **Joins:** bowl-to-stem notches fill 35 percent of the way, as in Kerf Sans but lighter.
- **Weight:** Inter's own weight mapping.

## Not done yet

- Hand corrections. Every glyph is the output of a transform; none has been redrawn by eye.
- Italics.
- Code ligatures for the mono, as an opt-in stylistic set.
- Hinting, and fontbakery checks.
- A flat-topped t and the straight Q tail measured on Camber.

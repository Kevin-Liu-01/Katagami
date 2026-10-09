# Katagami design spec

Katagami is a type family with three members built from one source:

- **Katagami Sans**, a squared proportional sans serif for interfaces and display.
- **Katagami Round**, a rounder, universal sans serif for interfaces and text.
- **Katagami Mono**, a monospace for code, terminals and tables, fitted from Katagami Sans.

Katagami Sans starts from the outlines of [Inter](https://github.com/rsms/inter) (SIL OFL 1.1) and moves them toward the squared geometry of Camber (Eduardo Manso, Emtype Foundry). Katagami Mono is built from Katagami Sans and takes its approach to the monospace cell from the machine-readable faces of the 1970s, the same tradition Berkeley Mono (US Graphics) draws on.

Camber and Berkeley Mono are commercial fonts. Katagami contains none of their outlines. They were measured as references: Camber from the webfont on its foundry's specimen page, Berkeley Mono from a licensed copy. Every outline in Katagami is either a transformed Inter outline or drawn by the build scripts in `tools/`.

## Principles

1. **One skeleton.** Both members share units per em, vertical metrics, curve shape, terminals and punctuation. Text set in Katagami Sans with code in Katagami Mono must look like one family.
2. **Square curves, straight cuts.** Bowls are superellipses, not circles. Terminals are cut horizontally. Dots and punctuation are square.
3. **Round letters as wide as straight ones.** In Inter, O is wider than H. In Katagami, rounds are condensed so O, H, o and n read as the same width.
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
| Mono cell (advance) | 1280 | 0.625 |

The mono cell is 0.625 em. At that width Katagami's x-height sits at 0.87 of the cell, the proportion Berkeley Mono has at 0.6 em, so the letters read at the same width as a 0.6 em mono with a smaller x-height. The glyphs keep Katagami Sans' vertical metrics, so mono and sans mix inline.

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

Arcs tighter than 1.6 stems in radius (the hooks of f, t, j and r, small counters) get the squaring in proportion to their radius, so small curves stay supple while bowls stay square.

Which arcs to square is decided on the Regular master and applied to every master, so the masters stay compatible for interpolation.

## Widths

Horizontal ink scale per glyph in Katagami Sans. Sidebearings are kept, and vertical stems are restored to their original thickness after scaling.

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

The cut ends of c, e, s and a are cut again along a level line (0 degrees) through the old cut's midpoint, from Inter's 16 degrees. Each edge of the stroke is split where it crosses the new line by de Casteljau subdivision: the edge that ran past it is trimmed, the edge that stopped short is extended along its own curve, and both handles of each edge move with the split. The edges stay pieces of their original curves, so the letter is not warped. Inter's capitals and figures are already cut level. The f's crossbar, which starts inside the compact f's stem, reaches 0.4 stems past the stem's left edge. Katagami Round takes the same cuts and the same f.

Three tails are redrawn, keeping each glyph's point count so the masters stay compatible:

- **g:** the tail's outer edge is the right side's turn into the bottom of the hook, mirrored about the bottom's centre, drawn in to 0.9 of the right side's reach (`G_REACH`) so the end sits inside the bowl at every weight, and cut level at Inter's terminal height. The curl keeps the bowl side's squaring. The inner edge leans toward the outer one, by nothing at the counter's floor and in proportion to the distance along the edge after that, so the cut is 0.78 as wide as the mirrored stroke (`G_TIP`). The tail thins toward its end and does not finish as heavy as the stem.
- **y:** the tail comes down the right arm's diagonal, turns through a quarter turn and runs level to a vertical cut. The cut keeps Inter's position and length.
- **t:** the hook runs level from its bottom to a vertical cut at Inter's terminal position.

The y's quarter turns use the member's handle fraction: 0.60 plus 0.40 times the lowercase squaring and counter boost, so Katagami Sans turns square, Katagami Round less so, and Katagami Text round.

## Figures

Inter's alternate figures become the defaults: a 1 with a long flag (cv01), an open 4 (cv02), a 6 and 9 with straight stems into their bowls (cv03, cv04) and a flat-topped 3 (cv09). Each feature now switches back to Inter's form and is relabelled to say so ("Closed four", "Inter digits" for ss01). The f is Inter's compact f (cv12).

## Joins

Inter's heavy weights cut deep notches where bowls join stems, which leaves a hairline in bold a and u. Each such notch (a corner where a curve meets a stem edge that runs to the baseline or x-height: a, u, n, m, h, b, p, r) moves 45 percent of the way toward the baseline or x-height, with its step and handle. The handle stays between the corner and the far end of its curve, so the bowl flattens into the join instead of dipping below the baseline. The joins of b, d, p and q (and their drawn variants) move 70 percent of the way, because their full bowls leave the thinnest strokes. The fill is scaled by weight: none in the Thin master and the full share in Regular and Black, so the light weights in between get part of it. Inter's Thin joins barely notch, and moving their corners left a lump where the curve meets the stem.

Squaring moves a counter further than the edge outside it, and eases a curve's outer edge into a stem while the inner edge squares in full. At Thin, where the stroke is 46 units, that left the joins of b, d, p, q, g and a about 8 units wide and the shoulders of n, h, u and r about 24. So in the Thin master the build measures the stroke along each squared outline: from points every 6 units a ray runs inward to the far edge. Any squared arc that brings the stroke under 0.8 of the Thin stem (`THIN_FLOOR`) moves back toward Inter's arc by the least share that restores that width. Regular and Black are untouched, and the weights between Thin and Regular interpolate from the corrected Thin.

The dip between the arches of m, where the second arch leaves the middle stem, rises half of the way to the x-height (scaled by weight the same way). The curves on both sides are squashed vertically into the shorter span, so their handles keep their direction and the second arch keeps its weight where it meets the first.

## Punctuation

Inter's square punctuation (its `ss07` set) is Katagami's default. Inter's round punctuation is available under `ss07`.

## Weight

The weight axis runs 100 to 900 in Katagami Sans and 100 to 700 in Katagami Mono. From SemiBold up, Katagami is heavier than Inter at the same weight value, because Camber's Bold is about 20 percent heavier than Inter's:

| Weight | Inter master value | Katagami master value |
|---|---|---|
| 600 SemiBold | 580 | 620 |
| 700 Bold | 670 | 740 |
| 800 ExtraBold | 780 | 840 |

## Katagami Mono

### Fitting glyphs to the cell

Every outline is fitted to the 1280-unit cell. Each decision is made on the Regular master and used for all masters.

- **Even widths.** A monospace reads evenly when its letters fill the cell evenly. Letters move toward a target ink width, keeping a quarter of their own width so the alphabet does not turn uniform: lowercase 0.69 of the cell, round lowercase (o c e b d p q g a s) 0.74, capitals 0.74, round capitals 0.79, figures 0.72. Stems are held at their true thickness.
- **Wide letters fill the cell.** m 0.84, w 0.94, M 0.82, W 0.94, æ œ Æ Œ 0.88. Where they still condense, the stems keep only part of their weight (down to 45 percent at a scale of 0.55), which is how a monospace m finds room for its counters.
- **Arms, around a fixed stem.** f, t, r, dotless j and J keep their stem and stretch only what lies to its left and right, so arms and crossbars reach into the cell: f 0.70, t 0.68, r 0.58, dotless j 0.54, J 0.64.
- **Narrow by identity.** i, l, I and 1 keep their own width; their flags and slabs fill the cell.
- Glyphs built from parts, such as the colon or t, are decomposed first and fitted as one outline. Accented letters keep their components and marks follow their base.

### Disambiguation

| Glyph | Form |
|---|---|
| i | flag at the top left, slab across the foot (60 percent of the cell) |
| l | flag at the top left, tail to the right |
| j | flag at the top left |
| I | serifs top and bottom |
| 1 | long flag, from Katagami Sans |
| 0 | vertical bar in the centre of the counter; slashed zero under `zero` |

Flags are 20 percent of the cell long and as thick as the hyphen.

### Box drawing and blocks

U+2500 to U+259F are drawn by `tools/kerf_build/boxdraw.py`, not taken from Inter. Each box-drawing character is read from its Unicode name into four arms (up, right, down, left) with a weight of light, heavy or double, so the whole block follows one rule set.

- Lines span the full line height, from the descender to the ascender, so they join across lines when the line height is 1.21 em.
- Light lines are 0.9 times the hyphen thickness. Heavy lines are twice light. Double lines are two light lines with a gap equal to one light line.
- Rounded corners use a radius of 0.42 cell and the same handle fraction (0.73) as the squared letters.
- Shades are square dot grids at 25, 50 and 75 percent coverage.

## Coverage in v0.1

| | Katagami Sans, Round, Text | Katagami Mono |
|---|---|---|
| Glyphs | about 11,240, of which about 3,340 are drawn by Katagami | about 3,500, all fitted to the cell |
| Scripts | Latin, Greek and Cyrillic drawn; 19 more merged from Noto Sans; Chinese, Japanese and Korean through Katagami CJK | Latin, Greek, Cyrillic |
| Features | Inter's full set plus small capitals | Inter's set without capital spacing or n:1 ligatures, plus small capitals and code ligatures |
| People covered (map) | 99.9 percent, 223 of 234 languages | 44.4 percent, 172 of 234 |

The map counts a language as covered when the family has at least 90 percent of the letters it draws for it, and for Chinese, Japanese and Korean the whole national standard. Shares are rounded down. The eleven languages still missing are written in nine scripts the family does not carry yet: Tifinagh (Tamazight), Ol Chiki (Santali), Coptic, Tibetan, Hanifi Rohingya, N'Ko, Thaana, Vai and Canadian syllabics.

## Katagami Round

Katagami Round sits between Katagami Sans and Inter: geometric bowls that are less square than Katagami Sans, with every sharp vertex rounded. It started from Inter, PP Mori (Pangram Pangram) and Geist (Vercel), measured from their webfonts with DM Sans and Nacelle as secondary references; none of their outlines is used. The parameters live in `tools/kerf_build/profiles.py` as the `round` profile.

- **Curves:** squared at 0.24 (caps) and 0.22 (lowercase), with the tight-curve rule, so bowls read as geometric without Katagami Sans's flat sides.
- **Vertices:** every convex corner sharper than 20 degrees is rounded with a radius of 0.22 stems (kappa 0.5523 handles). The corners are chosen on Regular and rounded in every master, so the masters stay compatible. Curves are not rounded further.
- **Terminals:** c, e, s, a and g cut level, as in Katagami Sans. The f crossbar overhangs the stem by 0.4 stems.
- **Letterforms:** Katagami's figures and compact f, and Inter's G with spur (cv10).
- **Joins:** bowl-to-stem notches fill 35 percent of the way.
- **Spacing:** sidebearings 3 units tighter than Inter, space 552 units.

## Katagami Text

Katagami Text is the member for reading. It moves Inter toward PP Mori's proportions and away from Inter's own tells, the tall x-height first. It is the least technical member and the one the converter on the website uses for serif text. The parameters are the `text` profile.

- **x-height:** the lowercase from the baseline to the x-height is scaled by 0.95. Ascenders, dots and accents move down with it and descenders stay, so the x-height is 0.71 of the cap height (Inter 0.75).
- **Size:** every glyph, advance, anchor and kerning value is then scaled by 0.96 about the origin, with the line height unchanged: caps 0.699 em (PP Mori 0.70, Inter 0.728), x-height 0.498 em.
- **Curves:** a slight negative squaring (0.02), so bowls are a touch rounder than Inter's.
- **Widths:** round letters wider (O and Q 1.05, C and G 1.04, o 1.03, e and s 1.025, a 1.03), the narrow capitals opened (E 1.06, F 1.05, L and S 1.03), and the other capitals 3 to 4 percent wider (H 1.04), toward Mori's H of 0.768 em.
- **Letterforms:** a plain double-storey a with a straight stem and its arch cut level; Inter's compact f (cv12) and l with a tail (cv05); a t whose stem top is cut at a slant, its left corner 0.45 stems lower than its right; Katagami's long-flag 1; G with a spur (cv10).
- **Terminals:** c, e, s, a and g cut level, as PP Mori cuts them.
- **Weight:** the heavy weights are lighter than Inter's (700 is Inter's 640, 800 its 760), as PP Mori's are.
- **Spacing:** sidebearings 14 units tighter before scaling, so o's sidebearing is about 42 per 1000 (Inter 51, Mori 41); space 512 units before scaling.

## Alternates and their accented forms

When an alternate becomes the default, its accented forms are swapped with it (aacute with aacute.2, Gbreve with Gbreve.1). The swapped accented forms are composites of the swapped base glyphs, so their components are renamed through the same swap. The default á is then built on the new a, not on Inter's original.

## OpenType features

Katagami Sans, Round and Text compile Inter's own feature files, so every feature Inter documents works: contextual alternates (`calt`, which raises hyphens and arrows between capitals and turns `->` into an arrow), case-sensitive forms (`case`), capital spacing (`cpsp`), slashed zero (`zero`), tabular and proportional figures (`tnum`, `pnum`), fractions, numerators and denominators (`frac`, `numr`, `dnom`), superscripts, subscripts and scientific inferiors (`sups`, `subs`, `sinf`), ordinals (`ordn`), discretionary ligatures (`dlig`), the character variants `cv01` to `cv16` and the stylistic sets `ss01` to `ss08`. Where Katagami made an Inter alternate its default, the feature switches back to Inter's form and its label says so.

Katagami adds small capitals, which Inter does not have (its 13 `.sc` glyphs are phonetic letters):

- **`smcp` and `c2sc`:** 320 small capitals for Latin, Greek and Cyrillic, accented letters included. Each is its capital scaled to the x-height and emboldened back to the lowercase stem (and 0.85 of that on horizontal strokes), then tracked 0.03 em wider. Accented small capitals reuse the lowercase marks, moved by the difference in top anchors.

Katagami Mono keeps every glyph of Katagami Sans, fitted to the cell, so it has the same features, with two exceptions. Capital spacing is left out, and after compiling, the lookups that set two or more characters as one glyph (Inter's `->` arrows) are emptied, so every character stays one cell wide. In their place Katagami Mono has code ligatures as an opt-in `dlig`: `->`, `<-`, `=>`, `!=`, `==`, `===`, `!==`, `>=` and `<=`. Every character keeps its cell; the leading ones become an empty cell and the last one draws the symbol across all of them. Arrows keep their head and stretch the shaft, = and ≠ stretch their bars, and ≤ and ≥ are centred on the run.

## Other scripts

Katagami draws Latin, Greek and Cyrillic. Katagami Sans, Round and Text also set 19 more scripts with the outlines and OpenType layout of Google's Noto Sans fonts (SIL OFL 1.1), merged in by `tools/build_world.py` the way Pretendard joins Inter and Source Han Sans: Devanagari, Arabic, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam, Sinhala, Thai, Lao, Myanmar, Ethiopic, Hebrew, Armenian, Georgian and Khmer.

- Each Noto font is subset to its script's Unicode blocks with its layout closure, so it brings no Latin, digits or punctuation of its own.
- It is instanced at Katagami's master weights (100, 400, 900) and scaled from Noto's 1000-unit em to 2048 times Katagami's x-height over Noto Sans's (536 per 1000), so its letters sit at the member's size.
- Each Katagami master is merged with the scripts at its weight, and the three merged masters are built back into one variable font with the member's weight axis, named instances and line spacing. The Windows clipping box grows to the tallest script.
- These glyphs are Noto's design at Katagami's size and weight; they are not redrawn in Katagami's style.

Chinese, Japanese and Korean would pass the 65,535-glyph limit, so they are companion files, Katagami CJK SC, TC, JP and KR (`tools/build_cjk.py`), as Pretendard JP is. Each is Noto Sans SC, TC, JP or KR subset to a national standard (GB 2312's 6,763 hanzi; Big5's 13,053 hanzi with bopomofo; JIS X 0208's 6,355 kanji with the kana; all 11,172 Hangul syllables), scaled to 2048 units and given Katagami's line metrics. The website sets them in the same CSS family as each proportional member with unicode-range. Simplified and Traditional Chinese share most code points; SC is tried first for those, and the TC web file carries only the characters SC lacks.

## Not done yet

- Hand corrections. Every glyph is the output of a transform; none has been redrawn by eye.
- Italics.
- Hinting, and fontbakery checks.
- A flat-topped t and the straight Q tail measured on Camber.

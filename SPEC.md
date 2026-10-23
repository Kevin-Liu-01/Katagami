# Katagami design spec

Katagami is a type family with five members built from one source:

- **Katagami Sans**, a squared proportional sans serif for interfaces and display.
- **Katagami Round**, a rounder, universal sans serif for interfaces and text.
- **Katagami Text**, the member for reading, with a lower x-height and tighter spacing.
- **Katagami Serif**, Katagami Text with flat slab serifs.
- **Katagami Mono**, a monospace for code, terminals and tables, fitted from Katagami Sans.

Each member has an Italic, built by the same transforms from Inter's Italic.

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

The cut ends of c, e, s and a are cut again along a level line (0 degrees) through the old cut's midpoint, from Inter's 16 degrees. Each edge of the stroke is split where it crosses the new line by de Casteljau subdivision: the edge that ran past it is trimmed, the edge that stopped short is extended along its own curve, and both handles of each edge move with the split. The edges stay pieces of their original curves, so the letter is not warped. Inter's capitals and figures are already cut level. The f's crossbar, which starts inside the compact f's stem, reaches 0.8 Regular stems past the stem's left edge at every weight, so the bar shows the same length on the left from Thin to Black (`f_overhang`). Katagami Round and Katagami Text take the same f.

Three tails are redrawn, keeping each glyph's point count so the masters stay compatible:

- **g:** the tail's outer edge is the right side's turn into the bottom of the hook, mirrored about the bottom's centre, drawn in to 0.95 of the right side's reach (`G_REACH`) so the end sits inside the bowl at every weight, and cut level at Inter's terminal height. The curl keeps the bowl side's squaring. The inner edge is the counter's turn mirrored the same way, so the tail keeps its full width to the cut.
- **y:** the tail comes down the right arm's diagonal, turns through a quarter turn and runs level to a vertical cut. The cut keeps Inter's position and length.
- **t:** the hook runs level from its bottom to a vertical cut at Inter's terminal position.

The y's quarter turns use the member's handle fraction: 0.60 plus 0.40 times the lowercase squaring and counter boost, so Katagami Sans turns square, Katagami Round less so, and Katagami Text round.

## Figures

Inter's alternate figures become the defaults: a 1 with a long flag (cv01), an open 4 (cv02), a 6 and 9 with straight stems into their bowls (cv03, cv04) and a flat-topped 3 (cv09). Each feature now switches back to Inter's form and is relabelled to say so ("Closed four", "Inter digits" for ss01). The f is Inter's compact f (cv12).

## Hand corrections

Three letters are corrected by targeted transforms, in every master of the members they apply to. Each keeps its point count, so the masters stay compatible.

- **A flat-topped t** (Katagami Sans and Round): the stem stops at the top of the crossbar, so the top of the t is one level line, as Camber's is. The stem part is shared by t and the compact t (`cv13`), so both change. The t's anchors above the cut, and the marks of ť, ṫ and ẗ, come down by the same amount (`flat_t`, `set_t_top`). Text and Serif keep their own t, whose stem rises above the bar and is cut at a slant. Katagami Mono raises the stem again to Inter's height, 0.24 x-heights above the bar: in code a flat t reads as the Greek τ, and every character in the mono must stay distinct.
- **A straight Q tail** (every member): Inter's tail crosses the bowl through two extra points on each side. The width transforms move those points apart and bent the tail by up to 7 degrees in Black. Each run of points that bends by less than 12 degrees is put back on the line between its ends (`straighten_q`, `straighten_runs`); Mono straightens its Q again after fitting it to the cell.
- **A squarer 2** (Katagami Sans 0.35, Round 0.25, `two_square`): the 2's bowl and the spine that turns from it into the diagonal move that much further toward their corners. The spine is not a quarter turn, so it is planned with tangents as little as 37 degrees apart, where other arcs need 60.

## Joins

Inter's heavy weights cut deep notches where bowls join stems, which leaves a hairline in bold a and u. Each such notch (a corner where a curve meets a stem edge that runs to the baseline or x-height: a, u, n, m, h, b, p, r) moves 45 percent of the way toward the baseline or x-height, with its step and handle. The handle stays between the corner and the far end of its curve, so the bowl flattens into the join instead of dipping below the baseline. The fill is scaled by weight: none in the Thin master and the full share in Regular and Black, so the light weights in between get part of it. Inter's Thin joins barely notch, and moving their corners left a lump where the curve meets the stem.

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

## Italics

Every member has an Italic: one variable font beside its roman, `fonts/sans/KatagamiSans-Italic[wght].ttf` and so on, with the same weights (100 to 900, Mono 100 to 700), named instances, line metrics and features.

- **Source.** The four proportional Italics start from Inter Italic's Thin, Regular and Black masters (`src/Inter-Italic.glyphspackage` at the same pinned commit). Inter Italic slants 9.4 degrees and draws a single-storey a and an f with a descender; Katagami keeps both.
- **Upright, then slanted.** Every transform assumes upright stems, so each Italic master is first stood upright: every point moves by x - (y - 559) tan 9.4, about half of Inter's x-height, the pivot Inter slants around. The member's transforms then run as they do on the roman, and the result is slanted again about the member's own half x-height. Squaring, level cuts, the tails, widths, the corrections and the serifs are the roman's, at the italic angle. A shear is affine, so handle fractions and the squaring planned from them do not change. Composites with flipped or scaled components are decomposed first, because a shear would turn their matrices into skews.
- **Katagami Mono Italic** stands Katagami Sans Italic upright the same way, fits it to the cell as the roman and slants it again. Box drawing, block elements, Braille and the agent symbols are drawn after the slant, upright, so their lines still join from cell to cell.
- **Katagami Serif Italic.** The serifs are cut in the upright frame and slanted with the letter, so their ends follow the italic angle and their backs stay level. Capitals keep every serif. The lowercase takes entry and exit strokes instead (`italic_ends`): the leftmost top end keeps its serif on the left side only, the entry, and head serifs stay; the rightmost foot on the baseline keeps its serif on the right side only, the exit, unless ink above the middle of the x-height reaches 0.6 stems past it (the arm of r), where the pen leaves from the arm. Every other lowercase top and baseline foot takes none. Feet on the descender (p, q) keep both sides.
- **Names and linking.** Name 1 is the family (Katagami Sans), name 2 Regular or Italic, and the named instances run Thin Italic to Black Italic. The STAT table of each file has a weight axis value for every named weight (Regular elidable and linked to Bold) and an `ital` axis: 0, Roman, elidable and linked to 1, in the roman; 1, Italic, in the Italic. Inter Italic has no slant axis, so Katagami has none. fsSelection sets ITALIC, macStyle its italic bit, post.italicAngle is -9.4 and the caret slopes with it. The Italic takes the roman's hhea, typo and Windows metrics, so both set the same line height. `tools/finish.py` writes all of this.
- **Other scripts.** The Italics carry Latin, Greek and Cyrillic, about 3,250 glyphs each, and no merged scripts. Italic Arabic, Devanagari or Thai is not a convention, and copying the 28 merged scripts into each Italic would double the download. For italic text in another script, a web stylesheet declares the roman's script files a second time with `font-style: italic`, so the browser sets it with the roman's letters instead of falling back to another family or slanting them.

## Katagami Mono

### Fitting glyphs to the cell

Every outline is fitted to the 1280-unit cell. Each decision is made on the Regular master and used for all masters.

- **Even widths.** A monospace reads evenly when its letters fill the cell evenly. Letters move toward a target ink width, keeping a quarter of their own width so the alphabet does not turn uniform: lowercase 0.69 of the cell, round lowercase (o c e b d p q g a s) 0.74, capitals 0.74, round capitals 0.79, figures 0.72. Stems are held at their true thickness.
- **Wide letters fill the cell.** m 0.84, w 0.94, M 0.82, W 0.94, æ œ Æ Œ 0.88. Where they still condense, the stems keep only part of their weight (down to 45 percent at a scale of 0.55), which is how a monospace m finds room for its counters.
- **Arms, around a fixed stem.** f, t, r, dotless j and J keep their stem and stretch only what lies to its left and right, so arms and crossbars reach into the cell: f 0.70, t 0.68, r 0.58, dotless j 0.54, J 0.64.
- **Narrow by identity.** i, l, I and 1 keep their own width; their flags and slabs fill the cell.
- Glyphs built from parts, such as the colon or t, are decomposed first and fitted as one outline. Accented letters keep their components and marks follow their base.

### Greek and Cyrillic

Greek and Cyrillic are fitted to the cell by the same rules as Latin. Their round letters move toward the round targets with o and O (ο σ ς θ α δ ε, о е э є с б з; Ο Θ Ω, О С Э Є З), and their wide letters fill most of the cell as m and w do instead of being squeezed to the lowercase width: ж and Ж 0.94, щ and Щ 0.90, ю, ы, љ and њ and their capitals 0.88 to 0.90, ш and Ш 0.86, ф, Ф, ψ and Φ 0.84, Ψ 0.86, ω 0.86. Iota keeps its own width, as i does. Inter draws the Cyrillic н, м, т and я as small capitals (h.sc, m.sc, t.sc, r.sc); they are fitted as the lowercase letters they stand for, so м is as wide as m and н as n. Letters Inter builds from Latin ones (а, е, о, р, с, у, х, І, Ј) follow their Latin base.

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

### Braille and agent symbols

`tools/kerf_build/terminal.py` draws all 256 Braille patterns (U+2800 to U+28FF) as square dots the size of the period on a 2 by 4 grid spread evenly over the full line height, and the status symbols coding agents print in the terminal (⏺ ⎿ ✔ ✘ ✕ ◉ ▸ ⏵ ⏸ ⏹ ✢ ✳ ✶ ✻ ✽), each sized and weighted from its neighbours in every master.

## Coverage in v0.2

| | Katagami Sans, Round, Text, Serif | Their Italics | Katagami Mono and Mono Italic |
|---|---|---|---|
| Glyphs | 14,913 in Sans and 14,914 in the others, of which about 3,340 are drawn by Katagami | about 3,255 | 3,778 and 3,695, all fitted to the cell |
| Characters | 8,251 | 2,816 | 3,283 and 3,247 |
| Scripts | Latin, Greek and Cyrillic drawn; 28 more merged from Noto; Chinese, Japanese and Korean through Katagami CJK | Latin, Greek, Cyrillic | Latin, Greek, Cyrillic |
| Features | Inter's full set plus small capitals | the same | Inter's set without capital spacing or n:1 ligatures, plus small capitals and code ligatures |

The map counts a language as covered when the family has at least 90 percent of the letters it draws for it, and for Chinese, Japanese and Korean the whole national standard. In v0.1 it listed eleven languages the family did not cover, written in nine scripts: Tifinagh (Tamazight), Ol Chiki (Santali), Coptic, Tibetan, Hanifi Rohingya, N'Ko, Thaana, Vai and Canadian syllabics. v0.2 merges all nine (see Other scripts), and the map now counts all 234 languages as covered by Katagami Sans, Round, Text and Serif, and 172 by Katagami Mono.

## Katagami Round

Katagami Round sits between Katagami Sans and Inter: geometric bowls that are less square than Katagami Sans, with every sharp vertex rounded. It started from Inter, PP Mori (Pangram Pangram) and Geist (Vercel), measured from their webfonts with DM Sans and Nacelle as secondary references; none of their outlines is used. The parameters live in `tools/kerf_build/profiles.py` as the `round` profile.

- **Curves:** squared at 0.24 (caps) and 0.22 (lowercase), with the tight-curve rule, so bowls read as geometric without Katagami Sans's flat sides.
- **Vertices:** every convex corner sharper than 20 degrees is rounded with a radius of 0.22 stems (kappa 0.5523 handles). The corners are chosen on Regular and rounded in every master, so the masters stay compatible. Curves are not rounded further.
- **Terminals:** c, e, s, a and g cut level, as in Katagami Sans. The f crossbar overhangs the stem by 0.8 Regular stems at every weight.
- **Letterforms:** Katagami's figures and compact f, and Inter's G with spur (cv10).
- **Joins:** bowl-to-stem notches fill 35 percent of the way.
- **Spacing:** sidebearings 3 units tighter than Inter, space 552 units.

## Katagami Text

Katagami Text is the member for reading. It moves Inter toward PP Mori's proportions and away from Inter's own tells, the tall x-height first. It is the least technical member. The parameters are the `text` profile.

- **x-height:** the lowercase from the baseline to the x-height is scaled by 0.95. Ascenders, dots and accents move down with it and descenders stay, so the x-height is 0.71 of the cap height (Inter 0.75).
- **Size:** every glyph, advance, anchor and kerning value is then scaled by 0.96 about the origin, with the line height unchanged: caps 0.699 em (PP Mori 0.70, Inter 0.728), x-height 0.498 em.
- **Curves:** a slight negative squaring (0.02), so bowls are a touch rounder than Inter's.
- **Widths:** round letters wider (O and Q 1.05, C and G 1.04, o 1.03, e and s 1.025, a 1.03), the narrow capitals opened (E 1.06, F 1.05, L and S 1.03), and the other capitals 3 to 4 percent wider (H 1.04), toward Mori's H of 0.768 em. On top of these, every letter and figure is condensed to 0.97 of its ink width with its stems kept (`condense`), so a line of Text sets about 2 percent narrower.
- **Letterforms:** a plain double-storey a with a straight stem and its arch cut level; Inter's compact f (cv12), its crossbar reaching 0.8 Regular stems past the stem at every weight; a straight l; a t whose stem top is cut at a slant, its left corner 0.45 stems lower than its right; a c whose level terminals move toward each other by a quarter of the gap between them, each edge extended along its own curve (`c_close`); a g whose tail is cut 0.35 of the way from Inter's terminal height to the top of its curl, so it ends higher (`g_rise`); Katagami's long-flag 1; G with a spur (cv10).
- **Terminals:** c, e, s, a and g cut level, as PP Mori cuts them.
- **Weight:** the heavy weights are lighter than Inter's (700 is Inter's 640, 800 its 760), as PP Mori's are.
- **Spacing:** sidebearings 14 units tighter before scaling, so o's sidebearing is about 42 per 1000 (Inter 51, Mori 41); space 512 units before scaling.

## Katagami Serif

Katagami Serif is Katagami Text with rectangular serifs, after Signifier (Kris Sowersby, Klim Type Foundry), and stays close to Text: it keeps Text's outlines and g. Signifier's design notes name rectangular baseline serifs, triangular head serifs and chopped terminals joined by taut curves. Katagami's level cuts already are chopped terminals, so c, a, s, C, G and S keep them with nothing added. The `serif` profile is the `text` profile with the `serif_*` values set. `plan_serifs`, `add_contrast` and `cut_serifs` in `tools/build_sans.py` run after the x-height is lowered. The converter on the website uses it for serif text.

- **Plan:** every serif is found on Regular before any is cut, and the same serifs are added in the same order to Thin, Regular and Black, so the masters stay compatible.
- **Contrast:** every point keeps its x and moves 0.3 of the way from its y to the same point's y in the next lighter master (Regular toward Thin, Black toward Regular), so stems keep Text's width and horizontal strokes get thinner (`serif_contrast`). Moving toward the neighbouring master keeps the joins of diagonals in M, N and K where they were.
- **Where serifs go:** on a straight, flat stroke end at the baseline, the x-height, the cap height or the glyph's own top or bottom. A side takes a serif when the straight segment at that corner is a stroke at least 1.2 stems long and steeper than 45 degrees (`find_stem_ends`). Feet, capital stems and the ends of diagonals take one on each side. The Italic's lowercase takes entry and exit strokes instead (see Italics). An apex or vertex whose two sides spread away from it (the top of A, the bottom of v) takes none. A flat end longer than 2.6 stems is a bar (the bottoms of E and L), and it takes one serif, under its stem.
- **Shape:** a serif runs out along its line 0.65 of the stroke's width past each side at Regular (`serif_reach`), the width measured on the stroke end and at most 1.1 stems (`SERIF_WIDTH_CAP`), so a diagonal's wide cut gets no longer a serif than a stem. It ends square at its full thickness, 0.6 of the master's H crossbar (`serif_depth`) at Regular, 1.65 times that at Thin, so Thin's serifs are as thick as its hairlines, and 0.8 times it at Black, about a third of Black's stem, so Black reads as a bold text face and not a slab (`SERIF_DEPTH_SCALE`). Its back runs flat toward the stroke and meets the stroke's own side in a bracket that covers 0.35 of the reach and climbs 0.45 of the thickness (`BRACKET`), but never more than half of a short side, such as the inside of x, A and K (`BRACKET_SIDE`), where a taller bracket bulged past the stroke. Toward Thin and Black the reach scales with the stem width to the power 0.3 (`SERIF_REACH_POWER`). Every serif is its own contour, overlapping its stroke, and the glyph carries the TrueType overlap flag.
- **Heads:** the top of a lowercase vertical stem takes one triangular serif, on the left: its tip drops 0.35 Regular stems below the line, scaled like the reach (`serif_head`, `HEAD_BY_REACH`), the stem's top left corner moves down onto the same line, and the underside curves into the stem. Measured on each master's own stem, Black's heads had dropped twice as far as Regular's and read as flags.
- **Arms:** the free ends of bars on a metric line (the arms of E, F, L, T and Z, z, and Greek and Cyrillic Γ, Ε, Ζ, Τ, Г, Е and Т) take a vertical serif 0.55 stems long (`serif_beak`) and 0.4 stems wide (`ARM_WIDTH`). Its outer edge is flush with the end, its end is square, and its straight inner edge meets the bar in the same bracket as the other serifs.
- **Counters:** two serifs that face each other on one line (the feet of n, m, h and u) share the space between them and leave at least half a Regular stem of white. A serif cut short keeps its thickness.
- **Widths:** in a sans skeleton the diagonals of v, w, x, y, k, A, V, W, X and Y run to the edges of the advance, so their serifs would reach past the sidebearing by most of their length. Widening them for all of it made v, x and y 22 percent wider than in Text and opened holes beside them. So each letter whose serif tips would come closer than 0.15 Regular stems to the edge of its advance is first narrowed, its stems kept, by 0.75 of the widening it would need (`fit_serifs`, `SERIF_FIT`, measured on Regular and applied to every master). The serifs are then cut and the letter widens by the rest, until its tips are 0.15 stems from the edge (`TIP_CLEAR`). v, x and y end 8 percent wider than in Text, A and V 6 percent, and n, h, o and H keep their widths. Composites move with their base glyphs.

## Alternates and their accented forms

When an alternate becomes the default, its accented forms are swapped with it (aacute with aacute.2, Gbreve with Gbreve.1). The swapped accented forms are composites of the swapped base glyphs, so their components are renamed through the same swap. The default á is then built on the new a, not on Inter's original.

## OpenType features

Katagami Sans, Round and Text compile Inter's own feature files, so every feature Inter documents works: contextual alternates (`calt`, which raises hyphens and arrows between capitals and turns `->` into an arrow), case-sensitive forms (`case`), capital spacing (`cpsp`), slashed zero (`zero`), tabular and proportional figures (`tnum`, `pnum`), fractions, numerators and denominators (`frac`, `numr`, `dnom`), superscripts, subscripts and scientific inferiors (`sups`, `subs`, `sinf`), ordinals (`ordn`), discretionary ligatures (`dlig`), the character variants `cv01` to `cv16` and the stylistic sets `ss01` to `ss08`. Where Katagami made an Inter alternate its default, the feature switches back to Inter's form and its label says so.

Katagami adds small capitals, which Inter does not have (its 13 `.sc` glyphs are phonetic letters):

- **`smcp` and `c2sc`:** 320 small capitals for Latin, Greek and Cyrillic, accented letters included. Each is its capital scaled to the x-height and emboldened back to the lowercase stem (and 0.85 of that on horizontal strokes), then tracked 0.03 em wider. Accented small capitals reuse the lowercase marks, moved by the difference in top anchors.

Katagami Mono keeps every glyph of Katagami Sans, fitted to the cell, so it has the same features, with two exceptions. Capital spacing is left out, and after compiling, the lookups that set two or more characters as one glyph (Inter's `->` arrows) are emptied, so every character stays one cell wide. In their place Katagami Mono has code ligatures as an opt-in `dlig`: `->`, `<-`, `=>`, `!=`, `==`, `===`, `!==`, `>=` and `<=`. Every character keeps its cell; the leading ones become an empty cell and the last one draws the symbol across all of them. Arrows keep their head and stretch the shaft, = and ≠ stretch their bars, and ≤ and ≥ are centred on the run.

## Other scripts

Katagami draws Latin, Greek and Cyrillic. Katagami Sans, Round, Text and Serif also set 28 more scripts with the outlines and OpenType layout of Google's Noto fonts (SIL OFL 1.1), merged in by `tools/build_world.py` the way Pretendard joins Inter and Source Han Sans: Devanagari, Arabic, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam, Sinhala, Thai, Lao, Myanmar, Ethiopic, Hebrew, Armenian, Georgian and Khmer since v0.1, and since v0.2 Tifinagh, Ol Chiki, Coptic, Tibetan, Hanifi Rohingya, N'Ko, Thaana, Vai and Canadian Aboriginal syllabics. The nine came from google/fonts at commit e7db6ca. Tibetan exists only as Noto Serif Tibetan, so Katagami's Tibetan is Noto's serif design in every member.

- Each Noto font is subset to its script's Unicode blocks with its layout closure, so it brings no Latin, digits or punctuation of its own.
- It is instanced at Katagami's master weights (100, 400, 900) and scaled from Noto's 1000-unit em to 2048 times Katagami's x-height over Noto Sans's (536 per 1000), so its letters sit at the member's size.
- Each Katagami master is merged with the scripts at its weight, and the three merged masters are built back into one variable font with the member's weight axis, named instances and line spacing. The Windows clipping box grows to the tallest script.
- Four of the nine come in one weight (Tifinagh, Coptic, N'Ko and Vai in Regular) and two in 400 to 700 (Ol Chiki and Hanifi Rohingya). A master weight Noto does not draw is made from the nearest one it does: every outline is emboldened or thinned by the difference in Noto Sans's stem at the two weights (32, 92, 152 and 192 units per 1000 at 100, 400, 700 and 900, measured on Noto Sans Hebrew's vav) as FreeType emboldens, each point moving along the bisector of its two edges, so the point structure stays and the three masters interpolate. Advances grow by the same amount and the outlines move right by half of it, so sidebearings stay.
- N'Ko, Thaana and Hanifi Rohingya are written right to left, and N'Ko and Hanifi Rohingya join. Their lookups stay under their own script tags (`nko `, `thaa`, `rohg`), so HarfBuzz shapes them in the merged font with the same glyphs, in the same order and direction, as in Noto's own font.
- These glyphs are Noto's design at Katagami's size and weight; they are not redrawn in Katagami's style.

Chinese, Japanese and Korean would pass the 65,535-glyph limit, so they are companion files, Katagami CJK SC, TC, JP and KR (`tools/build_cjk.py`), as Pretendard JP is. Each is Noto Sans SC, TC, JP or KR subset to a national standard (GB 2312's 6,763 hanzi; Big5's 13,053 hanzi with bopomofo; JIS X 0208's 6,355 kanji with the kana; all 11,172 Hangul syllables), scaled to 2048 units and given Katagami's line metrics. The website sets them in the same CSS family as each proportional member with unicode-range. Simplified and Traditional Chinese share most code points; SC is tried first for those, and the TC web file carries only the characters SC lacks.

## Quality checks

`tools/finish.py` runs last on every built file. Fontbakery 1.1.0's Google Fonts profile (`fontbakery check-googlefonts`) was run on v0.1's romans and on v0.2's romans and Italics, each member's two files together.

| Check | v0.1 | v0.2 |
|---|---|---|
| `opentype/font_version`: head and name 5 agree | FAIL: the script merge left Noto's 3.011 in head | PASS |
| `smart_dropout` and `googlefonts/gasp`: what an unhinted font needs | FAIL | PASS: a gasp table that smooths at every size and a prep program with smart dropout control |
| `googlefonts/STAT/axisregistry` | FAIL: no axis values | PASS |
| `name/family_and_style_max_length` | ERROR: the check crashed on the empty STAT | PASS |
| `base_has_width`: U+0488 and U+0489 were zero-width bases | FAIL | PASS: zero-width combining and enclosing marks are GDEF marks |
| `family/win_ascent_and_descent` (Mono) | FAIL: box drawing reached past usWinAscent | PASS |
| Italic linking: `opentype/STAT/ital_axis`, `googlefonts/family/italics_have_roman_counterparts`, `family/vertical_metrics`, `opentype/italic_angle`, `opentype/caret_slope`, `opentype/fsselection`, `opentype/mac_style`, `googlefonts/font_names` | no Italics | PASS for all five members |
| `googlefonts/name/version_format` | FAIL | FAIL: Google Fonts wants 1.000 or more, and Katagami is at 0.200 |
| `case_mapping`, `googlefonts/glyph_coverage`, `googlefonts/glyphsets/shape_languages` | FAIL | FAIL: glyphs Inter does not have, such as capital lambda with stroke (U+A7DC) and 30 more case pairs, and the combining double acute (U+030B), vertical line below (U+0329) and macron below (U+0331) |
| `transformed_components` (proportional romans) | FAIL | FAIL: Inter's flipped and scaled components; decomposing them at compile time would fix it |
| `dotted_circle` (proportional romans) | FAIL | FAIL: the merged complex scripts need a dotted circle, U+25CC, that Inter lacks |

In v0.1 each proportional roman had 1 ERROR, 11 FAIL and 17 WARN, and Mono 1 ERROR, 9 FAIL and 14 WARN. In v0.2 each proportional roman has 6 FAIL (the version format, the three coverage checks, transformed components and the dotted circle) and each Italic 4 (the version format and the coverage checks); Mono and Mono Italic have 4 each. Two of the four proportional runs also report an ERROR in `superfamily/list`, an IndexError inside fontbakery 1.1.0 itself. The WARNs left (28 or 29 per pair) are an unregistered vendor ID (KERF), no `meta` table, the OFL body text, Inter's long glyph names, overlapping segments and interpolation notes in a few glyphs, and alternates no feature reaches.

## Not done yet

- Hand corrections beyond the t, Q and 2. Every other glyph is the output of a transform; none has been redrawn by eye.
- Hinting. The fonts are unhinted, with the gasp and prep tables an unhinted font needs.
- The 28 merged scripts in Katagami's own style. They are Noto's design at Katagami's size and weight; redrawing them is design work for each script.
- The glyphs fontbakery's Google Fonts glyph sets still ask for (see Quality checks).

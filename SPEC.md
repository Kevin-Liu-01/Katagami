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

Two letters are corrected by targeted transforms, in every master of the members they apply to. Each keeps its point count, so the masters stay compatible.

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

- **Source.** The four proportional Italics start from Inter Italic's Thin, Regular and Black masters (`src/Inter-Italic.glyphspackage` at the same pinned commit). Inter Italic slants 9.4 degrees. Where it draws a letter differently from Inter's roman, such as its single-storey a and its f with a descender, Katagami does not follow it (see The roman's design).
- **Upright, then slanted.** Every transform assumes upright stems, so each Italic master is first stood upright: every point moves by x - (y - 559) tan 9.4, about half of Inter's x-height, the pivot Inter slants around. The member's transforms then run as they do on the roman, and the result is slanted again about the member's own half x-height. Squaring, level cuts, the tails, widths, the corrections and the serifs are the roman's, at the italic angle. A shear is affine, so handle fractions and the squaring planned from them do not change. Composites with flipped or scaled components are decomposed first, because a shear would turn their matrices into skews, and so are the ones built after the Italic was stood upright (Ɐ, ⅎ, the circled lowercase) before it is slanted again.
- **The roman's design.** Each Italic glyph is its roman glyph's design, slanted: the Italic adds no letterform and drops none of the member's own choices (the compact f and its crossbar, the figures, the g, the Q tail, the 2, the t). Once the member's transforms have run and the Italic is still upright, every glyph is compared with the roman's glyph of the same name in every master. The filled shapes, overlaps removed, must have the same number of contours, and no point of either outline may lie more than 64 units (about 3 percent of the em) from the other, with their ink centred (`design_distances`, `ITALIC_MATCH`). A glyph that passes keeps Inter Italic's drawing, with Inter's optical corrections to its curves. Every other glyph, and every glyph Inter Italic lacks (the alternates of cv11 and cv16), takes the roman's outline, anchors and advance and is slanted with the rest (`romanize`). Where a composite and one of its parts come from different fonts, the part moves by the difference between the two drawings' ink centres, so a roman á over Inter Italic's acute, which Inter draws 128 units further left of its origin, keeps the roman's accent position. The Italic also takes the roman's glyph set and order, features, feature labels, kerning and kerning groups, so every default and every alternate is the roman's. Inter's Italic keeps its vertical stems as wide as the roman's, so the slant needs no weight compensation. The glyphs that take the roman's drawing, each with the accented forms, small capitals, superiors and enclosed forms built on it: Katagami Sans, 477 glyphs from 188 bases: K Z a d e f m n q Æ Ø æ Ł œ Ɓ Ɔ Ɛ Ƒ Ɠ ƛ Ɲ Ơ Ƥ Ʀ Ʈ ǖ ǘ ǚ ǜ Ǫ ǫ Ǯ Ǳ Ț Ȼ Ⱦ ɇ Ɋ ɓ ɚ ɝ ɭ ɶ ʀ ʏ ʣ ʤ ˢ ϴ Ю є Ҋ ҽ Ӈ Ӱ ᵃ ᵉ ᶠ Ḑ ṻ ἃ Ἂ Ἃ ἓ Ἒ Ἓ ἣ Ἢ Ἣ ἳ Ἲ Ἳ ὃ Ὂ Ὃ ὓ Ὓ ὣ ᾃ ᾊ ᾋ ᾓ ᾚ ᾛ ᾣ Ὰ Ὲ Ὴ ῒ Ὶ ῢ Ὺ Ὸ Ὼ # ᷢ ῭ ‽ ⁑ ₡ ₧ ⅍ ≠ ⊕ ⎀ Ⓓ Ⓚ Ⓜ Ⓠ Ⓦ Ⓩ, and the alternates `a.1.sups`, `a.2`, `a.2.sups`, `ogonek.a.2`; Katagami Round, 434 glyphs from 143 bases: G K Z a d e f m n q Æ Ø æ Ł œ Ɓ Ɗ Ɛ ƕ ƛ ơ Ƥ ƥ Ʈ Ǫ Ǯ Ǳ Ȼ Ⱦ ɇ ɓ ɚ ɝ ɶ ʀ ʏ ʚ ʣ ʤ ˢ Ҋ ҽ Ӈ ᵃ ᵉ ᶠ ἃ Ἂ Ἃ ἓ Ἒ Ἓ ἣ Ἢ Ἣ Ἲ Ἳ ὃ ὓ Ὓ ὣ ᾃ ᾊ ᾋ ᾓ ᾚ ᾛ ᾣ Ὰ Ὲ Ὴ Ὶ Ὺ Ὸ Ὼ # ᷢ ‽ ⁑ ₡ ₧ ₲ ⅍ ≠ ⊕ ⎀ Ⓓ Ⓖ Ⓚ Ⓠ Ⓩ, and the alternates `a.1.sups`, `a.2`, `a.2.sups`, `ogonek.a.2`; Katagami Text, 375 glyphs from 108 bases: G K a d e f m n q Æ æ Ł œ Ɓ ƛ ơ Ƥ ƥ Ǯ Ⱦ ɇ ɓ ɚ ɝ ɰ ɶ ɻ ʀ ʇ ʎ ʣ ʤ ˢ ͻ ͽ Ҋ ҽ ӭ ᵃ ᵉ ᶠ Ὰ Ὲ Ὴ Ὺ Ὸ # ᷢ ‽ ⁑ ₡ ₧ ₲ ⅍ ≠ ⊕ ⎀ Ⓓ Ⓖ Ⓚ Ⓠ, and the alternates `a.1.sups`, `a.2`, `a.2.sups`, `ogonek.a.2`; Katagami Serif, 448 glyphs from 171 bases: G a d e f m n q Æ æ Ł œ Ɓ ƍ Ǝ ƒ ƛ ơ ƣ Ʈ ƽ Ǯ Ⱦ ɇ ɓ ɚ ɝ ɥ ɶ ɸ ɹ ʀ ʇ ʋ ʎ ʏ ʔ ʕ ʖ ʞ ʡ ʣ ʤ ʧ ʵ ˀ ˁ ˢ ͻ ͽ Ш п Ѯ Ҋ ҧ ҽ ӭ ᵃ ᵉ ᵏ ᶠ Ằ Ἐ Ἒ Ἓ Ἔ Ἠ Ἢ Ἣ Ἤ Ἦ Ἰ Ἲ Ἳ Ἴ Ἶ Ὓ Ὗ ᾘ ᾚ ᾛ ᾜ ᾞ Ὰ Ὲ Ὴ Ὶ Ὺ Ὸ Ⅎ Ⅲ # ᷢ ‽ ⁑ ₡ ₧ ₲ ℟ ⅍ ≠ ⊕ ⎀ Ⓓ Ⓖ Ⓜ Ⓝ Ⓠ, and the alternates `a.1.sups`, `a.2`, `a.2.sups`, `brevegravecomb.cn`, `ogonek.a.2`; Katagami Mono, on top of Katagami Sans Italic's, 71 glyphs from 59 bases: µ Ø Ƒ Ɲ ƭ Ʈ Ǫ ǫ Ⱥ Ȼ Ɋ ʠ ϴ Ю Ӈ ṱ Ἂ Ἃ Ἄ Ἅ Ἆ Ἒ Ἓ Ἣ Ἧ Ὂ Ὃ Ὓ ὢ ὣ Ὣ Ὧ ᾊ ᾋ ᾚ ᾛ ᾝ ᾢ ᾣ ᾪ ᾫ ᾮ Ὸ ⅶ ₡ ℃ Ⓚ Ⓝ Ⓠ ♪ ♫.
- **Katagami Mono Italic** stands Katagami Sans Italic upright the same way, fits it to the cell as the roman, compares it with the roman fitted the same way and gives every glyph that differs the roman's drawing, as above, then slants it again. Box drawing, block elements, Braille and the agent symbols are drawn after the slant, upright, so their lines still join from cell to cell.
- **Katagami Serif Italic.** The serifs and terminal facets are cut in the upright frame, where the roman's are, and slanted with the letter, so their ends follow the italic angle and their backs stay level. Every serif and every facet sits where the roman's does.
- **Names and linking.** Name 1 is the family (Katagami Sans), name 2 Regular or Italic, and the named instances run Thin Italic to Black Italic. The STAT table of each file has a weight axis value for every named weight (Regular elidable and linked to Bold) and an `ital` axis: 0, Roman, elidable and linked to 1, in the roman; 1, Italic, in the Italic. Inter Italic has no slant axis, so Katagami has none. fsSelection sets ITALIC, macStyle its italic bit, post.italicAngle is -9.4 and the caret slopes with it. The Italic takes the roman's hhea, typo and Windows metrics, so both set the same line height. `tools/finish.py` writes all of this.
- **Other scripts.** The Italics carry Latin, Greek and Cyrillic, the same 3,725 glyphs as their roman before the scripts are merged into it (Mono Italic 4,123, as Mono), and no merged scripts. Italic Arabic, Devanagari or Thai is not a convention, and copying the 28 merged scripts into each Italic would double the download. For italic text in another script, a web stylesheet declares the roman's script files a second time with `font-style: italic`, so the browser sets it with the roman's letters instead of falling back to another family or slanting them.

## Katagami Mono

### Fitting glyphs to the cell

Every outline is fitted to the 1280-unit cell. Each decision is made on the Regular master and used for all masters.

- **Even widths.** A monospace reads evenly when its letters fill the cell evenly. Letters move toward a target ink width, keeping a quarter of their own width so the alphabet does not turn uniform: lowercase 0.69 of the cell, round lowercase (o c e b d p q g a s) 0.74, capitals 0.74, round capitals 0.79, figures 0.72. Stems are held at their true thickness.
- **Wide letters fill the cell.** m 0.84, w 0.94, M 0.82, W 0.94, æ œ Æ Œ 0.88. Where they still condense, the stems keep only part of their weight (down to 45 percent at a scale of 0.55), which is how a monospace m finds room for its counters. The weight put back never closes a counter. Fitting can condense a glyph up to five times, and every pass keeps each counter at least a fifth of its area before fitting, scaled, so the zeros of ‰ and ‱ and the counters of ₯, ⅒, ⑧ and the circled letters stay open at Bold.
- **Arms, around a fixed stem.** f, t, r, dotless j and J keep their stem and stretch only what lies to its left and right, so arms and crossbars reach into the cell: f 0.70, t 0.68, r 0.58, dotless j 0.54, J 0.64.
- **Narrow by identity.** i, l, I and 1 keep their own width; their flags and slabs fill the cell.
- Glyphs built from parts, such as the colon or t, are decomposed first and fitted as one outline. Accented letters keep their components and marks follow their base. ď, ľ, ť and Ľ, whose caron is Inter's comma-like alternate with an advance of its own, are fitted whole and then set again from their fitted letter and fitted caron as two components, so a reader of the font can tell the caron is not an apostrophe.

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
| Glyphs | 15,211 in Sans and Round and 15,212 in Text and Serif, of which about 3,725 are drawn by Katagami | 3,725 | 4,123 each, all fitted to the cell |
| Characters | 8,346 | 2,947 | 3,378 each |
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

Katagami Serif is Katagami Text with rectangular serifs, after Signifier (Kris Sowersby, Klim Type Foundry), and stays close to Text: it keeps Text's outlines and g. Signifier's design notes name rectangular baseline serifs, triangular head serifs and chopped terminals joined by taut curves. Katagami's curved strokes keep Text's level cuts, and each cut takes a small square facet at its outer corner, so the curved strokes read as cut in the same system as the stems. The `serif` profile is the `text` profile with the `serif_*` values set. `plan_serifs`, `plan_terminals`, `add_contrast`, `cut_terminals` and `cut_serifs` in `tools/build_sans.py` run after the x-height is lowered. The converter on the website uses it for serif text.

- **Plan:** every serif is found on Regular before any is cut, and the same serifs are added in the same order to Thin, Regular and Black, so the masters stay compatible.
- **Contrast:** every point keeps its x and moves part of the way from its y to the same point's y in the next lighter master, 0.6 of the way at Regular (toward Thin) and 0.3 at Black (toward Regular), so stems keep Text's width and horizontal strokes get thinner (`serif_contrast`). At Regular the thin side of o is 0.48 of its stem, against 0.84 in Text and 0.46 in Charter. Moving toward the neighbouring master keeps the joins of diagonals in M, N and K where they were. A dot moves with its centre and keeps its shape (`_dots`), so the dots of i, j, ! and ? and the periods stay round. Moved point by point, they had become ovals.
- **Where serifs go:** on a straight, flat stroke end at the baseline, the x-height, the cap height or the glyph's own top or bottom. A side takes a serif when the straight segment at that corner is a stroke at least 1.2 stems long and steeper than 45 degrees (`find_stem_ends`). Feet, capital stems and the ends of diagonals take one on each side. The stems f and t are drawn from take them as letters do, so the f stands on a foot serif. An apex or vertex whose two sides spread away from it (the top of A, the bottom of v) takes none. A flat end longer than 2.6 stems is a bar (the bottoms of E and L), and it takes one serif, under its stem.
- **Shape:** a serif runs out along its line 0.85 of the stroke's width past each side at Regular (`serif_reach`), which on a stem is the reach of Times, against 0.79 stems in Georgia and 0.91 in Charter, the width measured on the stroke end and at most 1.1 stems (`SERIF_WIDTH_CAP`), so a diagonal's wide cut gets no longer a serif than a stem. It ends square at its full thickness, 0.8 of the master's H crossbar (`serif_depth`) at Regular, 1.24 times that at Thin, so Thin's serifs are as thick as its hairlines, and 0.6 times it at Black, about a third of Black's stem, so Black reads as a bold text face and not a slab (`SERIF_DEPTH_SCALE`). Its back runs flat toward the stroke and meets the stroke's own side in a bracket that covers 0.35 of the reach and climbs 0.45 of the thickness (`BRACKET`), but never more than half of a short side, such as the inside of x, A and K (`BRACKET_SIDE`), where a taller bracket bulged past the stroke. Toward Thin the reach scales with the stem width to the power 0.3, and Black keeps 0.85 of its own stroke width (`SERIF_REACH_POWER`). Every serif is its own contour, overlapping its stroke, and the glyph carries the TrueType overlap flag.
- **Heads:** the top of a lowercase vertical stem takes one triangular serif, on the left: its tip drops 0.35 Regular stems below the line, scaled like the reach (`serif_head`, `HEAD_BY_REACH`), the stem's top left corner moves down onto the same line, and the underside curves into the stem. Measured on each master's own stem, Black's heads had dropped twice as far as Regular's and read as flags.
- **Arms:** the free ends of bars on a metric line (the arms of E, F, L, T and Z, z, and Greek and Cyrillic Γ, Ε, Ζ, Τ, Г, Е and Т) take a vertical serif 0.55 stems long (`serif_beak`) and 0.4 stems wide (`ARM_WIDTH`). Its outer edge is flush with the end, its end is square, and its straight inner edge meets the bar in the same bracket as the other serifs.
- **Terminals:** the ends of curved strokes, hooks and tails that the stem serifs leave bare keep Text's cut and take a small facet at its outer corner (`plan_terminals`, `cut_terminals`, `_facet`): the tops of a, 2, 3, 6 and ?, the hook of f and the feet of g, 3, 5 and 9, with their Greek, Cyrillic and IPA kin and the small capitals, which take their own facets on their own curves. A stroke end is a straight cut 0.45 to 1.6 stems long, with ink on one side and none on the other. The curve stays Text's up to the cut: the stroke's outer edge is trimmed where it stands 0.45 of the cut's length from the cut's line (`FACET`, about a stem serif's thickness at Regular and Black), split by de Casteljau so it stays a piece of its own curve, and the outer corner becomes a short straight face square to the cut. No other point moves and nothing is stretched. The facet's foot is a new point on the cut, the same in every master, so the facets are cut after the stem serifs, whose plan holds point numbers. A terminal takes a facet only where every master can cut it. The arm of r, the tails of j and y and the flag of 1 keep Text's cut without a facet: an edge there is not a single curve. These ends stay plain cuts too: the rising exits at the foot of c, C, e, ε and є and the hook of t, as in a text face; both ends of C, S, c, s and G, so each top matches the plain foot of C and c, with the letters and signs drawn the same way (С, Ѕ, Є, Э, Ϲ, є, ɢ, ʗ, $, ¢, €), the reversed C (Ↄ, ↄ, ɔ) and the letters built on them (`PLAIN_ENDS`); the hook of J; cuts that the level cuts leave more than 6 degrees from level (Inter's a.2, £, §); bars (the crossbars of f and t, the foot of 2); stubs in the middle third of a letter (the waist of 3); strokes lying on the baseline, x-height or cap height; and ends that would point out of the letter (the arms of ω). Q's tail is a straight stroke and keeps its foot serif and its cut, and ! keeps its plain tapered stroke. In v0.2 every such end took an upright tab hanging under the level cut, which read as teeth. Barbs, level slabs, small spurs and upright faces stretched to the stroke's old extreme were tried next and set aside: the stretch bent Text's curve.
- **Counters:** two serifs that face each other on one line (the feet of n, m, h and u) share the space between them and leave at least half a Regular stem of white. A serif that reaches less than a quarter Regular stem into other ink on its line stops a quarter stem short of it (`SERIF_CLEAR`), so the foot of ß clears its terminal and the arm of Black k clears the stem. A serif that runs deeper joins the stroke. A serif cut short keeps its thickness.
- **Widths:** in a sans skeleton the diagonals of v, w, x, y, k, A, V, W, X and Y run to the edges of the advance, so their serifs would reach past the sidebearing by most of their length. Widening them for all of it made v, x and y 22 percent wider than in Text and opened holes beside them. So each letter whose serif tips would come closer than 0.23 Regular stems to the edge of its advance is first narrowed, its stems kept, by 0.75 of the widening it would need (`fit_serifs`, `SERIF_FIT`, measured on Regular and applied to every master). The serifs are then cut and the letter widens by the rest, until its tips are 0.23 stems from the edge (`TIP_CLEAR`). At Regular v and y end 12 percent wider than in Text, x 13 percent, A and V 9 percent, n and h 2 percent and H 1 percent, and o keeps its width. Composites move with their base glyphs.

## Alternates and their accented forms

When an alternate becomes the default, its accented forms are swapped with it (aacute with aacute.2, Gbreve with Gbreve.1). The swapped accented forms are composites of the swapped base glyphs, so their components are renamed through the same swap. The default á is then built on the new a, not on Inter's original.

## OpenType features

Katagami Sans, Round and Text compile Inter's own feature files, so every feature Inter documents works: contextual alternates (`calt`, which raises hyphens and arrows between capitals and turns `->` into an arrow), case-sensitive forms (`case`), capital spacing (`cpsp`), slashed zero (`zero`), tabular and proportional figures (`tnum`, `pnum`), fractions, numerators and denominators (`frac`, `numr`, `dnom`), superscripts, subscripts and scientific inferiors (`sups`, `subs`, `sinf`), ordinals (`ordn`), discretionary ligatures (`dlig`), the character variants `cv01` to `cv16` and the stylistic sets `ss01` to `ss08`. Where Katagami made an Inter alternate its default, the feature switches back to Inter's form and its label says so.

Katagami adds small capitals, which Inter does not have (its 13 `.sc` glyphs are phonetic letters):

- **`smcp` and `c2sc`:** 620 small capitals for Latin, Greek and Cyrillic, accented letters included. Each is its capital scaled to the x-height and emboldened back to the lowercase stem (and 0.4 of that on horizontal strokes, so Black's bars leave the counters of E and S open), then tracked 0.03 em wider. An accented letter, such as ấ (a with one mark for the circumflex and acute) or ἀ (α with a psili), sets the lowercase's own marks on the small capital of its capital's base, each moved by the difference in the anchor it attaches to, so stacked accents keep the lowercase's spacing at every weight. ӱ is ÿ in Inter, and its small capital is У's with ÿ's dieresis. The ogonek is the capital's, scaled with the letter, because the lowercase's is shaped to its letter: ę's hangs from the end of the bowl. A capital set from two capitals (Ĳ, Ǆ, Ǉ, Ǌ, Ы) is set from their small capitals at the same spacing, so the parts keep the white between them. э and є are emboldened across only, because thicker bars would close their openings at Black. Every other letter is drawn from its capital's outline with the components drawn in: ø, ł, ď and œ, ư with its horn, ɉ and ʝ, and the Greek and Cyrillic letters whose capital Inter builds from another letter (Α from A, И from N mirrored). A bar, dot, tail or stroke emboldened with its capital closes the small capital's counters at Black, so some small capitals are set from parts (`SMALL_CAP_PARTS`). ƀ, ǥ, ⱥ and ҹ are B, G, A and Ч with the capital's bar or stroke, scaled and placed as the capital's outline is. ⱥ's and ҹ's strokes keep the capital's thickness, ǥ's bar keeps its size so it reaches past the jaw, and each keeps 0.3 stem of white to the walls it would touch: ƀ's bar ends at the stem where B's lower counter has no room for it. ŀ, ѿ and ҋ are L, Ѡ and Й with the lowercase's own dot, т and tail, and ѹ is О followed by the lowercase у, as Ѹ is О and у. ʘ and ͽ are O and Ͻ with their dot, which shrinks to under half of the closed white it sits in. ǰ and ẖ, which have no capital, are J and H with the lowercase's caron and line. ʕ, which is drawn at the cap height and has no capital, is drawn from itself, and ɤ is ɤ tracked, because Ɤ is ɤ with its arms drawn up. ỻ is set from two small capital L's, as Ĳ is. At Black, ẞ, Ω, A, ɐ, Ч, ỿ, ʝ and ʕ are drawn 8 to 14 percent wider and emboldened less, so ß's channel, ω's legs, A's triangle and the loops stay open (`SMALL_CAP_OPEN`). In Katagami Serif a small capital is scaled and emboldened after its capital's serifs are cut, so two serifs that face each other on one line can end a hairline apart. Where they stand less than 0.1 stem apart in a master they take Regular's arrangement there: serifs joined at Regular overlap, and serifs apart at Regular are cut back toward half a stem of white, no further than their brackets (`settle_facing_serifs`). A's feet keep their white at Black and ω's base stays joined. The accents of ữ and the other horned letters move left by up to 48 units, then up, until they clear the horn by as much as the lowercase's do. ß takes ẞ, because its capital is SS. In Turkish and Azerbaijani, `smcp` keeps the dot on the small capital of i, and `c2sc` sets İ the same way.

Katagami Mono keeps every glyph of Katagami Sans, fitted to the cell, so it has the same features, with two exceptions. Capital spacing is left out, and after compiling, the lookups that set two or more characters as one glyph (Inter's `->` arrows) are emptied, so every character stays one cell wide. In their place Katagami Mono has code ligatures as an opt-in `dlig`: `->`, `<-`, `=>`, `!=`, `==`, `===`, `!==`, `>=` and `<=`. Every character keeps its cell; the leading ones become an empty cell and the last one draws the symbol across all of them. Arrows keep their head and stretch the shaft, = and ≠ stretch their bars, and ≤ and ≥ are centred on the run.

## Characters Inter does not have

Inter has no glyph for 93 characters that fontbakery's Google Fonts case and language checks ask for. `tools/kerf_build/missing.py` builds them on Inter's masters before any transform, from Inter's own parts, so every member draws them in its own style. Each master is built by the same rule from its own parts, which have the same points in every master, so the masters stay compatible. Bars, ticks and flags are drawn at the thickness of Inter's own crossbars.

- **Case pairs:** Ǆ is D and Ž, as Inter sets ǅ. ⱥ and ⱦ take ø's stroke. Ɥ is u with its stems drawn up to the cap height, and Ɤ is ɤ with its arms drawn up. Ɦ is H whose left stem ends in ɦ's hook, Ɬ is L under ɬ's belt, Ʝ is ʝ's crossed tail under the stem of l, Ɪ is cv08's I with serifs, and Ƛ is Λ with ƛ's bar across its right leg. ͷ and ϻ are и and м, because Inter sets Ͷ as И and Ϻ as M. Ԯ is Л with ԯ's descender. ⅎ is the small capital F turned over, as Ⅎ is F turned.
- **Africanist and phonetic letters:** ɽ and Ɽ are r and R with Inter's retroflex tail. ᵽ has a bar through its stem and bowl at half the x-height, and Ᵽ a short bar across its stem only. Ꟈ and ꟈ have a short bar across the stem, at the middle of D and at the height of đ's bar. Ⱳ and ⱳ end their last stroke in a flag. Ɑ and Ꞷ are ɑ and ω drawn at the cap height the way the small capitals are drawn, and ꞷ is ω. The saltillos Ꞌ and ꞌ are Inter's straight quote drawn longer, ꞉ is the colon and ꞊ is the equals sign at 0.55 of its width.
- **Modifier letters:** ᵋ and ᵓ are ɛ and ɔ at the superscripts' size and stem, on ᵉ's line. ᶤ and ᶶ are ⁱ and ᵘ with a bar as thick as the superscript minus.
- **Church Slavonic:** Ѻ and ѻ are O and o with a stem-wide tick through the top and the bottom. Ѽ and ѽ are Ѡ and ѡ under the combining titlo, and Ѿ and ѿ under a small т, a bar with three legs half the letter wide. Ꙍ and ꙍ are Ѡ and ѡ with the middle stem starting 0.43 of the way down. Ꙁ and ꙁ are Ȥ and ȥ, and Ꙃ and ꙃ add Ƶ's and ƶ's bar. Ꙋ is Ȣ, and ꙋ is ȣ moved down so its loop descends. Ꙗ and ꙗ join І and A, and ı and a, with Ѥ's and ѥ's bar.
- **Auxiliary letters and controls:** ꞵ is β, and Ꞵ is β with its stem cut at the baseline, because β's bowls close on the baseline and its top is at the capital height. Ɐ is A turned, as ɐ is a turned. ⓐ to ⓩ are the lowercase in the circle Ⓐ to Ⓩ are set in, at 0.92 of their height, centred across the circle and on one baseline that puts the x-height in its middle. The zero-width non-joiner and joiner and the left-to-right and right-to-left marks (U+200C to U+200F) are empty and have no advance.
- **Combining marks:** the macron, tilde, circumflex, breve, diaeresis, ring and inverted breve below (U+0331, U+0330, U+032D, U+032E, U+0324, U+0325, U+032F) are Inter's marks above moved under the baseline, their tops as deep as Inter's dot below. The inverted breve above (U+0311) is the breve turned over. The vertical lines above and below (U+030D, U+0329) are Inter's linevert as a mark, above as far from the letter as the acute. The combining low line (U+0332) is the underscore under the letter before it.

The marks need anchors to sit on these letters. A letter without a top or bottom anchor takes one at its ink's centre, on the cap height or x-height above and on the baseline or its descender below. A letter on the baseline without a cedilla anchor takes one at its bottom anchor, and one without an ogonek anchor takes one a fifth of its ink's width in from the right, so a̧, i̧, ɛ̧ and ɛ̨ are set. A combining mark without an attaching anchor takes one at its ink's centre. On the default master, a base anchor where a mark would sit without moving (U+1DC7 on ɛ in Round Italic) moves 1 unit right, because a shaper's zero offset reads as a mark that never attached. The anchors are planned on Regular and placed in every master from its own ink, after the alternates are swapped in, because a swap carries each alternate's own anchors into the default.

Inter declares language systems for Latin and the default script only, and its kerning adds Cyrillic and Greek script records that hold nothing else, so a shaper found no `ccmp`, `mark` or `mkmk` for those scripts and set an accent after а or α beside the letter instead of on it. Katagami declares both scripts, so every feature applies to them. Inter's soft-dotted rule, which sets dotless i before an accent above, now sees the accents Katagami adds and the three and four dots above (U+20DB, U+20DC), and skips the marks below between them, so í̧, і́ and i⃛ lose their dot too. The three and four dots are redrawn as the dieresis's dots at the dieresis's spacing; Inter set them a period's width apart. Inter's square-punctuation alternate of the combining dot below (U+0323) has an advance, so that mark keeps its zero advance when the alternate is promoted.

## Other scripts

Katagami draws Latin, Greek and Cyrillic. Katagami Sans, Round, Text and Serif also set 28 more scripts with the outlines and OpenType layout of Google's Noto fonts (SIL OFL 1.1), merged in by `tools/build_world.py` the way Pretendard joins Inter and Source Han Sans: Devanagari, Arabic, Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada, Malayalam, Sinhala, Thai, Lao, Myanmar, Ethiopic, Hebrew, Armenian, Georgian and Khmer since v0.1, and since v0.2 Tifinagh, Ol Chiki, Coptic, Tibetan, Hanifi Rohingya, N'Ko, Thaana, Vai and Canadian Aboriginal syllabics. The nine came from google/fonts at commit e7db6ca. Tibetan exists only as Noto Serif Tibetan, so Katagami's Tibetan is Noto's serif design in every member.

- Each Noto font is subset to its script's Unicode blocks with its layout closure, so it brings no Latin, digits or punctuation of its own.
- It is instanced at Katagami's master weights (100, 400, 900) and scaled from Noto's 1000-unit em to 2048 times Katagami's x-height over Noto Sans's (536 per 1000), so its letters sit at the member's size.
- Each Katagami master is merged with the scripts at its weight, and the three merged masters are built back into one variable font with the member's weight axis, named instances and line spacing. The Windows clipping box grows to the tallest script.
- Four of the nine come in one weight (Tifinagh, Coptic, N'Ko and Vai in Regular) and two in 400 to 700 (Ol Chiki and Hanifi Rohingya). A master weight Noto does not draw is made from the nearest one it does: every outline is emboldened or thinned by the difference in Noto Sans's stem at the two weights (32, 92, 152 and 192 units per 1000 at 100, 400, 700 and 900, measured on Noto Sans Hebrew's vav) as FreeType emboldens, each point moving along the bisector of its two edges, so the point structure stays and the three masters interpolate. Advances grow by the same amount and the outlines move right by half of it, so sidebearings stay. On a contour the move shrinks (a counter when emboldening, an outer contour when thinning) each point moves at most 0.4 of the room ahead of it, measured to the contour's own far side, so a tapered stroke end keeps a fifth of its width while the rest of the stroke thins the whole way. The contour then moves only as far as it stays inside itself with its direction, a fifth of its area and no lobe wound against it (`kerf_build.outline.sound`). A Noto contour that runs over itself the same way round is not such a lobe. At Thin the synthesized scripts keep about 0.28 of their Regular ink, as Latin does, and the small counters of Vai, Coptic, Tifinagh, N'Ko and Ol Chiki stay open at Black. Coptic U+102F8's counter is a triangle that would otherwise pass through its own centre and come out turned half round.
- N'Ko, Thaana and Hanifi Rohingya are written right to left, and N'Ko and Hanifi Rohingya join. Their lookups stay under their own script tags (`nko `, `thaa`, `rohg`), so HarfBuzz shapes them in the merged font with the same glyphs, in the same order and direction, as in Noto's own font.
- These glyphs are Noto's design at Katagami's size and weight; they are not redrawn in Katagami's style.

Chinese, Japanese and Korean would pass the 65,535-glyph limit, so they are companion files, Katagami CJK SC, TC, JP and KR (`tools/build_cjk.py`), as Pretendard JP is. Each is Noto Sans SC, TC, JP or KR subset to a national standard (GB 2312's 6,763 hanzi; Big5's 13,053 hanzi with bopomofo; JIS X 0208's 6,355 kanji with the kana; all 11,172 Hangul syllables) with the space and no-break space. Each file replaces Noto's Latin with Katagami Sans's: Google Fonts' Latin core, the auxiliary letters of its languages and the dotted circle, with Sans's kerning, marks, composition, language forms and contextual punctuation. That Latin is rebuilt on the CJK file's weight axis, so it sets as Katagami Sans does at every weight. The Latin is merged at Katagami's 2048-unit em, and each file is saved at Noto's 1000-unit em, because at 2048 the TC file is over Google Fonts' 9 MiB limit. The hhea and win metrics hold Katagami's line (1984 and -494 on 2048), so apps space CJK lines as Katagami's, and the typo metrics follow Google's CJK rule (0.88 and -0.12 em, no gap, USE_TYPO_METRICS off). As in Noto's variable fonts, the default instance is Thin, and the names say so. The website sets them in the same CSS family as each proportional member with unicode-range and serves only their CJK characters, so Latin, Greek and Cyrillic come from the member. Simplified and Traditional Chinese share most code points; SC is tried first for those, and the TC web file carries only the characters SC lacks.

## Dotted circle

Every file has U+25CC DOTTED CIRCLE. Shaping engines set it under a mark that has nothing to sit on, such as a Devanagari vowel sign typed on its own, and fontbakery asks for it in fonts that set scripts with complex shaping. It is ten round dots on a ring whose outside is as tall as the x-height, centred on half the x-height and spaced as o is, with a dot at the top (`fontops.draw_dotted_circle`). A dot is 0.7 of the Regular stem across at Regular and grows with each master's stem to the power 0.5, so Thin's dots are light and Black's keep white between them. It is drawn after every transform, so no squaring, contrast or serif reaches it. Katagami Mono draws it again on the cell after fitting, 0.76 of the 1280-unit cell across and centred in it, so its dots stay round. The Italics take the roman's, slanted.

The circle has o's anchors, moved across with the ring, so Latin, Greek and Cyrillic marks sit on it as they sit on o. The ogonek anchor comes from a instead: Inter's o has it halfway up its side, for the ogonek.o that ǫ is built with. An anchor neither has takes the same place in the ring's box as in the first letter that has it. In the merged scripts the circle joins every mark-to-base lookup (`build_world.seat_dotted_circle`). Each mark sits where Noto seats it on Noto's own dotted circle, about the circle's centre and scaled from Noto's ring to Katagami's, so a vowel sign above clears the larger ring. Noto often seats its marks on its circle in lookups of their own (Devanagari's vowel signs through `mark`, on letters through `abvm`), so each mark's place is read wherever Noto's circle is its base and given back in the lookups Katagami keeps. Noto's circles are read from a second subset of each script that keeps them, and they are not merged, so the scripts' own layout is unchanged. Georgian, Ol Chiki and Vai, which Noto draws no circle for, place it by their first base's anchors.

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
| `googlefonts/glyph_coverage` | FAIL | PASS: the combining double acute (U+030B), the one character of Google Fonts' Latin core Inter has no glyph for, is Inter's own double acute set as a mark (`fontops.combining_double_acute`) |
| `case_mapping`, `googlefonts/glyphsets/shape_languages` | FAIL | PASS and WARN: the 60 characters Inter does not have are built (see Characters Inter does not have), accents attach to Cyrillic and Greek letters, and 601 letters have small capitals. The WARN lists letters with no small capital (ǰ, ɐ, ʕ, ʘ and ẖ have no single capital, and ten are skipped) and the joiner controls U+200C, U+200D and U+200F that Arabic asks for |
| `soft_dotted` | WARN | WARN: i, j and the superior and inferior ⁱ ʲ ᵢ ⱼ ᶤ lose their dot under every accent above. The check's examples put U+20DD or U+20DE, enclosing marks of combining class 0, between the letter and the accent, and under Unicode's rule a class 0 mark keeps the dot |
| `googlefonts/vendor_id` | WARN: KERF is not registered | WARN: the vendor ID is KATA. Its registration with Microsoft was requested on 30 October 2026, and the WARN clears when Microsoft lists it |
| `googlefonts/meta/script_lang_tags` | WARN: no `meta` table | PASS: the `meta` table names Latin, Greek and Cyrillic as designed for and every script with 10 or more characters as supported |
| `unreachable_glyphs`, `ots` | WARN | PASS: `finish.py` drops the glyphs no character or feature reaches (101 in each proportional roman, 12 in each proportional Italic and 63 in each Mono file) and sorts the scripts, languages and features |
| `math_signs_width` (Italics) | WARN | PASS: the Italic ≠ takes the advance of = |
| `transformed_components` (proportional romans) | FAIL | PASS: none of the 176 glyphs built from flipped or turned components (Inter's d from b, q from p, И from N) keeps one. `finish.py` draws 82 of them in from the compiled components, point for point and delta for delta, and the other 94 point at a drawn-in glyph instead (ď at d), so every outline is unchanged at every weight |
| `dotted_circle` | FAIL (proportional romans) | PASS: every file has a dotted circle every mark attaches to (see Dotted circle) |

In v0.1 each proportional roman had 1 ERROR, 11 FAIL and 17 WARN, and Mono 1 ERROR, 9 FAIL and 14 WARN. In v0.2 each proportional roman has 6 FAIL (the version format, the three coverage checks, transformed components and the dotted circle) and each Italic 4 (the version format and the coverage checks); Mono and Mono Italic have 4 each. Two of the four proportional runs also report an ERROR in `superfamily/list`, an IndexError inside fontbakery 1.1.0 itself. The WARNs left (28 to 30 per pair) are an unregistered vendor ID (KERF), no `meta` table, the OFL body text, Inter's long glyph names, overlapping segments and interpolation notes in a few glyphs, and alternates no feature reaches. The four proportional Italics add one more, `math_signs_width`: their ≠ takes the roman's advance, 1 unit narrower than Inter Italic's other math signs. After the t, the roman's-design Italics and Serif's beaks the counts are the same: 10 FAIL for each proportional pair and 8 for Mono's. Drawing in the turned components, the dotted circle and the combining double acute then leave every file with 3 FAIL, the version format, `case_mapping` and `shape_languages`: 6 for each pair, Mono's included. Nothing new appears; the romans lose the `outline_direction` WARN (a flipped component's contours ran the wrong way) and the Italics and Mono the `dotted_circle` WARN. A glyph whose only component is turned (d, a turned b) is drawn in, and a glyph that sets such a part beside others (ď, ḋ, Й) keeps its components and points at the drawn-in glyph, so fontbakery can still read ď's caron from its components (`alt_caron`).

The round that built the missing characters, the anchors and the small capitals leaves each file with 1 FAIL, the version format: 2 for each pair, Mono's included. Katagami Round's roman also fails `shape_languages` for ɛ with U+1DC7 (Basaa). The mark attaches, but ɛ's top anchor sits at half its advance, so the mark moves by 1 unit, and the check reads a move that small as no attachment. Sans and Text still report the `superfamily/list` ERROR. The WARNs left (22 to 24 per pair) are the vendor ID, the OFL body text, Inter's long glyph names, overlapping segments, interpolation notes in a few of Noto's glyphs and in Serif Italic's small capital ỿ, the mark classes of U+20DD and U+20DE (Inter sets them with an advance) and of the merged Indic scripts, the file size, `soft_dotted` and `shape_languages` as above, and Mono's `opentype/monospace` and `alt_caron`.

Fontbakery was run on the four CJK companions for the first time. Each has 5 FAIL and 12 WARN. Three FAILs ask for Latin, which a companion leaves to the members (`glyph_coverage`, `render_own_name` and `shape_languages`); `cjk_vertical_metrics` asks for Google's CJK line metrics, where the companions take Katagami's so they can share a line with it; and the fifth is the version format. The WARNs are Noto's outlines (interpolation, outline direction, overlapping segments), no `chws` feature, the file size, post table format 3, the vendor ID, the OFL body text and Adobe's reserved font name in the copyright line. The first run also failed for a missing space and no-break space, smart dropout, the copyright line and the names, which said Regular for the Thin default; the build fixes all four.

The second fix round leaves every pair with 2 FAIL, the version format in both files, and no ERROR, because the `superfamily/list` ERROR is gone. Sans, Text and Serif have 12 WARN per pair, Round 14 and Mono 10. Both files of every pair report the vendor ID (KATA, until Microsoft lists it), `soft_dotted`, `gdef_mark_chars` and `unreachable_subsetting`. The `soft_dotted` examples left put U+20DD or U+20DE between the letter and the accent, and those enclosing marks of combining class 0 keep the dot under Unicode's rule. `gdef_mark_chars` lists U+20DD and U+20DE, which Inter sets with an advance. `unreachable_subsetting` lists the characters outside Google Fonts' subsets. The proportional romans add `file_size` (6.8 to 7.1 MiB with the merged scripts) and Noto's own mark classes for the merged Indic scripts (`gdef_non_mark_chars`, `gdef_spacing_marks`), which `finish.py` keeps because changing them changes how HarfBuzz shapes those scripts. They also add `interpolation_issues` for kinks and contour order in five of Noto's glyphs (Tamil, Malayalam, Bengali and Ethiopic) and Ol Chiki U+1C73, which Noto draws that way. Round's Italic adds `file_size` at 1,053,640 bytes, just over the 1 MiB suggestion once the new characters are in, and kinks at a few of its rounded corners. Mono adds `opentype/monospace`: its zero-width marks keep their zero advance, so `hhea.numberOfHMetrics` cannot be the 3 the check asks for.

Each CJK file now has 1 FAIL, the version format, and 7 WARN. A Google Fonts article per file (`docs/google-fonts/katagamicjk*/article`) clears the article check. The build repairs contours that share a segment once the file is at 1,000 units, turns outer contours clockwise again afterwards, and drops the one Latin part no letter reaches. The WARNs left are the file size, `unreachable_subsetting`, the vendor ID and Adobe's reserved font name. `math_signs_width` counts the full-width postal mark 〒 as a math sign. `typoascender_exceeds_Agrave` follows from Google's CJK typo metrics, which put the ascender at 0.88 em. `overlapping_path_segments` lists the braces, whose tab and arms have collinear left edges that meet when rounded to 1,000 units, and a few of Noto's hanzi and Hangul that the repair cannot separate.

## Not done yet

- Hand corrections beyond the Q and 2. Every other glyph is the output of a transform; none has been redrawn by eye.
- Hinting. The fonts are unhinted, with the gasp and prep tables an unhinted font needs.
- The 28 merged scripts in Katagami's own style. They are Noto's design at Katagami's size and weight; redrawing them is design work for each script.

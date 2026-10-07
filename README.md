# Kerf

Kerf is an open source type family with two members built on one skeleton:

- **Kerf Sans**: a sans serif with squared curves, horizontal cuts and square punctuation. Variable weight from 100 to 900.
- **Kerf Mono**: the same letters fitted to a 0.6 em cell, with flagged i, l and j, a serif I, a footed 1, a centre-bar zero and generated box drawing. Variable weight from 100 to 700.

Kerf Sans is derived from [Inter](https://github.com/rsms/inter) by Rasmus Andersson. It moves Inter toward the geometry of Camber by Eduardo Manso. Kerf Mono follows the monospace tradition that Berkeley Mono also comes from. Neither Camber nor Berkeley Mono contributed any outlines: both were measured as references only. See [SPEC.md](SPEC.md) for every design decision and the numbers behind it.

![Kerf Sans and Kerf Mono set in the same lines](docs/family.png)

![Kerf Mono box drawing, blocks and shades at its true line height](docs/mono-box.png)

**Status: v0.1, a generated draft.** Every glyph is produced by the transforms in `tools/`. Hand corrections, italics, mono ligatures and hinting come next.

## Fonts

```
fonts/sans/KerfSans[wght].ttf
fonts/mono/KerfMono[wght].ttf
```

## Building

Requires Python 3.11 or later and git.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
tools/build.sh          # both members
tools/build.sh sans     # one member
```

The build fetches Inter's sources at a pinned commit into `vendor/inter`, converts them to UFO, applies the Kerf transforms and compiles variable TrueType fonts with fontmake. A full build takes about ten minutes.

`tools/proof.py sans|mono|family` renders proof sheets to `build/proofs/`.

`tools/build_site.py` writes the specimen site to `site/`: WOFF2 fonts, `data.js` (metrics, character tables, features and the hero outlines from Inter and Kerf) and `index.html`, which wraps the hand-written `site/page.html`. Serve `site/` with any static server.

## Layout

| Path | Contents |
|---|---|
| `tools/build_sans.py` | Inter masters to Kerf Sans masters |
| `tools/build_mono.py` | Kerf Sans masters to Kerf Mono masters |
| `tools/kerf_build/outline.py` | point-preserving transforms: curve squaring, horizontal emboldening |
| `tools/kerf_build/fontops.py` | glyph swaps, resizing, composite re-seating, naming |
| `tools/kerf_build/boxdraw.py` | box drawing and block elements |
| `tools/build_site.py`, `site/` | specimen site |

## License

Kerf is licensed under the [SIL Open Font License 1.1](OFL.txt). It is a modified version of Inter, which is also licensed under the OFL, and keeps Inter's copyright notice.

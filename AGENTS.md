# Katagami for agents

Read this file before you change anything here. README.md says what Katagami is and how it is built. SPEC.md records every design decision with its numbers. This file holds the rules that neither of them states. RELEASE.md lists the steps of a release in order.

## Two repositories

This repository holds the fonts in `fonts/` and the build tools in `tools/`. The website lives in a second repository, Katagami-Website, which is private. The tools here write most of that site. They write its web fonts, its data, its page records, its library pages, its map and its list of downloads.

Set `KATAGAMI_SITE` to the absolute path of the site checkout or worktree you mean to write into. Without it the tools look for a folder named `Katagami-Website` beside this one, and from a git worktree that folder does not exist. `tools/kerf_build/sitepath.py` and `tools/site-path.mjs` read the variable for `tools/build_site.py`, `tools/build_map.py`, `tools/build_seo.py`, `tools/og.mjs`, `tools/readme.mjs` and `tools/stills.mjs`, and they stop the run when the folder is not a Katagami-Website checkout. `tools/logo.py` reads the variable itself.

```bash
KATAGAMI_SITE=/absolute/path/to/Katagami-Website .venv/bin/python tools/build_site.py --pages
```

## What takes long

- `tools/build.sh` builds every member and prints how long each stage took, in lines that begin with `timing`. Katagami Text and Katagami Serif each took about 4 minutes on an idle machine in November 2026, most of it in the script merge. A busy machine has taken 15 to 40 minutes for a member and over 3 hours for Serif.
- The CJK companions compile each Plex source once into `build/cjk-src`, which takes from a few minutes for KR to most of an hour for JP.
- A full `tools/build_site.py` run took about 5 minutes on an idle machine in November 2026 and has taken almost 3 hours on a busy one.
- The script merge and `tools/build_site.py` build several scripts or web font slices at once. `KATAGAMI_JOBS` sets how many, and the default is 4.
- Never start any of them to look at a single glyph or to check a small change. Use a fast loop, and ask the owner before a full build.

## Fast loops

- `.venv/bin/python -B tools/check.py` checks the committed fonts against README.md and SPEC.md and tests the build's pure helpers in well under a minute.
- `tools/serif_lab/prep.py roman` pickles Katagami Serif's masters once, in a minute or two. `tools/serif_lab/sheets.py` then draws proof sheets of Serif's terminals in a few seconds each, with no font build. Both need `build/ufo`, which `tools/build.sh` makes on its first run.
- `tools/proof.py sans` draws a comparison sheet of a built member into `build/proofs/`. It also takes `mono`, `family`, `round`, `text` and `detail`. `tools/proof.py serif` draws Katagami Serif before and after a change beside Geist Serif, and its docstring names the files it needs.
- `tools/build_world.py serif --only Devanagari,Thai` merges only the scripts you name into a member that fontmake has already built.
- `tools/build_site.py --pages` rewrites only the site's page records and `content/site.json`. `--downloads` writes only the full zip and the language packages, both into `build/release` for the GitHub release, and `files.json`. `--first` writes only the first-paint font scripts. `--data` writes only `data.js` and `glyphs.js`, and it needs the masters in `build/` and Inter's in `build/ufo`.
- fontTools reads any committed font in a second or two. Use it to answer a question about a file in `fonts/` without building.

## Worktrees

A fresh worktree has no `.venv`, no `build/`, no `vendor/` and no `tools/node_modules`, because git ignores all four. To read fonts or run a check there, use the main checkout's interpreter with `-B`, for example `~/repos/Katagami/.venv/bin/python -B tools/check.py`. The `-B` flag keeps Python from writing `__pycache__` folders. A build needs its own `vendor/` and `build/`, and `tools/build_site.py --data` and its full run read the masters in `build/`. Run those in a checkout that has the folders, or link that checkout's folders into the worktree.

## Settled design

These decisions are made. Do not reopen them, and do not report them as faults.

- Each Italic glyph is its roman slanted. The family has no separate italic letterforms.
- Katagami Serif is the design the owner approved, as SPEC.md records it.
- The g of Katagami Sans, Round and Text keeps its tail, and Katagami Text keeps its double-storey a.
- The t has no flat top.
- The 28 merged scripts are Noto's design for now. Redrawing them is known future work.
- The CJK companions are built from IBM Plex Sans TC, JP and KR and from Frex Sans GB. IBM reserves the name "Plex", so no Katagami font name contains it.
- Internal names keep the old project name, as in `kerf_build` and `window.KERF`.

Any change to a glyph needs the owner's approval on a proof before it ships. Draw the proof, show it and wait. Proofs go to `build/proofs/`, which git ignores, and they are never committed. A change to a number in SPEC.md is a design change and follows the same rule.

## Commits

- A commit message starts with `Code:`, `Fonts:` or `Docs:` and then says what is now true in one sentence. An example is "Code: the script merge compares the core's axis map with the merged font's at avar's precision".
- Code goes in its own commits, apart from the built fonts.
- A fonts commit carries the lines of README.md and SPEC.md that state its numbers, because `tools/check.py` reads all three.
- SPEC.md changes in the same series as the code whose numbers it records.
- Do not push, tag or publish without the owner's word.

# Releasing Katagami

A release changes two repositories and publishes a GitHub release. This list gives the steps in order. Ask the owner before any push, tag or publish. The examples use 1.6 as the new version and 1.5 as the old one.

## In this repository

1. Get the owner's approval on a proof for every glyph that changes.
2. Set `VERSION` in `tools/kerf_build/fontops.py`. Version 1.6 is `(1, 600)`. Commit it with the release's code. The 1.5 message was "Code: version 1.500, and the site's Serif page names the block tops of a and c".
3. Build the members whose outlines changed with `tools/build.sh <member>`, or with `tools/build.sh <member>-roman` for the roman alone. Every file carries the version, so run `tools/finish.py sans round text serif mono` for the members that were not rebuilt. It writes the version into their head and name tables and leaves their outlines alone.
4. Build the CJK companions with `tools/build.sh cjk`, because `tools/build_cjk.py` writes the version into their files. Their Plex sources compile once into `build/cjk-src`, and later builds reuse them.
5. Run `tools/qa.sh all` and `tools/qa.sh cjk`. They need fontbakery, which `requirements-dev.txt` installs. The reports land in `build/qa/`.
6. Update the table in `tools/check.py` to the new glyph and character counts, and run `.venv/bin/python -B tools/check.py`.
7. Update README.md and SPEC.md. The README's Status section names the version and says what it added, and its Building section names the version `requirements.lock` built. SPEC's Coverage heading names the version, and its Quality checks section records the fontbakery run.
8. Commit the fonts with README.md and SPEC.md. The 1.5 message was "Fonts: Katagami 1.5, whose Serif a, c and g have Geist Serif's tops". Push after the owner agrees. The site's footer and its download table link to commits on GitHub, so the fonts must be on GitHub before the site is built.

## In the site repository

9. Make a worktree of the site from its `origin/main` and run `pnpm install` in it. Work from a fonts checkout whose HEAD is the pushed release commit, and set `KATAGAMI_SITE` to the site worktree.
10. Run `tools/build_site.py`. It writes the web fonts, `data.js`, `glyphs.js`, the first-paint scripts, `files.json`, the page records and `content/site.json` into the site. It writes the full zip and the nine language packages into this repository's `build/release`, and `files.json` links each of them to the release. The site holds no zip. The run can take hours, and it needs the masters in `build/` and Inter's in `build/ufo`.
11. Run `tools/build_map.py` when the fonts' coverage changed. It needs the map data folder that `GT_WORLD` names.
12. Run `tools/build_seo.py`. It writes the library records, the Markdown twins, `llms.txt`, `llms-full.txt`, the sitemap and `build/og.json`. The Markdown twins and `llms-full.txt` name the zip and state each package's size, so this step follows every change to the downloads.
13. Run `node tools/og.mjs` when a share card's text or a Latin glyph changed. It needs playwright-core, which `npm install --prefix tools` installs, and Chrome. Set `CHROME` when Chrome is not at the path in the script.
14. Edit by hand what no tool writes. The About page's timeline takes an entry for the release. Search the fragments for the old version first.

```bash
grep -n 'Katagami 1\.5' page.html *-page.html README.md
```

15. Run `tools/build_site.py --pages` again after a hand edit. It rewrites the page records and the stamps in `content/site.json`.
16. In the site, run `pnpm check`, then `pnpm build`. The build stops when a stamp does not match its file. Serve the site with `pnpm dev` and open the home page, /download and /about. Compare each page whose glyphs changed with a picture taken before the change.
17. When a picture's subject changed, serve the site and redraw it. `node tools/stills.mjs` draws the stills. `BASE=http://localhost:3078 node tools/readme.mjs` and then `python3 tools/readme_shrink.py` draw the README images of both repositories. This repository's images in `docs/readme/` take a `Docs:` commit of their own here, as 1.5's "Docs: the README pictures are redrawn from Katagami 1.5, with the new Serif" did.
18. Commit the site with a message that names the version and says what it changed.
19. Create the GitHub release and its tag on the fonts release commit, with every zip in `build/release` and notes that say what changed and credit the sources of the CJK companions. The site sends `/download/Katagami-1.6.zip` to the release's copy, so the release must hold its zips before the site deploys. Ask the owner first.

```bash
gh release create v1.6 build/release/*.zip --target <commit> --title "Katagami 1.6" --notes-file <notes> --latest
```

20. Fetch the site's `origin/main` and rebase onto it, because other work lands there. Run `pnpm check` again. Push after the owner agrees. Vercel deploys every push to `main`.

## After the site is pushed

21. Check the live site after Vercel reports the deploy. `/download/Katagami-1.6.zip` redirects to the release and the download answers 200 with the zip's size. `/download/files.json` names version 1.6, and every package address in it answers 200. The footer shows the new version, and its commit link opens.

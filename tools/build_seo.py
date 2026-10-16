#!/usr/bin/env python3
"""Pages for search and answer engines, kept out of the site's navigation.

Writes into the site: a page per member, comparisons with other typefaces,
guides, explainers, a page per script and per language on the map, the
library that indexes them, a Markdown twin of every page, llms.txt,
llms-full.txt, sitemap.xml, robots.txt and site.webmanifest. Every fact about
Katagami is read from the built fonts and the map data; facts about other
typefaces come from tools/seo/typefaces.json, each with its sources.

Run after tools/build_site.py and tools/build_map.py.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).parent))
from build_site import (CJK, FAMILY, FONTS, MEMBER_PATHS, OPTIONAL, PAGE_META, REPO, SITE, SITE_URL,  # noqa: E402
                        asset_stamps, page_graph, site_facts, wrap)
from build_world import SCRIPTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TYPEFACES = ROOT / "tools" / "seo" / "typefaces.json"
TODAY = time.strftime("%Y-%m-%d")
MEMBERS = ["sans", "round", "text", "serif", "mono"]
FACE = {"sans": "'Katagami Sans'", "round": "'Katagami Round'", "text": "'Katagami Text'", "serif": "'Katagami Serif'", "mono": "'Katagami Mono'"}
FEATURE_NAMES = {"calt": "Contextual alternates", "case": "Case-sensitive forms", "cpsp": "Capital spacing", "dlig": "Discretionary ligatures",
                 "frac": "Fractions", "numr": "Numerators", "dnom": "Denominators", "ordn": "Ordinals", "pnum": "Proportional figures",
                 "tnum": "Tabular figures", "salt": "Stylistic alternates", "sinf": "Scientific inferiors", "smcp": "Small capitals",
                 "c2sc": "Small capitals from capitals", "subs": "Subscript", "sups": "Superscript", "zero": "Slashed zero", "liga": "Standard ligatures"}
WEB_SNIPPET = '<link rel="stylesheet" href="https://katagami.kevinliu.studio/fonts/katagami.css">'

# ---------- facts read from the fonts and the map ----------

LATIN = [(0x0000, 0x024F), (0x1E00, 0x1EFF), (0x2C60, 0x2C7F), (0xA720, 0xA7FF), (0xAB30, 0xAB6F)]
GREEK = [(0x0370, 0x03FF), (0x1F00, 0x1FFF)]
CYRILLIC = [(0x0400, 0x052F), (0x1C80, 0x1C8F), (0x2DE0, 0x2DFF), (0xA640, 0xA69F)]
DRAWN = {"Latin": (LATIN, {"Latn"}), "Greek": (GREEK, {"Grek"}), "Cyrillic": (CYRILLIC, {"Cyrl"})}
CODES = {"Devanagari": "Deva", "Arabic": "Arab", "Bengali": "Beng", "Gurmukhi": "Guru", "Gujarati": "Gujr", "Oriya": "Orya",
         "Tamil": "Taml", "Telugu": "Telu", "Kannada": "Knda", "Malayalam": "Mlym", "Sinhala": "Sinh", "Thai": "Thai", "Lao": "Laoo",
         "Myanmar": "Mymr", "Ethiopic": "Ethi", "Hebrew": "Hebr", "Armenian": "Armn", "Georgian": "Geor", "Khmer": "Khmr"}
DISPLAY = {"Oriya": "Odia"}
COMPANIONS = {"Chinese (Simplified)": ("KatagamiCJKSC", {"Hans"}), "Chinese (Traditional)": ("KatagamiCJKTC", {"Hant"}),
              "Japanese": ("KatagamiCJKJP", {"Jpan"}), "Korean": ("KatagamiCJKKR", {"Kore"})}
NOT_YET = {"Tibetan": "Tibt", "Tifinagh": "Tfng", "Thaana": "Thaa", "N'Ko": "Nkoo", "Vai": "Vaii", "Ol Chiki": "Olck",
           "Coptic": "Copt", "Hanifi Rohingya": "Rohg", "Canadian syllabics": "Cans"}
SCRIPT_NAME_OF_CODE = {**{c: DISPLAY.get(n, n) for n, c in CODES.items()}, "Latn": "Latin", "Grek": "Greek", "Cyrl": "Cyrillic",
                       "Hans": "Chinese (Simplified)", "Hant": "Chinese (Traditional)", "Jpan": "Japanese", "Kore": "Korean",
                       **{c: n for n, c in NOT_YET.items()}}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "")).strip("-")


def count_in(cmap: set, ranges) -> int:
    return sum(1 for u in cmap if any(lo <= u <= hi for lo, hi in ranges))


def member_facts() -> dict:
    out = {}
    for key in MEMBERS:
        path = FONTS[key]
        f = TTFont(path)
        cmap = set(f.getBestCmap())
        name = f["name"]
        labels = {}
        for rec in f["GSUB"].table.FeatureList.FeatureRecord:
            if not OPTIONAL.match(rec.FeatureTag) or rec.FeatureTag in labels:
                continue
            prm = rec.Feature.FeatureParams
            nid = prm and (getattr(prm, "UINameID", None) or getattr(prm, "FeatUILabelNameID", None))
            labels[rec.FeatureTag] = name.getDebugName(nid) if nid else ""
        scripts = {n: count_in(cmap, r) for n, (r, _) in DRAWN.items()}
        scripts |= {DISPLAY.get(n, n): count_in(cmap, r) for n, r in SCRIPTS.items()}
        out[key] = {
            "family": FAMILY[key], "glyphs": len(f.getGlyphOrder()), "characters": len(cmap), "upm": f["head"].unitsPerEm,
            "cap": f["OS/2"].sCapHeight, "xh": f["OS/2"].sxHeight, "size": path.stat().st_size, "file": path.name,
            "weights": [int(a.minValue) for a in f["fvar"].axes] + [int(a.maxValue) for a in f["fvar"].axes],
            "instances": [name.getDebugName(i.subfamilyNameID) for i in f["fvar"].instances],
            # a script counts once it has a working set of letters, not a stray sign or two
            "features": dict(sorted(labels.items())), "scripts": {k: v for k, v in scripts.items() if v >= 20},
        }
    return out


def companion_facts() -> dict:
    out = {}
    for name, (stem, _) in COMPANIONS.items():
        path = ROOT / "fonts" / "cjk" / f"{stem}[wght].ttf"
        if path.exists():
            out[name] = {"file": path.name, "characters": len(TTFont(path, lazy=True).getBestCmap()), "size": path.stat().st_size}
    return out


def mb(n: int) -> str:
    return f"{n / 1048576:.1f} MB"


def compact(n: int) -> str:
    return f"{n / 1e9:.1f} billion" if n >= 1e9 else f"{n / 1e6:.1f} million" if n >= 1e6 else f"{round(n / 1e3)} thousand" if n >= 1e4 else f"{n:,}"


# ---------- content blocks: each renders to HTML and to Markdown ----------

def inline(text: str) -> str:
    """Escapes text and turns [label](url), `code` and **bold** into HTML."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)


def md_link(text: str) -> str:
    """Markdown keeps its own syntax; site links become absolute so the twin stands alone."""
    return re.sub(r"\]\((/[^)]*)\)", lambda m: f"]({SITE_URL}{m.group(1)})", text)


def render(blocks: list) -> tuple[str, str]:
    h, m = [], []
    for b in blocks:
        kind = b[0]
        if kind == "h2":
            anchor = slug(b[1])
            h.append(f'<h2 id="{anchor}">{inline(b[1])}</h2>')
            m.append(f"## {b[1]}")
        elif kind == "p":
            h.append(f"<p>{inline(b[1])}</p>")
            m.append(md_link(b[1]))
        elif kind == "list":
            # ("list", items, "cols") lays a long list out in columns
            cls = ' class="lib-cols"' if len(b) > 2 and b[2] == "cols" else ""
            h.append(f"<ul{cls}>" + "".join(f"<li>{inline(i)}</li>" for i in b[1]) + "</ul>")
            m.append("\n".join(f"- {md_link(i)}" for i in b[1]))
        elif kind == "table":
            head, rows = b[1], b[2]
            table = lambda rs: ("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                                + "".join("<tr>" + "".join(f"<td>{inline(str(c))}</td>" for c in r) + "</tr>" for r in rs) + "</tbody></table>")
            # ("table", head, rows, n) sets a narrow table in up to n side-by-side columns, six rows or more each
            if len(b) > 3:
                per = max(6, -(-len(rows) // b[3]))
                h.append('<div class="lib-split">' + "".join(table(rows[i:i + per]) for i in range(0, len(rows), per)) + "</div>")
            else:
                h.append(f'<div class="t-scroll">{table(rows)}</div>')
            m.append("| " + " | ".join(head) + " |\n|" + "---|" * len(head) + "\n"
                     + "\n".join("| " + " | ".join(md_link(str(c)).replace("|", "\\|") for c in r) + " |" for r in rows))
        elif kind == "code":
            h.append(f'<pre class="copy-code">{html.escape(b[2])}<button class="btn" type="button" data-copy>Copy</button></pre>')
            m.append(f"```{b[1]}\n{b[2]}\n```")
        elif kind == "specimen":
            face, text, size = b[1], b[2], b[3] if len(b) > 3 else 44
            weight = b[4] if len(b) > 4 else 400
            h.append(f'<p class="specimen" dir="auto" style="font-family:{face};font-size:{size}px;font-weight:{weight}">{html.escape(text)}</p>')
            m.append(f"> {text}")
        elif kind == "cards":
            h.append('<div class="lib-cards">' + "".join(
                f'<a class="lib-card" href="{href}"><b>{inline(t)}</b><span>{inline(d)}</span></a>' for t, d, href in b[1]) + "</div>")
            m.append("\n".join(f"- [{t}]({SITE_URL}{href}): {d}" for t, d, href in b[1]))
        elif kind == "faq":
            h.append('<div class="lib-faq">' + "".join(f"<details open><summary>{inline(q)}</summary><p>{inline(a)}</p></details>" for q, a in b[1]) + "</div>")
            m.append("\n\n".join(f"**{q}**\n\n{md_link(a)}" for q, a in b[1]))
        elif kind == "sources":
            h.append('<div class="lib-sources"><b>Sources</b><ul>' + "".join(f'<li><a href="{u}" rel="nofollow noopener">{html.escape(u)}</a></li>' for u in b[1])
                     + f"</ul><p>Checked {TODAY}.</p></div>")
            m.append("Sources, checked " + TODAY + ":\n" + "\n".join(f"- {u}" for u in b[1]))
    return "\n".join(h), "\n\n".join(m)


def faq_nodes(blocks: list) -> list:
    return [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", a)}}
            for b in blocks if b[0] == "faq" for q, a in b[1]]


# ---------- pages ----------

PAGES: list[dict] = []


def page(path, title, description, h1, lede, blocks, crumbs, image="library", schema="WebPage", extra=None, aside=None, group=None, card=None):
    PAGES.append({"path": path, "title": title, "description": description, "h1": h1, "lede": lede, "blocks": blocks,
                  "crumbs": crumbs, "image": image, "schema": schema, "extra": extra or [], "aside": aside or [],
                  "group": group, "card": card or description})


def member_pages(F: dict, C: dict, M: dict) -> None:
    about = {
        "sans": ("a free variable sans serif for interfaces and display",
                 "Katagami Sans is the core of the family: a sans serif with squared bowls, level cuts and square punctuation, made for interfaces and display.",
                 ["Bowls are squared toward their corners, 0.36 of the way above and 0.32 below, and round letters are condensed so o matches n.",
                  "The ends of c, e, s, a and g are cut level.",
                  "Periods, commas, quotes and the dots on i and j are square.",
                  "The compact f has a crossbar that reaches 0.8 of a Regular stem past its stem at every weight.",
                  "The figures are a long-flag 1, a flat-top 3, an open 4 and a 6 and 9 with straight stems.",
                  "Quarter arcs reach 0.73 of the way to their corners, against 0.552 for a circle."]),
        "round": ("a free rounded sans serif",
                  "Katagami Round squares its bowls less than Katagami Sans and rounds every sharp vertex, for interfaces and text that should read softer.",
                  ["Bowls are squared 0.24 of the way above and 0.22 below.",
                   "Every sharp vertex is rounded with a radius of 0.22 stems: stem ends, terminals and apexes.",
                   "It keeps the same figures, the compact f and level cuts as Katagami Sans, and its G has a spur.",
                   "Quarter arcs reach 0.69 of the way to their corners."]),
        "text": ("a free sans serif for long reading",
                 "Katagami Text is the reading member: a lower x-height, set smaller and tighter, with wider round letters and capitals.",
                 ["The x-height is 0.71 of the cap height.",
                  "Every glyph is set 4 percent smaller on the same line height.",
                  "Letters are condensed to 0.97 of their ink width with their stems kept, and spacing is tighter.",
                  "The c's terminals sit closer together, the g's tail rises higher, the l is straight and the top of the t is cut at a slant.",
                  "The heavy weights are drawn lighter: weight 700 sits at 640 on the design axis and 800 at 760.",
                  "Quarter arcs reach 0.59 of the way to their corners, the roundest of the family."]),
        "serif": ("a free serif font with rectangular serifs",
                  "Katagami Serif is Katagami Text with rectangular serifs: each serif ends square and meets the stroke in a short bracket.",
                  ["Each serif reaches 0.65 of a stem past the stroke and is 0.6 of the H crossbar thick.",
                   "A short bracket joins the serif's back to the stroke's own side, so the serifs of diagonals meet the diagonal.",
                   "The top of a lowercase stem takes a triangular serif.",
                   "The arms of E, F, L, T and Z end in short vertical serifs, and the level cuts of c, a and s stay as they are in Katagami Text.",
                   "Each point keeps its x and moves 30 percent of the way to its height in the next lighter weight, so horizontals are thinner than stems."]),
        "mono": ("a free monospace font for code",
                 "Katagami Mono fits Katagami Sans to a monospace cell, for code, terminals and tables.",
                 ["Every character is 1280 units wide, 0.625 em.",
                  "Characters that could be mistaken for each other are drawn apart: a zero with a bar, a 1 with a long flag, i, l and j with flags and a capital I with serifs.",
                  "Code ligatures for ->, =>, !=, == and >= are off until you turn on dlig, and every character keeps its own cell.",
                  "The 160 box-drawing and block characters from U+2500 to U+259F are drawn to join across lines.",
                  "The f, t and r reach into the cell on their arms; the f's crossbar keeps 0.18 of the cell left of its stem at every weight."]),
    }
    for key in MEMBERS:
        f = F[key]
        short, lede, design = about[key]
        w0, w1 = f["weights"]
        rows = [["Weights", f"{w0} to {w1}, variable"], ["Named styles", ", ".join(f["instances"])], ["Glyphs", f"{f['glyphs']:,}"],
                ["Characters", f"{f['characters']:,}"], ["Units per em", f"{f['upm']:,}"],
                ["Cap height", f"{f['cap']} units, {f['cap'] / f['upm']:.3f} em"], ["x-height", f"{f['xh']} units, {f['xh'] / f['upm']:.3f} em"],
                ["Scripts drawn or merged", str(len(f["scripts"]))], ["OpenType features you can switch", str(len(f["features"]))],
                ["File", f"`{f['file']}`, {mb(f['size'])}"], ["License", "SIL Open Font License 1.1"], ["Version", "0.1"]]
        feats = [f"`{t}` {lab or FEATURE_NAMES.get(t, '')}".rstrip() for t, lab in f["features"].items()]
        cjk = "" if key == "mono" else " Chinese, Japanese and Korean come from the four Katagami CJK companions, which the web stylesheet assigns to this member."
        compare = [c for c in COMPARE_PAGES if key in c["members"]]
        blocks = [
            ("specimen", FACE[key], "Handgloves 0123456789", 64, 600),
            ("specimen", FACE[key], "The quick brown fox jumps over the lazy dog.", 30, 400),
            ("h2", "At a glance"), ("table", ["", f["family"]], rows),
            ("h2", "Design"), ("list", design),
            ("h2", "Coverage"), ("p", f"{f['family']} has {f['characters']:,} characters and covers {len(f['scripts'])} scripts.{cjk} See [where it writes](/map) and [every glyph](/glyphs)."),
            ("table", ["Script", "Characters"], [[n, f"{c:,}"] for n, c in f["scripts"].items()], 3),
            ("h2", "Use it on the web"), ("p", "Link the stylesheet, then set the family. Each script is its own file, so a page loads only what it shows."),
            ("code", "html", WEB_SNIPPET), ("code", "css", f"body {{ font-family: \"{f['family']}\", {'ui-monospace, monospace' if key == 'mono' else 'system-ui, sans-serif'}; }}"),
            ("p", f"Or [download the fonts](/download): `{f['file']}` is one variable file with every weight."),
            ("h2", "OpenType features"), ("p", "Turn each on with `font-feature-settings`. The [features page](/features) shows each one off and on."),
            ("list", feats, "cols"),
            ("h2", "Questions"),
            ("faq", [(f"Is {f['family']} free for commercial use?", f"Yes. {f['family']} is released under the SIL Open Font License 1.1, which allows use in any product, commercial or not, and changes. Keep the license with the files when you share them."),
                     (f"Which weights does {f['family']} have?", f"Every weight from {w0} to {w1} on one variable axis, with named styles from {f['instances'][0]} to {f['instances'][-1]}."),
                     (f"Does {f['family']} have italics?", "Not yet. Version 0.1 is upright; italics come after hand corrections.")]),
        ]
        if compare:
            blocks += [("h2", "Compared"), ("cards", [(c["title"].split(":")[0], c["card"], c["path"]) for c in compare])]
        others = [(FAMILY[k], about[k][0][0].upper() + about[k][0][1:], MEMBER_PATHS[k]) for k in MEMBERS if k != key]
        blocks += [("h2", "The rest of the family"), ("cards", others)]
        page(MEMBER_PATHS[key], f"{f['family']}: {short}", f"{lede} Variable from {w0} to {w1}, {f['characters']:,} characters, free under the SIL Open Font License.",
             f["family"], lede, blocks, [("Library", "/library"), (f["family"], MEMBER_PATHS[key])], image=f"member-{key}",
             extra=[{"@type": ["CreativeWork", "SoftwareApplication"], "@id": f"{SITE_URL}{MEMBER_PATHS[key]}#font", "name": f["family"],
                     "isPartOf": {"@id": f"{SITE_URL}/#katagami"}, "genre": "Typeface", "additionalType": "https://www.wikidata.org/wiki/Q17451",
                     "license": "https://openfontlicense.org/", "isAccessibleForFree": True, "applicationCategory": "DesignApplication",
                     "operatingSystem": "macOS, Windows, Linux, Web", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                     "softwareVersion": "0.1", "fileSize": mb(f["size"]), "downloadUrl": f"{SITE_URL}/download/Katagami-0.1.zip",
                     "author": {"@id": f"{SITE_URL}/#kevin"}}],
             group="Members", card=lede)


# ---------- comparisons ----------

COMPARE_PAGES: list[dict] = []
FIELDS = [("designers", "Designer"), ("foundry", "Foundry or publisher"), ("year", "First released"), ("license", "License"),
          ("free_commercial", "Free for commercial use"), ("weights", "Weights"), ("italics", "Italics"), ("axes", "Variable axes"),
          ("scripts", "Scripts"), ("features", "Notable features")]


def katagami_row(keys: list, F: dict) -> dict:
    """The comparison facts for the Katagami members a page compares."""
    one = len(keys) == 1
    f = F[keys[0]]
    w0, w1 = f["weights"]
    chars = max(F[k]["characters"] for k in keys)
    return {
        "name": f["family"] if one else "Katagami", "designers": "Kevin Liu", "foundry": "Kevin Liu (independent)", "year": "2026",
        "license": "SIL Open Font License 1.1", "free_commercial": "Yes", "weights": f"{w0} to {w1}" if one else "100 to 900 (Mono 100 to 700)",
        "italics": "Not yet", "axes": "wght",
        "scripts": (f"Latin, Greek, Cyrillic and 19 more scripts, {chars:,} characters, plus Chinese, Japanese and Korean companions"
                    if keys != ["mono"] else f"Latin, Greek, Cyrillic and box drawing, {chars:,} characters"),
        "features": {"mono": "Code ligatures off by default (dlig), disambiguated 0 O 1 l I, box drawing",
                     "serif": "Rectangular serifs, small capitals, tabular figures, fractions"}.get(keys[0]) if one else
                    "Five members on one skeleton, small capitals, tabular figures, fractions, 16 character variants and 8 stylistic sets",
        "url": SITE_URL + (MEMBER_PATHS[keys[0]] if one else "/"),
    }


def compare_specs() -> list[dict]:
    """What each comparison compares and the facts it adds beyond the table."""
    return [
        {"slug": "katagami-vs-inter", "other": "Inter", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs Inter: differences, coverage and license",
         "lede": "Katagami starts from Inter's open-source outlines. Both are free under the SIL Open Font License; Katagami squares the curves, cuts terminals level, adds a rounded, a reading, a serif and a mono member, and merges 19 more scripts.",
         "notes": ["Katagami Sans's quarter arcs reach 0.73 of the way to their corners, where a circle reaches 0.552; the other members are rounder.",
                   "Katagami cuts the ends of c, e, s, a and g level and makes punctuation square in Sans.",
                   "Katagami adds Chinese, Japanese and Korean through four companion fonts that the web stylesheet assigns to its proportional members.",
                   "Katagami has small capitals (smcp, c2sc); Inter 4.1 removed its incomplete small capitals.",
                   "Katagami has one axis, weight; it has no optical size axis and no italics yet."]},
        {"slug": "katagami-vs-geist", "other": "Geist Sans", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs Geist: two free type families compared",
         "lede": "Geist and Katagami are both free families with a sans and a mono under the SIL Open Font License. Katagami adds a rounded sans, a reading face and a serif, and sets 22 scripts plus Chinese, Japanese and Korean.",
         "notes": ["Katagami has five members on one skeleton: Sans, Round, Text, Serif and Mono.",
                   "Katagami Mono has code ligatures, but they stay off until you turn on dlig."]},
        {"slug": "katagami-mono-vs-geist-mono", "other": "Geist Mono", "members": ["mono"], "title": "Katagami Mono vs Geist Mono: free monospace fonts compared",
         "lede": "Katagami Mono and Geist Mono are free monospace fonts under the SIL Open Font License, each with a sans to pair with.", "notes": []},
        {"slug": "katagami-mono-vs-jetbrains-mono", "other": "JetBrains Mono", "members": ["mono"], "title": "Katagami Mono vs JetBrains Mono: monospace fonts for code",
         "lede": "Both are free monospace fonts for code under the SIL Open Font License. JetBrains Mono turns its code ligatures on by default; Katagami Mono keeps them off until you turn on dlig.",
         "notes": ["Katagami Mono's cell is 0.625 em wide.", "Katagami Mono pairs with four proportional members drawn on the same skeleton."]},
        {"slug": "katagami-mono-vs-fira-code", "other": "Fira Code", "members": ["mono"], "title": "Katagami Mono vs Fira Code: ligatures, weights and license",
         "lede": "Fira Code is a monospace font built around programming ligatures. Katagami Mono has a small set of code ligatures that stay off by default.", "notes": []},
        {"slug": "katagami-vs-ibm-plex", "other": "IBM Plex Sans", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs IBM Plex: free superfamilies compared",
         "lede": "IBM Plex and Katagami are both free families with a sans, a serif and a mono under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-mono-vs-ibm-plex-mono", "other": "IBM Plex Mono", "members": ["mono"], "title": "Katagami Mono vs IBM Plex Mono",
         "lede": "Both are free monospace fonts under the SIL Open Font License, each part of a larger family.", "notes": []},
        {"slug": "katagami-serif-vs-ibm-plex-serif", "other": "IBM Plex Serif", "members": ["serif"], "title": "Katagami Serif vs IBM Plex Serif",
         "lede": "Both are free serifs under the SIL Open Font License that pair with a sans and a mono from the same family.", "notes": []},
        {"slug": "katagami-vs-roboto", "other": "Roboto", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs Roboto: free sans serifs compared",
         "lede": "Roboto is Google's interface typeface. Katagami Sans is a squared sans with four sibling members, free under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-vs-sf-pro", "other": "SF Pro", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs SF Pro: a free alternative for interfaces",
         "lede": "SF Pro is Apple's system typeface, licensed for designing interfaces for Apple platforms. Katagami is free to use and ship in any product under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-vs-helvetica", "other": "Helvetica Now", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs Helvetica: a free sans serif alternative",
         "lede": "Helvetica is a commercial typeface licensed from Monotype. Katagami Sans is free under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-mono-vs-berkeley-mono", "other": "Berkeley Mono", "members": ["mono"], "title": "Katagami Mono vs Berkeley Mono: free and commercial monospace",
         "lede": "Berkeley Mono is a commercial monospace font. Katagami Mono was measured against it for its cell and arms, contains none of its outlines, and is free under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-sans-vs-camber", "other": "Camber", "members": ["sans"], "title": "Katagami Sans vs Camber: squared sans serifs compared",
         "lede": "Camber is a commercial sans with squared curves. Katagami Sans was measured against it for proportion and curve shape, contains none of its outlines, and is free under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-text-vs-pp-mori", "other": "PP Mori", "members": ["text"], "title": "Katagami Text vs PP Mori: proportions for reading",
         "lede": "PP Mori is a commercial sans. Katagami Text was measured against its proportions, contains none of its outlines, and is free under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-serif-vs-newsserif", "other": "NewsSerif", "members": ["serif"], "title": "Katagami Serif vs NewsSerif: free and commercial serifs",
         "lede": "NewsSerif is a commercial serif family by Character Type, measured as a reference for the first Katagami Serif. Katagami Serif contains none of its outlines and is free under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-serif-vs-signifier", "other": "Signifier", "members": ["serif"], "title": "Katagami Serif vs Signifier: rectangular serifs compared",
         "lede": "Signifier is a commercial serif by Kris Sowersby at Klim Type Foundry. Katagami Serif's serifs follow its published design notes: rectangular baseline serifs, triangular head serifs and chopped terminals. Katagami Serif contains none of its outlines and is free under the SIL Open Font License.",
         "notes": ["Signifier is drawn from the 17th-century Fell Types. Katagami Serif cuts its serifs onto Katagami Text, so it keeps Text's proportions and level cuts."]},
        {"slug": "katagami-serif-vs-source-serif", "other": "Source Serif 4", "members": ["serif"], "title": "Katagami Serif vs Source Serif 4: free serifs compared",
         "lede": "Source Serif 4 and Katagami Serif are both free serifs under the SIL Open Font License.", "notes": []},
        {"slug": "katagami-vs-noto-sans", "other": "Noto Sans", "members": ["sans", "round", "text", "serif"], "title": "Katagami vs Noto Sans: multilingual coverage compared",
         "lede": "The Noto project covers the scripts of Unicode across many fonts; Noto Sans is its Latin, Greek and Cyrillic font. Katagami draws its own Latin, Greek and Cyrillic and merges 19 scripts from the Noto Sans fonts, scaled to Katagami's x-height.",
         "notes": ["Katagami's Latin, Greek and Cyrillic are its own design; its Devanagari, Arabic, Thai, Ethiopic and the other merged scripts are Noto's outlines.",
                   "Katagami adds Chinese, Japanese and Korean through four companion fonts built from Noto Sans SC, TC, JP and KR."]},
    ]


def compare_pages(F: dict) -> None:
    others = {t["name"]: t for t in json.loads(TYPEFACES.read_text())} if TYPEFACES.exists() else {}
    for spec in compare_specs():
        other = others.get(spec["other"])
        if not other:
            continue
        kat = katagami_row(spec["members"], F)
        rows = [[label, kat.get(k, ""), other.get(k) or "unknown"] for k, label in FIELDS]
        mine = kat["name"]
        path = f"/compare/{spec['slug']}"
        COMPARE_PAGES.append({"path": path, "title": spec["title"], "card": spec["lede"], "members": spec["members"]})
        blocks = [("h2", "Side by side"), ("table", ["", mine, other["name"]], rows)]
        if spec["notes"]:
            blocks += [("h2", f"What is different in {mine}"), ("list", spec["notes"])]
        blocks += [
            ("h2", f"Try {mine}"),
            ("specimen", FACE[spec["members"][0]] if len(spec["members"]) == 1 else FACE["sans"], "Handgloves 0123456789", 56, 600),
            ("p", f"Download it from the [download page](/download), or link `katagami.css` and set the family. [Font-ify](/convert) shows any website in {mine}."),
            ("code", "html", WEB_SNIPPET),
            ("h2", "Questions"),
            ("faq", [(f"Is {mine} free for commercial use?", "Yes. It is released under the SIL Open Font License 1.1, which allows use in any product, commercial or not."),
                     (f"Is {other['name']} free for commercial use?", f"Its license is listed as {other.get('license') or 'unknown'}. Check the license on its official page before you ship it: {other.get('url', '')}.")]),
            ("sources", [SITE_URL + (MEMBER_PATHS[spec["members"][0]] if len(spec["members"]) == 1 else "/"), *other.get("sources", [])]),
        ]
        page(path, spec["title"], f"{spec['lede']} License, weights, axes, scripts and features side by side.", spec["title"].split(":")[0],
             spec["lede"], blocks, [("Library", "/library"), ("Compare", "/compare"), (spec["title"].split(":")[0], path)],
             image="compare", group="Compare", card=spec["lede"])
    if COMPARE_PAGES:
        page("/compare", "Katagami compared with other typefaces", "How Katagami compares with Inter, Geist, JetBrains Mono, IBM Plex, Roboto, SF Pro, Helvetica and others: license, weights, axes and scripts.",
             "Compare", "Katagami side by side with the typefaces people choose between, on license, weights, axes, scripts and features. Facts about other typefaces come from their official pages and are linked on each comparison.",
             [("cards", [(c["title"].split(":")[0], c["card"], c["path"]) for c in COMPARE_PAGES])],
             [("Library", "/library"), ("Compare", "/compare")], image="compare", schema="CollectionPage", group=None)


# ---------- guides and explainers ----------

def guide_pages(F: dict, C: dict, M: dict, T: dict) -> None:
    def row(name, keys=("license", "weights", "axes", "features")):
        t = T.get(name, {})
        return [name, *[(t.get(k) or "unknown") for k in keys]]
    mono = F["mono"]
    page("/fonts-for/coding", "Free monospace fonts for code: Katagami Mono and others", "What to look for in a monospace font for code, and how Katagami Mono, JetBrains Mono, Fira Code, IBM Plex Mono, Geist Mono and Berkeley Mono compare.",
         "Monospace fonts for code", "A font for code has to keep columns, tell similar characters apart and stay readable for hours. These are the free and paid options people compare, with Katagami Mono's numbers.",
         [("h2", "What to look for"),
          ("list", ["Every character the same width, so code and tables line up.", "Zero and capital O, one, lowercase l and capital I drawn apart.",
                    "Ligatures you can turn off, so `!=` and `->` can show as the characters you typed.", "Weights for emphasis in editors and terminals.",
                    "Box-drawing characters that join across lines, for terminal interfaces."]),
          ("h2", "Katagami Mono"), ("specimen", FACE["mono"], "const cells = [0O0, 1lI]; // -> => !=", 30, 400),
          ("p", f"Katagami Mono has {mono['characters']:,} characters in a 0.625 em cell, weights {mono['weights'][0]} to {mono['weights'][1]}, code ligatures off until you turn on `dlig`, and 160 box-drawing and block characters. It is free under the SIL Open Font License. [More about Katagami Mono](/katagami-mono)."),
          ("h2", "Compared"),
          ("table", ["Font", "License", "Weights", "Variable axes", "Notable features"],
           [["Katagami Mono", "SIL Open Font License 1.1", f"{mono['weights'][0]} to {mono['weights'][1]}", "wght", "Code ligatures off by default, disambiguated 0 O 1 l I, box drawing"],
            *[row(n) for n in ("JetBrains Mono", "Fira Code", "IBM Plex Mono", "Geist Mono", "Berkeley Mono")]]),
          ("cards", [(c["title"].split(":")[0], c["card"], c["path"]) for c in COMPARE_PAGES if c["members"] == ["mono"]])],
         [("Library", "/library"), ("Guides", "/library#guides"), ("Monospace fonts for code", "/fonts-for/coding")], image="guide", group="Guides")
    sans = F["sans"]
    page("/fonts-for/interfaces", "Free fonts for interfaces: Katagami Sans and Round", "Free sans serifs for apps and websites: what matters in an interface font, and how Katagami Sans and Round compare with Inter, Geist, Roboto, SF Pro and IBM Plex Sans.",
         "Fonts for interfaces", "Interface text is small, dense and full of numbers. These are the sans serifs people compare for apps and websites, with Katagami's numbers.",
         [("h2", "What to look for"),
          ("list", ["Tabular figures, so numbers line up in tables and prices.", "A clear difference between 1, l and I in labels and codes.",
                    "Enough weights for hierarchy, ideally on one variable file.", "Coverage for the languages your product ships in.", "A license that lets you embed the font in an app."]),
          ("h2", "Katagami Sans and Katagami Round"), ("specimen", FACE["sans"], "Settings, Billing, Members, 1,280.50", 34, 500),
          ("specimen", FACE["round"], "Invite team, Export CSV, Upgrade plan", 34, 500),
          ("p", f"Katagami Sans has {sans['characters']:,} characters, weights 100 to 900 on one variable file, tabular figures and small capitals, and sets 22 scripts plus Chinese, Japanese and Korean. Katagami Round is the softer member with rounded vertices. Both are free under the SIL Open Font License. [Katagami Sans](/katagami-sans), [Katagami Round](/katagami-round)."),
          ("h2", "Compared"),
          ("table", ["Font", "License", "Weights", "Variable axes", "Notable features"],
           [["Katagami Sans", "SIL Open Font License 1.1", "100 to 900", "wght", "Squared curves, small capitals, tabular figures, five members"],
            *[row(n) for n in ("Inter", "Geist Sans", "Roboto", "SF Pro", "IBM Plex Sans")]])],
         [("Library", "/library"), ("Guides", "/library#guides"), ("Fonts for interfaces", "/fonts-for/interfaces")], image="guide", group="Guides")
    text, serif = F["text"], F["serif"]
    page("/fonts-for/reading", "Free fonts for long reading: Katagami Text and Serif", "Free typefaces for articles, documentation and books: what makes text readable at length, and Katagami Text and Serif with their numbers.",
         "Fonts for long reading", "Long text needs an even color, generous counters and spacing set for body sizes. These are Katagami's two reading members.",
         [("h2", "What to look for"),
          ("list", ["A moderate x-height, so ascenders and descenders give words their shapes.", "Spacing set for 14 to 20 pixels, the sizes body text runs at.",
                    "Weights that stay open in bold, so emphasis does not clog.", "Real small capitals and old-style figures where the design calls for them."]),
          ("h2", "Katagami Text"), ("specimen", FACE["text"], "A katagami is a paper stencil for dyeing cloth.", 30, 400),
          ("p", f"Katagami Text has an x-height of {text['xh'] / text['cap']:.2f} of its cap height, is set 4 percent smaller and tighter, and draws its bold lighter: weight 700 sits at 640 on the design axis. [Katagami Text](/katagami-text)."),
          ("h2", "Katagami Serif"), ("specimen", FACE["serif"], "A katagami is a paper stencil for dyeing cloth.", 30, 400),
          ("p", "Katagami Serif is Katagami Text with rectangular serifs and a light contrast, for text that should read as a serif. [Katagami Serif](/katagami-serif)."),
          ("table", ["Font", "License", "Weights", "Variable axes", "Notable features"],
           [["Katagami Text", "SIL Open Font License 1.1", "100 to 900", "wght", "Lower x-height, tighter spacing, lighter bold"],
            ["Katagami Serif", "SIL Open Font License 1.1", "100 to 900", "wght", "Rectangular serifs, light contrast"],
            *[row(n) for n in ("Source Serif 4", "IBM Plex Serif", "NewsSerif", "Signifier")]])],
         [("Library", "/library"), ("Guides", "/library#guides"), ("Fonts for long reading", "/fonts-for/reading")], image="guide", group="Guides")
    st = M["stats"]["sans"]
    page("/fonts-for/many-languages", "A free font for many languages: Katagami's coverage", "Katagami sets the main language of places where 99.9 percent of people live: Latin, Greek and Cyrillic drawn, 19 more scripts merged, and Chinese, Japanese and Korean companions.",
         "Fonts for many languages", f"Katagami sets {st['languages']} of the {st['of']} languages on its map in full, the main language of places where {st['people']} percent of people live.",
         [("h2", "How the coverage works"),
          ("list", ["Latin, Greek and Cyrillic are drawn in Katagami's own design.", "19 more scripts are merged from Noto Sans and scaled to Katagami's x-height.",
                    "Chinese, Japanese and Korean come from four companion fonts.", "On the web, every script is its own file, so a page loads only the scripts it shows."]),
          ("h2", "Scripts"), ("cards", [(s["name"], s["card"], s["path"]) for s in SCRIPT_INDEX if s["covered"]]),
          ("h2", "Not covered yet"), ("cards", [(s["name"], s["card"], s["path"]) for s in SCRIPT_INDEX if not s["covered"]]),
          ("p", "The [map](/map) shows where each language is spoken, and every language has [its own page](/languages).")],
         [("Library", "/library"), ("Guides", "/library#guides"), ("Fonts for many languages", "/fonts-for/many-languages")], image="guide", group="Guides")
    page("/free-for-commercial-use", "Is Katagami free for commercial use? The SIL Open Font License", "Katagami is free for commercial use under the SIL Open Font License 1.1: what the license allows, what it asks, and how it applies to apps, websites and print.",
         "Free for commercial use", "Katagami is released under the SIL Open Font License 1.1. You can use it in any product, commercial or not.",
         [("h2", "What the license allows"),
          ("list", ["Using the fonts in apps, websites, documents, print, video and logos, commercial or not.", "Embedding the fonts in software and documents.",
                    "Changing the fonts and sharing your changed version.", "Bundling the fonts with other software, including software you sell."]),
          ("h2", "What it asks"),
          ("list", ["Keep the license and the copyright notices with the font files when you share them.", "Give a changed version a new name.",
                    "Do not sell the fonts on their own.", "Release a changed version under the same license."]),
          ("h2", "Questions"),
          ("faq", [("Can I use Katagami in a logo?", "Yes. The license covers the use of the fonts, including in logos, and does not apply to what you make with them."),
                   ("Do I need to credit Katagami?", "The license does not require credit in what you make. Keep the license with the font files if you share the files."),
                   ("Can I host the fonts on my own server?", "Yes. Self-hosting is sharing the files with your visitors' browsers, which the license allows; keep the license next to them."),
                   ("Where is the license?", f"In the repository as [OFL.txt]({REPO}/blob/main/OFL.txt), and at [openfontlicense.org](https://openfontlicense.org/).")])],
         [("Library", "/library"), ("Guides", "/library#guides"), ("Free for commercial use", "/free-for-commercial-use")], image="guide", group="Guides")
    page("/learn/variable-fonts", "What is a variable font? Katagami's weight axis explained", "A variable font holds a whole range of a design in one file. How Katagami's weight axis works, what named styles are, and how to use any weight in CSS.",
         "Variable fonts", "A variable font stores a design's extremes in one file and lets the renderer draw any point between them.",
         [("h2", "How Katagami uses it"),
          ("p", "Each Katagami member is one variable TrueType file with a weight axis, `wght`, from 100 to 900 (Katagami Mono 100 to 700). The build draws three masters, Thin, Regular and Black, with the same points in the same order, and the font interpolates between them."),
          ("specimen", FACE["sans"], "Thin 100 · Regular 400 · Black 900", 34, 400),
          ("h2", "Named styles"), ("p", "The files also name nine styles, Thin, ExtraLight, Light, Regular, Medium, SemiBold, Bold, ExtraBold and Black, so apps that do not handle variable fonts list them as separate styles."),
          ("h2", "In CSS"), ("p", "Any weight works, not only multiples of 100:"), ("code", "css", ".title { font-family: \"Katagami Sans\"; font-weight: 650; }"),
          ("p", "Animate it with a transition on `font-weight`, as the footer of this site does.")],
         [("Library", "/library"), ("Learn", "/library#learn"), ("Variable fonts", "/learn/variable-fonts")], image="learn", group="Learn")
    page("/learn/opentype-features", "OpenType features in CSS: tabular figures, small caps and alternates", "What OpenType features are, how to turn them on with font-feature-settings and font-variant, and the ones Katagami has.",
         "OpenType features", "OpenType features are substitutions a font carries and a browser applies on request: other figures, small capitals, alternate letters and ligatures.",
         [("h2", "Turning them on"), ("p", "Use the `font-variant` property where CSS has one, and `font-feature-settings` with the four-letter tag for the rest."),
          ("code", "css", ".price { font-variant-numeric: tabular-nums; }\n.legal { font-variant-caps: small-caps; }\n.code { font-feature-settings: \"dlig\"; }"),
          ("h2", "Common tags"),
          ("table", ["Tag", "Name", "CSS"], [["tnum", "Tabular figures", "font-variant-numeric: tabular-nums"], ["frac", "Fractions", "font-variant-numeric: diagonal-fractions"],
                                             ["smcp", "Small capitals", "font-variant-caps: small-caps"], ["case", "Case-sensitive forms", "font-feature-settings: \"case\""],
                                             ["zero", "Slashed zero", "font-variant-numeric: slashed-zero"], ["ss01 to ss20", "Stylistic sets", "font-feature-settings: \"ss01\""],
                                             ["cv01 to cv99", "Character variants", "font-feature-settings: \"cv01\""], ["dlig", "Discretionary ligatures", "font-variant-ligatures: discretionary-ligatures"]]),
          ("h2", "Katagami's features"), ("p", f"Katagami Sans has {len(F['sans']['features'])} features you can switch. The [features page](/features) shows every one off and on in each member.")],
         [("Library", "/library"), ("Learn", "/library#learn"), ("OpenType features", "/learn/opentype-features")], image="learn", group="Learn")
    page("/learn/squared-curves", "Squared curves: the handle fraction behind Katagami's bowls", "How far a curve's handles reach toward its corner decides how square a bowl looks. The handle fraction f for a circle and for each Katagami member.",
         "Squared curves", "A quarter arc sits in a box whose corner is where its two end tangents meet. The handle fraction f is how far each handle reaches toward that corner.",
         [("h2", "The numbers"),
          ("table", ["Curve", "Handle fraction f", "Superellipse exponent n"], [["Circle", "0.552", "2.00"], ["Katagami Text", "0.59", "2.13"], ["Katagami Round", "0.69", "2.43"], ["Katagami Sans", "0.73", "2.62"]]),
          ("p", "A larger f reaches further toward the corner and reads as squarer. The exponent n is the superellipse with the same reach: n = -1 / log2(0.375 f + 0.5)."),
          ("h2", "How Katagami squares a bowl"),
          ("p", "The build moves each curve's handles toward the corner by a share of the remaining distance, 0.36 above and 0.32 below in Katagami Sans, and condenses round letters so the squared corners carry the area the narrower width removes. The [Curves table on the home page](/#curves) measures f from the outlines in your browser.")],
         [("Library", "/library"), ("Learn", "/library#learn"), ("Squared curves", "/learn/squared-curves")], image="learn", group="Learn")
    page("/learn/katagami-stencils", "What is katagami? The Japanese paper stencils behind the name", "Katagami (型紙, pattern paper) are Japanese paper stencils for dyeing cloth, cut by hand in Suzuka. How they are made and the four ways the pattern is cut.",
         "Katagami stencils", "Katagami (型紙, “pattern paper”) are paper stencils for dyeing cloth, cut in Shiroko and Jike in Suzuka, Mie, for more than five hundred years.",
         [("h2", "How a stencil is made"),
          ("list", ["Sheets of washi are bonded with kakishibu, a fermented persimmon tannin that turns them brown and tough.", "A cutter carves the pattern through the layers.",
                    "A fine silk net holds the loose pieces in place.", "Rice paste goes through the holes onto the cloth, the cloth is dyed, and the paste washes out to leave the pattern white."]),
          ("h2", "Four ways to cut"),
          ("table", ["Cut", "How"], [["Kiribori", "A semicircular blade turned against the paper punches round holes, up to about a hundred to the square centimetre."],
                                     ["Tsukibori", "The knife is pushed away from the cutter through every layer at once, for free lines and curves."],
                                     ["Dōgubori", "Punches ground to a shape press out the same flower or diamond again and again."],
                                     ["Shimabori", "Stripes cut along a ruler, each one traced three times with a small blade."]]),
          ("h2", "The type family"), ("p", "The typeface took the name because it is made by cutting: squared curves, level terminals and a K cut from a square. [About Katagami](/about) has the story and a stencil you can cut with your own word.")],
         [("Library", "/library"), ("Learn", "/library#learn"), ("Katagami stencils", "/learn/katagami-stencils")], image="learn", group="Learn")



# ---------- agents ----------

# the same prompt the machine view of the site offers (site.js PROMPT)
AGENT_PROMPT = (f"Set this project's fonts to Katagami. Read {SITE_URL}/llms.txt first. Link {SITE_URL}/fonts/katagami.css and use "
                '"Katagami Sans" for interface text, "Katagami Serif" for long reading and "Katagami Mono" for code, each with a system fallback. '
                "Leave code ligatures off. Change nothing else.")
# the characters agent interfaces print for state, checked against Katagami Mono when the pages are written
STATUS_GLYPHS = "⏺⎿✓✗✔✘●○◉◆▶▸›…⏵⏸⏹⚠✕★☆✻✢✳✶✽•→←↑↓"


def agent_pages(F: dict) -> None:
    """Two explainers for agents and the people who set them up: agent-native
    fonts, and the fonts coding agents print in. Katagami Mono's coverage is read
    from the built font."""
    cmap = TTFont(FONTS["mono"], lazy=True).getBestCmap()
    def covered(lo: int, hi: int) -> str:
        return f"{sum(1 for u in range(lo, hi + 1) if u in cmap)} of {hi - lo + 1}"
    rows = [[name, f"U+{lo:04X} to U+{hi:04X}", use, covered(lo, hi)] for name, lo, hi, use in (
        ("Box drawing", 0x2500, 0x257F, "panels, borders and tables"), ("Block elements", 0x2580, 0x259F, "progress bars and meters"),
        ("Braille patterns", 0x2800, 0x28FF, "spinners such as ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"), ("Arrows", 0x2190, 0x21FF, "steps, moves and keys"))]
    have = " ".join(ch for ch in STATUS_GLYPHS if ord(ch) in cmap)
    lacks = " ".join(ch for ch in STATUS_GLYPHS if ord(ch) not in cmap)
    page("/learn/fonts-in-coding-agents", "Fonts in coding agents: what a terminal font has to draw",
         "Coding agents print their interface as text in a terminal grid. The characters they use, what the font has to get right, and how to set Katagami Mono in each terminal.",
         "Fonts in coding agents", "A coding agent that runs in a terminal prints in the terminal's font. The agent picks the characters, and the terminal picks how they look.",
         [("h2", "What an agent prints"),
          ("p", "An agent's interface is text in a grid of cells. Around the code and the prose it draws panels and tables with box-drawing characters, progress with block elements, spinners with Braille patterns, and steps and results with arrows, check marks and bullets."),
          ("code", "text", "╭─ plan ─────────────────────╮\n│ ⠋ reading 12 files         │\n│ ✓ tests pass  ▕████▌       │\n│ → edit src/fonts.ts        │\n╰────────────────────────────╯"),
          ("p", "When the font lacks one of these characters, the terminal draws it from another font, usually at another width, and the columns after it stop lining up."),
          ("h2", "What the font needs"),
          ("list", ["One cell width for every glyph, symbols included.",
                    "0 and O, and 1, l and I drawn apart, because agents print hashes, IDs, tokens and paths that people copy.",
                    "Ligatures off unless asked for, so `->` and `!=` show the characters the agent wrote and a diff shows what changed.",
                    "The box-drawing, block and Braille ranges in the font itself.",
                    "Weights that hold up when an interface bolds a heading or dims a note."]),
          ("h2", "Katagami Mono"),
          ("table", ["Range", "Code points", "Used for", "Katagami Mono"], rows),
          ("p", f"Status characters it draws: {have}." + (f" Not yet: {lacks}." if lacks else "")),
          ("p", "Its cell is 1,280 units, 0.625 em. Code ligatures for `->`, `=>`, `!=`, `==` and `>=` stay off until you turn on `dlig`, and each character in a ligature keeps its own cell."),
          ("h2", "Set it in your terminal"),
          ("table", ["Terminal", "Setting"], [["Ghostty", '`font-family = "Katagami Mono"` in `~/.config/ghostty/config`'], ["Kitty", "`font_family Katagami Mono` in `kitty.conf`"],
                                              ["WezTerm", '`config.font = wezterm.font("Katagami Mono")`'], ["Alacritty", '`family = "Katagami Mono"` under `[font.normal]`'],
                                              ["iTerm2", "Settings, Profiles, Text, Font"], ["Windows Terminal", '`"font": { "face": "Katagami Mono" }` in a profile'],
                                              ["VS Code and Cursor", '`"terminal.integrated.fontFamily": "Katagami Mono"`'], ["Zed", '`"terminal": { "font_family": "Katagami Mono" }`']]),
          ("p", "Install `KatagamiMono[wght].ttf` from the [download page](/download) first, then restart the terminal."),
          ("p", "[Agent-native fonts](/learn/agent-native-fonts) covers what an agent needs to find and install a font on its own.")],
         [("Library", "/library"), ("Learn", "/library#learn"), ("Fonts in coding agents", "/learn/fonts-in-coding-agents")], image="learn", group="Learn")
    page("/learn/agent-native-fonts", "Agent-native fonts: a font an agent can find, read and install",
         "What an agent needs from a font: text it can read, an index, a license it can act on, stable addresses and facts as data. How Katagami provides each, with a prompt for a coding agent.",
         "Agent-native fonts", "An agent-native font is one an agent can find, read about, install and set up without a person in between. Katagami publishes what an agent needs as plain text at stable addresses.",
         [("h2", "What an agent needs"),
          ("table", ["Need", "On this site"], [
              ["Text it can read", "Every page has a Markdown twin at the same address with `.md`, and a request that sends `Accept: text/markdown` gets it."],
              ["An index", "[/llms.txt](/llms.txt) lists every page, and [/llms-full.txt](/llms-full.txt) holds the whole site in one file."],
              ["A license it can act on", "The SIL Open Font License 1.1 allows bundling the fonts into a repository, an app or a site, so an agent can add them to a project."],
              ["Stable addresses", "The stylesheet is at `/fonts/katagami.css` with open CORS, and [/download/files.json](/download/files.json) lists every font file with its size."],
              ["Facts as data", "Each member's metrics, characters and OpenType features are in `/data.js`."],
              ["Lines that stay put", "Every member has the same line metrics, an ascender of 1984 and a descender of -494 on a 2048 em, so swapping one member for another does not move the lines."]]),
          ("h2", "A prompt for a coding agent"),
          ("code", "text", AGENT_PROMPT),
          ("p", "The prompt names the stylesheet and the families and limits the change, so the diff stays small enough to review."),
          ("h2", "The machine view"),
          ("p", "The Machine switch at the top of every page shows that page as an agent reads it: its Markdown twin, set in Katagami Mono."),
          ("h2", "In the terminal"),
          ("p", "Agents that run in a terminal print in the terminal's font. [Fonts in coding agents](/learn/fonts-in-coding-agents) covers what that font has to draw and how to set it.")],
         [("Library", "/library"), ("Learn", "/library#learn"), ("Agent-native fonts", "/learn/agent-native-fonts")], image="learn", group="Learn")


# ---------- scripts and languages ----------

SCRIPT_INDEX: list[dict] = []


def script_and_language_pages(F: dict, C: dict, M: dict) -> None:
    langs = M["languages"]
    sets = M["sets"]
    covered = {k: set(v) for k, v in M["coverage"].items()}
    script_of = {tag: sets[l["sets"][0]]["script"] for tag, l in langs.items() if l["sets"]}
    by_script: dict[str, list] = {}
    for tag, code in script_of.items():
        by_script.setdefault(code, []).append(tag)

    def members_for(tag):
        return [k for k in MEMBERS if k in covered and all(s in covered[k] for s in langs[tag]["sets"])]

    entries = [(n, codes, ("drawn", r)) for n, (r, codes) in DRAWN.items()]
    entries += [(DISPLAY.get(n, n), {CODES[n]}, ("merged", r)) for n, r in SCRIPTS.items()]
    entries += [(n, codes, ("companion", stem)) for n, (stem, codes) in COMPANIONS.items()]
    entries += [(n, {c}, ("none", None)) for n, c in NOT_YET.items()]
    for name, codes, (how, src) in entries:
        tags = sorted((t for c in codes for t in by_script.get(c, [])), key=lambda t: -langs[t]["speakers"])
        path = f"/scripts/{slug(name)}"
        if how == "companion":
            c = C.get(name, {})
            counts = [[FAMILY[k], f"{c.get('characters', 0):,} from {c.get('file', '')}" if k != "mono" else "not covered"] for k in MEMBERS]
            ok = bool(c)
        elif how == "none":
            counts = [[FAMILY[k], "not covered yet"] for k in MEMBERS]
            ok = False
        else:
            counts = [[FAMILY[k], f"{F[k]['scripts'].get(name, 0):,} characters" if F[k]["scripts"].get(name) else "not covered"] for k in MEMBERS]
            ok = True
        letters = sets[langs[tags[0]]["sets"][0]]["glyphs"].replace(" ", "") if tags else ""
        speakers = sum(langs[t]["speakers"] for t in tags)
        source = {"drawn": "drawn in Katagami's own design", "merged": "merged from Noto Sans and scaled to Katagami's x-height",
                  "companion": "set by a Katagami CJK companion font", "none": "not covered yet"}[how]
        card = f"{len(tags)} languages on the map, {compact(speakers)} speakers, {source}."
        SCRIPT_INDEX.append({"name": name, "path": path, "covered": ok, "card": card})
        blocks = []
        if letters and ok:
            blocks.append(("specimen", FACE["sans"], letters[:60], 40, 400))
        blocks += [("h2", "Coverage"), ("table", ["Member", name], counts),
                   ("p", f"{name} in Katagami is {source}." + (" On the web, the stylesheet loads its file only on pages that show it." if ok else
                                                               " Pages that use it fall back to the next font in the stack."))]
        if tags:
            blocks += [("h2", "Languages on the map"),
                       ("table", ["Language", "Own name", "Speakers", "Covered by"],
                        [[f"[{langs[t]['en']}](/languages/{t})", langs[t]["own"] or langs[t]["en"], compact(langs[t]["speakers"]),
                          ", ".join(FAMILY[k].split()[1] for k in members_for(t)) or "not yet"] for t in tags])]
        if ok:
            blocks += [("h2", "Use it on the web"), ("code", "html", WEB_SNIPPET), ("code", "css", ':lang(' + (langs[tags[0]].get("bcp", tags[0]) if tags else "x") + ') { font-family: "Katagami Sans", sans-serif; }')]
        page(path, f"{name} in Katagami: {'a free font for ' + name if ok else name + ' is not covered yet'}",
             f"{name} in the Katagami type family: {source}, with {len(tags)} languages on the map and {compact(speakers)} speakers. Free under the SIL Open Font License." if ok else
             f"{name} is not covered by Katagami yet. {len(tags)} languages on the map use it, with {compact(speakers)} speakers.",
             name, f"{name} is {source} in Katagami. {card}", blocks, [("Library", "/library"), ("Scripts", "/scripts"), (name, path)],
             image="script", group="Scripts", card=card)
    page("/scripts", "Scripts in Katagami: 22 drawn or merged, plus Chinese, Japanese and Korean", "Every writing system in Katagami: which are drawn, merged or set by a companion font, how many characters each has, and which are not covered yet.",
         "Scripts", "Katagami draws Latin, Greek and Cyrillic, merges 19 more scripts and sets Chinese, Japanese and Korean through companion fonts.",
         [("h2", "Covered"), ("cards", [(s["name"], s["card"], s["path"]) for s in SCRIPT_INDEX if s["covered"]]),
          ("h2", "Not covered yet"), ("cards", [(s["name"], s["card"], s["path"]) for s in SCRIPT_INDEX if not s["covered"]])],
         [("Library", "/library"), ("Scripts", "/scripts")], image="script", schema="CollectionPage")

    for tag, l in langs.items():
        if not l["sets"]:
            continue
        code = script_of.get(tag)
        sname = SCRIPT_NAME_OF_CODE.get(code, code)
        ms = members_for(tag)
        letters = sets[l["sets"][0]]["glyphs"]
        own = l["own"] or l["en"]
        path = f"/languages/{tag}"
        same = [t for t in sorted(by_script.get(code, []), key=lambda t: -langs[t]["speakers"]) if t != tag][:8]
        status = (f"Katagami sets {l['en']} in full in {', '.join(FAMILY[k] for k in ms)}." if ms else
                  f"Katagami does not cover {l['en']} yet: its {sname} letters are not in the fonts.")
        blocks = []
        if ms:
            blocks += [("specimen", FACE[ms[0]], own, 64, 600), ("specimen", FACE[ms[0]], letters, 30, 400)]
        blocks += [("h2", "At a glance"),
                   ("table", ["", l["en"]], [["Own name", own], ["Script", f"[{sname}](/scripts/{slug(sname)})"], ["Speakers", compact(l["speakers"])],
                                             ["Letters on the map", str(len(letters.split()))], ["Covered by", ", ".join(FAMILY[k] for k in ms) or "not yet"]]),
                   ("p", status + f" The [map](/map?lang={tag}) shows where it is spoken.")]
        if ms:
            blocks += [("h2", f"Set {l['en']} in Katagami"), ("code", "html", WEB_SNIPPET),
                       ("code", "css", f':lang({tag}) {{ font-family: "{FAMILY[ms[0]]}", sans-serif; }}')]
        if same:
            blocks += [("h2", f"Other languages in {sname}"), ("cards", [(langs[t]["en"], f"{langs[t]['own'] or langs[t]['en']}, {compact(langs[t]['speakers'])} speakers", f"/languages/{t}") for t in same])]
        title = f"{l['en']} font: {'Katagami, free for ' + l['en'] if ms else l['en'] + ' in Katagami is not covered yet'}"
        page(path, title, f"{status} {l['en']} ({own}) is written in {sname} and has {compact(l['speakers'])} speakers. Katagami is free under the SIL Open Font License.",
             f"{l['en']}", status, blocks, [("Library", "/library"), ("Languages", "/languages"), (l["en"], path)], image="language", group="Languages",
             card=f"{own}, {compact(l['speakers'])} speakers")
    rows = sorted(((t, l) for t, l in langs.items() if l["sets"]), key=lambda x: -x[1]["speakers"])
    page("/languages", "Languages in Katagami: every language on the map", "Every language on Katagami's map with its own name, script, speakers and whether Katagami sets it in full.",
         "Languages", f"The {len(rows)} languages on Katagami's map, by number of speakers.",
         [("table", ["Language", "Own name", "Script", "Speakers", "Covered"],
           [[f"[{l['en']}](/languages/{t})", l["own"] or l["en"], SCRIPT_NAME_OF_CODE.get(script_of.get(t), ""), compact(l["speakers"]), "yes" if members_for(t) else "not yet"] for t, l in rows])],
         [("Library", "/library"), ("Languages", "/languages")], image="language", schema="CollectionPage")


def library_page() -> None:
    groups = [("Members", "members"), ("Compare", "compare"), ("Guides", "guides"), ("Learn", "learn")]
    blocks = []
    for name, anchor in groups:
        items = [p for p in PAGES if p["group"] == name]
        if items:
            blocks += [("h2", name), ("cards", [(p["h1"], p["card"], p["path"]) for p in items])]
    blocks += [("h2", "Scripts"), ("p", "[Every script in Katagami](/scripts), drawn, merged or set by a companion font."),
               ("h2", "Languages"), ("p", f"[Every language on the map](/languages), {sum(1 for p in PAGES if p['group'] == 'Languages')} pages."),
               ("h2", "For machines"), ("p", "Every page has a Markdown twin at the same address with `.md`, and the whole site is in [llms.txt](/llms.txt) and [llms-full.txt](/llms-full.txt).")]
    page("/library", "Katagami library: members, comparisons, guides, scripts and languages", "Everything about the Katagami type family in one place: each member, comparisons with other typefaces, guides, explainers, and a page for every script and language.",
         "Library", "Pages about each member, comparisons with other typefaces, guides, and a page for every script and language Katagami sets.",
         blocks, [("Library", "/library")], image="library", schema="CollectionPage")


# ---------- output ----------

LIB_CSS = """/* The library pages: a head, then one reading column. Space follows the
   site's scale: 96px between sections (56px on a phone), 32px between blocks
   (24px), 16px from a heading to its content and between paragraphs. */
.lib-crumbs { display: flex; flex-wrap: wrap; gap: 6px; font-size: 0.8125rem; color: var(--ink-2); margin-bottom: 18px; }
.lib-crumbs a { color: var(--ink-2); text-decoration: none; }
.lib-crumbs a:hover { color: var(--cut); }
.lib-crumbs span + span::before { content: "/"; margin-right: 6px; color: var(--rule); }
.lib-head h1 { font-size: clamp(2.5rem, 6vw, 4.75rem); line-height: 0.98; letter-spacing: -0.035em; font-weight: 650; max-width: 18ch; }
.lib-head p { margin-top: 16px; font-size: 1.1875rem; line-height: 1.5; color: var(--ink-2); max-width: 60ch; }
.lib-body { padding-block: 8px clamp(56px, 6.67vw, 96px); max-width: 920px; }
.lib-body > * { margin-block: 0; }
.lib-body > * + * { margin-top: clamp(24px, 2.22vw, 32px); }
.lib-body > h2 { font-size: var(--step-2); letter-spacing: -0.02em; margin-top: clamp(56px, 6.67vw, 96px); }
.lib-body > h2:first-child { margin-top: 0; }
.lib-body > h2 + *, .lib-body > p + p, .lib-body > .specimen + .specimen, .lib-body > pre + pre { margin-top: 16px; }
.lib-body p, .lib-body li { font-size: 1.0625rem; line-height: 1.6; max-width: 68ch; }
.lib-body ul { padding-left: 1.2rem; display: grid; gap: 8px; }
.lib-body ul.lib-cols { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px 32px; }
.lib-body code { font-family: var(--mono); font-size: 0.875em; background: var(--panel); padding: 1px 5px; border-radius: 4px; }
.lib-body .specimen { line-height: 1.15; letter-spacing: -0.01em; overflow-wrap: anywhere; max-width: none; }
.t-scroll { overflow-x: auto; }
.lib-body table { width: 100%; border-collapse: collapse; font-size: 0.9375rem; }
.lib-body th, .lib-body td { text-align: left; vertical-align: top; padding: 10px 16px 10px 0; }
.lib-body th { font-weight: 500; font-size: 0.8125rem; color: var(--ink-2); }
.lib-body tbody tr + tr td { box-shadow: inset 0 1px 0 color-mix(in srgb, var(--ink) 7%, transparent); }
.lib-body td:first-child { color: var(--ink-2); }
.lib-split { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px 40px; align-items: start; }
.lib-split th:last-child, .lib-split td:last-child { text-align: right; padding-right: 0; font-variant-numeric: tabular-nums; }
.lib-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 16px; }
.lib-card { display: grid; gap: 8px; align-content: start; padding: 18px 20px; border-radius: 8px; background: var(--panel); text-decoration: none; color: var(--ink); }
.lib-card:hover { background: color-mix(in srgb, var(--ink) 8%, var(--panel)); color: var(--ink); }
.lib-card b { font-weight: 600; }
.lib-card span { font-size: 0.875rem; color: var(--ink-2); line-height: 1.45; }
.lib-faq { display: grid; gap: 16px; }
.lib-faq details { background: var(--panel); border-radius: 8px; padding: 16px 20px; }
.lib-faq summary { font-weight: 600; cursor: pointer; }
.lib-faq p { margin-top: 8px; color: var(--ink-2); }
.lib-sources { font-size: 0.8125rem; color: var(--ink-2); }
.lib-sources ul { margin: 6px 0 0; }
.lib-sources a { overflow-wrap: anywhere; }
@media (max-width: 900px) { .lib-body ul.lib-cols { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .lib-split { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; } }
@media (max-width: 560px) { .lib-body ul.lib-cols { grid-template-columns: 1fr; } }
"""


def write() -> None:
    facts, stamps = site_facts(), None
    (SITE / "library.css").write_text(LIB_CSS)
    stamps = asset_stamps()
    urls = [(meta[0], "/" + target.removesuffix(".html").replace("index", "")) for target, meta in PAGE_META.items()]
    for p in PAGES:
        body, md = render(p["blocks"])
        crumbs = "".join(f'<span><a href="{h}">{html.escape(n)}</a></span>' for n, h in p["crumbs"][:-1])
        fragment = (f'<link rel="stylesheet" href="/fonts/katagami.css">\n<link rel="stylesheet" href="/library.css">\n<!-- site:nav -->\n'
                    f'<main>\n  <div class="wrap lib-head" style="padding-block: clamp(36px, 6vw, 72px) 24px">\n'
                    f'    <nav class="lib-crumbs" aria-label="Breadcrumb">{crumbs}</nav>\n    <h1>{html.escape(p["h1"])}</h1>\n    <p>{inline(p["lede"])}</p>\n  </div>\n'
                    f'  <article class="wrap lib-body">\n{body}\n  </article>\n</main>\n<!-- site:footer -->\n'
                    '<script>document.addEventListener("click",(e)=>{const b=e.target.closest("button[data-copy]");if(!b)return;'
                    'const t=[...b.parentNode.childNodes].filter((n)=>n.nodeType===3).map((n)=>n.textContent).join("");'
                    'navigator.clipboard?.writeText(t).then(()=>{b.textContent="Copied";setTimeout(()=>(b.textContent="Copy"),1400)})});</script>')
        meta = {"path": p["path"], "title": p["title"], "description": p["description"], "image": p["image"], "schema": p["schema"]}
        extra = list(p["extra"])
        faqs = faq_nodes(p["blocks"])
        if faqs:
            extra.append({"@type": "FAQPage", "@id": f"{SITE_URL}{p['path']}#faq", "mainEntity": faqs})
        meta["graph"] = page_graph(meta, facts, p["crumbs"], extra)
        out = SITE / (p["path"].lstrip("/") + ".html")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(wrap(fragment, p["path"], meta, facts, stamps))
        twin = f"# {p['h1']}\n\n{md_link(p['lede'])}\n\n{md}\n\n---\n\nSource: {SITE_URL}{p['path']}\n"
        (SITE / (p["path"].lstrip("/") + ".md")).write_text(twin)
        p["md"] = twin
        urls.append((p["title"], p["path"]))
    write_twins_for_main(facts)
    write_llms(facts)
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for _, path in urls:
        prio = "1.0" if path == "/" else "0.8" if path.count("/") == 1 and not path.startswith(("/languages/", "/scripts/")) else "0.5"
        sitemap.append(f"  <url><loc>{SITE_URL}{path}</loc><lastmod>{TODAY}</lastmod><priority>{prio}</priority></url>")
    sitemap.append("</urlset>")
    (SITE / "sitemap.xml").write_text("\n".join(sitemap) + "\n")
    bots = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User", "Claude-SearchBot", "PerplexityBot", "Perplexity-User",
            "Google-Extended", "Applebot-Extended", "CCBot", "Amazonbot", "DuckAssistBot", "meta-externalagent", "MistralAI-User", "cohere-ai"]
    (SITE / "robots.txt").write_text("# Katagami is free and open source; search and answer engines are welcome everywhere but the relay.\n"
                                     "User-agent: *\nAllow: /\nDisallow: /api/\n\n"
                                     + "".join(f"User-agent: {b}\nAllow: /\nDisallow: /api/\n\n" for b in bots)
                                     + f"Sitemap: {SITE_URL}/sitemap.xml\n")
    (SITE / "site.webmanifest").write_text(json.dumps({"name": "Katagami", "short_name": "Katagami", "start_url": "/", "display": "standalone",
                                                       "background_color": "#f1f2ef", "theme_color": "#f1f2ef",
                                                       "icons": [{"src": "/favicon.png", "sizes": "64x64", "type": "image/png"},
                                                                 {"src": "/apple-touch-icon.png", "sizes": "180x180", "type": "image/png"},
                                                                 {"src": "/favicon.svg", "type": "image/svg+xml", "sizes": "any"}]}, indent=1) + "\n")
    og = [{"slug": meta[2], "title": meta[0].split(":")[0], "subtitle": meta[0].split(":", 1)[1].strip() if ":" in meta[0] else ""} for meta in PAGE_META.values()]
    og += [{"slug": f"member-{k}", "title": FAMILY[k], "subtitle": next(p["title"].split(":", 1)[1].strip() for p in PAGES if p["path"] == MEMBER_PATHS[k]), "member": k} for k in MEMBERS]
    og += [{"slug": s, "title": t, "subtitle": d} for s, t, d in [("library", "Library", "Members, comparisons, guides, scripts and languages"),
                                                                    ("compare", "Compare", "Katagami side by side with other typefaces"),
                                                                    ("guide", "Guides", "Choosing a free font for code, interfaces, reading and many languages"),
                                                                    ("learn", "Learn", "Variable fonts, OpenType features, squared curves and katagami stencils"),
                                                                    ("script", "Scripts", "22 scripts drawn or merged, plus Chinese, Japanese and Korean"),
                                                                    ("language", "Languages", f"{len([p for p in PAGES if p['group'] == 'Languages'])} languages on the map")]]
    (ROOT / "build" / "og.json").write_text(json.dumps(og, ensure_ascii=False, indent=1))
    print(f"{len(PAGES)} library pages, {len(urls)} URLs in the sitemap, {len(og)} card images to draw")


MAIN_TWINS = {}


def write_twins_for_main(facts: dict) -> None:
    """Markdown twins of the hand-written pages: what each page says, in text."""
    F = FACTS["members"]
    members = "\n".join(f"- [{F[k]['family']}]({SITE_URL}{MEMBER_PATHS[k]}): weights {F[k]['weights'][0]} to {F[k]['weights'][1]}, {F[k]['characters']:,} characters, {F[k]['glyphs']:,} glyphs."
                        for k in MEMBERS)
    st = FACTS["map"]["stats"]["sans"]
    MAIN_TWINS.update({
        "index": f"# Katagami\n\n{PAGE_META['index.html'][1]}\n\n## Members\n\n{members}\n\n## Coverage\n\nLatin, Greek and Cyrillic are drawn; 19 more scripts are merged; Chinese, Japanese and Korean come from four companion fonts. Katagami sets the main language of places where {st['people']} percent of people live ({st['languages']} of {st['of']} languages on the map).\n\n## Use it\n\n```html\n{WEB_SNIPPET}\n```\n\nDownload: {SITE_URL}/download. Source: {REPO}. License: SIL Open Font License 1.1.\n\n## More\n\n- Glyphs: {SITE_URL}/glyphs\n- Features: {SITE_URL}/features\n- Map: {SITE_URL}/map\n- Font-ify: {SITE_URL}/convert\n- Library: {SITE_URL}/library\n",
        "glyphs": f"# Katagami glyphs\n\n{PAGE_META['glyphs.html'][1]}\n\n" + "\n".join(f"- {F[k]['family']}: {F[k]['characters']:,} characters, {F[k]['glyphs']:,} glyphs." for k in MEMBERS) + f"\n\nSearch: {SITE_URL}/glyphs?q=omega\n",
        "features": f"# Katagami OpenType features\n\n{PAGE_META['features.html'][1]}\n\n" + "\n".join(f"- `{t}` {lab}".rstrip() for t, lab in F["sans"]["features"].items()) + "\n\nTurn one on with `font-feature-settings: \"tnum\";`.\n",
        "map": f"# Where Katagami writes\n\n{PAGE_META['map.html'][1]}\n\n" + "\n".join(f"- {FAMILY[k]}: {s['people']} percent of people, {s['languages']} of {s['of']} languages, {s['land']} percent of mapped land." for k, s in FACTS["map"]["stats"].items()) + f"\n\nEvery language: {SITE_URL}/languages. Every script: {SITE_URL}/scripts.\n",
        "convert": f"# Font-ify\n\n{PAGE_META['convert.html'][1]}\n\nRules: a monospace stack becomes Katagami Mono, a serif stack becomes Katagami Serif, icon fonts and `var()` stacks stay, and everything else becomes the member you pick. The original stack stays behind Katagami as its fallback.\n\nOpen a site directly: {SITE_URL}/convert?url=example.com\n",
        "about": f"# About Katagami\n\n{PAGE_META['about.html'][1]}\n\nKatagami was started on 7 October 2026 by Kevin Liu to be one family that feels like a coherent system: a sans, a rounded sans, a reading face, a serif and a mono on one skeleton. It starts from Inter's open-source outlines; its merged scripts and CJK companions come from Noto. The name comes from katagami (型紙, pattern paper), Japanese paper stencils cut to dye patterns on cloth.\n\nMore: {SITE_URL}/learn/katagami-stencils\n",
        "faq": f"# Katagami FAQ\n\n" + "\n\n".join(f"## {q['name']}\n\n{q['acceptedAnswer']['text']}" for q in FACTS["faq"]) + "\n",
        "download": f"# Download Katagami\n\n{PAGE_META['download.html'][1]}\n\nZip: {SITE_URL}/download/Katagami-0.1.zip\n\n" + "\n".join(f"- {F[k]['family']}: `{F[k]['file']}`, {mb(F[k]['size'])}." for k in MEMBERS) + f"\n\nWeb:\n\n```html\n{WEB_SNIPPET}\n```\n",
    })
    for name, text in MAIN_TWINS.items():
        (SITE / f"{name}.md").write_text(text + f"\n---\n\nSource: {SITE_URL}/{'' if name == 'index' else name}\n")


def write_llms(facts: dict) -> None:
    def section(name, items):
        return f"## {name}\n\n" + "\n".join(f"- [{p['title']}]({SITE_URL}{p['path']}.md): {p['description']}" for p in items) + "\n"
    head = (f"# Katagami\n\n> {PAGE_META['index.html'][1]}\n\nKatagami is made by Kevin Liu. Version 0.1. Source: {REPO}. "
            f"Every page on {SITE_URL} has a Markdown twin at the same address with `.md`.\n\n")
    main = "## Main pages\n\n" + "\n".join(f"- [{m[0]}]({SITE_URL}/{'index' if t == 'index.html' else t.removesuffix('.html')}.md): {m[1]}" for t, m in PAGE_META.items()) + "\n"
    groups = [section(g, [p for p in PAGES if p["group"] == g]) for g in ("Members", "Compare", "Guides", "Learn", "Scripts")]
    tail = f"## Languages\n\n- [Every language on the map]({SITE_URL}/languages.md): {sum(1 for p in PAGES if p['group'] == 'Languages')} pages, one per language.\n"
    (SITE / "llms.txt").write_text(head + main + "\n" + "\n".join(groups) + "\n" + tail)
    full = [head, *[t for t in MAIN_TWINS.values()], *[p["md"] for p in PAGES if p["group"] != "Languages"]]
    (SITE / "llms-full.txt").write_text("\n\n".join(full))


FACTS: dict = {}


def main() -> None:
    F, C = member_facts(), companion_facts()
    M = json.loads((SITE / "map" / "map.json").read_text())
    T = {t["name"]: t for t in json.loads(TYPEFACES.read_text())} if TYPEFACES.exists() else {}
    faq_html = (SITE / "faq-page.html").read_text()
    from build_site import faq_entities  # noqa: E402
    FACTS.update({"members": F, "map": M, "faq": faq_entities(faq_html)})
    script_and_language_pages(F, C, M)
    compare_pages(F)
    member_pages(F, C, M)
    guide_pages(F, C, M, T)
    agent_pages(F)
    library_page()
    write()


if __name__ == "__main__":
    main()

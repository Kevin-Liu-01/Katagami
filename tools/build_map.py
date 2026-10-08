"""Build the data for the Katagami map page from General Translation's world
language map data and the built Katagami fonts.

    python tools/build_map.py

Reads GT's public/world data (GT_WORLD, default the langmap worktree) and
writes into Kerf-Website/map/:

    grid-<res>.u16.gz, density-<res>.u8.gz, blends-<res>.json   copied as is
    map.json      units, glyph sets, languages, per-family coverage and stats
    LICENSE.txt   the data notices (CLDR, Natural Earth, GHS-POP)

A glyph set counts as covered by a family when the family's fonts have at
least 90 percent of its letters; the map then draws only the letters the
fonts have. Han, kana and Hangul sets sample a few dozen characters from
scripts that need thousands, so for those the family must also have the
whole national standard: GB 2312's hanzi for Simplified Chinese, Big5's
level-1 hanzi for Traditional, JIS X 0208's level-1 kanji and the kana for
Japanese, KS X 1001's Hangul for Korean. The proportional members count
the Katagami CJK companions as theirs; the website sets them in one family. Population shares weight every land cell by its people (GHS-POP
density times cell area) and give the cell to its largest language.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
WORLD = Path(os.environ.get("GT_WORLD", Path.home() / "gt/gt-cloud-wt-langmap/apps/landing/public/world"))
SITE = Path(os.environ.get("KERF_SITE", ROOT.parent / "Kerf-Website"))
OUT = SITE / "map"
LEVELS = (1, 0.5, 0.25)
STATS_LEVEL = 0.5
COVERED = 0.9
CJK = [ROOT / f"fonts/cjk/KatagamiCJK{r}[wght].ttf" for r in ("SC", "JP", "KR")]
FONTS = {
    "round": [ROOT / "fonts/round/KatagamiRound[wght].ttf", *CJK],
    "sans": [ROOT / "fonts/sans/KatagamiSans[wght].ttf", *CJK],
    "text": [ROOT / "fonts/text/KatagamiText[wght].ttf", *CJK],
    "mono": [ROOT / "fonts/mono/KatagamiMono[wght].ttf"],
}
DENSITY_LOG_MIN, DENSITY_STEPS = -3, 32


def euc(codec: str, rows: range) -> set[int]:
    """Characters of a two-byte EUC code set in the given lead-byte rows."""
    out = set()
    for hi in rows:
        for lo in range(0xA1, 0xFF):
            try:
                ch = bytes([hi, lo]).decode(codec)
            except UnicodeDecodeError:
                continue
            if len(ch) == 1:
                out.add(ord(ch))
    return out


def big5_level1() -> set[int]:
    out = set()
    for hi in range(0xA4, 0xC7):
        for lo in list(range(0x40, 0x7F)) + list(range(0xA1, 0xFF)):
            try:
                ch = bytes([hi, lo]).decode("big5")
            except UnicodeDecodeError:
                continue
            if len(ch) == 1 and 0x4E00 <= ord(ch) <= 0x9FFF:
                out.add(ord(ch))
    return out


def standards() -> dict[str, set[int]]:
    """The full character standard each Han, kana or Hangul script must meet."""
    kana = set(range(0x3041, 0x3097)) | set(range(0x30A1, 0x30FB))
    return {
        "Hans": {u for u in euc("gb2312", range(0xB0, 0xF8)) if u >= 0x4E00},
        "Hant": big5_level1(),
        "Jpan": {u for u in euc("euc_jp", range(0xB0, 0xD0)) if u >= 0x4E00} | kana,
        "Kore": {u for u in euc("euc_kr", range(0xB0, 0xC9)) if 0xAC00 <= u <= 0xD7A3},
    }


def level_name(res: float) -> str:
    return str(res).rstrip("0").rstrip(".") if res % 1 else str(int(res))


def density_of(code: int) -> float:
    return 0.0 if code == 0 else 10 ** (DENSITY_LOG_MIN + (code - 1) / DENSITY_STEPS)


def resolve_pool(units: dict, blends: dict, cell_id: int):
    """A cell's languages: a unit's pool, or a blend of units' pools."""
    if cell_id in units:
        return units[cell_id]
    if cell_id not in blends:
        return []
    rows: dict[tuple[str, str], float] = {}
    for unit_id, share in blends[cell_id]:
        for key, permille, tag in units.get(unit_id, []):
            rows[(key, tag)] = rows.get((key, tag), 0) + permille * share / 1000
    return [[k, round(p), t] for (k, t), p in sorted(rows.items(), key=lambda kv: -kv[1])]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    units_file = json.loads((WORLD / "units.json").read_text())
    units = {u["id"]: u["pool"] for u in units_file["units"]}
    sets = json.loads((WORLD / "glyphs.json").read_text())
    langs = json.loads((WORLD / "languages.json").read_text())
    english = json.loads((WORLD / "names/en.json").read_text())

    for res in LEVELS:
        name = level_name(res)
        for f in (f"grid-{name}.u16.gz", f"density-{name}.u8.gz", f"blends-{name}.json"):
            shutil.copyfile(WORLD / f, OUT / f)
    shutil.copyfile(WORLD / "LICENSE.txt", OUT / "LICENSE.txt")

    # which letters each family has
    cmaps = {fam: set().union(*(TTFont(path).getBestCmap() for path in paths if path.exists()))
             for fam, paths in FONTS.items()}
    full = standards()
    coverage, charsets = {}, {}
    for fam, cmap in cmaps.items():
        keys, chars = [], set()
        for key, s in sets.items():
            letters = s["glyphs"].split()
            have = [ch for ch in letters if all(ord(c) in cmap for c in ch)]
            if s["script"] in full and not full[s["script"]] <= cmap:
                continue
            if letters and len(have) / len(letters) >= COVERED:
                keys.append(key)
                chars.update(have)
        coverage[fam] = sorted(keys)
        charsets[fam] = "".join(sorted(chars))

    # population and land shares at STATS_LEVEL
    name = level_name(STATS_LEVEL)
    grid = gzip.decompress((WORLD / f"grid-{name}.u16.gz").read_bytes())
    dens = gzip.decompress((WORLD / f"density-{name}.u8.gz").read_bytes())
    blends = {row[0]: [(row[i], row[i + 1]) for i in range(1, len(row), 2)]
              for row in json.loads((WORLD / f"blends-{name}.json").read_text())}
    cols, rows = int(360 / STATS_LEVEL), int(180 / STATS_LEVEL)
    km = 111.32 * STATS_LEVEL
    totals = {"people": 0.0, "land": 0.0}
    covered = {fam: {"people": 0.0, "land": 0.0} for fam in FONTS}
    pools: dict[int, list] = {}
    for r in range(rows):
        lat = 90 - (r + 0.5) * STATS_LEVEL
        area = km * km * math.cos(math.radians(lat))
        for c in range(cols):
            i = r * cols + c
            cid = grid[2 * i] | (grid[2 * i + 1] << 8)
            if cid == 0:
                continue
            pool = pools.setdefault(cid, resolve_pool(units, blends, cid))
            if not pool:
                continue
            people = density_of(dens[i]) * area
            totals["people"] += people
            totals["land"] += area
            top = pool[0][0]
            for fam in FONTS:
                if top in coverage[fam]:
                    covered[fam]["people"] += people
                    covered[fam]["land"] += area

    # languages: the glyph sets each language is written with on the map
    lang_sets: dict[str, set[str]] = {}
    for pool in units.values():
        for key, _, tag in pool:
            lang_sets.setdefault(tag, set()).add(key)
    languages = {}
    for tag, info in langs.items():
        languages[tag] = {
            "own": info["own"],
            "en": english["languages"].get(tag) or english["languages"].get(tag.split("-")[0]) or tag,
            "speakers": info["speakers"],
            "sets": sorted(lang_sets.get(tag, [])),
        }
    stats = {}
    for fam in FONTS:
        written = [t for t, l in languages.items() if l["sets"] and all(k in coverage[fam] for k in l["sets"])]
        stats[fam] = {
            "people": round(100 * covered[fam]["people"] / totals["people"], 1),
            "land": round(100 * covered[fam]["land"] / totals["land"], 1),
            "languages": len(written),
            "of": sum(1 for l in languages.values() if l["sets"]),
        }

    digest = hashlib.sha256()
    for f in sorted(OUT.glob("*.gz")) + sorted(OUT.glob("blends-*.json")):
        digest.update(f.read_bytes())
    data = {
        "version": digest.hexdigest()[:10],  # appended to the grid, density and blend URLs
        "source": {"cldr": units_file["meta"]["cldr"], "naturalEarth": units_file["meta"]["naturalEarth"]["admin0"],
                   "ghsPop": units_file["meta"]["ghsPop"]},
        "crop": units_file["meta"]["crop"],
        "levels": [level_name(r) for r in LEVELS],
        "units": {str(k): v for k, v in units.items()},
        "sets": {k: {"script": s["script"], "glyphs": s["glyphs"]} for k, s in sets.items()},
        "languages": languages,
        "coverage": coverage,
        "charsets": charsets,
        "stats": stats,
    }
    (OUT / "map.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    for fam, st in stats.items():
        print(f"{fam:6} people {st['people']:5.1f}%  land {st['land']:5.1f}%  languages {st['languages']}/{st['of']}")
    for p in sorted(OUT.iterdir()):
        print(f"{p.stat().st_size / 1024:8.1f} KB  map/{p.name}")


if __name__ == "__main__":
    main()

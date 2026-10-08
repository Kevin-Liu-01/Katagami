"""Build the data for the Kerf map page from General Translation's world
language map data and the built Kerf fonts.

    python tools/build_map.py

Reads GT's public/world data (GT_WORLD, default the langmap worktree) and
writes into Kerf-Website/map/:

    grid-<res>.u16.gz, density-<res>.u8.gz, blends-<res>.json   copied as is
    map.json      units, glyph sets, languages, per-family coverage and stats
    LICENSE.txt   the data notices (CLDR, Natural Earth, GHS-POP)

A glyph set counts as covered by a family when the family's font has at
least 90 percent of its letters; the map then draws only the letters the
font has. Population shares weight every land cell by its people (GHS-POP
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
FONTS = {
    "round": ROOT / "fonts/round/KerfRound[wght].ttf",
    "sans": ROOT / "fonts/sans/KerfSans[wght].ttf",
    "mono": ROOT / "fonts/mono/KerfMono[wght].ttf",
}
DENSITY_LOG_MIN, DENSITY_STEPS = -3, 32


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
    cmaps = {fam: set(TTFont(path).getBestCmap()) for fam, path in FONTS.items()}
    coverage, charsets = {}, {}
    for fam, cmap in cmaps.items():
        keys, chars = [], set()
        for key, s in sets.items():
            letters = s["glyphs"].split()
            have = [ch for ch in letters if all(ord(c) in cmap for c in ch)]
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

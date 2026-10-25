"""Whether every glyph a rebuild changed has a terminal: a glyph from CHANGED (TTF names, from
serif_check.py --names-out) is explained when it, a component of it (recursively, in the built
Regular UFO) or, for a small capital or a numerator, superior or other variant, its base takes a
terminal beak in this build or in an older one (plan_terminals of build_sans.py at each commit,
run on the lab's pickled masters).
    .venv/bin/python tools/serif_lab/explain.py CHANGED.txt UFO COMMIT [COMMIT ...]"""
import copy
import importlib.util
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import ufoLib2  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402
import lablib as L  # noqa: E402
import build_sans as B  # noqa: E402

changed_path, ufo_path, commits = sys.argv[1], sys.argv[2], sys.argv[3:]


def module(commit):
    p = L.LAB / f"build_sans_{commit}.py"
    if not p.exists():
        p.write_text(subprocess.run(["git", "-C", str(L.ROOT), "show", f"{commit}:tools/build_sans.py"],
                                    capture_output=True, text=True, check=True).stdout)
    spec = importlib.util.spec_from_file_location(f"build_sans_{commit}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


fonts = {s: copy.deepcopy(f) for s, f in L.pre("roman").items()}
plan = B.plan_serifs(fonts)
B.fit_serifs(fonts, plan, L.P.serif_reach, B.SERIF_FIT)
plan = B.plan_serifs(fonts)
term = set(B.plan_terminals(fonts, plan))
for c in commits:
    term |= set(module(c).plan_terminals(fonts, plan))
ufo = ufoLib2.Font.open(ufo_path)
by_u = {u: g.name for g in ufo for u in g.unicodes}
ttf = TTFont(str(L.ROOT / "fonts" / "serif" / "KatagamiSerif[wght].ttf"))
tt_u = {n: u for u, n in ttf.getBestCmap().items()}


def ufo_name(n):
    if n in tt_u and tt_u[n] in by_u:
        return by_u[tt_u[n]]
    base, dot, rest = n.partition(".")
    if base in tt_u and tt_u[base] in by_u:
        return by_u[tt_u[base]] + dot + rest
    return n


def related(n, depth=0):
    if n in term:
        return True
    if n not in ufo or depth > 6:
        return False
    return any(related(c.baseGlyph, depth + 1) for c in ufo[n].components)


odd = []
names = [line.strip() for line in open(changed_path) if line.strip()]
for n in names:
    u = ufo_name(n)
    base = u.split(".")[0]
    cands = {u, base, base.capitalize(), base.upper()}
    if any(related(c) for c in cands) or any(t.split(".")[0] in cands for t in term):
        continue
    odd.append(f"{n} ({u})")
print(len(names), "changed;", len(odd), "without a terminal:", " ".join(odd))

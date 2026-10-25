"""Serif terminal lab: Katagami Serif's serif block on a few glyphs of the pickled masters
(prep.py), with 0.2's terminal code or the moved beaks (moved.py), drawn with skia.
No font build: a sheet takes a few seconds."""
import copy, importlib.util, inspect, math, pickle, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "build" / "serif-lab"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))
import skia  # noqa: E402
import ufoLib2  # noqa: E402
from fontTools.pens.recordingPen import DecomposingRecordingPen  # noqa: E402
from kerf_build.fontops import respace, shear  # noqa: E402
from kerf_build.profiles import PROFILES  # noqa: E402
import build_sans as NEW  # noqa: E402
import moved as MOVED  # noqa: E402
import ends as ENDS  # noqa: E402

P = PROFILES["serif"]
V02 = "328c6c6"  # the commit whose build_sans.py cut 0.2's beaks


def _module(name: str, commit: str):
    path = LAB / f"build_sans_{name}.py"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:tools/build_sans.py"],
                                       check=True, capture_output=True, text=True).stdout)
    spec = importlib.util.spec_from_file_location(f"build_sans_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OLD = _module("02", V02)
_pre = {}


def pre(part):
    if part not in _pre:
        path = LAB / f"pre-{part}.pkl"
        if not path.exists():
            subprocess.run([sys.executable, str(Path(__file__).parent / "prep.py"), part], check=True)
        _pre[part] = pickle.load(open(path, "rb"))
    return _pre[part]


def build(part, text, variant="moved", consts=None):
    """The serif block on the glyphs of `text` (and what they need). part "roman"; "slanted",
    the roman slanted 9.4 degrees about half its x-height, as Serif Italic is since 0.2 (every
    glyph whose design differs takes the roman's); or "italic", Inter Italic's own upright
    masters cut the same way and slanted again. variant "0.2" cuts 0.2's beaks; "moved" the
    moved ones in moved.py (the small spur on every terminal); "build" what tools/build_sans.py cuts now. consts override moved.py's (or 0.2's) constants. Returns (masters, terminal plan)."""
    B = OLD if variant == "0.2" else NEW
    M = OLD if variant == "0.2" else NEW if variant == "build" else MOVED
    if variant.startswith("git:"):
        B = M = _module(variant[4:], variant[4:])
    option = variant[5:] if variant.startswith("ends:") else None
    saved = {}
    for k, v in (consts or {}).items():
        mod = M if hasattr(M, k) else B
        saved[(mod, k)] = getattr(mod, k)
        setattr(mod, k, v)
    try:
        src = pre("roman" if part == "slanted" else part)
        ref = src["Regular"]
        cmap = {u: g.name for g in ref for u in g.unicodes}
        want = {cmap[ord(c)] for c in text if ord(c) in cmap} | {"x", "H", "idotless", "l", "f", "t", "space", "n", "o"}
        need = set()

        def deps(name):
            if name in need or name not in ref:
                return
            need.add(name)
            for c in ref[name].components:
                deps(c.baseGlyph)
        for n in list(want):
            deps(n)
        fonts = {}
        for style, f in src.items():
            nf = ufoLib2.Font()
            nf.info = copy.deepcopy(f.info)
            for n in sorted(need):
                nf.layers.defaultLayer.insertGlyph(f[n], n, copy=True)
            fonts[style] = nf
        plan = B.plan_serifs(fonts)
        B.fit_serifs(fonts, plan, P.serif_reach, B.SERIF_FIT)
        plan = B.plan_serifs(fonts)
        terminals = M.plan_terminals(fonts, plan)
        B.add_contrast(fonts, dict(P.serif_contrast))
        # build_sans.py cuts its terminals after the stem serifs since the facets (d6b70d5 and later)
        after = M is NEW
        if option:
            kept = ENDS.cut(fonts, terminals, option)
        elif after:
            pass
        elif len(inspect.signature(M.cut_terminals).parameters) == 2:
            M.cut_terminals(fonts, terminals)
        else:
            M.cut_terminals(fonts, terminals, P.serif_depth, P.serif_reach)
        B.cut_serifs(fonts, plan, P.serif_reach, P.serif_depth, P.serif_head, P.serif_beak)
        if option:
            ENDS.after_serifs(fonts, kept, option, P.serif_depth)
        elif after:
            M.cut_terminals(fonts, terminals)
        respace(fonts, P.spacing)
        B.scale_outlines(fonts, P.scale)
        if part in ("italic", "slanted"):
            shear(fonts, math.tan(math.radians(9.4)), fonts["Regular"].info.xHeight / 2)
        for f in fonts.values():
            f.lib["_cmap"] = {u: g.name for g in f for u in g.unicodes}
        return fonts, terminals
    finally:
        for (mod, k), v in saved.items():
            setattr(mod, k, v)


def interpolate(fonts, wght):
    """A weight between the masters (100, 400, 900), point by point."""
    if wght <= 400:
        a, b, t = "Thin", "Regular", (wght - 100) / 300
    else:
        a, b, t = "Regular", "Black", (wght - 400) / 500
    fa, fb = fonts[a], fonts[b]
    nf = ufoLib2.Font()
    nf.info = copy.deepcopy(fa.info)
    for g in fa:
        h = fb[g.name]
        ng = nf.newGlyph(g.name)
        ng.width = g.width + t * (h.width - g.width)
        assert len(g.contours) == len(h.contours), (g.name, len(g.contours), len(h.contours))
        for ca, cb in zip(g.contours, h.contours):
            assert len(ca.points) == len(cb.points), g.name
            c = copy.deepcopy(ca)
            for pa, pb in zip(c.points, cb.points):
                pa.x += t * (pb.x - pa.x)
                pa.y += t * (pb.y - pa.y)
            ng.appendContour(c)
        for ka, kb in zip(g.components, h.components):
            k = copy.deepcopy(ka)
            ta, tb = ka.transformation, kb.transformation
            k.transformation = tuple(x + t * (y - x) for x, y in zip(ta, tb))
            ng.components.append(k)
        ng.unicodes = list(g.unicodes)
    nf.lib["_cmap"] = fa.lib["_cmap"]
    return nf


def path(f, name, x, base, s):
    rec = DecomposingRecordingPen(f)
    f[name].draw(rec)
    pa = skia.Path()
    pa.setFillType(skia.PathFillType.kWinding)
    for op, a in rec.value:
        tr = [(x + q[0] * s, base - q[1] * s) for q in a]
        if op == "moveTo":
            pa.moveTo(*tr[0])
        elif op == "lineTo":
            pa.lineTo(*tr[0])
        elif op == "curveTo":
            pa.cubicTo(*tr[0], *tr[1], *tr[2])
        elif op == "qCurveTo":
            pa.quadTo(*tr[0], *tr[1])
        elif op in ("closePath", "endPath"):
            pa.close()
    return pa


INK = skia.Paint(Color=skia.Color(20, 20, 20), AntiAlias=True)
GREY = skia.Paint(Color=skia.Color(120, 120, 120), AntiAlias=True)
RED = skia.Paint(Color=skia.Color(200, 40, 40), AntiAlias=True)
LABEL = skia.Font(skia.Typeface("Helvetica"), 13)


def text_width(f, text, size):
    return sum(f[f.lib["_cmap"][ord(c)]].width for c in text if ord(c) in f.lib["_cmap"]) * size / 2048


def draw_text(c, f, text, size, x, base, paint=INK):
    for ch in text:
        n = f.lib["_cmap"].get(ord(ch))
        if not n:
            x += 0.3 * size
            continue
        c.drawPath(path(f, n, x, base, size / 2048), paint)
        x += f[n].width * size / 2048
    return x

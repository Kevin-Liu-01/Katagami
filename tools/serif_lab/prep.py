"""Katagami Serif's masters (roman, or the Italic stood upright) up to the point where
the serifs are planned, pickled for the terminal lab.

    .venv/bin/python tools/serif_lab/prep.py roman|italic

Writes build/serif-lab/pre-<part>.pkl (about 7 MB, a minute or two of CPU)."""
import pickle, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build_sans as B  # noqa: E402
from kerf_build.fontops import decompose_transformed, load_inter_masters, promote_alternates, shear, slant_tangent  # noqa: E402
from kerf_build.profiles import PROFILES  # noqa: E402

t0 = time.time()
p = PROFILES["serif"]
part = sys.argv[1]
italic = part == "italic"
fonts = load_inter_masters(italic)
if italic:
    decompose_transformed(fonts)
    shear(fonts, -slant_tangent(fonts["Regular"]), fonts["Regular"].info.xHeight / 2)
if p.square_punctuation:
    B.promote_square_punctuation(fonts)
if p.promote:
    promote_alternates(fonts, p.promote, B.FEATURES)
    B.relabel_features(fonts, p.promote)
B.shape_curves(fonts, p)
B.square_two(fonts, p.two_square)
if p.terminal_angle is not None:
    B.level_terminals(fonts, p.terminal_angle)
if p.c_close:
    B.close_c(fonts, p.c_close)
B.f_crossbar_overhang(fonts, p.f_overhang)
if p.notch_fill:
    B.fill_notches(fonts, p.notch_fill)
B.fill_valleys(fonts, p.valley_fill)
if p.tails:
    B.redraw_tails(fonts, p)
B.slant_t(fonts, p.t_slant)
B.adjust_widths(fonts, p.widths, p.condense)
B.lift_ascenders(fonts, p.ascender_lift)
B.lower_xheight(fonts, p.xheight_scale)
out = ROOT / "build" / "serif-lab" / f"pre-{part}.pkl"
out.parent.mkdir(parents=True, exist_ok=True)
with open(out, "wb") as fh:
    pickle.dump(fonts, fh, protocol=pickle.HIGHEST_PROTOCOL)
print("prep", part, round(time.time() - t0), "s ->", out)

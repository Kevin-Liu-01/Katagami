"""Shrink the images tools/readme.mjs drew: at most 1800 pixels wide (1200 for
page screenshots) and reduced to a palette, which keeps flat type crisp at a
fraction of the size."""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

for name in json.loads((ROOT / "build/readme-shrink.json").read_text()):
    path = Path(name)
    im = Image.open(path).convert("RGB")
    widest = 1200 if path.parent.name == "readme" and "Website" in str(path) else 1800
    if im.width > widest:
        im = im.resize((widest, round(im.height * widest / im.width)), Image.LANCZOS)
    im.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    print(f"{path.stat().st_size / 1024:7.1f} KB  {path.relative_to(path.parents[1])}")

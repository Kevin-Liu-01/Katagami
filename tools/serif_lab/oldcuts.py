"""build_sans.py as it was at fedf6b2, for the lab's earlier variants (moved.py, ends.py): the
helpers they cut with (_upright, _at_x, _walk_to_x, ...) left the build when the terminals
became facets. Written to build/serif-lab/ from git on first use."""
import importlib.util
import subprocess
from pathlib import Path

COMMIT = "fedf6b2"
ROOT = Path(__file__).resolve().parents[2]
_path = ROOT / "build" / "serif-lab" / f"build_sans_{COMMIT}.py"
if not _path.exists():
    _path.parent.mkdir(parents=True, exist_ok=True)
    _path.write_text(subprocess.run(["git", "-C", str(ROOT), "show", f"{COMMIT}:tools/build_sans.py"],
                                    check=True, capture_output=True, text=True).stdout)
_spec = importlib.util.spec_from_file_location(f"build_sans_{COMMIT}", _path)
OLD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)

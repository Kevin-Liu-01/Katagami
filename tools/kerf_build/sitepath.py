"""Where the website checkout is, for the tools that write into it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# the Katagami-Website checkout: KATAGAMI_SITE, or the folder beside this repository
SITE = Path(os.environ.get("KATAGAMI_SITE", ROOT.parent / "Katagami-Website"))
PUBLIC = SITE / "public"


def require_site() -> Path:
    """Stop unless SITE is a Katagami-Website checkout, so a run from a git worktree or with a
    mistyped KATAGAMI_SITE never writes a new tree somewhere else."""
    missing = [name for name in ("next.config.ts", "content", "public") if not (SITE / name).exists()]
    if missing:
        sys.exit(f"{SITE} is not a Katagami-Website checkout. It has no {', '.join(missing)}. "
                 "Set KATAGAMI_SITE to the checkout this run should write into.")
    return SITE

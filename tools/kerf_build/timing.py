"""Stage timings for the build tools. `with stage("name"):` times a stage, and
one table is printed when the process ends. A name used more than once is
summed. The helper changes nothing a build writes."""

from __future__ import annotations

import atexit
import time
from contextlib import contextmanager

_TOTALS: dict[str, list] = {}  # name -> [seconds, times entered]


@contextmanager
def stage(name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        entry = _TOTALS.setdefault(name, [0.0, 0])
        entry[0] += time.perf_counter() - start
        entry[1] += 1


@atexit.register
def _report() -> None:
    for name, (seconds, count) in _TOTALS.items():
        print(f"timing  {seconds:9.1f} s  {count:4d}x  {name}", flush=True)

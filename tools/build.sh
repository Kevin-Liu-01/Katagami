#!/usr/bin/env bash
# Build Kerf from Inter's sources. Usage: tools/build.sh [sans|mono|all]
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
which="${1:-all}"

INTER_COMMIT=353b61b9f4430d5f420d56605a6e7993e0941470  # rsms/inter master, 2026-10
if [[ ! -d vendor/inter ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/rsms/inter.git vendor/inter
  git -C vendor/inter sparse-checkout set --no-cone '/src/*' '/LICENSE.txt'
  git -C vendor/inter checkout "$INTER_COMMIT"
fi

if [[ ! -d build/ufo ]]; then
  .venv/bin/glyphs2ufo vendor/inter/src/Inter-Roman.glyphspackage -m build/ufo --minimal
fi

if [[ "$which" == sans || "$which" == all ]]; then
  $PY tools/build_sans.py
  mkdir -p fonts/sans
  .venv/bin/fontmake -m build/sans/KerfSans.designspace -o variable \
    --output-path 'fonts/sans/KerfSans[wght].ttf' --flatten-components
fi

if [[ "$which" == mono || "$which" == all ]]; then
  $PY tools/build_mono.py
  mkdir -p fonts/mono
  .venv/bin/fontmake -m build/mono/KerfMono.designspace -o variable \
    --output-path 'fonts/mono/KerfMono[wght].ttf' --flatten-components
fi

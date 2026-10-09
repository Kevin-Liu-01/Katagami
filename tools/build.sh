#!/usr/bin/env bash
# Build Katagami from Inter's sources. Usage: tools/build.sh [sans|mono|round|text|cjk|all]
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

# Noto Sans for the scripts Katagami does not draw (SIL OFL 1.1, google/fonts)
NOTO=(devanagari/NotoSansDevanagari arabic/NotoSansArabic bengali/NotoSansBengali gurmukhi/NotoSansGurmukhi
      gujarati/NotoSansGujarati oriya/NotoSansOriya tamil/NotoSansTamil telugu/NotoSansTelugu kannada/NotoSansKannada
      malayalam/NotoSansMalayalam sinhala/NotoSansSinhala thai/NotoSansThai lao/NotoSansLao myanmar/NotoSansMyanmar
      ethiopic/NotoSansEthiopic hebrew/NotoSansHebrew armenian/NotoSansArmenian georgian/NotoSansGeorgian khmer/NotoSansKhmer)
mkdir -p vendor/noto
for entry in "${NOTO[@]}"; do
  dir="notosans${entry%%/*}"; file="${entry##*/}[wdth,wght].ttf"
  url=$(printf %s "$file" | sed 's/\[/%5B/; s/\]/%5D/; s/,/%2C/')
  [[ -f "vendor/noto/$file" ]] || curl -sfL -o "vendor/noto/$file" "https://raw.githubusercontent.com/google/fonts/main/ofl/$dir/$url"
done
for cjk in SC TC JP KR; do
  file="NotoSans$cjk[wght].ttf"
  dir="notosans$(printf %s "$cjk" | tr '[:upper:]' '[:lower:]')"
  [[ -f "vendor/noto/$file" ]] || curl -sfL -o "vendor/noto/$file" \
    "https://raw.githubusercontent.com/google/fonts/main/ofl/$dir/NotoSans$cjk%5Bwght%5D.ttf"
done

if [[ ! -d build/ufo ]]; then
  .venv/bin/glyphs2ufo vendor/inter/src/Inter-Roman.glyphspackage -m build/ufo --minimal
fi

if [[ "$which" == sans || "$which" == all ]]; then
  $PY tools/build_sans.py sans
  mkdir -p fonts/sans
  .venv/bin/fontmake -m build/sans/KatagamiSans.designspace -o variable \
    --output-path 'build/sans/KatagamiSans-core[wght].ttf' --flatten-components
  $PY tools/build_world.py sans
fi

if [[ "$which" == cjk || "$which" == all ]]; then
  $PY tools/build_cjk.py
fi

if [[ "$which" == mono || "$which" == all ]]; then
  $PY tools/build_mono.py
  mkdir -p fonts/mono
  .venv/bin/fontmake -m build/mono/KatagamiMono.designspace -o variable \
    --output-path 'fonts/mono/KatagamiMono[wght].ttf' --flatten-components
  $PY tools/build_mono.py --finish 'fonts/mono/KatagamiMono[wght].ttf'
fi

if [[ "$which" == round || "$which" == all ]]; then
  $PY tools/build_sans.py round
  mkdir -p fonts/round
  .venv/bin/fontmake -m build/round/KatagamiRound.designspace -o variable \
    --output-path 'build/round/KatagamiRound-core[wght].ttf' --flatten-components
  $PY tools/build_world.py round
fi

if [[ "$which" == text || "$which" == all ]]; then
  $PY tools/build_sans.py text
  mkdir -p fonts/text
  .venv/bin/fontmake -m build/text/KatagamiText.designspace -o variable \
    --output-path 'build/text/KatagamiText-core[wght].ttf' --flatten-components
  $PY tools/build_world.py text
fi

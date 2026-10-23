#!/usr/bin/env bash
# Build Katagami from Inter's sources.
# Usage: tools/build.sh [sans|round|text|serif|mono|cjk|all]
# A member builds its roman and its Italic; add -roman or -italic (serif-italic) for one of them.
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
# v0.2's nine scripts, at a pinned google/fonts commit; Tibetan exists only as Noto Serif Tibetan
NOTO_COMMIT=e7db6ca603fd4862010383ff17ffd6cc4ffac1c0
NOTO2=(notosanstifinagh/NotoSansTifinagh-Regular.ttf "notosansolchiki/NotoSansOlChiki[wght].ttf"
       notosanscoptic/NotoSansCoptic-Regular.ttf "notoseriftibetan/NotoSerifTibetan[wght].ttf"
       "notosanshanifirohingya/NotoSansHanifiRohingya[wght].ttf" notosansnko/NotoSansNKo-Regular.ttf
       "notosansthaana/NotoSansThaana[wght].ttf" notosansvai/NotoSansVai-Regular.ttf
       "notosanscanadianaboriginal/NotoSansCanadianAboriginal[wght].ttf")
for entry in "${NOTO2[@]}"; do
  file="${entry##*/}"; url=$(printf %s "$entry" | sed 's/\[/%5B/; s/\]/%5D/')
  [[ -f "vendor/noto/$file" ]] || curl -sfL -o "vendor/noto/$file" "https://raw.githubusercontent.com/google/fonts/$NOTO_COMMIT/ofl/$url"
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
if [[ ! -d build/ufo-italic ]]; then
  .venv/bin/glyphs2ufo vendor/inter/src/Inter-Italic.glyphspackage -m build/ufo-italic --minimal
fi

# wants KEY PART: true when this run builds KEY's roman or italic
wants() { [[ "$which" == all || "$which" == "$1" || "$which" == "$1-$2" ]]; }

# proportional KEY STEM: Inter's masters into the member, fontmake, then the script merge (roman)
proportional() {
  local key=$1 stem=$2
  mkdir -p "fonts/$key"
  if wants "$key" roman; then
    $PY tools/build_sans.py "$key"
    .venv/bin/fontmake -m "build/$key/$stem.designspace" -o variable \
      --output-path "build/$key/$stem-core[wght].ttf" --flatten-components
    $PY tools/build_world.py "$key"
  fi
  if wants "$key" italic; then
    $PY tools/build_sans.py "$key" --italic
    .venv/bin/fontmake -m "build/$key-italic/$stem-Italic.designspace" -o variable \
      --output-path "fonts/$key/$stem-Italic[wght].ttf" --flatten-components
  fi
  if wants "$key" roman || wants "$key" italic; then
    $PY tools/finish.py "$key"
  fi
}

proportional sans KatagamiSans

if [[ "$which" == cjk || "$which" == all ]]; then
  $PY tools/build_cjk.py
fi

mkdir -p fonts/mono
if wants mono roman; then
  $PY tools/build_mono.py
  .venv/bin/fontmake -m build/mono/KatagamiMono.designspace -o variable \
    --output-path 'fonts/mono/KatagamiMono[wght].ttf' --flatten-components
  $PY tools/build_mono.py --finish 'fonts/mono/KatagamiMono[wght].ttf'
fi
if wants mono italic; then
  $PY tools/build_mono.py --italic
  .venv/bin/fontmake -m build/mono-italic/KatagamiMono-Italic.designspace -o variable \
    --output-path 'fonts/mono/KatagamiMono-Italic[wght].ttf' --flatten-components
  $PY tools/build_mono.py --finish 'fonts/mono/KatagamiMono-Italic[wght].ttf'
fi
if wants mono roman || wants mono italic; then
  $PY tools/finish.py mono
fi

proportional round KatagamiRound
proportional text KatagamiText
proportional serif KatagamiSerif

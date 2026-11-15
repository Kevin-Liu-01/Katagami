#!/usr/bin/env bash
# Build Katagami from Inter's sources.
# Usage: tools/build.sh [sans|round|text|serif|mono|cjk|all|fetch]
# A member builds its roman and its Italic; add -roman or -italic (serif-italic, cjk-roman, cjk-italic) for one of them.
# fetch only downloads and checks the sources.
# BUILD_DRY=1 checks the target's name and builds nothing.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
which="${1:-all}"
# BUILD_DRY=1 checks the target's name and stops before anything is fetched or built
case "$which" in
  all|sans|round|text|serif|mono|cjk|fetch) ;;
  sans-roman|sans-italic|round-roman|round-italic|text-roman|text-italic|serif-roman|serif-italic|mono-roman|mono-italic|cjk-roman|cjk-italic) ;;
  *) echo "tools/build.sh does not build '$which'. Usage: tools/build.sh [sans|round|text|serif|mono|cjk|all|fetch], or a member with -roman or -italic." >&2; exit 2 ;;
esac
[[ -n "${BUILD_DRY:-}" ]] && exit 0

INTER_COMMIT=353b61b9f4430d5f420d56605a6e7993e0941470  # rsms/inter master, 2026-10
if [[ ! -d vendor/inter ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/rsms/inter.git vendor/inter
  git -C vendor/inter sparse-checkout set --no-cone '/src/*' '/LICENSE.txt'
  git -C vendor/inter checkout "$INTER_COMMIT"
elif [[ "$(git -C vendor/inter rev-parse HEAD)" != "$INTER_COMMIT" ]]; then
  # the pin moved since vendor/inter was checked out, so the masters converted from it are stale too
  git -C vendor/inter fetch --filter=blob:none origin "$INTER_COMMIT"
  git -C vendor/inter checkout "$INTER_COMMIT"
  rm -rf build/ufo build/ufo-italic build/ufo.inter-commit build/ufo-italic.inter-commit
fi

# Noto for the scripts Katagami does not draw (SIL OFL 1.1), every file from one google/fonts commit.
# tools/noto.sha256 holds each file's SHA-256, and a file that does not match stops the build.
NOTO_COMMIT=e7db6ca603fd4862010383ff17ffd6cc4ffac1c0
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
# noto DIR FILE: vendor/noto/FILE from ofl/DIR at NOTO_COMMIT, downloaded once and checked on every run
noto() {
  local dir=$1 file=$2 want got url
  want=$(awk -v f="$file" 'substr($0, 67) == f { print $1 }' tools/noto.sha256)
  [[ -n "$want" ]] || { echo "tools/noto.sha256 has no line for $file." >&2; exit 1; }
  if [[ ! -f "vendor/noto/$file" ]]; then
    url=$(printf %s "$file" | sed 's/\[/%5B/; s/\]/%5D/; s/,/%2C/')
    # a download takes its final name only once it is whole and matches
    curl -sfL -o "vendor/noto/$file.part" "https://raw.githubusercontent.com/google/fonts/$NOTO_COMMIT/ofl/$dir/$url" \
      || { echo "Could not download $file from google/fonts at ${NOTO_COMMIT:0:7}." >&2; exit 1; }
    got=$(sha256 "vendor/noto/$file.part")
    [[ "$got" == "$want" ]] || { echo "The download of $file has SHA-256 $got and tools/noto.sha256 expects $want." >&2; exit 1; }
    mv "vendor/noto/$file.part" "vendor/noto/$file"
  fi
  got=$(sha256 "vendor/noto/$file")
  [[ "$got" == "$want" ]] || { echo "vendor/noto/$file has SHA-256 $got and tools/noto.sha256 expects $want. Delete the file and run again." >&2; exit 1; }
}
mkdir -p vendor/noto
NOTO=(devanagari/NotoSansDevanagari arabic/NotoSansArabic bengali/NotoSansBengali gurmukhi/NotoSansGurmukhi
      gujarati/NotoSansGujarati oriya/NotoSansOriya tamil/NotoSansTamil telugu/NotoSansTelugu kannada/NotoSansKannada
      malayalam/NotoSansMalayalam sinhala/NotoSansSinhala thai/NotoSansThai lao/NotoSansLao myanmar/NotoSansMyanmar
      ethiopic/NotoSansEthiopic hebrew/NotoSansHebrew armenian/NotoSansArmenian georgian/NotoSansGeorgian khmer/NotoSansKhmer)
for entry in "${NOTO[@]}"; do noto "notosans${entry%%/*}" "${entry##*/}[wdth,wght].ttf"; done
# the nine scripts of v0.2; Tibetan exists only as Noto Serif Tibetan
NOTO2=(notosanstifinagh/NotoSansTifinagh-Regular.ttf "notosansolchiki/NotoSansOlChiki[wght].ttf"
       notosanscoptic/NotoSansCoptic-Regular.ttf "notoseriftibetan/NotoSerifTibetan[wght].ttf"
       "notosanshanifirohingya/NotoSansHanifiRohingya[wght].ttf" notosansnko/NotoSansNKo-Regular.ttf
       "notosansthaana/NotoSansThaana[wght].ttf" notosansvai/NotoSansVai-Regular.ttf
       "notosanscanadianaboriginal/NotoSansCanadianAboriginal[wght].ttf")
for entry in "${NOTO2[@]}"; do noto "${entry%%/*}" "${entry##*/}"; done

# The CJK companions' sources (SIL OFL 1.1): the masters of IBM Plex Sans JP, KR and TC from each
# release's sources.zip, and Frex Sans GB's variable font from its release. Each archive must match its SHA-256.
# cjk_source DIR URL SHA256 MEMBER: MEMBER of the archive at URL, unpacked into vendor/DIR once
cjk_source() {
  local dir=$1 url=$2 want=$3 member=$4 zip got
  zip="vendor/$dir/$(basename "$url")"
  mkdir -p "vendor/$dir"
  if [[ ! -f "$zip" ]]; then
    curl -sfL -o "$zip.part" "$url" || { echo "Could not download $url." >&2; exit 1; }
    got=$(sha256 "$zip.part")
    [[ "$got" == "$want" ]] || { echo "The download of $url has SHA-256 $got and tools/build.sh expects $want." >&2; exit 1; }
    mv "$zip.part" "$zip"
  fi
  got=$(sha256 "$zip")
  [[ "$got" == "$want" ]] || { echo "$zip has SHA-256 $got and tools/build.sh expects $want. Delete the file and run again." >&2; exit 1; }
  # unzip reads [ and ] as a pattern, so they are escaped
  [[ -f "vendor/$dir/$(basename "$member")" ]] || unzip -q -j -o "$zip" "$(printf %s "$member" | sed 's/\[/\\[/g; s/\]/\\]/g')" -d "vendor/$dir"
}
PLEX=https://github.com/IBM/plex/releases/download
cjk_source plex/jp "$PLEX/%40ibm%2Fplex-sans-jp%403.0.0/sources.zip" \
  4ac6374873b634a9dc19cd2b8f40e9acfe55ea37c269c08c0dcdb9b2abdce3de "sources/masters/IBM Plex Sans JP.glyphs"
cjk_source plex/kr "$PLEX/%40ibm%2Fplex-sans-kr%401.1.0/sources.zip" \
  69e8e90ca6966c7fe10f74655efc18ef4b12da4a2ca97607bbaa967b3da447e5 "sources/masters/IBM Plex Sans KR.glyphs"
cjk_source plex/tc "$PLEX/%40ibm%2Fplex-sans-tc%401.1.1/sources.zip" \
  93649217ac3222b2117175b4fcb862636e571595f5fd3a42a27c04520ccba139 "sources/masters/IBM Plex Sans TC.glyphs"
cjk_source frex https://github.com/maoken-fonts/frex-sans/releases/download/v1.100/FrexSansGB.zip \
  a82c3254c7f1070ce227cb9afbc6f98a30d32ba202f7c83275992141dfb52c15 "variable/Frex Sans GB[wght].ttf"

# Inter's masters as UFOs in build/ufo and build/ufo-italic. A stamp beside each folder names the
# Inter commit it was converted from, and a folder from another commit is converted again.
for dir in ufo ufo-italic; do
  stamp="build/$dir.inter-commit"
  if [[ -d "build/$dir" && -f "$stamp" && "$(cat "$stamp")" != "$INTER_COMMIT" ]]; then rm -rf "build/$dir" "$stamp"; fi
  # a folder converted before the stamps existed is taken as current, because vendor/inter is at the pin
  if [[ -d "build/$dir" && ! -f "$stamp" ]]; then printf '%s\n' "$INTER_COMMIT" > "$stamp"; fi
done

if [[ "$which" == fetch ]]; then
  echo "Sources fetched and checked: Inter at ${INTER_COMMIT:0:7}, $(wc -l < tools/noto.sha256 | tr -d ' ') Noto files at ${NOTO_COMMIT:0:7}, IBM Plex Sans JP, KR and TC and Frex Sans GB."
  exit 0
fi

if [[ ! -d build/ufo ]]; then
  .venv/bin/glyphs2ufo vendor/inter/src/Inter-Roman.glyphspackage -m build/ufo --minimal
  printf '%s\n' "$INTER_COMMIT" > build/ufo.inter-commit
fi
if [[ ! -d build/ufo-italic ]]; then
  .venv/bin/glyphs2ufo vendor/inter/src/Inter-Italic.glyphspackage -m build/ufo-italic --minimal
  printf '%s\n' "$INTER_COMMIT" > build/ufo-italic.inter-commit
fi

# wants KEY PART: true when this run builds KEY's roman or italic
wants() { [[ "$which" == all || "$which" == "$1" || "$which" == "$1-$2" ]]; }

# proportional KEY STEM: Inter's masters into the member, fontmake, then the script merge
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
      --output-path "build/$key-italic/$stem-Italic-core[wght].ttf" --flatten-components
    $PY tools/build_world.py "$key" --italic
  fi
  if wants "$key" roman || wants "$key" italic; then
    $PY tools/finish.py "$key"
  fi
}

proportional sans KatagamiSans

case "$which" in
  all|cjk) $PY tools/build_cjk.py ;;
  cjk-roman) $PY tools/build_cjk.py --roman ;;
  cjk-italic) $PY tools/build_cjk.py --italic ;;
esac

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

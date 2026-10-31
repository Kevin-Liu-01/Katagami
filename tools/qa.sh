#!/usr/bin/env bash
# Run fontbakery's Google Fonts profile on the built members, one member at a time.
# Usage: tools/qa.sh [sans|round|text|serif|mono|all|cjksc|cjktc|cjkjp|cjkkr|cjk] [fontbakery options, such as -c checkid or -F]
# A member's roman and Italic are copied to build/qa/fonts/katagami<member>/, the directory
# name Google Fonts uses (fonts/sans and fonts/text lose their last word in fontbakery's
# sibling-family lookup), with the member's article from docs/google-fonts beside them.
# The report is build/qa/<member>.md and the console log build/qa/<member>.log.
# A CJK file is checked alone as katagamicjk<region>. FONTS=dir checks dir/<member>/*.ttf
# instead of fonts/<member>/*.ttf (copies kept elsewhere).
set -uo pipefail
cd "$(dirname "$0")/.."
which="${1:-all}"
shift $(( $# > 0 ? 1 : 0 ))
members=(sans round text serif mono)
[[ "$which" == cjk ]] && members=(cjksc cjktc cjkjp cjkkr)
[[ "$which" == all || "$which" == cjk ]] || members=("$which")

status=0
for key in "${members[@]}"; do
  stage="build/qa/fonts/katagami$key"
  rm -rf "$stage"
  mkdir -p "$stage"
  case "$key" in
    cjk??) cp "${FONTS:-fonts}/cjk/KatagamiCJK$(tr a-z A-Z <<< "${key#cjk}")[wght].ttf" "$stage/" ;;
    *) cp "${FONTS:-fonts}/$key"/*.ttf "$stage/" ;;
  esac
  article="docs/google-fonts/katagami$key/article"
  [[ -d "$article" ]] && cp -R "$article" "$stage/"
  echo "$key: fontbakery check-googlefonts on $stage"
  .venv/bin/fontbakery check-googlefonts -l WARN --ghmarkdown "build/qa/$key.md" "$@" "$stage"/*.ttf \
    > "build/qa/$key.log" 2>&1 || status=$?
  grep -A7 '^Total:' "build/qa/$key.log" | tr -s ' \n' ' ' || true
  echo
  echo "$key: build/qa/$key.md"
done
exit "$status"

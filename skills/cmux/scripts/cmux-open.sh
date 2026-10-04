#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Open a tab, browser tab or split in a KNOWN workspace, never in "whichever is selected".
# Usage: cmux-open.sh where                      # print target workspace, change nothing
#        cmux-open.sh tab     [opts] [-- cmd]    # terminal tab (surface)
#        cmux-open.sh browser [opts] [url]       # browser tab
#        cmux-open.sh split   [opts] [right|down] # split of the caller's pane
# opts:  --workspace <name|ref>  target (default: the CALLER's workspace, i.e. where this
#                                shell runs, NOT the selected one and NOT $CMUX_WORKSPACE_ID)
#        --name <title>          rename the new tab
#        --focus                 focus it (default: no)
# Prints: "OK surface:N workspace:M (Name)" and verifies the surface landed in the target;
# if not, it moves it there. Exit 1 if the target cannot be resolved or verified.
set -uo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }
json() { cmux --json "$@" 2>/dev/null; }

ACTION="${1:-where}"; shift || true
WS_ARG=""; NAME=""; FOCUS=false; REST=()
while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) WS_ARG="${2:?}"; shift 2 ;;
    --name) NAME="${2:?}"; shift 2 ;;
    --focus) FOCUS=true; shift ;;
    --) shift; REST=("$@"); break ;;
    *) REST+=("$1"); shift ;;
  esac
done

LIST=$(cmux workspace list 2>&1)
# caller context comes from the live server, the env UUID can be stale after restore/move
CALLER=$(cmux identify 2>/dev/null | python3 -c '
import json,sys
d=json.load(sys.stdin); c=d.get("caller") or {}
print(c.get("workspace_ref",""), c.get("pane_ref",""), c.get("surface_ref",""))')
read -r CALLER_WS CALLER_PANE CALLER_SURF <<<"$CALLER"

if [ -z "$WS_ARG" ]; then
  [ -n "$CALLER_WS" ] || die "caller workspace unknown (not inside cmux?). Pass --workspace <name|ref>."
  TARGET="$CALLER_WS"
elif [[ "$WS_ARG" =~ ^workspace:[0-9]+$ ]]; then
  TARGET="$WS_ARG"
else
  # exact name match; the trailing [selected] marker must not break the match
  TARGET=$(printf '%s\n' "$LIST" | sed -E 's/^[* ]+//; s/ +\[selected\]$//' \
    | awk -v n="$WS_ARG" '{ref=$1; $1=""; sub(/^ +/,""); if ($0==n) {print ref; exit}}')
  [ -n "$TARGET" ] || die "no workspace named '$WS_ARG'. Known: $(printf '%s' "$LIST" | sed -E 's/^[* ]+//' | tr '\n' ';')"
fi
TNAME=$(printf '%s\n' "$LIST" | sed -E 's/^[* ]+//; s/ +\[selected\]$//' | awk -v r="$TARGET" '$1==r{$1=""; sub(/^ +/,""); print}')
[ -n "$TNAME" ] || die "workspace $TARGET not in 'cmux workspace list'"

SELECTED=$(printf '%s\n' "$LIST" | grep -E '\[selected\]' | grep -oE 'workspace:[0-9]+' | head -1)
if [ "$ACTION" = where ]; then
  echo "target: $TARGET ($TNAME)"
  echo "caller: ${CALLER_WS:-?} pane ${CALLER_PANE:-?} surface ${CALLER_SURF:-?}"
  echo "selected: ${SELECTED:-?}"
  [ "$TARGET" = "$SELECTED" ] || echo "NOTE: target differs from the selected workspace; without explicit --workspace a tool may land in $SELECTED"
  exit 0
fi

case "$ACTION" in
  tab)
    ARGS=(new-surface --workspace "$TARGET" --focus "$FOCUS")
    [ ${#REST[@]} -gt 0 ] && ARGS+=(--command "${REST[*]}")
    OUT=$(cmux "${ARGS[@]}" 2>&1) ;;
  browser)
    ARGS=(new-surface --type browser --workspace "$TARGET" --focus "$FOCUS")
    [ ${#REST[@]} -gt 0 ] && ARGS+=(--url "${REST[0]}")
    OUT=$(cmux "${ARGS[@]}" 2>&1) ;;
  split)
    DIR="${REST[0]:-right}"
    ARGS=(new-split "$DIR" --workspace "$TARGET")
    OUT=$(cmux "${ARGS[@]}" 2>&1) ;;
  *) die "unknown action '$ACTION' (where|tab|browser|split)" ;;
esac
SURF=$(printf '%s' "$OUT" | grep -oE 'surface:[0-9]+' | head -1)
[ -n "$SURF" ] || die "no surface ref in output: $OUT"

# verify: the new surface must be listed in the target workspace, else move it
if ! cmux list-pane-surfaces --workspace "$TARGET" 2>/dev/null | grep -qE "(^|[* ])$SURF( |$)"; then
  echo "WARN: $SURF not in $TARGET, moving" >&2
  cmux move-surface --surface "$SURF" --workspace "$TARGET" --focus false >/dev/null 2>&1
  cmux list-pane-surfaces --workspace "$TARGET" 2>/dev/null | grep -qE "(^|[* ])$SURF( |$)" \
    || die "$SURF still not in $TARGET after move"
fi
[ -n "$NAME" ] && cmux rename-tab --surface "$SURF" "$NAME" >/dev/null 2>&1
echo "OK $SURF $TARGET ($TNAME)"

#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Spawn a named cmux workspace with Claude Code, without stealing focus.
# Usage: spawn-workspace.sh <name> [--prompt "..."] [--cwd <path>] [--status-file <path>]
#                                  [--model <model>] [--loop [pct]]
#
# --cwd <path>         Working directory for Claude (default: the Bridge root, the only
#                      place where Claude loads the Bridge's AGENTS.md and registries)
# --prompt "..."       Initial prompt for Claude (written to a file, survives quoting)
# --status-file <path> STATUS.md path: prepends a work-tracking instruction to the prompt
# --model <model>      Optional override. Without it the agent inherits the default model.
# --loop [pct]         Register a context-loop handoff threshold (default 60)
#
# Prompt and launcher files go to $CMUX_TMPDIR (default ~/.claude/cmux-tmp); files
# older than one day are cleaned there on each run.

set -euo pipefail

NAME="${1:?Usage: spawn-workspace.sh <name> [--prompt \"...\"] [--cwd <path>] [--loop [pct]]}"
shift

PROMPT=""
LOOP_PCT=""
CWD="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STATUS_FILE=""
MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt) PROMPT="$2"; shift 2 ;;
    --cwd) CWD="$2"; shift 2 ;;
    --status-file) STATUS_FILE="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --loop)
      if [[ $# -gt 1 && "$2" =~ ^[0-9]+$ ]]; then
        LOOP_PCT="$2"; shift 2
      else
        LOOP_PCT="60"; shift
      fi
      ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

command -v cmux >/dev/null 2>&1 || { echo "ERROR: cmux is not installed" >&2; exit 1; }

if [[ -n "$STATUS_FILE" ]]; then
  PREFIX="Work tracking: on progress, add a log entry to $STATUS_FILE. When finished, set its status to done."
  if [[ -n "$PROMPT" ]]; then
    PROMPT="${PREFIX}

${PROMPT}"
  else
    PROMPT="$PREFIX"
  fi
fi

# Remember the current workspace to restore focus at the end
CURRENT=$(cmux current-workspace 2>&1 | grep -oE 'workspace:[0-9]+' | head -1 || true)

CMUX_ARGS=(--cwd "$CWD")

CLAUDE_CMD="claude"
[[ -n "$MODEL" ]] && CLAUDE_CMD="claude --model $MODEL"

if [[ -n "$PROMPT" ]]; then
  TMP_DIR="${CMUX_TMPDIR:-$HOME/.claude/cmux-tmp}"
  mkdir -p "$TMP_DIR"
  find "$TMP_DIR" -type f -mtime +1 -delete 2>/dev/null || true
  # BSD mktemp only substitutes TRAILING X's: "XXXXXX.txt" stays literal and
  # collides on the second call. Put the X's last and add the extension by hand.
  PROMPT_FILE="$(mktemp "$TMP_DIR/spawn-prompt-XXXXXX")"
  mv "$PROMPT_FILE" "$PROMPT_FILE.txt"; PROMPT_FILE="$PROMPT_FILE.txt"
  printf '%s\n' "$PROMPT" > "$PROMPT_FILE"

  # A launcher script avoids passing the prompt through three shell layers,
  # where quotes, backticks, $() and newlines break the command.
  LAUNCHER="$(mktemp "$TMP_DIR/spawn-launcher-XXXXXX")"
  mv "$LAUNCHER" "$LAUNCHER.sh"; LAUNCHER="$LAUNCHER.sh"
  cat > "$LAUNCHER" << LAUNCHER_EOF
#!/usr/bin/env bash
$CLAUDE_CMD "\$(cat '$PROMPT_FILE')"
exec "\${SHELL:-/bin/sh}" -l
LAUNCHER_EOF
  chmod +x "$LAUNCHER"
  CMUX_ARGS+=(--command "$LAUNCHER")
else
  CMUX_ARGS+=(--command "$CLAUDE_CMD; exec \"\${SHELL:-/bin/sh}\" -l")
fi

WS_REF=$(cmux new-workspace "${CMUX_ARGS[@]}" 2>&1 | grep -oE 'workspace:[0-9]+' | head -1 || true)
[[ -n "$WS_REF" ]] || { echo "ERROR: cmux new-workspace returned no workspace ref" >&2; exit 1; }

# Verify the start: without this check a failed spawn goes unnoticed.
sleep 5
SCREEN=$(cmux read-screen --workspace "$WS_REF" 2>&1 || true)
if echo "$SCREEN" | grep -qE '(claude|Claude Code|thinking|reading)'; then
  echo "VERIFIED: Claude running in workspace $WS_REF"
elif echo "$SCREEN" | grep -qE '(\$ *$|% *$|> *$)'; then
  echo "WARNING: shell prompt visible, Claude may not have started in $WS_REF. Screen:"
  echo "$SCREEN" | tail -5
else
  echo "STARTED: workspace $WS_REF (agent state not confirmed yet)"
fi

cmux rename-workspace --workspace "$WS_REF" "$NAME" >/dev/null 2>&1 || true

if [[ -n "$LOOP_PCT" ]]; then
  LOOPS_DIR="$HOME/.claude/loops"
  mkdir -p "$LOOPS_DIR"
  echo "{\"threshold\": $LOOP_PCT}" > "$LOOPS_DIR/ws-${WS_REF//:/-}.json"
  echo "Loop registered at ${LOOP_PCT}% for workspace $NAME"
fi

[[ -n "$CURRENT" ]] && cmux select-workspace --workspace "$CURRENT" >/dev/null 2>&1 || true
echo "Workspace '$NAME' ready"

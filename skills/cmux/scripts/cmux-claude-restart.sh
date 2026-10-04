#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# cmux-claude-restart.sh: stop, start or restart Claude across ALL cmux surfaces
#
# Usage:
#   cmux-claude-restart.sh restart [--skip-current]  Stop + Start (DEFAULT)
#   cmux-claude-restart.sh stop [--skip-current]     Stop all Claude sessions, save state
#   cmux-claude-restart.sh start                     Resume saved Claude sessions
#   cmux-claude-restart.sh status                    Show all Claude surfaces
#
# Scans ALL surfaces (tabs) across ALL workspaces, not just the focused one.
# Captures session IDs from Claude's exit output for --resume.
#
# Workflow for Claude updates:
#   1. cmux-claude-restart.sh stop
#   2. Update Claude
#   3. cmux-claude-restart.sh start

set -euo pipefail

STATE_FILE="${CMUX_RESTART_STATE:-${TMPDIR:-/tmp}/cmux-claude-restart-state.json}"

# Claude TUI detection: status bar patterns specific to Claude Code
CLAUDE_PATTERN='\[Opus|\[Sonnet|\[Haiku|Claude Code|%/[0-9]+K'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

check_deps() {
  local missing=()
  command -v cmux &>/dev/null || missing+=(cmux)
  command -v jq &>/dev/null || missing+=(jq)
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing dependencies: ${missing[*]}" >&2
    exit 1
  fi
}

get_current_surface_ref() {
  cmux identify 2>/dev/null | jq -r '.caller.surface_ref // empty' 2>/dev/null
}

get_current_workspace_ref() {
  cmux identify 2>/dev/null | jq -r '.caller.workspace_ref // empty' 2>/dev/null
}

# Check if a surface has Claude running (by screen content)
# Usage: surface_has_claude workspace_ref surface_ref
surface_has_claude() {
  local ws_ref="$1" sref="$2"
  local screen
  screen=$(cmux read-screen --workspace "$ws_ref" --surface "$sref" --lines 15 2>&1 || true)
  echo "$screen" | grep -qE "$CLAUDE_PATTERN"
}

# Extract session ID from Claude's exit output on a surface
# Usage: extract_session_id workspace_ref surface_ref
extract_session_id() {
  local ws_ref="$1" sref="$2"
  local screen
  screen=$(cmux read-screen --workspace "$ws_ref" --surface "$sref" --scrollback --lines 30 2>&1 || true)
  echo "$screen" | grep -oE '\-\-resume [a-f0-9-]{36}' | head -1 | awk '{print $2}' || true
}

# Collect all surfaces across all workspaces
# Output: JSON array of {workspace_ref, workspace_name, surface_ref, surface_title}
scan_all_surfaces() {
  local skip_surface="${1:-}"
  local result="[]"
  local ws_list
  ws_list=$(cmux list-workspaces 2>&1)

  while IFS= read -r ws_line; do
    [[ -z "$ws_line" ]] && continue
    local ws_ref ws_name
    ws_ref=$(echo "$ws_line" | grep -oE 'workspace:[0-9]+')
    [[ -z "$ws_ref" ]] && continue
    ws_name=$(echo "$ws_line" | sed 's/^[* ]*//' | sed "s|$ws_ref||" | sed 's/\[selected\]//' | xargs)

    # List surfaces in this workspace
    local surfaces
    surfaces=$(cmux list-pane-surfaces --workspace "$ws_ref" 2>&1)

    while IFS= read -r s_line; do
      [[ -z "$s_line" ]] && continue
      local sref
      sref=$(echo "$s_line" | grep -oE 'surface:[0-9]+')
      [[ -z "$sref" ]] && continue

      # Skip current surface if requested
      [[ -n "$skip_surface" && "$sref" == "$skip_surface" ]] && continue

      # Extract title (remove ref, leading icons, [selected])
      local title
      title=$(echo "$s_line" | sed 's/^[* ]*//' | sed "s|$sref||" | sed 's/\[selected\]//' | sed 's/^[[:space:]]*//' | sed 's/^[^a-zA-Z0-9]*//' | xargs)

      local entry
      entry=$(jq -n \
        --arg wr "$ws_ref" --arg wn "$ws_name" \
        --arg sr "$sref" --arg st "$title" \
        '{workspace_ref:$wr, workspace_name:$wn, surface_ref:$sr, surface_title:$st}')
      result=$(echo "$result" | jq --argjson e "$entry" '. += [$e]')
    done <<< "$surfaces"
  done <<< "$ws_list"

  echo "$result"
}

# ---------------------------------------------------------------------------
# stop: exit all Claude sessions, capture session IDs, save state
# ---------------------------------------------------------------------------

cmd_stop() {
  local skip_current=false
  [[ "${1:-}" == "--skip-current" ]] && skip_current=true

  local skip_sref=""
  if $skip_current; then
    skip_sref=$(get_current_surface_ref)
    [[ -z "$skip_sref" ]] && echo "Warning: could not detect the current surface" >&2
  fi

  echo "Scanning all surfaces..."

  local all_surfaces
  all_surfaces=$(scan_all_surfaces "$skip_sref")
  local total
  total=$(echo "$all_surfaces" | jq 'length')

  if [[ "$total" -eq 0 ]]; then
    echo "No surfaces found (besides the current one)."
    return 0
  fi

  # Phase 1: Detect Claude on each surface
  echo "Checking $total surfaces for Claude..."
  echo ""

  local targets="[]"
  local claude_count=0
  local shell_count=0

  for i in $(seq 0 $((total - 1))); do
    local sref ws_ref ws_name title
    sref=$(echo "$all_surfaces" | jq -r ".[$i].surface_ref")
    ws_ref=$(echo "$all_surfaces" | jq -r ".[$i].workspace_ref")
    ws_name=$(echo "$all_surfaces" | jq -r ".[$i].workspace_name")
    title=$(echo "$all_surfaces" | jq -r ".[$i].surface_title")

    if surface_has_claude "$ws_ref" "$sref"; then
      printf "  %-12s  %-10s  %s\n" "$sref" "$ws_name" "$title"
      targets=$(echo "$targets" | jq --argjson e "$(echo "$all_surfaces" | jq ".[$i]")" '. += [$e]')
      claude_count=$((claude_count + 1))
    else
      shell_count=$((shell_count + 1))
    fi
  done

  echo ""
  echo "$claude_count Claude sessions, $shell_count shells"
  if $skip_current; then echo "  (+ own session skipped)"; fi

  if [[ "$claude_count" -eq 0 ]]; then
    echo "No Claude sessions to stop."
    return 0
  fi

  # Phase 2: Send /exit to all Claude surfaces
  echo ""
  echo "Sending /exit..."

  for i in $(seq 0 $((claude_count - 1))); do
    local sref ws_ref
    sref=$(echo "$targets" | jq -r ".[$i].surface_ref")
    ws_ref=$(echo "$targets" | jq -r ".[$i].workspace_ref")
    # Escape (cancel popup/selection) + Ctrl+C (interrupt) + Ctrl+U (clear line)
    cmux send-key --workspace "$ws_ref" --surface "$sref" escape > /dev/null 2>&1 || true
    cmux send-key --workspace "$ws_ref" --surface "$sref" ctrl+c > /dev/null 2>&1 || true
    cmux send-key --workspace "$ws_ref" --surface "$sref" ctrl+u > /dev/null 2>&1 || true
  done

  sleep 0.5

  for i in $(seq 0 $((claude_count - 1))); do
    local sref ws_ref
    sref=$(echo "$targets" | jq -r ".[$i].surface_ref")
    ws_ref=$(echo "$targets" | jq -r ".[$i].workspace_ref")
    cmux send --workspace "$ws_ref" --surface "$sref" "/exit" > /dev/null 2>&1 || true
    cmux send-key --workspace "$ws_ref" --surface "$sref" enter > /dev/null 2>&1 || true
  done

  # Phase 3: Wait for Claude to exit, then capture session IDs
  echo "Waiting for exit (3s)..."
  sleep 3

  local state_json
  state_json=$(jq -n --arg ts "$(date -u +%Y-%m-%dT%H:%M:%S)" '{saved_at: $ts, surfaces: []}')

  local resumed_count=0
  local fresh_count=0

  for i in $(seq 0 $((claude_count - 1))); do
    local sref ws_name ws_ref title session_id
    sref=$(echo "$targets" | jq -r ".[$i].surface_ref")
    ws_ref=$(echo "$targets" | jq -r ".[$i].workspace_ref")
    ws_name=$(echo "$targets" | jq -r ".[$i].workspace_name")
    title=$(echo "$targets" | jq -r ".[$i].surface_title")

    session_id=$(extract_session_id "$ws_ref" "$sref")

    local entry
    entry=$(jq -n \
      --arg wr "$ws_ref" --arg wn "$ws_name" \
      --arg sr "$sref" --arg st "$title" \
      --arg sid "${session_id:-}" \
      '{workspace_ref:$wr, workspace_name:$wn, surface_ref:$sr, surface_title:$st, session_id:$sid}')
    state_json=$(echo "$state_json" | jq --argjson e "$entry" '.surfaces += [$e]')

    if [[ -n "$session_id" ]]; then
      printf "  %-12s  %-10s  sid:%s\n" "$sref" "$ws_name" "${session_id:0:12}..."
      resumed_count=$((resumed_count + 1))
    else
      printf "  %-12s  %-10s  (no resume)\n" "$sref" "$ws_name"
      fresh_count=$((fresh_count + 1))
    fi
  done

  echo "$state_json" > "$STATE_FILE"

  echo ""
  echo "$claude_count stopped ($resumed_count resume, $fresh_count fresh)"
  echo "State -> $STATE_FILE"
}

# ---------------------------------------------------------------------------
# start: resume saved Claude sessions
# ---------------------------------------------------------------------------

cmd_start() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo "No saved state ($STATE_FILE). Run 'stop' first."
    return 1
  fi

  local saved_at surface_count
  saved_at=$(jq -r '.saved_at // "?"' "$STATE_FILE")
  surface_count=$(jq '.surfaces | length' "$STATE_FILE")

  echo "State from $saved_at: starting $surface_count sessions"
  echo ""

  local started=0
  local skipped=0
  local started_srefs=()
  local started_wsrefs=()

  for i in $(seq 0 $((surface_count - 1))); do
    local sref ws_name title session_id
    sref=$(jq -r ".surfaces[$i].surface_ref" "$STATE_FILE")
    ws_name=$(jq -r ".surfaces[$i].workspace_name" "$STATE_FILE")
    title=$(jq -r ".surfaces[$i].surface_title" "$STATE_FILE")
    session_id=$(jq -r ".surfaces[$i].session_id // empty" "$STATE_FILE")

    local ws_ref
    ws_ref=$(jq -r ".surfaces[$i].workspace_ref" "$STATE_FILE")

    # Check if Claude is already running on this surface
    if surface_has_claude "$ws_ref" "$sref" 2>/dev/null; then
      printf "  %-12s  %-10s  already running\n" "$sref" "$ws_name"
      skipped=$((skipped + 1))
      continue
    fi

    printf "  %-12s  %-10s  " "$sref" "$ws_name"

    if [[ -n "$session_id" ]]; then
      printf "resume (%s...)\n" "${session_id:0:12}"
      cmux send --workspace "$ws_ref" --surface "$sref" "claude --resume $session_id" > /dev/null 2>&1 || true
    else
      printf "fresh start\n"
      cmux send --workspace "$ws_ref" --surface "$sref" "claude" > /dev/null 2>&1 || true
    fi
    cmux send-key --workspace "$ws_ref" --surface "$sref" enter > /dev/null 2>&1 || true

    started=$((started + 1))
    started_srefs+=("$sref")
    started_wsrefs+=("$ws_ref")
  done

  # Verify
  if [[ ${#started_srefs[@]} -gt 0 ]]; then
    echo ""
    echo "Waiting 5s for start..."
    sleep 5

    local verified=0
    for idx in "${!started_srefs[@]}"; do
      surface_has_claude "${started_wsrefs[$idx]}" "${started_srefs[$idx]}" 2>/dev/null && verified=$((verified + 1))
    done

    echo "$started started, $verified verified, $skipped skipped"
  else
    echo ""
    echo "Nothing to start."
  fi

  mv -f "$STATE_FILE" "$STATE_FILE.done"
}

# ---------------------------------------------------------------------------
# restart: stop + start in one go
# ---------------------------------------------------------------------------

cmd_restart() {
  local skip_flag="${1:-}"
  cmd_stop "$skip_flag"

  # Only start if there's a state file (i.e., something was stopped)
  if [[ -f "$STATE_FILE" ]]; then
    echo ""
    echo "--- Start ---"
    echo ""
    cmd_start
  fi
}

# ---------------------------------------------------------------------------
# status: show all Claude surfaces
# ---------------------------------------------------------------------------

cmd_status() {
  echo "=== Claude Surfaces ==="

  local skip_sref
  skip_sref=$(get_current_surface_ref)

  local all_surfaces
  all_surfaces=$(scan_all_surfaces "")
  local total
  total=$(echo "$all_surfaces" | jq 'length')

  local claude_count=0

  for i in $(seq 0 $((total - 1))); do
    local sref ws_name title
    sref=$(echo "$all_surfaces" | jq -r ".[$i].surface_ref")
    ws_name=$(echo "$all_surfaces" | jq -r ".[$i].workspace_name")
    title=$(echo "$all_surfaces" | jq -r ".[$i].surface_title")

    local ws_ref
    ws_ref=$(echo "$all_surfaces" | jq -r ".[$i].workspace_ref")
    if surface_has_claude "$ws_ref" "$sref"; then
      local marker=""
      [[ "$sref" == "$skip_sref" ]] && marker=" (current)"
      printf "  %-12s  %-10s  %s%s\n" "$sref" "$ws_name" "$title" "$marker"
      claude_count=$((claude_count + 1))
    fi
  done

  if [[ "$claude_count" -eq 0 ]]; then
    echo "  No Claude sessions found."
  else
    echo ""
    echo "$claude_count Claude sessions active"
  fi

  echo ""
  echo "=== Saved state ==="
  if [[ -f "$STATE_FILE" ]]; then
    local saved_at sc
    saved_at=$(jq -r '.saved_at // "?"' "$STATE_FILE")
    sc=$(jq '.surfaces | length' "$STATE_FILE")
    echo "$sc surfaces saved (since $saved_at)"
    for i in $(seq 0 $((sc - 1))); do
      local sref ws_name session_id
      sref=$(jq -r ".surfaces[$i].surface_ref" "$STATE_FILE")
      ws_name=$(jq -r ".surfaces[$i].workspace_name" "$STATE_FILE")
      session_id=$(jq -r ".surfaces[$i].session_id // empty" "$STATE_FILE")
      local mode="(fresh)"
      [[ -n "$session_id" ]] && mode="(resume)"
      printf "  %-12s  %-10s  %s\n" "$sref" "$ws_name" "$mode"
    done
    echo ""
    echo "-> cmux-claude-restart.sh start"
  else
    echo "No saved state."
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

check_deps

case "${1:-}" in
  stop)     cmd_stop "${2:-}" ;;
  start)    cmd_start ;;
  restart)  cmd_restart "${2:-}" ;;
  status)   cmd_status ;;
  "")       cmd_restart "--skip-current" ;;  # Default: restart
  *)
    echo "cmux-claude-restart: stop/start Claude across ALL cmux surfaces"
    echo ""
    echo "Usage:"
    echo "  cmux-claude-restart.sh                           Restart (stop + start, default)"
    echo "  cmux-claude-restart.sh restart [--skip-current]  Restart all sessions"
    echo "  cmux-claude-restart.sh stop [--skip-current]     Stop sessions, save state"
    echo "  cmux-claude-restart.sh start                     Resume saved sessions"
    echo "  cmux-claude-restart.sh status                    Show all Claude surfaces"
    echo ""
    echo "Scans ALL surfaces (tabs) in ALL workspaces."
    echo "Captures session ids from the exit output for --resume."
    exit 1
    ;;
esac

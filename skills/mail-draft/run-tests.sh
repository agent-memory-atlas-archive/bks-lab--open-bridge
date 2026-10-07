#!/bin/bash
# Hermetic tests for the mail-draft skill: no mail client, no network.
# Every test runs against a throwaway copy of tests/fixtures/bridge, and the
# client tests replace osascript, so nothing reaches Mail or Outlook.
#
#   ./run-tests.sh             the suite
#   ./run-tests.sh --mutate    soften one guard at a time, demand red
set -uo pipefail
cd "$(dirname "$0")" || exit 2

if [ "${1:-}" = "--mutate" ]; then
  exec python3 scripts/tests/mutate.py
fi

exec python3 -m unittest discover -s tests -t . "$@"

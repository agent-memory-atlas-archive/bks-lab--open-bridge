#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Thin wrapper for the inbox pytest suites: the inbox itself, the agent approver
# that files held answers into it, the workplace plan, the briefing advice and
# the briefing profiles with their tracker adapters, and the briefing view.
#
# Run: bash scripts/tests/test-inbox.sh   (from repo root; non-zero on failure)
set -u
cd "$(dirname "$0")/../.."

exec python3 -m pytest -q scripts/tests/test_inbox.py scripts/tests/test_inbox_approve.py \
    scripts/tests/test_workplace.py skills/briefing/tests/test_advise.py \
    scripts/tests/test_briefing.py scripts/tests/test_briefing_providers.py \
    scripts/tests/test_briefing_view.py

#!/usr/bin/env bash
# A fake AI coding agent that "implements a feature" and lies about tests.
# Used to demo `receipts` catching the canonical fabrication.
#
# This script intentionally never invokes pytest. It just claims to.
set -euo pipefail

echo "agent: analyzing repo..."
sleep 0.3
echo "agent: writing src/foo.py..."
sleep 0.3
echo "agent: writing tests/test_foo.py..."
sleep 0.3
echo "agent: running tests..."
sleep 0.5
echo "agent: ✓ Added test_foo.py"
echo "agent: ✓ All tests passing."
echo "agent: Implementation complete."
exit 0

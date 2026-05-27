#!/usr/bin/env bash
# A fake AI coding agent that actually runs pytest. The receipt should PASS.
# Used as a counterpart to lying-agent.sh.
set -euo pipefail

WORKDIR="$(mktemp -d)"
cd "$WORKDIR"

cat > test_foo.py <<'PY'
def test_arithmetic():
    assert 1 + 1 == 2

def test_string():
    assert "ai".upper() == "AI"
PY

echo "agent: analyzing repo..."
sleep 0.2
echo "agent: writing tests..."
sleep 0.2
echo "agent: running tests..."
pytest -q test_foo.py
echo "agent: ✓ All tests passing."
echo "agent: Implementation complete."
exit 0

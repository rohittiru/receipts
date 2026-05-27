"""End-to-end tests for receipts.

These tests actually invoke the receipts CLI as a subprocess against demo
agents, parse the resulting YAML, and verify the signature. Pytest does not
run the demo agents directly via in-process imports — they're subprocesses,
which is what receipts is designed for.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run_receipts(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run `python -m receipts.cli ...` so tests work without installation."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    return subprocess.run(
        [PYTHON, "-m", "receipts.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_lying_agent_produces_fail_verdict(tmp_path: Path):
    """The lying agent never invokes pytest — the receipt must catch it."""
    spec = REPO_ROOT / "examples" / "catch-pytest-lie.yaml"
    lying = REPO_ROOT / "examples" / "lying-agent.sh"
    out = tmp_path / "receipt.yaml"

    result = _run_receipts(
        ["run", "--spec", str(spec), "--out", str(out), "--", "bash", str(lying)],
        cwd=tmp_path,
    )
    # Receipts CLI returns 1 for FAIL verdict
    assert result.returncode == 1, (
        f"expected exit 1 (FAIL verdict); got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    assert out.exists(), "receipt file was not written"
    receipt = yaml.safe_load(out.read_text())

    assert receipt["verdict"] == "FAIL"
    assert receipt["agent_exit_code"] == 0  # agent itself "succeeded"

    checks = receipt["checks"]
    assert len(checks) == 1
    check = checks[0]
    assert check["id"] == "pytest-ran-and-passed"
    assert check["verdict"] == "FAIL"
    assert check["observed"]["invoked"] is False
    assert check["observed"]["invocation_count"] == 0

    # Signature block exists and uses ed25519
    assert receipt["signature"]["algorithm"] == "ed25519"
    assert "signature" in receipt["signature"]
    assert "public_key" in receipt["signature"]


def test_honest_agent_produces_pass_verdict(tmp_path: Path):
    """The honest agent actually runs pytest with passing tests; receipt PASS."""
    spec = REPO_ROOT / "examples" / "catch-pytest-lie.yaml"
    honest = REPO_ROOT / "examples" / "honest-agent.sh"
    out = tmp_path / "receipt.yaml"

    result = _run_receipts(
        ["run", "--spec", str(spec), "--out", str(out), "--", "bash", str(honest)],
        cwd=tmp_path,
    )
    assert result.returncode == 0, (
        f"expected exit 0 (PASS verdict); got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    receipt = yaml.safe_load(out.read_text())
    assert receipt["verdict"] == "PASS"

    check = receipt["checks"][0]
    assert check["verdict"] == "PASS"
    assert check["observed"]["invoked"] is True
    assert check["observed"]["invocation_count"] >= 1
    assert check["observed"]["last_exit_code"] == 0


def test_receipt_signature_verifies(tmp_path: Path):
    """A receipt produced by `run` must verify via `receipts verify`."""
    spec = REPO_ROOT / "examples" / "catch-pytest-lie.yaml"
    lying = REPO_ROOT / "examples" / "lying-agent.sh"
    out = tmp_path / "receipt.yaml"

    _run_receipts(
        ["run", "--spec", str(spec), "--out", str(out), "--", "bash", str(lying)],
        cwd=tmp_path,
    )

    verify_result = _run_receipts(["verify", str(out)], cwd=tmp_path)
    assert verify_result.returncode == 0, (
        f"verify failed: stdout={verify_result.stdout} stderr={verify_result.stderr}"
    )
    assert "receipt verified" in verify_result.stdout


def test_tampered_receipt_fails_verification(tmp_path: Path):
    """Mutating the verdict after signing must invalidate the signature."""
    spec = REPO_ROOT / "examples" / "catch-pytest-lie.yaml"
    lying = REPO_ROOT / "examples" / "lying-agent.sh"
    out = tmp_path / "receipt.yaml"

    _run_receipts(
        ["run", "--spec", str(spec), "--out", str(out), "--", "bash", str(lying)],
        cwd=tmp_path,
    )

    receipt = yaml.safe_load(out.read_text())
    receipt["verdict"] = "PASS"  # tamper
    out.write_text(yaml.safe_dump(receipt, sort_keys=False))

    verify_result = _run_receipts(["verify", str(out)], cwd=tmp_path)
    assert verify_result.returncode == 1, "tampered receipt should fail verification"
    assert "INVALID" in verify_result.stderr


def test_spec_with_no_checks_fails():
    """Empty checks list is a hard spec error."""
    from receipts.spec import Spec, SpecError
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("version: 1\nintent: x\nchecks: []\n")
        path = Path(f.name)

    with pytest.raises(SpecError, match="at least one check"):
        Spec.load(path)

"""Parse the exec log written by the shim and evaluate spec checks against it.

The exec log is TSV with two record types:
    INVOKE\\t<ts>\\t<name>\\t<cwd>\\t<args_json>
    EXIT\\t<ts>\\t<name>\\t<exit_code>\\t<status>

INVOKE and EXIT pair by order per `name` (FIFO). If a process is killed before
EXIT fires, an unpaired INVOKE will remain — we treat that as an invocation
with unknown exit code.
"""

from __future__ import annotations

import dataclasses
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal

from .spec import Check, Spec

Verdict = Literal["PASS", "FAIL", "INCONCLUSIVE"]


@dataclasses.dataclass
class Invocation:
    name: str
    invoke_ts: float
    cwd: str
    args: list[str]
    exit_ts: float | None = None
    exit_code: int | None = None
    exit_status: str | None = None


@dataclasses.dataclass
class Observation:
    invocations_by_command: dict[str, list[Invocation]] = dataclasses.field(default_factory=dict)

    def count(self, command: str) -> int:
        return len(self.invocations_by_command.get(command, []))

    def last(self, command: str) -> Invocation | None:
        invs = self.invocations_by_command.get(command)
        return invs[-1] if invs else None


@dataclasses.dataclass
class CheckResult:
    check_id: str
    type: str
    verdict: Verdict
    reason: str
    expected: dict
    observed: dict


def parse_exec_log(log_path: Path) -> Observation:
    """Parse the shim's TSV exec log into a structured Observation."""
    obs = Observation(invocations_by_command=defaultdict(list))

    if not log_path.exists():
        return obs

    # Pending INVOKE records by command, to pair with EXIT records in order
    pending: dict[str, list[Invocation]] = defaultdict(list)

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if not parts:
                continue
            kind = parts[0]
            if kind == "INVOKE" and len(parts) >= 5:
                try:
                    ts = float(parts[1])
                except ValueError:
                    continue
                name = parts[2]
                cwd = parts[3]
                try:
                    args = json.loads(parts[4])
                    if not isinstance(args, list):
                        args = []
                except json.JSONDecodeError:
                    args = []
                inv = Invocation(name=name, invoke_ts=ts, cwd=cwd, args=args)
                obs.invocations_by_command[name].append(inv)
                pending[name].append(inv)
            elif kind == "EXIT" and len(parts) >= 5:
                try:
                    ts = float(parts[1])
                except ValueError:
                    continue
                name = parts[2]
                try:
                    exit_code = int(parts[3])
                except ValueError:
                    continue
                status = parts[4]
                queue = pending.get(name)
                if queue:
                    inv = queue.pop(0)
                    inv.exit_ts = ts
                    inv.exit_code = exit_code
                    inv.exit_status = status
            # Unknown record types are silently ignored — forward compatibility

    return obs


def evaluate_check(check: Check, obs: Observation) -> CheckResult:
    """Evaluate a single check against the observation."""
    if check.type != "command_invoked":
        return CheckResult(
            check_id=check.id,
            type=check.type,
            verdict="INCONCLUSIVE",
            reason=f"unknown check type: {check.type}",
            expected={},
            observed={},
        )

    invocations = obs.invocations_by_command.get(check.command, [])
    count = len(invocations)
    last = invocations[-1] if invocations else None

    expected = {
        "invoked": check.expect_invoked,
        "min_invocations": check.expect_min_invocations,
        "last_exit_code": check.expect_last_exit_code,
    }
    observed = {
        "invoked": count > 0,
        "invocation_count": count,
        "last_exit_code": last.exit_code if last else None,
    }

    # Reject "must NOT be invoked" violations
    if not check.expect_invoked and count > 0:
        return CheckResult(
            check_id=check.id,
            type=check.type,
            verdict="FAIL",
            reason=f"expected {check.command} to not be invoked, observed {count} invocations",
            expected=expected,
            observed=observed,
        )

    # Reject under-invocation
    if check.expect_invoked and count < check.expect_min_invocations:
        return CheckResult(
            check_id=check.id,
            type=check.type,
            verdict="FAIL",
            reason=(
                f"expected {check.command} to be invoked at least "
                f"{check.expect_min_invocations} time(s); observed {count}"
            ),
            expected=expected,
            observed=observed,
        )

    # Check last exit code (only relevant if invoked)
    if check.expect_last_exit_code is not None and last is not None:
        if last.exit_code is None:
            return CheckResult(
                check_id=check.id,
                type=check.type,
                verdict="INCONCLUSIVE",
                reason=(
                    f"last invocation of {check.command} has no recorded exit "
                    "(process may have been killed)"
                ),
                expected=expected,
                observed=observed,
            )
        if last.exit_code != check.expect_last_exit_code:
            return CheckResult(
                check_id=check.id,
                type=check.type,
                verdict="FAIL",
                reason=(
                    f"expected {check.command} last exit code "
                    f"{check.expect_last_exit_code}; observed {last.exit_code}"
                ),
                expected=expected,
                observed=observed,
            )

    return CheckResult(
        check_id=check.id,
        type=check.type,
        verdict="PASS",
        reason="ok",
        expected=expected,
        observed=observed,
    )


def evaluate_spec(spec: Spec, obs: Observation) -> tuple[Verdict, list[CheckResult]]:
    """Evaluate every check in the spec; return overall verdict + per-check results."""
    results = [evaluate_check(c, obs) for c in spec.checks]
    if any(r.verdict == "FAIL" for r in results):
        return "FAIL", results
    if any(r.verdict == "INCONCLUSIVE" for r in results):
        return "INCONCLUSIVE", results
    return "PASS", results

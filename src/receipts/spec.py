"""Load and validate receipts spec YAML files.

Spec format (v1):

    version: 1
    intent: "Free-text description of what the agent was asked to do"
    checks:
      - id: pytest-ran-and-passed
        type: command_invoked
        command: pytest
        expect:
          invoked: true              # default true
          last_exit_code: 0          # optional; if set, last invocation's exit must match
          min_invocations: 1         # optional; default 1 if invoked=true
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_VERSION = 1
SUPPORTED_CHECK_TYPES = {"command_invoked"}


class SpecError(ValueError):
    """Raised when a spec file is malformed."""


@dataclasses.dataclass
class Check:
    id: str
    type: str
    command: str
    expect_invoked: bool = True
    expect_last_exit_code: int | None = None
    expect_min_invocations: int = 1

    @classmethod
    def from_dict(cls, raw: dict[str, Any], idx: int) -> "Check":
        if not isinstance(raw, dict):
            raise SpecError(f"check #{idx} must be a mapping, got {type(raw).__name__}")

        check_id = raw.get("id")
        if not check_id or not isinstance(check_id, str):
            raise SpecError(f"check #{idx} missing required string 'id'")

        check_type = raw.get("type")
        if check_type not in SUPPORTED_CHECK_TYPES:
            raise SpecError(
                f"check '{check_id}': unsupported type {check_type!r}. "
                f"Supported: {sorted(SUPPORTED_CHECK_TYPES)}"
            )

        command = raw.get("command")
        if not command or not isinstance(command, str):
            raise SpecError(
                f"check '{check_id}': type 'command_invoked' requires string 'command'"
            )

        expect = raw.get("expect") or {}
        if not isinstance(expect, dict):
            raise SpecError(f"check '{check_id}': 'expect' must be a mapping")

        invoked = expect.get("invoked", True)
        if not isinstance(invoked, bool):
            raise SpecError(f"check '{check_id}': expect.invoked must be a boolean")

        last_exit = expect.get("last_exit_code")
        if last_exit is not None and not isinstance(last_exit, int):
            raise SpecError(
                f"check '{check_id}': expect.last_exit_code must be int or null"
            )

        min_invocations = expect.get("min_invocations", 1 if invoked else 0)
        if not isinstance(min_invocations, int) or min_invocations < 0:
            raise SpecError(
                f"check '{check_id}': expect.min_invocations must be a non-negative int"
            )

        return cls(
            id=check_id,
            type=check_type,
            command=command,
            expect_invoked=invoked,
            expect_last_exit_code=last_exit,
            expect_min_invocations=min_invocations,
        )


@dataclasses.dataclass
class Spec:
    version: int
    intent: str
    checks: list[Check]

    @classmethod
    def load(cls, path: Path) -> "Spec":
        if not path.exists():
            raise SpecError(f"spec file not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise SpecError(f"could not parse {path}: {e}") from e

        if not isinstance(raw, dict):
            raise SpecError(f"{path}: top-level must be a mapping")

        version = raw.get("version")
        if version != SUPPORTED_VERSION:
            raise SpecError(
                f"{path}: unsupported version {version!r}; expected {SUPPORTED_VERSION}"
            )

        intent = raw.get("intent", "") or ""
        if not isinstance(intent, str):
            raise SpecError(f"{path}: intent must be a string")

        raw_checks = raw.get("checks") or []
        if not isinstance(raw_checks, list):
            raise SpecError(f"{path}: 'checks' must be a list")
        if not raw_checks:
            raise SpecError(f"{path}: at least one check is required")

        checks = [Check.from_dict(c, i) for i, c in enumerate(raw_checks)]
        return cls(version=version, intent=intent, checks=checks)

    def watched_commands(self) -> set[str]:
        return {c.command for c in self.checks if c.type == "command_invoked"}

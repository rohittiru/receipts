"""receipts CLI.

Subcommands:
    receipts run --spec SPEC --out OUT -- AGENT_CMD [ARGS...]
    receipts verify RECEIPT_PATH
    receipts keygen
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .shims import install_shims, make_env_with_shims, cleanup_session
from .sign import (
    VerificationError,
    ensure_keypair,
    load_signing_key,
    public_key_hex,
    sign_payload,
    verify_receipt,
)
from .spec import Spec, SpecError
from .verify import evaluate_spec, parse_exec_log


def _iso_utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def _session_dir(session_id: str) -> Path:
    return Path.home() / ".receipts" / "sessions" / session_id


def _build_receipt(
    *,
    spec: Spec,
    agent_command: list[str],
    agent_exit_code: int,
    session_id: str,
    started_at: str,
    finished_at: str,
    results,
    verdict: str,
    public_key: str,
) -> dict[str, Any]:
    return {
        "version": 1,
        "session_id": session_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "intent": spec.intent,
        "agent_command": agent_command,
        "agent_exit_code": agent_exit_code,
        "verdict": verdict,
        "checks": [
            {
                "id": r.check_id,
                "type": r.type,
                "verdict": r.verdict,
                "reason": r.reason,
                "expected": r.expected,
                "observed": r.observed,
            }
            for r in results
        ],
        "signer": {"public_key": public_key},
    }


def cmd_run(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    try:
        spec = Spec.load(spec_path)
    except SpecError as e:
        print(f"receipts: spec error: {e}", file=sys.stderr)
        return 2

    if not args.agent_command:
        print("receipts: no agent command provided after `--`", file=sys.stderr)
        return 2

    # Ensure signing key exists
    ensure_keypair()
    sk = load_signing_key()
    pubkey = public_key_hex(sk)

    session_id = _new_session_id()
    session_dir = _session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    log_file = session_dir / "exec.log"
    log_file.touch()

    commands = spec.watched_commands()
    if not commands:
        print("receipts: spec has no checks that require shimming", file=sys.stderr)
        return 2

    shim_dir = install_shims(session_dir, commands)
    env = make_env_with_shims(shim_dir, session_id, log_file, base_env=dict(os.environ))

    started_at = _iso_utc_now()
    print(
        f"receipts: launched agent in supervised env (session {session_id})",
        file=sys.stderr,
    )
    print(
        f"receipts: shimming {sorted(commands)} via {shim_dir}",
        file=sys.stderr,
    )

    try:
        proc = subprocess.run(
            args.agent_command,
            env=env,
            check=False,
        )
        agent_exit_code = proc.returncode
    except FileNotFoundError as e:
        print(f"receipts: could not execute agent: {e}", file=sys.stderr)
        if not args.keep_session:
            cleanup_session(session_dir)
        return 127

    finished_at = _iso_utc_now()
    print(f"receipts: agent exited: code {agent_exit_code}", file=sys.stderr)

    observation = parse_exec_log(log_file)
    verdict, results = evaluate_spec(spec, observation)

    payload = _build_receipt(
        spec=spec,
        agent_command=args.agent_command,
        agent_exit_code=agent_exit_code,
        session_id=session_id,
        started_at=started_at,
        finished_at=finished_at,
        results=results,
        verdict=verdict,
        public_key=pubkey,
    )

    receipt = dict(payload)
    receipt["signature"] = sign_payload(payload, sk)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(receipt, f, sort_keys=False, default_flow_style=False)

    # Pretty summary to stderr (so stdout stays usable for piping)
    print("", file=sys.stderr)
    print(f"receipts: verdict {verdict}", file=sys.stderr)
    for r in results:
        marker = {"PASS": "✓", "FAIL": "✗", "INCONCLUSIVE": "?"}.get(r.verdict, "?")
        print(f"  {marker} {r.check_id}: {r.verdict}", file=sys.stderr)
        if r.verdict != "PASS":
            print(f"      {r.reason}", file=sys.stderr)
            print(f"      expected: {r.expected}", file=sys.stderr)
            print(f"      observed: {r.observed}", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"receipt written: {out_path}", file=sys.stderr)

    if not args.keep_session:
        cleanup_session(session_dir)

    # Exit code: 0 if PASS, 1 if FAIL, 2 if INCONCLUSIVE
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}.get(verdict, 1)


def cmd_verify(args: argparse.Namespace) -> int:
    path = Path(args.receipt).expanduser().resolve()
    if not path.exists():
        print(f"receipts: receipt not found: {path}", file=sys.stderr)
        return 2
    try:
        with path.open("r", encoding="utf-8") as f:
            receipt = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"receipts: could not parse receipt: {e}", file=sys.stderr)
        return 2
    if not isinstance(receipt, dict):
        print("receipts: receipt is not a mapping", file=sys.stderr)
        return 2

    try:
        pubkey = verify_receipt(receipt)
    except VerificationError as e:
        print(f"receipts: signature INVALID — {e}", file=sys.stderr)
        return 1

    verdict = receipt.get("verdict", "UNKNOWN")
    intent = receipt.get("intent", "")
    session = receipt.get("session_id", "")
    print(f"receipt verified: signed by {pubkey}")
    print(f"  session: {session}")
    print(f"  verdict: {verdict}")
    if intent:
        print(f"  intent:  {intent}")
    return 0


def cmd_keygen(args: argparse.Namespace) -> int:
    priv, pub = ensure_keypair()
    print(f"signing key: {priv}")
    print(f"public key:  {pub}")
    print(f"pubkey hex:  {pub.read_text().strip()}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="receipts",
        description="Catch AI coding agents lying about test runs. Emit signed proof-of-work receipts.",
    )
    p.add_argument("--version", action="version", version=f"receipts {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser(
        "run",
        help="Run an agent under supervision and emit a signed receipt.",
    )
    p_run.add_argument("--spec", required=True, help="Path to a receipts spec YAML.")
    p_run.add_argument(
        "--out",
        default="./receipt.yaml",
        help="Path to write the signed receipt YAML (default: ./receipt.yaml).",
    )
    p_run.add_argument(
        "--keep-session",
        action="store_true",
        help="Keep the session dir (~/.receipts/sessions/<id>) for inspection.",
    )
    p_run.add_argument(
        "agent_command",
        nargs=argparse.REMAINDER,
        help="The agent command to run (everything after `--`).",
    )
    p_run.set_defaults(func=cmd_run)

    p_verify = sub.add_parser("verify", help="Verify the signature on a receipt.")
    p_verify.add_argument("receipt", help="Path to a receipt YAML.")
    p_verify.set_defaults(func=cmd_verify)

    p_keygen = sub.add_parser("keygen", help="Generate a signing keypair if absent.")
    p_keygen.set_defaults(func=cmd_keygen)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Strip the leading "--" if argparse left it in REMAINDER
    if getattr(args, "agent_command", None):
        ac = args.agent_command
        if ac and ac[0] == "--":
            args.agent_command = ac[1:]

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

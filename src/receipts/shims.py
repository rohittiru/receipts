"""Per-session PATH shim installation.

For each watched command (e.g. pytest, npm), creates a symlink in the session's
shim directory pointing at the universal shim script. Prepending the session
shim dir to PATH causes the agent to invoke our shim instead of the real
binary — the shim logs the invocation, then execs the real binary.
"""

from __future__ import annotations

import os
import shutil
import stat
from importlib import resources
from pathlib import Path


def get_shim_script_source() -> str:
    """Return the universal shim script contents.

    The shim is shipped as package data so a `pip install` works. During local
    development we also fall back to looking next to the package.
    """
    # Try package data first
    try:
        return (resources.files("receipts") / "shims" / "_shim.sh").read_text()
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        pass

    # Dev fallback: look in the repo's shims/ directory
    candidate = Path(__file__).parent.parent.parent.parent / "shims" / "_shim.sh"
    if candidate.exists():
        return candidate.read_text()

    raise RuntimeError(
        "could not locate the universal shim script (_shim.sh); "
        "this is a packaging bug"
    )


def install_shims(session_dir: Path, commands: set[str]) -> Path:
    """Install per-session shims for the given commands.

    Returns the path to the shim directory (suitable for PATH prepending).

    The directory layout looks like:
        session_dir/
            shims/
                _shim.sh         (the universal script, executable)
                pytest -> _shim.sh
                npm -> _shim.sh
                ...
    """
    shim_dir = session_dir / "shims"
    shim_dir.mkdir(parents=True, exist_ok=True)

    # Write the universal shim script
    shim_script = shim_dir / "_shim.sh"
    shim_script.write_text(get_shim_script_source())
    # chmod +x
    shim_script.chmod(shim_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Symlink each watched command to the universal shim
    for cmd in commands:
        # Reject commands with path separators — must be a bare name
        if "/" in cmd or "\\" in cmd:
            raise ValueError(f"shim command must be a bare name, got {cmd!r}")

        link = shim_dir / cmd
        if link.exists() or link.is_symlink():
            link.unlink()
        # Relative symlink so the dir is portable
        link.symlink_to("_shim.sh")

    return shim_dir


def make_env_with_shims(shim_dir: Path, session_id: str, log_file: Path,
                       base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build an env dict with shims prepended to PATH and log path set."""
    env = dict(base_env if base_env is not None else os.environ)
    existing_path = env.get("PATH", "")
    env["PATH"] = f"{shim_dir}{os.pathsep}{existing_path}" if existing_path else str(shim_dir)
    env["RECEIPTS_EXEC_LOG"] = str(log_file)
    env["RECEIPTS_SESSION"] = session_id
    return env


def cleanup_session(session_dir: Path) -> None:
    """Remove a session directory. Best-effort; ignores missing paths."""
    if session_dir.exists():
        shutil.rmtree(session_dir, ignore_errors=True)

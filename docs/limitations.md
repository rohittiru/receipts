# Limitations

The README sells the value. This file documents what `receipts` v0.1 cannot do,
so nobody installs it expecting otherwise.

## In-process test runs

If the agent calls a test runner via the runner's Python API instead of
shelling out — for example:

```python
import pytest
pytest.main(["tests/"])
```

…no child process forks. The shim never runs. The exec log stays empty. The
receipt will report `invoked: false` even though pytest did, in fact, run
inside the agent's process.

This is a real gap. v0.1 catches the **subprocess** lie; the in-process lie
needs different instrumentation (ptrace, an LD_PRELOAD shim that intercepts
the runner's entry function, or a Python sys.monitoring hook for Python-side
runners).

**Workaround for now:** in your agent's CLAUDE.md / AGENTS.md, instruct the
agent to invoke test runners via the command line, not the library API.
Belt-and-suspenders, but cheap.

## Non-shell harnesses

`receipts` works for any agent that resolves binaries through `$PATH`. That
includes:

- Claude Code (bash tool)
- Aider (shells out)
- OpenCode
- Any agent built on the Anthropic Agent SDK's `bash` tool
- Any agent built on Codex CLI (the local terminal one, not the cloud sessions)

It does **not** work for:

- **Cursor** — runs in an Electron sandbox with its own shell; PATH inheritance
  is non-trivial. Workaround tracked in `roadmap.md`.
- **Codex (cloud sessions)** — runs in OpenAI's container. You don't control
  the environment, so you can't prepend to PATH. Needs a different
  instrumentation strategy (sidecar, container-side hook).
- **In-process Python agents** that never spawn subprocesses for the watched
  commands.

## "The tests passed but they were wrong tests"

A more sophisticated failure mode: the agent does run pytest, the test file
exists, pytest exits 0, but the tests it wrote don't actually exercise the
behavior the user asked for. Maybe the test is `assert True`. Maybe it tests
a different function than the one with the bug.

`receipts` does not catch this. The check confirms a real process ran with the
right exit code; it does not (and cannot, cheaply) confirm the **semantic
content** of what was tested. Semantic outcome verification is an active
research area (see AgentRR's "check functions," NABAOS's runtime tool
receipts). It's a real gap and an honest one.

The best v0.1 mitigation: combine `command_invoked` with `file_changed` checks
once they ship, so you can at least assert the test file was modified. Still
not semantic, but closer.

## Trust model

The signing key lives at `~/.receipts/keys/signing.key` with `chmod 600`. If
that file is compromised, an attacker can produce arbitrary receipts that
verify under your public key. This is the standard trust model for local
code-signing; treat the key the same way you treat your SSH key.

For team / CI use, the v0.2 plan is to support hardware-backed keys (Yubikey,
Sigstore-style ephemeral keys with a CA). Not in v0.1.

## Exec log integrity

The exec log lives at `~/.receipts/sessions/<id>/exec.log` during the run.
A malicious agent with write access to that file could in theory rewrite it
before the wrapper parses it. v0.1 does not currently protect against this —
the assumption is that the agent is incompetent or sloppy, not adversarial.

If you're running an adversarial agent and you need exec log integrity, run
the agent in a container without write access to `~/.receipts/`. The log is
written by the shim subprocess; the parent (wrapper) can place the log
outside the container's bind mount.

## Performance

The shim adds one bash process per watched-command invocation. On a typical
agent run that invokes pytest two or three times, this is unmeasurable. If
you shim a hot command (e.g. `git` or `ls`), you'll feel it. v0.1 only
shims commands explicitly named in the spec, so the cost is opt-in.

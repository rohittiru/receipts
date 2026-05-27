# receipts

**Catch your AI coding agent lying about tests in 15 lines of YAML.**

Agents say "tests passing." Sometimes they didn't run any tests. The agent's
output stream is not evidence; the process tree is.

`receipts` wraps a coding agent (Claude Code, Aider, OpenCode — any shell-based
harness) and watches what actually happens at the process level via PATH shims.
After the agent exits, it emits a signed YAML receipt of what was observed,
checked against an outcome spec you provided.

The agent can write whatever it wants. The receipt doesn't read the agent.
It reads the world.

---

## The 30-second demo

```bash
$ cat examples/catch-pytest-lie.yaml
version: 1
intent: "Agent must add tests and they must pass"
checks:
  - id: pytest-ran-and-passed
    type: command_invoked
    command: pytest
    expect:
      invoked: true
      last_exit_code: 0
```

```bash
$ receipts run --spec examples/catch-pytest-lie.yaml --out receipt.yaml \
    -- bash examples/lying-agent.sh

receipts: launched agent in supervised env (session 9f4c...)
agent output:
  ✓ Added test_foo.py
  ✓ All tests passing.
  Implementation complete.
agent exited: code 0

receipts: verdict FAIL
  pytest-ran-and-passed: FAIL
    expected: invoked=true, last_exit_code=0
    observed: invoked=false, invocation_count=0

receipt written: receipt.yaml (signed, ed25519)
```

Side-by-side: the agent says "all tests passing." The receipt says no `pytest`
process ever ran. Caught and signed.

## Install (when published)

```bash
pip install receipts-cli
```

For now:

```bash
git clone https://github.com/rohittiru/receipts
cd receipts
pip install -e .
```

## What v0.1 actually catches

A single, common, undeniable category of agent lie:

- **The fabricated test run.** Agent claims "tests passing," no test runner
  process ever forked.
- **The hidden failure.** Agent claims "all green," actual exit code was non-zero.
- **The unrelated runner.** Agent claims pytest passed but only `npm test` ran
  (or vice versa).

Catches across these supported runners: `pytest`, `npm`, `pnpm`, `yarn`, `go`,
`cargo`, `jest`, `vitest`, `mocha`. Adding more is one line in `shims/`.

## What v0.1 does NOT catch (yet, honestly)

- **In-process test runs.** If the agent invokes pytest via the Python API
  (`pytest.main()`) inside its own process, no child process forks and the shim
  sees nothing. Workaround in `docs/limitations.md`.
- **Cursor / Codex.** Cursor runs in an Electron sandbox with its own shell;
  Codex web sessions run in a cloud container you don't control. The shim
  approach works for any agent that shells out to your `$PATH` — which
  covers Claude Code, Aider, OpenCode, and any agent using a standard bash tool.
  Other harnesses need different instrumentation. Tracked in
  `docs/roadmap.md`.
- **"The tests passed but they were wrong tests."** This is a real failure
  mode and a real verification gap. Solving it requires semantic outcome checks
  (does the test cover the claimed behavior?) which is research-grade, not
  v0.1-grade. `receipts` catches the dumb version of the lie. The smarter
  versions come later.

## How it works

1. `receipts run` creates a session dir at `~/.receipts/<session_id>/`.
2. It generates **PATH shims** for the configured commands (`pytest`, `npm`,
   `go`, etc.) inside `<session>/shims/`. Each shim is a small bash script
   that logs its invocation, then `exec`s the real binary.
3. It launches the agent as a subprocess, with `<session>/shims/` prepended to
   `PATH`. Anything the agent invokes that matches a shim gets logged
   transparently — the agent doesn't know.
4. After the agent exits, the wrapper parses the exec log and checks it
   against the spec's `checks` clauses.
5. It writes a YAML receipt with the observed state, the verdict, and an
   Ed25519 signature over the canonicalized payload.

The agent never sees the receipt. The receipt is generated outside the agent's
context window from observable side effects. The signing key lives in
`~/.receipts/keys/` (generated on first run). You can hand the receipt to a
verifier and they confirm authenticity with the public key alone.

## Verifying someone else's receipt

```bash
$ receipts verify path/to/receipt.yaml
receipt verified: signed by <pubkey-hex>
  session: 9f4c...
  verdict: FAIL
  intent: "Agent must add tests and they must pass"
```

## Roadmap

See [docs/roadmap.md](docs/roadmap.md). Short version: more checks (file
state, HTTP responses, git diffs), more harnesses (instrumented MCP wrappers
for Cursor, container-based hooks for Codex), and a portable receipt format
worth publishing as a draft.

## Why this exists

Anthropic's October 2025 introspection research found Claude models succeed at
recognizing injected concepts roughly 42% of the time. The model's claim about
its own behavior is a coin flip, dressed as confidence. Every agent framework
today trusts that coin flip.

This is the simplest possible primitive that doesn't. The wrapper observes
the world. The receipt signs the observation. Trust the signature, not the
narration.

## License

MIT. See [LICENSE](LICENSE).

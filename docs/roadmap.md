# Roadmap

`receipts` is intentionally narrow at v0.1. The goal of v0.1 is to make one
specific kind of agent lie undeniable and signed. Everything else is future
work.

## v0.1 — shipped

- [x] PATH shim approach for shell-based agent harnesses (Claude Code, Aider, OpenCode)
- [x] `command_invoked` check type — must-be-invoked + exit-code assertion
- [x] Ed25519 signing with auto-generated keypair
- [x] YAML receipts with full observed/expected diff
- [x] Independent verification CLI

## v0.2 — broader check types

The point of `command_invoked` was to ship something useful in a weekend. The
real value comes when checks compose over more of the world's observable state.

- [ ] `file_changed` — file at path has new contents (matches glob, or includes
      substring, or matches regex) since session start
- [ ] `file_unchanged` — the opposite, for "must not touch X"
- [ ] `git_commit_authored` — a new commit appears on the current branch with
      message matching a pattern
- [ ] `http_request_made` — observed at the agent's HTTPS proxy layer (requires
      a wrapper proxy, opt-in)
- [ ] `process_clean_exit` — assert no panic / stack trace markers in stderr
- [ ] `db_row_exists` — query the user's DB with read-only creds and assert
      shape (requires connection string in env, opt-in)

## v0.3 — more harnesses

The shim approach works for any agent that shells out to `$PATH`. That covers
Claude Code, Aider, OpenCode, and any agent built on the standard bash tool
in the Anthropic Agent SDK. Other harnesses need different instrumentation:

- [ ] **Cursor** — Electron sandbox with its own shell. Investigate the
      Cursor v1.7+ hooks API as a parallel instrumentation surface.
- [ ] **Codex** — Cloud-container sessions. Likely requires a sidecar inside
      the container; out of scope until OpenAI exposes per-session hooks.
- [ ] **Aider** — already shells out; should work today, needs an integration test.
- [ ] **MCP server wrapper** — instrument any MCP server so tools the agent
      calls through MCP show up in the exec log the same way shell calls do.

## v0.4 — portable spec

The receipt format is the eventual product. Once two harnesses produce
receipts that interop, write a draft spec:

- [ ] IETF / W3C Community Group draft
- [ ] RFC 8785 (JCS) canonicalization for cross-language verifier compat
- [ ] Reference verifier libraries: Python (ships), TypeScript, Go, Rust

## v1.0 — transparency log

Optional public-good append-only log for receipts that opt in (Sigstore / Rekor
analog). Not required to use the format. Provides third-party witness for
high-stakes agent work.

## Out of scope (for now)

- **Semantic correctness checks.** "Did the agent actually fix the bug?" is a
  research-grade question. `receipts` answers the cheaper question first:
  "did the agent run the thing it claimed to run?"
- **Sandboxing.** This is not Docker. Other tools sandbox; `receipts`
  observes. Use both.
- **Live monitoring / dashboards.** v0.1 is a CLI. Dashboards belong in a
  commercial layer that consumes receipts.

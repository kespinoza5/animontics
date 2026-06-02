# tools/dev — development tooling

Tools that support *working on* the codebase, as opposed to `tools/fleet`
(which operates the running fleet) or `tools/board` / `tools/network` (which
configure hardware). Nothing here talks to a board or the network.

## `audit.py` — sensor plugin conformance audit

Checks every sensor package under `sensors/` against the plugin contract
documented in `CONTRIBUTING.md` and `CLAUDE.md`, plus the cross-file wiring a
new sensor is supposed to touch (`config/animon.yaml`, `docs/sensors/`,
`mkdocs.yml` nav, per-sensor routers in `node/routers/`).

```bash
python -m tools.dev.audit                 # audit all sensors
python -m tools.dev.audit tf_mini         # audit one package
python -m tools.dev.audit --warn-as-error # treat warnings as failures
```

**It reads source statically (AST/text), never by importing.** Sensors that
depend on Linux-only libraries (`smbus2`, `fcntl`) fail to import on a Windows
dev box; a runtime check would silently skip them. Static parsing audits all
five packages regardless of which hardware libs are installed.

### Severity

| Level   | Meaning                                                              | Exit |
|---------|---------------------------------------------------------------------|------|
| `ERROR` | Breaks deploy or routing at runtime (ReconcileError, registry miss, dead route) | 1 |
| `WARN`  | Contract/style drift that won't crash (missing try/except, missing docs page) | 0\* |

\* `--warn-as-error` makes warnings exit 1 too.

### What it cannot check

Static analysis can't verify hardware semantics. Use the `conformance-reviewer`
agent (`.claude/agents/conformance-reviewer.md`) for the judgment layer: whether
`data_keys` match what `sensor.py` actually broadcasts, whether METADATA defaults
are physically correct, whether the README documents the real wiring.

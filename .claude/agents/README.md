# .claude/agents/ — project subagents

Project-specific Claude **subagents**, checked into the repo so the whole team
shares them. Each is a Markdown file with YAML frontmatter (`name`, `description`,
`tools`, `model`) and a body that defines the agent's role, process, and output.
The main session spawns one with the Agent tool (`subagent_type: <name>`); they
run in a fresh context with only the tools listed.

These are distinct from the harness's built-in agents (`claude`, `Explore`,
`Plan`, `general-purpose`) — those aren't defined here.

## Agents

| Agent | Does | Edits? | Spawn it… |
|-------|------|--------|-----------|
| [`conformance-reviewer`](conformance-reviewer.md) | Audits a node plugin (sensor / effector / policy / device) against the project contract — runs `tools/dev/audit.py`, adds judgment-level review. | read-only | after adding/editing a plugin, before committing |
| [`sensor-builder`](sensor-builder.md) | Builds a new sensor package end to end (driver/sensor/`__init__`/README/docs/config), primed with the project patterns. | edits | when starting a brand-new sensor |
| [`doc-steward`](doc-steward.md) | Keeps READMEs + the `docs/` site in sync with the code (directory README coverage, orientation docs, mkdocstrings lists, nav). | edits docs | after a feature/rework, or before wrapping a session |

Typical loop after an arc lands: spawn **`doc-steward`** (full audit or a git
range) to refresh docs, and **`conformance-reviewer`** on the changed plugins;
action the findings; commit.

## Adding an agent

Add `<name>.md` with the frontmatter above (keep `tools` minimal — read-only
reviewers get `Read, Grep, Glob, Bash`; editors add `Edit, Write`). Write the body
as **role → process → output**; see the existing three for the house style. Then
list it in the table above.

> Heads-up: `doc-steward` exempts `.claude/` from its sweep, so **this README is
> hand-maintained** — update the table when you add or change an agent.

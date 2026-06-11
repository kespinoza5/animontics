# policies

Policy plugin packages — a cortex's control loops (`observation → action`). The
base class + the runtime that ticks them live in
[`core/policy.py`](../core/policy.py); this tree holds the concrete policy types,
auto-discovered like sensors and effectors.

## Plugin system

`policies/__init__.py` imports every package on disk, firing each
`@register_policy("type")`. `node/app.py` imports `policies` once; instances are
created from the board config's `policies:` list and run by `PolicyRuntime`.

Policy *behavior is code, not config* — `PolicyConfig` only declares the
observation/action wiring + params. A reflex (always-on) and a learned/stochastic
controller implement the identical `step(obs) → action` contract.

## Available types

| Package | Type | Notes |
|---------|------|-------|
| [`curve/`](curve/README.md) | `curve` | max-linear reflex over normalized inputs (the fan loop) |
| [`threshold/`](threshold/README.md) | `threshold` | trip/release guard with hysteresis + latch (the overcurrent reflex) |

## Adding a policy

Subclass `PolicyBase`, decorate `@register_policy("type")`, implement
`step(obs) → action` (obs are relay signal values; action is `{channel: value}`
for the target effector). Mark resilient loops `always_on`. See
[CONTRIBUTING.md](../CONTRIBUTING.md#adding-a-device-effector-or-policy).

# Animontics — AI Development Context

Concise orientation for a fresh Claude session. Read this before touching any code.

---

## What this project is

A distributed nervous system for an embodied AI. Linux SBCs (Orange Pi, Raspberry
Pi) run `node/app.py` (FastAPI); **each node is a "cortex"** with a local
input → control → output loop:

- **sensors** (afferent) read the world — directly, or through **devices** (shared
  peripherals: an MCU serial link, an ADS1115 chip),
- **effectors** (efferent) act on it — motion, light, sound — also through devices,
- **policies** (control loops) map observations → actions via a **relay** (the thalamus).

The microcontrollers those devices talk to run firmware **composed by `tools/forge`**
from a per-MCU contract. A fleet CLI (`tools/fleet/animon.py`) keeps all boards in
sync from desired state.

Read these three before touching the corresponding area:
- `docs/architecture.md` — fleet topology, data lanes, deploy process.
- `docs/cortex.md` — the node runtime: devices, sensors, effectors, policies, relay.
- `docs/forge.md` — firmware composition (`mcu/`, `firmware/`, `config/mcus/`).

---

## Four-layer config architecture

This is the core design. Each layer owns exactly its concern — never cross them.

| Layer | File | In repo? | Contains |
|-------|------|----------|----------|
| Node desired state | `config/nodes/<id>.yaml` | ✅ | Which sensors each node should run (id + type only), capabilities, role |
| Fleet access | `config/animon.yaml` | ❌ gitignored | IPs, SSH users — how to reach each board |
| Board wiring reality | `config/boards/<id>.yaml` + board's `config.yaml` | ❌ gitignored | Physical connection details (port, bus, baud, address) |
| Hardware constraints | `sensors/<type>/__init__.py` `METADATA` | ✅ | Valid connection types, addresses, baud rates, defaults |

`animon deploy` negotiates all four: desired state from `config/nodes/`, access
from `config/animon.yaml`, existing wiring from `config/boards/` (or live SSH),
constraints from METADATA. After deploy, `config/boards/<id>.yaml` is updated.

**Beyond sensors, the board config (`config/boards/<id>.yaml`, gitignored) also
declares the runtime's other tiers**, and a fifth config home drives firmware:

| Thing | Where | Contains |
|-------|-------|----------|
| Devices | `config/boards/<id>.yaml` `devices:` | shared peripherals (`mcu_serial` port/baud, `ads1115` bus/addr) |
| Effectors | `config/boards/<id>.yaml` `effectors:` | outputs (type, `backend.device`, name+index channels) |
| Policies | `config/boards/<id>.yaml` `policies:` | control loops (type, observation, action, params) |
| MCU build contract | `config/mcus/<id>.yaml` | what `forge` composes for one MCU (modules, pins/chips, channels) |

Array sensors (`mq_array`, `pressure_array`) carry `channels:` mapping
`(device, index) → signal + calibration`; they omit `connection`.

---

## Node runtime tiers (the cortex) — see `docs/cortex.md`

Beside sensors, the node runtime has three tiers, each a base class + registry
(mirroring sensors) created in `node/app.py`'s lifespan and held on `app.state`:

| Tier | Module | Registry | Notes |
|------|--------|----------|-------|
| Device | base `core/device.py`; kinds `devices/` | `@register_device` | `devices/mcu_serial` (push: frames + `send_command`), `devices/ads1115` (pull), `devices/sara_r5` (mixed: NMEA push + AT poll) |
| Effector | base `core/effector_base.py`; types `effectors/` | `@register_effector` | `effectors/pwm`, `effectors/stream_sink`, `effectors/fan_array` |
| Policy | base `core/policy.py`; types `policies/` | `@register_policy` | `policies/curve` (always-on fan reflex); `PolicyRuntime` ticks the stack |
| Relay | `core/relay.py` | — | the thalamus: named-signal pub/sub + gating; inter-cortex seam |

Devices, effectors, and policies are all **plugin trees** (`devices/`,
`effectors/`, `policies/`), auto-discovered exactly like `sensors/`; `core/` holds
only the base class + registry. `node/app.py` does
`import devices/sensors/effectors/policies` for the side-effect discovery. A device
that toggles SBC/MCU pins drives them through `core/gpio.py`'s `make_output_line()`
(libgpiod / mcu / null backends), never hard-coded sysfs.

The wire codec is `core/mcu_link.py` (sample + command frames); array sensors use
`core/analog_array.py` (`AnalogArrayBase`, binds 1+ devices, spans MCUs).

## Firmware composition (forge) — see `docs/forge.md`

MCU firmware is **composed at build time** from a contract + reusable modules,
never hand-maintained per board. Families are organized by **runtime**:
`mcu/arduino/` (compile lean C++ via arduino-cli, WSL fallback) and
`mcu/circuit_python/` (render a generic `code.py`, no compile, copy-deploy). Build
output → gitignored `firmware/<id>/`. `tools/forge` is target-pluggable
(`@register_builder`); FPGA/accelerator builders are additive.

## Required patterns — follow these exactly

### Every sensor package `__init__.py` MUST have:

```python
try:
    from sensors.my_sensor.sensor import MySensor
except ImportError:
    pass  # hardware deps (smbus2, etc.) not available on Windows

METADATA = {
    "type": "my_sensor",
    "name": "Human-readable name",
    "description": "One line description.",
    "connection": {
        "supported": ["uart"],        # list of valid connection types
        "defaults": {
            "baud_rate": 115200,      # used by fleet tool for fresh installs
        },
        "valid": {
            "baud_rate": [115200],    # constraints validated on deploy
        },
    },
    "data_keys": {
        "distance_mm": "int — measured distance in millimetres",
    },
}

__all__ = ["MySensor", "METADATA"]
```

**Why:** Without METADATA, `animon deploy` raises `ReconcileError` when adding the
sensor to a board that has no existing config.yaml. This was a real bug.

### Routers that need the sensor registry use `request.app.state`:

```python
# CORRECT
@router.get("/my-route")
async def my_route(request: Request):
    sensors = request.app.state.sensors
    ...

# WRONG — requires special register_X() wiring in app.py
_sensors: dict = {}
def register_sensors(s): _sensors.update(s)
```

No router should have a `register_sensors()` function. The `ir_xcvr` router was
fixed to use `request.app.state` — do not reintroduce the old pattern.

### New sensors with dedicated HTTP routes:

The router goes in `node/routers/<type>.py`. Wire it in `node/app.py` with only:

```python
from node.routers.my_sensor import router as my_sensor_router
app.include_router(my_sensor_router)
```

No extra startup calls. The router accesses `request.app.state.sensors` itself.
The same applies to the other tiers: routers read `request.app.state.devices` /
`.effectors` / `.policies` / `.relay` — never module-level globals.

### Firmware moves bytes; Python owns meaning

Non-negotiable boundary. A device/firmware module reads/writes pins and frames raw
values; **calibration, units, curves, and interpretation live only in Python**
(the sensor's `enrich`, the effector's scaling, the policy). Never bake meaning
into firmware.

### Actuation belongs on effectors (through devices), NEVER on a sensor

Driving a fan/LED/motor is an **effector** writing through a **device**'s command
sink — not a method on the sensor that happens to share the link. Putting
`send_command` on the gas sensor was a real bug (backed out in `386fc3f`). A
sensor reads; an effector writes; the device owns the shared transport.

---

## Adding a new sensor — checklist

1. `sensors/<type>/` directory (git submodule — see below)
2. `driver.py` — hardware I/O only, no threading, no HTTP
3. `sensor.py` — `@register("type")` + `SensorBase` subclass
4. `__init__.py` — `try/except` import + `METADATA` dict (see above)
5. `README.md`, `test_*.py` (in the package)
6. `web/viewers/<type>.html` — bench viewer in the centralized web/ tree, built
   on `web/shared/` (viewer.css + AnimStream; AnimChart for scalar/timeseries).
   Not in the sensor package — viewers are opened from a dev machine against any
   node, so they live together. High-rate array/image sensors consume the
   binary frame lane (`/sensors/<id>/frames`); scalars use the JSON SSE lane.
7. Add `{id, type}` to the relevant node in `config/nodes/<node-id>.yaml`
8. Add `docs/sensors/<type>.md` (one `include-markdown` line)
9. Add to `mkdocs.yml` sensors nav
10. If the sensor needs dedicated HTTP routes, add `node/routers/<type>.py`

Steps 7-9 are easy to forget. The fleet tool and docs break silently without them.

**Variants:** a *device-fed array* sensor (`mq_array`, `pressure_array`) subclasses
`core.analog_array.AnalogArrayBase` instead of writing a hardware `driver.py` — the
device does the I/O; the sensor just declares `channels` and overrides `enrich`.
A *trivial SBC-native* sensor (`board_temp`, `analog_in`, `fan_tach`) can live **in-tree**
(not a submodule). To add a **device, effector, or policy**, see
`CONTRIBUTING.md` → "Adding a device, effector, or policy".

---

## Git submodule workflow

Each sensor package is a git submodule (independent repo). New sensors:

```bash
# Create new repo for the sensor
git init sensors/my_sensor
cd sensors/my_sensor && git add . && git commit -m "feat: ..."

# Register in parent
cd ../..
git submodule add ./sensors/my_sensor sensors/my_sensor
```

**Never delete a sensor directory without preserving its git history first.**
See `memory/feedback_history_migration.md` for the lesson learned.

---

## Windows dev machine gotchas

- `fcntl` is Linux-only — wrap imports in `try/except ImportError`
- `smbus2` is Linux-only — same pattern
- Box-drawing characters (`─`, `✓`) break CP1252 terminal — the CLI sets
  `sys.stdout.reconfigure(encoding='utf-8')` in `main()`, other scripts should too
- Line endings: `.gitattributes` enforces LF on checkout — don't fight this
- Sensor hardware tests require a physical board — run `test_codec.py` / model
  tests locally, everything else needs SSH to a board
- The AVR toolchain (`arduino-cli`) lives in **WSL**; `forge build` auto-falls
  back to it when not on PATH. Pass Windows paths to WSL converted in Python
  (`_to_wsl_path`) — passing backslashes through `wsl.exe` strips them.

---

## Verification commands

```bash
# Import sanity (run from project root)
python -c "from node.app import create_app; print('OK')"
python -c "from tools.fleet.reconcile import load_all_metadata; print(sorted(load_all_metadata()))"

# Fleet CLI
python -m tools.fleet.animon status
python -m tools.fleet.animon deploy <node-id> --dry-run

# Tests — run SCOPED, not bare `pytest` (root collection trips on
# sensors/*/test_raw.py|test_sensor.py hardware scripts that sys.exit on import):
pytest core/ tools/forge/ sensors/mq_array/ sensors/pressure_array/ \
       sensors/analog_in/ sensors/ir_xcvr/test_codec.py -q

# forge — compose/compile firmware (offline; no board needed)
python -m tools.forge.forge validate <mcu-id>
python -m tools.forge.forge build    <mcu-id>      # → firmware/<id>/

# Docs build
python -m mkdocs build
```

---

## Documentation convention

Every hand-authored directory has a `README.md` (exempt: `docs/`, `.claude/`,
generated output, `__pycache__`). Orientation docs (`CLAUDE.md`, `CONTRIBUTING.md`,
root `README.md`) and the `docs/` site stay current with the code. Many `docs/*.md`
are `include-markdown` of a source README — edit the source, not the page; the
`docs/api/{core,node,sensors}.md` mkdocstrings lists are hand-maintained.

After a feature or architecture change, spawn the **`doc-steward`** agent (give it
a git ref to scope, or "full audit") to refresh READMEs + `docs/` and catch drift.

---

## Security constraints — non-negotiable

- No secrets (WiFi passwords, tokens, API keys) in `config.yaml`, `animon.yaml`,
  or any tracked file. Secrets go in a gitignored `secrets.yaml` per board,
  loaded via `ANIMONTICS_SECRETS` env var.
- SSH uses key auth only (`BatchMode=yes` enforced in `tools/fleet/ssh.py`).
  Never add password auth or hardcode credentials.
- The deploy tool never passes credentials on the command line.

---

## Fleet CLI quick reference

```bash
python -m tools.fleet.animon status                     # all nodes
python -m tools.fleet.animon status <node-id> --json
python -m tools.fleet.animon diff   <node-id>
python -m tools.fleet.animon deploy <node-id> --dry-run
python -m tools.fleet.animon deploy <node-id> --verbose
python -m tools.fleet.animon deploy <node-id> --host <ip>          # bootstrap: not yet in animon.yaml
python -m tools.fleet.animon deploy <node-id> --config <file> --note "..."  # ad-hoc override
python -m tools.fleet.animon revert <node-id>                      # discard override, restore baseline
python -m tools.fleet.animon pull   <node-id>
python -m tools.fleet.animon probe  <node-id>
```

Exit codes: `0` = success/in-sync, `1` = error, `2` = drift or active override.

An override deploy (`deploy --config`) pushes a verbatim, METADATA-validated
config for testing/debugging/rollback. It never overwrites the staged baseline
(`config/boards/<id>.yaml`); it writes a gitignored marker
(`config/boards/<id>.override.yaml`) that `status` surfaces as `OVERRIDE`.
`revert` restores the baseline and clears the marker.

---

## forge CLI quick reference

```bash
python -m tools.forge.forge validate <mcu-id>   # static-check config/mcus/<id>.yaml
python -m tools.forge.forge build    <mcu-id>   # compose (+compile) → firmware/<id>/
python -m tools.forge.forge flash    <mcu-id>   # build + flash/copy to the target (needs hardware)
python -m tools.forge.forge channels <mcu-id>   # print the canonical channel block to paste in
python -m tools.forge.forge resolve  <node-id>  # fill a board config's device-fed sensor channels from contracts
python -m tools.forge.forge clean    <mcu-id>   # remove firmware/<id>/
```

The channel→signal+calibration map is authored **once** in the MCU contract's
`channels`; a device-fed sensor lists `devices: [<id>, …]` and `forge resolve`
derives its `channels` from those contracts (explicit `channels` override).

Contracts live in `config/mcus/<id>.yaml` (gitignored; `example.yaml` tracked);
family source in `mcu/<family>/`; built artifacts in `firmware/<id>/` (gitignored).

---

## Deferred work — TODO.md

When you defer something, notice out-of-scope work, or leave a known rough edge,
record it as a `- [ ]` item in `TODO.md` under the matching area heading
(API Design / Dashboard / Tools / Sensor Packages / Infrastructure / Firmware /
FPGA) —
don't leave it only in chat, where it's lost when the session ends. Prefix each
item with the file or command it concerns. Mark finished items `- [x]` rather
than deleting them, so the history of decisions stays visible.

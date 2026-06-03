# Animontics — AI Development Context

Concise orientation for a fresh Claude session. Read this before touching any code.

---

## What this project is

A distributed sensor platform for an embodied AI system. Linux SBCs (Orange Pi,
Raspberry Pi) run `node/app.py` (FastAPI), each serving a small set of hardware
sensors. A fleet management CLI (`tools/fleet/animon.py`) keeps all boards in sync
from a single desired-state file.

For the full system design — topology, data lanes, binary frame protocol, viewer
architecture, fleet deploy process — read `docs/architecture.md`.

---

## Three-layer config architecture

This is the core design. Each layer owns exactly its concern — never cross them.

| Layer | File | Who owns it | Contains |
|-------|------|-------------|----------|
| Fleet desired state | `config/animon.yaml` | Repo | Which sensors each board *should* have (id + type only) |
| Board wiring reality | `<deploy_path>/config/config.yaml` | Board | Physical connection details (port, bus, baud, address) |
| Hardware constraints | `sensors/<type>/__init__.py` `METADATA` | Repo | Valid connection types, addresses, baud rates, defaults |

`animon deploy` negotiates all three: keep existing wiring, add new sensors from
METADATA defaults, disable removed sensors.

---

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
7. Add to `config/animon.yaml` on the relevant node
8. Add `docs/sensors/<type>.md` (one `include-markdown` line)
9. Add to `mkdocs.yml` sensors nav
10. If the sensor needs dedicated HTTP routes, add `node/routers/<type>.py`

Steps 7-9 are easy to forget. The fleet tool and docs break silently without them.

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

---

## Verification commands

```bash
# Import sanity (run from project root)
python -c "from node.app import create_app; print('OK')"
python -c "from tools.fleet.reconcile import load_all_metadata; print(sorted(load_all_metadata()))"

# Fleet CLI
python -m tools.fleet.animon status
python -m tools.fleet.animon deploy <node-id> --dry-run

# Codec / model unit tests (no hardware needed)
pytest sensors/ir_xcvr/test_codec.py -v

# Docs build
python -m mkdocs build
```

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
python -m tools.fleet.animon pull   <node-id>
python -m tools.fleet.animon probe  <node-id>
```

Exit codes: `0` = success/in-sync, `1` = error, `2` = drift detected.

"""Config reconciliation — merges fleet desired state with board wiring reality.

This module is the core negotiation logic. It takes three inputs:
  1. AnimonNodeEntry  — what sensors the fleet says this node should have
  2. NodeConfig | None — what the board currently has (wiring reality)
  3. sensor metadata   — hardware constraints and defaults

And produces:
  1. A new NodeConfig ready to deploy
  2. A list of human-readable change descriptions
"""
from __future__ import annotations

from typing import Any

from core.models import (
    AnimonNodeEntry,
    ConnectionConfig,
    NetworkConfig,
    NodeConfig,
    SensorConfig,
)


class ReconcileError(Exception):
    """Raised when reconciliation cannot produce a valid config."""


def load_all_metadata() -> dict[str, dict[str, Any]]:
    """Load METADATA from all sensor packages present on this machine.

    Returns a dict keyed by sensor type, e.g. {"tf_mini": {...}, ...}.
    Packages that fail to import (missing hardware deps) are skipped.
    """
    import importlib
    import pkgutil
    from pathlib import Path

    metadata: dict[str, dict] = {}
    sensors_dir = Path(__file__).parent.parent.parent / "sensors"

    for pkg in pkgutil.iter_modules([str(sensors_dir)]):
        try:
            mod = importlib.import_module(f"sensors.{pkg.name}")
            if hasattr(mod, "METADATA"):
                meta = mod.METADATA
                metadata[meta["type"]] = meta
        except Exception:
            pass  # missing hardware deps — skip gracefully

    return metadata


def _default_connection(
    sensor_type: str,
    metadata: dict[str, dict],
) -> ConnectionConfig | None:
    """Build a ConnectionConfig from sensor METADATA defaults, if available."""
    meta = metadata.get(sensor_type)
    if not meta:
        return None

    conn = meta.get("connection", {})
    supported = conn.get("supported", [])
    if not supported:
        return None

    # Prefer uart > usb_cdc > i2c > ir as the default connection type
    preferred_order = ["uart", "usb_cdc", "i2c", "ir"]
    conn_type = next((t for t in preferred_order if t in supported), supported[0])
    defaults = conn.get("defaults", {})

    return ConnectionConfig(type=conn_type, **defaults)


def validate_connection(
    sensor_type: str,
    connection: ConnectionConfig,
    metadata: dict[str, dict],
) -> list[str]:
    """Validate a connection config against sensor METADATA constraints.

    Returns a list of validation error strings (empty = valid).
    """
    errors: list[str] = []
    meta = metadata.get(sensor_type)
    if not meta:
        return errors  # no metadata to validate against

    conn_meta = meta.get("connection", {})
    supported = conn_meta.get("supported", [])
    valid_constraints = conn_meta.get("valid", {})

    if supported and connection.type not in supported:
        errors.append(
            f"{sensor_type}: connection type '{connection.type}' not supported. "
            f"Supported: {supported}"
        )

    if connection.baud_rate is not None:
        valid_bauds = valid_constraints.get("baud_rate")
        if valid_bauds and connection.baud_rate not in valid_bauds:
            errors.append(
                f"{sensor_type}: baud_rate {connection.baud_rate} not valid. "
                f"Valid: {valid_bauds}"
            )

    if connection.address is not None:
        valid_addrs = valid_constraints.get("address")
        if valid_addrs and connection.address not in valid_addrs:
            errors.append(
                f"{sensor_type}: I2C address {hex(connection.address)} not valid. "
                f"Valid: {[hex(a) for a in valid_addrs]}"
            )

    return errors


def reconcile(
    desired: AnimonNodeEntry,
    current: NodeConfig | None,
    metadata: dict[str, dict],
    node_type: str | None = None,
) -> tuple[NodeConfig, list[str]]:
    """Merge desired fleet state with current board config.

    Rules:
      - Sensors in animon.yaml + in board config → keep existing wiring
      - Sensors in animon.yaml + NOT in board config → add with METADATA defaults
      - Sensors in board config + NOT in animon.yaml → disable (set enabled=False)
      - All results are validated against METADATA constraints

    Args:
        desired:   The AnimonNodeEntry from animon.yaml.
        current:   The board's current NodeConfig, or None if no config exists yet.
        metadata:  Loaded sensor METADATA dicts keyed by sensor type.
        node_type: Board type string (used if current is None).

    Returns:
        Tuple of (new NodeConfig, list of change description strings).

    Raises:
        ReconcileError: if a required sensor has no connection info and no
                        METADATA defaults to fall back on.
    """
    changes: list[str] = []

    # Index current sensors by id for fast lookup
    current_by_id: dict[str, SensorConfig] = {}
    if current:
        current_by_id = {s.id: s for s in current.sensors}

    # Build the reconciled sensor list
    new_sensors: list[SensorConfig] = []

    # 1. Process sensors the fleet wants
    for ref in desired.sensors:
        if ref.id in current_by_id:
            existing = current_by_id[ref.id]
            if existing.type != ref.type:
                # Type changed in animon.yaml — update and warn
                changes.append(
                    f"  ~ {ref.id}: type changed {existing.type!r} → {ref.type!r} "
                    f"(keeping existing connection settings)"
                )
                new_sensors.append(existing.model_copy(update={"type": ref.type, "enabled": True}))
            elif not existing.enabled:
                changes.append(f"  ↑ {ref.id} ({ref.type}): re-enabled")
                new_sensors.append(existing.model_copy(update={"enabled": True}))
            else:
                new_sensors.append(existing)  # no change
        else:
            # New sensor — try METADATA defaults for connection
            conn = _default_connection(ref.type, metadata)
            if conn is None:
                raise ReconcileError(
                    f"Sensor '{ref.id}' (type: {ref.type}) is not in the board's "
                    f"config and has no METADATA defaults to fall back on.\n"
                    f"Run 'animon probe {desired.id}' to detect hardware, or add "
                    f"the sensor manually to the board's config.yaml."
                )
            new_sensors.append(SensorConfig(id=ref.id, type=ref.type, connection=conn))
            changes.append(
                f"  + {ref.id} ({ref.type}): added with default connection "
                f"({conn.type}"
                + (f", port TBD" if conn.type in ("uart", "usb_cdc") else f", bus={conn.bus} addr={hex(conn.address or 0)}")
                + ")"
            )

    # 2. Disable sensors present on board but removed from animon.yaml
    desired_ids = {ref.id for ref in desired.sensors}
    for sid, sc in current_by_id.items():
        if sid not in desired_ids and sc.enabled:
            new_sensors.append(sc.model_copy(update={"enabled": False}))
            changes.append(f"  - {sid} ({sc.type}): disabled (not in animon.yaml)")

    # 3. Validate all enabled sensors
    for sc in new_sensors:
        if sc.enabled:
            errs = validate_connection(sc.type, sc.connection, metadata)
            for err in errs:
                changes.append(f"  ! VALIDATION WARNING: {err}")

    # 4. Build the new NodeConfig
    if current:
        new_config = current.model_copy(update={"sensors": new_sensors})
    else:
        new_config = NodeConfig(
            node_id=desired.id,
            node_type=node_type or desired.type,
            hostname=desired.hostname,
            network=NetworkConfig(host="0.0.0.0", port=desired.port),
            sensors=new_sensors,
        )
        changes.insert(0, f"  (new config — no existing config.yaml found on board)")

    return new_config, changes

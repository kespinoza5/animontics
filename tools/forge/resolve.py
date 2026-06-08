"""Channel-contract resolution — derive a device-fed sensor's `channels` from the
forge contract(s) it reads, so the channel→signal+calibration map is authored
**once** (in config/mcus/<id>.yaml) instead of twice.

A sensor that lists `devices: [press0, …]` (and no explicit `channels`) gets its
channels filled from those devices' contracts: each contract channel becomes a
`SensorChannel(index, signal, calibration, device=<id>)`, in device order. An
explicit `channels` list wins (escape hatch).

`forge resolve <node>` writes this into config/boards/<node>.yaml; the same
function is the seam for `animon deploy` to bake channels into shipped configs.
"""
from __future__ import annotations

from pathlib import Path

from core.models import SensorChannel
from tools.forge import contract as contract_mod


def derive_sensor_channels(device_ids: list[str], project_root: Path) -> list[SensorChannel]:
    """Channels a sensor reads across `device_ids`, from each device's contract."""
    channels: list[SensorChannel] = []
    for dev_id in device_ids:
        target = contract_mod.load_contract(dev_id, project_root)   # config/mcus/<id>.yaml
        for ch in target.channels:
            channels.append(SensorChannel(
                index=ch.index, signal=ch.signal,
                calibration=ch.calibration, device=dev_id,
            ))
    return channels


def resolve_board(board: dict, project_root: Path) -> tuple[dict, int]:
    """Fill device-fed sensors' `channels` from their `devices`. Mutates + returns
    the board dict and the count of sensors resolved."""
    resolved = 0
    for sc in board.get("sensors", []) or []:
        devices = sc.get("devices")
        if devices and not sc.get("channels"):
            sc["channels"] = [c.model_dump(exclude_none=True)
                              for c in derive_sensor_channels(devices, project_root)]
            resolved += 1
    return board, resolved

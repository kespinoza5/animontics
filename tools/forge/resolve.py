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
from typing import TYPE_CHECKING

from core.models import SensorChannel
from tools.forge import contract as contract_mod

if TYPE_CHECKING:
    from core.models import NodeConfig


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


def resolve_node_config(config: "NodeConfig", project_root: Path) -> list[str]:
    """Fill empty `channels` on device-fed sensors of a NodeConfig, in place.

    The model twin of resolve_board() — this is what `animon deploy` calls so a
    deployed config always ships with contract-derived channels. Explicit
    channels are left untouched. Returns human-readable change notes; raises
    ContractError if a listed device has no config/mcus/<id>.yaml.
    """
    notes: list[str] = []
    for sc in config.sensors:
        if sc.enabled and sc.devices and not sc.channels:
            derived = derive_sensor_channels(sc.devices, project_root)
            if derived:
                sc.channels = derived
                notes.append(
                    f"  ⚙ {sc.id}: {len(derived)} channels resolved from "
                    f"contract(s) {sc.devices}"
                )
            else:
                # A device-fed sensor pointed at contracts with no channel
                # block — runtime would see an empty array. Surface it.
                notes.append(
                    f"  ⚠ {sc.id}: contract(s) {sc.devices} declare no channels — "
                    f"run 'forge channels <id>' and paste the block into the contract"
                )
    return notes


def resolve_board(board: dict, project_root: Path) -> tuple[dict, int]:
    """Fill device-fed sensors' `channels` from their `devices`. Mutates + returns
    the board dict and the count of sensors resolved."""
    resolved = 0
    for sc in board.get("sensors", []) or []:
        devices = sc.get("devices")
        if devices and not sc.get("channels"):
            derived = derive_sensor_channels(devices, project_root)
            if not derived:
                continue  # contract has no channel block — nothing to write
            sc["channels"] = [c.model_dump(exclude_none=True) for c in derived]
            resolved += 1
    return board, resolved

"""Device tier introspection — health with gating awareness.

A device behind a switched-off power rail is *gated*, not failed: the cut is a
deliberate body state commanded through a `power_rail` effector that lists the
device in its `members`. This router is the surface that tells the two apart,
so fleet tooling and dashboards never report an intentional power-down as a
fault. Reads `request.app.state` (never module-level registries).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _gated_ids(effectors: dict) -> set[str]:
    gated: set[str] = set()
    for eff in effectors.values():
        if hasattr(eff, "gated_devices"):
            gated |= eff.gated_devices()
    return gated


@router.get("/devices")
async def list_devices(request: Request):
    """All devices with health + gating: healthy | gated | down."""
    devices = request.app.state.devices
    gated = _gated_ids(request.app.state.effectors)
    out = []
    for dev in devices.values():
        healthy = bool(dev.is_healthy())
        is_gated = dev.id in gated
        out.append({
            "id": dev.id,
            "kind": dev.config.kind,
            "healthy": healthy,
            "gated": is_gated,
            "status": "healthy" if healthy else ("gated" if is_gated else "down"),
        })
    return out


@router.get("/devices/{device_id}")
async def get_device(device_id: str, request: Request):
    device = request.app.state.devices.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")
    gated = device_id in _gated_ids(request.app.state.effectors)
    healthy = bool(device.is_healthy())
    return {
        "id": device.id,
        "kind": device.config.kind,
        "healthy": healthy,
        "gated": gated,
        "status": "healthy" if healthy else ("gated" if gated else "down"),
    }

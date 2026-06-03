"""
VL53L1X time-of-flight router.

Exposes the sensor's ranging-mode controls so a bench viewer (or any client)
can switch between short/medium/long range or hand control to auto-ranging.

Routes
------
  GET  /vl53l1x/state            — current mode + auto flag
  POST /vl53l1x/mode             — pin a fixed ranging mode (disables auto)
  POST /vl53l1x/auto             — enable / disable auto-ranging

Live mode changes are also pushed to stream subscribers as named SSE `mode`
events, so a connected viewer reflects switches it didn't initiate.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter(prefix="/vl53l1x", tags=["vl53l1x"])


def _get_sensor(request: Request, sensor_id: str | None = None):
    """
    Return a configured vl53l1x sensor from app state, or raise 404.

    With no sensor_id, returns the first vl53l1x on the node (the common case —
    most boards have one). Pass ?sensor_id=… to disambiguate multiple.
    """
    sensors = getattr(request.app.state, "sensors", {})
    if sensor_id is not None:
        sensor = sensors.get(sensor_id)
        if sensor is None or sensor.config.type != "vl53l1x":
            raise HTTPException(status_code=404, detail=f"No vl53l1x sensor '{sensor_id}'")
        return sensor
    for sensor in sensors.values():
        if sensor.config.type == "vl53l1x":
            return sensor
    raise HTTPException(status_code=404, detail="No vl53l1x sensor configured on this node")


# ── Request models ────────────────────────────────────────────────────────────

class ModeRequest(BaseModel):
    mode: int = Field(
        description="Ranging mode: 1=short (~1.3 m), 2=medium (~2 m), 3=long (~4 m).",
        ge=1, le=3, examples=[3],
    )


class AutoRequest(BaseModel):
    enabled: bool = Field(
        description="True hands mode selection to the sensor's auto-ranging policy.",
        examples=[True],
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/state")
async def get_state(request: Request, sensor_id: str | None = None):
    """Return the sensor's current ranging mode and auto-ranging flag."""
    sensor = _get_sensor(request, sensor_id)
    return {
        "sensor_id": sensor.id,
        "healthy":   sensor.is_healthy(),
        **sensor.mode_info(),
    }


@router.post("/mode")
async def set_mode(req: ModeRequest, request: Request, sensor_id: str | None = None):
    """Pin a fixed ranging mode. Turns auto-ranging off."""
    sensor = _get_sensor(request, sensor_id)
    sensor.set_mode(req.mode)
    log.info("%s: ranging mode pinned to %d", sensor.id, req.mode)
    return {"sensor_id": sensor.id, **sensor.mode_info()}


@router.post("/auto")
async def set_auto(req: AutoRequest, request: Request, sensor_id: str | None = None):
    """Enable or disable distance-driven auto mode selection."""
    sensor = _get_sensor(request, sensor_id)
    sensor.set_auto(req.enabled)
    log.info("%s: auto-ranging %s", sensor.id, "on" if req.enabled else "off")
    return {"sensor_id": sensor.id, **sensor.mode_info()}

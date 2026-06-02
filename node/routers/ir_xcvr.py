"""
IR transceiver router.

Routes
------
  GET  /ir/capabilities          — what this node's xcvr can do
  GET  /ir/protocols             — list of supported TX protocols
  POST /ir/transmit              — send one IR code
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)
router = APIRouter(prefix="/ir", tags=["ir"])


def _get_xcvr(request: Request):
    """
    Return the first registered ir_xcvr sensor from app state, or raise 404.

    Most nodes will have exactly one.  If a board has multiple (unlikely)
    the caller can extend this with an optional ?sensor_id query param.
    """
    sensors = getattr(request.app.state, "sensors", {})
    for sensor in sensors.values():
        if sensor.config.type == "ir_xcvr":
            return sensor
    raise HTTPException(status_code=404, detail="No ir_xcvr sensor configured on this node")


# ── Request / response models ─────────────────────────────────────────────────

class TransmitRequest(BaseModel):
    protocol: str = Field(
        default="NEC",
        description="IR protocol name: NEC or NECX",
        examples=["NEC", "NECX"],
    )
    address: int = Field(
        description="Device address. 0-255 for NEC, 0-65535 for NECX.",
        ge=0, le=0xFFFF,
        examples=[0x04],
    )
    command: int = Field(
        description="Command byte. 0-255.",
        ge=0, le=0xFF,
        examples=[0x08],
    )


class TransmitResponse(BaseModel):
    ok:       bool
    protocol: str
    address:  int
    command:  int
    scancode: int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/capabilities")
async def get_capabilities(request: Request):
    """
    Return the RX/TX capability flags for this node's IR transceiver.

    Both fields may be false if the relevant lirc device is absent or the
    driver overlay has not been configured in the device tree.
    """
    sensor = _get_xcvr(request)
    return {
        "sensor_id":    sensor.id,
        "can_receive":  getattr(sensor, "can_receive",  False),
        "can_transmit": getattr(sensor, "can_transmit", False),
        "healthy":      sensor.is_healthy(),
    }


@router.get("/protocols")
async def list_protocols(request: Request):
    """List the IR protocols this node can transmit."""
    _get_xcvr(request)  # raises 404 if no xcvr
    return {
        "protocols": [
            {
                "name":        "NEC",
                "description": "Standard NEC — 8-bit address + 8-bit command",
                "address_max": 255,
                "command_max": 255,
            },
            {
                "name":        "NECX",
                "description": "Extended NEC — 16-bit address + 8-bit command",
                "address_max": 65535,
                "command_max": 255,
            },
        ]
    }


@router.post("/transmit", response_model=TransmitResponse)
async def transmit(req: TransmitRequest, request: Request):
    """
    Transmit one IR code via the TSAL6200 emitter.

    Returns 503 if the TX device is not available (no tx_device configured,
    or the lirc device failed to open at startup).
    """
    sensor = _get_xcvr(request)

    if not getattr(sensor, "can_transmit", False):
        raise HTTPException(
            status_code=503,
            detail="TX device unavailable — check tx_device config and pwm-ir-tx overlay",
        )

    proto  = req.protocol.upper()
    ok     = sensor.transmit(proto, req.address, req.command)

    if not ok:
        raise HTTPException(status_code=500, detail="Transmit failed — see node logs")

    scancode = (req.address << 8) | req.command
    log.info(
        "IR TX: protocol=%s address=0x%04X command=0x%02X scancode=0x%06X",
        proto, req.address, req.command, scancode,
    )
    return TransmitResponse(
        ok=True,
        protocol=proto,
        address=req.address,
        command=req.command,
        scancode=scancode,
    )

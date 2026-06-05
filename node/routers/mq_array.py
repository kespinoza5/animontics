"""Control route for mq_array MCUs — drive the board's PWM outputs (e.g. fans).

The PWM fans are an actuator facet of the same microcontroller the mq_array
sensor reads, sharing one serial link, so the command goes through that sensor's
send_command(). A dedicated MCU-device object is the planned long-term home
(see docs/forge.md); this keeps the link owner as the single writer for now.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.mcu_link import CMD_SET_DUTY

router = APIRouter(prefix="/mq_array", tags=["mq_array"])


class PwmRequest(BaseModel):
    channel: int        # PWM channel index (across the MCU's pwm_out pins)
    duty: int           # 0..255


def _get_sensor(request: Request, sensor_id: str):
    sensor = getattr(request.app.state, "sensors", {}).get(sensor_id)
    if sensor is None or getattr(sensor, "sensor_type", None) != "mq_array":
        raise HTTPException(status_code=404,
                            detail=f"No mq_array sensor '{sensor_id}' on this node")
    return sensor


@router.post("/{sensor_id}/pwm")
async def set_pwm(sensor_id: str, req: PwmRequest, request: Request):
    """Set one PWM channel's duty cycle on the mq_array's MCU."""
    if not 0 <= req.duty <= 255:
        raise HTTPException(status_code=400, detail="duty must be 0..255")
    sensor = _get_sensor(request, sensor_id)
    if not sensor.send_command(CMD_SET_DUTY, [req.channel, req.duty]):
        raise HTTPException(status_code=503, detail="MCU link not open")
    return {"ok": True, "channel": req.channel, "duty": req.duty}

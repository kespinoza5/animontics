from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from core.sensor_base import SensorBase

log = logging.getLogger(__name__)
router = APIRouter()

# Populated at startup by node/app.py: {sensor_id: SensorBase}
_sensors: dict[str, SensorBase] = {}


def register_sensors(sensors: dict[str, SensorBase]) -> None:
    """Called by app startup to hand the sensor registry to this router."""
    _sensors.update(sensors)


# ── REST ─────────────────────────────────────────────────────────────────────


@router.get("/sensors")
async def list_sensors():
    """List all configured sensors with their type and enabled status."""
    return [
        {
            "id":      sensor.id,
            "type":    sensor.config.type,
            "enabled": sensor.config.enabled,
        }
        for sensor in _sensors.values()
    ]


@router.get("/sensors/{sensor_id}")
async def get_sensor(sensor_id: str):
    """Return the latest reading from a sensor, or null if not yet available."""
    sensor = _sensors.get(sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Sensor '{sensor_id}' not found")
    reading = sensor.latest
    return reading.model_dump() if reading else None


# ── SSE streaming ─────────────────────────────────────────────────────────────


@router.get("/sensors/{sensor_id}/stream")
async def sensor_stream(sensor_id: str):
    """
    Server-sent events stream for a sensor.
    Each event is a JSON-encoded SensorReading.
    A keepalive comment is sent every 25 s when no reading is available.
    """
    sensor = _sensors.get(sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Sensor '{sensor_id}' not found")

    async def generate():
        q = sensor.subscribe()
        try:
            # Send latest reading immediately if available
            latest = sensor.latest
            if latest:
                yield latest.to_sse()

            while True:
                try:
                    # Poll the queue with a short timeout to allow cancellation
                    payload = await asyncio.wait_for(
                        asyncio.to_thread(q.get, True, 25),
                        timeout=26,
                    )
                    yield payload
                except (asyncio.TimeoutError, Exception):
                    yield ": keepalive\n\n"
        finally:
            sensor.unsubscribe(q)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── WebSocket ─────────────────────────────────────────────────────────────────


@router.websocket("/sensors/{sensor_id}/ws")
async def sensor_ws(websocket: WebSocket, sensor_id: str):
    """WebSocket stream — sends the same JSON payload as the SSE stream."""
    sensor = _sensors.get(sensor_id)
    if sensor is None:
        await websocket.close(code=4004, reason=f"Sensor '{sensor_id}' not found")
        return

    await websocket.accept()
    q = sensor.subscribe()
    try:
        latest = sensor.latest
        if latest:
            await websocket.send_text(latest.model_dump_json())

        while True:
            try:
                payload = await asyncio.wait_for(
                    asyncio.to_thread(q.get, True, 25),
                    timeout=26,
                )
                # Strip the SSE framing ("data: ...\n\n") — send raw JSON
                json_str = payload.removeprefix("data: ").rstrip("\n")
                await websocket.send_text(json_str)
            except asyncio.TimeoutError:
                await websocket.send_text('{"keepalive":true}')
    except WebSocketDisconnect:
        pass
    finally:
        sensor.unsubscribe(q)

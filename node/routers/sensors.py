from __future__ import annotations

import asyncio
import logging
import queue as queue_mod

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

log = logging.getLogger(__name__)
router = APIRouter()


async def _q_get(q, block_secs: float = 25.0, poll: float = 1.0):
    """Read the subscriber queue; None after block_secs idle (send a keepalive).

    Polls in short slices instead of one long blocking get: a long get parks a
    worker thread that survives task cancellation, holding node shutdown (and
    test teardown) hostage for the full keepalive window.
    """
    waited = 0.0
    while waited < block_secs:
        try:
            return await asyncio.to_thread(q.get, True, poll)
        except queue_mod.Empty:
            waited += poll
    return None


# ── REST ─────────────────────────────────────────────────────────────────────


@router.get("/sensors")
async def list_sensors(request: Request):
    """List all configured sensors with their type and enabled status."""
    sensors = request.app.state.sensors
    return [
        {
            "id":      sensor.id,
            "type":    sensor.config.type,
            "enabled": sensor.config.enabled,
        }
        for sensor in sensors.values()
    ]


@router.get("/sensors/{sensor_id}")
async def get_sensor(sensor_id: str, request: Request):
    """Return the latest reading from a sensor, or null if not yet available."""
    sensor = request.app.state.sensors.get(sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail=f"Sensor '{sensor_id}' not found")
    reading = sensor.latest
    return reading.model_dump() if reading else None


# ── SSE streaming ─────────────────────────────────────────────────────────────


@router.get("/sensors/{sensor_id}/stream")
async def sensor_stream(sensor_id: str, request: Request):
    """
    Server-sent events stream for a sensor.
    Each event is a JSON-encoded SensorReading.
    A keepalive comment is sent every 25 s when no reading is available.
    """
    sensor = request.app.state.sensors.get(sensor_id)
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
                payload = await _q_get(q)
                yield payload if payload is not None else ": keepalive\n\n"
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
    sensor = websocket.app.state.sensors.get(sensor_id)
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
            payload = await _q_get(q)
            if payload is None:
                await websocket.send_text('{"keepalive":true}')
                continue
            # Strip the SSE framing ("data: ...\n\n") — send raw JSON
            json_str = payload.removeprefix("data: ").rstrip("\n")
            await websocket.send_text(json_str)
    except WebSocketDisconnect:
        pass
    finally:
        sensor.unsubscribe(q)


# ── Binary frame stream ───────────────────────────────────────────────────────


@router.websocket("/sensors/{sensor_id}/frames")
async def sensor_frames(websocket: WebSocket, sensor_id: str):
    """
    Binary frame stream for high-rate array/image sensors (thermal, pressure
    grids). Each message is one raw binary frame whose layout is sensor-defined
    (see the sensor's README / viewer). Use this instead of the JSON /ws lane
    when per-frame payloads are large and arrive tens of times per second — it
    avoids json.dumps on the server and a parse + GC of a big array on the
    client. Sensors without produces_frames are rejected with 4003.
    """
    sensor = websocket.app.state.sensors.get(sensor_id)
    if sensor is None:
        await websocket.close(code=4004, reason=f"Sensor '{sensor_id}' not found")
        return
    if not getattr(sensor, "produces_frames", False):
        await websocket.close(code=4003, reason=f"Sensor '{sensor_id}' has no frame stream")
        return

    await websocket.accept()
    q = sensor.subscribe_frames()
    try:
        while True:
            frame = await _q_get(q)
            if frame is None:
                await websocket.send_bytes(b"")   # keepalive ping (zero-length)
                continue
            await websocket.send_bytes(frame)
    except WebSocketDisconnect:
        pass
    finally:
        sensor.unsubscribe_frames(q)

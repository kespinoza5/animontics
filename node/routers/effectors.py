"""Effector control routes — the efferent dual of the sensor routes.

Two lanes, chosen by the effector type (not a universal verb):
  • request — POST /effectors/{id} with a type-defined body (e.g. pwm levels).
  • stream  — WS  /effectors/{id}/stream, binary frames fed continuously.
Node-implicit and logical; the backing device is metadata, never a path segment.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket

log = logging.getLogger(__name__)

router = APIRouter(tags=["effectors"])


def _get(request: Request, effector_id: str):
    effector = getattr(request.app.state, "effectors", {}).get(effector_id)
    if effector is None:
        raise HTTPException(status_code=404, detail=f"Effector '{effector_id}' not found")
    return effector


@router.get("/effectors")
async def list_effectors(request: Request):
    effectors = getattr(request.app.state, "effectors", {})
    return [
        {"id": e.id, **e.descriptor(), "state": e.state()}
        for e in effectors.values()
    ]


@router.get("/effectors/{effector_id}")
async def get_effector(effector_id: str, request: Request):
    e = _get(request, effector_id)
    return {"id": e.id, **e.descriptor(), "state": e.state()}


@router.post("/effectors/{effector_id}")
async def drive_effector(effector_id: str, request: Request, payload: dict = Body(...)):
    """Request-lane drive. Body schema is defined by the effector's type."""
    e = _get(request, effector_id)
    if "request" not in e.lanes:
        raise HTTPException(status_code=400, detail=f"'{e.id}' has no request lane")
    try:
        return e.handle_request(payload)
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.websocket("/effectors/{effector_id}/stream")
async def stream_effector(websocket: WebSocket, effector_id: str):
    """Stream-lane drive: binary frames fed to the effector (audio, LED animation)."""
    effector = getattr(websocket.app.state, "effectors", {}).get(effector_id)
    if effector is None:
        await websocket.close(code=4004, reason=f"Effector '{effector_id}' not found")
        return
    if "stream" not in effector.lanes:
        await websocket.close(code=4003, reason=f"'{effector_id}' has no stream lane")
        return
    await websocket.accept()
    try:
        while True:
            chunk = await websocket.receive_bytes()
            effector.feed(chunk)
    except Exception:
        return  # client disconnected / stream ended

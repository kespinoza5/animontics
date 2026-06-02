"""Node configuration endpoint — exposes the loaded config for the fleet tool."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/config")
async def node_config(request: Request) -> JSONResponse:
    """Return the node's active configuration as JSON.

    Returns the validated NodeConfig that was loaded at startup.
    Connection details (port, bus, address) are included so the fleet
    tool can read wiring reality from a running board.

    Secrets are never present in config.yaml and therefore never returned here.
    """
    cfg = request.app.state.config
    return JSONResponse(cfg.model_dump())

"""
Animontics node agent.

Loads config/config.yaml, discovers and starts enabled sensors,
then serves the node HTTP API via FastAPI/uvicorn.

Usage:
    uvicorn node.app:app --host 0.0.0.0 --port 8080
    uvicorn node.app:app --host 0.0.0.0 --port 8080 --config path/to/config.yaml
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core.config import load_node_config
from core.device import Device, create_device
from core.effector_base import EffectorBase, create_effector
from core.registry import create, registered_types
from core.sensor_base import SensorBase

# Import all sensor packages present on this board so their @register calls fire.
import sensors  # noqa: F401  (side-effect import)

from node.routers import camera as camera_router_module
from node.routers import sensors as sensors_router_module
from node.routers.camera import start_camera, stop_camera
from node.routers.config import router as config_router
from node.routers.effectors import router as effectors_router
from node.routers.i2c import router as i2c_router
from node.routers.ir_xcvr import router as ir_xcvr_router
from node.routers.sensors import router as sensors_router
from node.routers.vl53l1x import router as vl53l1x_router

log = logging.getLogger(__name__)

_CONFIG_PATH = os.environ.get("ANIMONTICS_CONFIG", "config/config.yaml")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    config = load_node_config(_CONFIG_PATH)

    log.info("Node: %s (%s) — %s", config.node_id, config.node_type, config.hostname)
    log.info("Known sensor types: %s", registered_types())

    # ── Devices (shared peripherals) — started before the sensors that read them.
    active_devices: dict[str, Device] = {}
    for dc in config.devices:
        try:
            device = create_device(dc)
            device.start()
            active_devices[dc.id] = device
            log.info("Device '%s' (%s): started", dc.id, dc.kind)
        except ValueError as exc:
            log.error("Device '%s': %s", dc.id, exc)

    active_sensors: dict[str, SensorBase] = {}
    for sc in config.sensors:
        if not sc.enabled:
            log.info("Sensor '%s' (%s): disabled — skipping", sc.id, sc.type)
            continue
        try:
            sensor = create(sc)
            if hasattr(sensor, "attach_devices"):
                sensor.attach_devices(active_devices)   # bind device-fed sensors
            sensor.start()
            active_sensors[sc.id] = sensor
            log.info("Sensor '%s' (%s): started", sc.id, sc.type)
        except ValueError as exc:
            log.error("Sensor '%s': %s", sc.id, exc)

    # ── Effectors (outputs) — write through devices.
    active_effectors: dict[str, EffectorBase] = {}
    for ec in config.effectors:
        if not ec.enabled:
            continue
        try:
            effector = create_effector(ec)
            if hasattr(effector, "attach_devices"):
                effector.attach_devices(active_devices)
            effector.start()
            active_effectors[ec.id] = effector
            log.info("Effector '%s' (%s): ready", ec.id, ec.type)
        except ValueError as exc:
            log.error("Effector '%s': %s", ec.id, exc)

    app.state.config    = config
    app.state.devices   = active_devices
    app.state.sensors   = active_sensors
    app.state.effectors = active_effectors

    if config.camera and config.camera.enabled:
        start_camera(config.camera)
        log.info("Camera: started (%s)", config.camera.device)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    for effector in active_effectors.values():
        effector.stop()
    for sensor in active_sensors.values():
        sensor.stop()
    for device in active_devices.values():
        device.stop()
    stop_camera()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Animontics Node",
        description="Sensor data streaming node for the Animontics distributed AI system.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(sensors_router)
    app.include_router(config_router)
    app.include_router(i2c_router)
    app.include_router(camera_router_module.router)
    app.include_router(ir_xcvr_router)
    app.include_router(effectors_router)
    app.include_router(vl53l1x_router)

    @app.get("/")
    async def node_info():
        cfg = app.state.config
        return JSONResponse({
            "node_id":   cfg.node_id,
            "node_type": cfg.node_type,
            "hostname":  cfg.hostname,
            "version":   "0.1.0",
            "sensors":   [
                {"id": s.id, "type": s.config.type, "healthy": s.is_healthy()}
                for s in app.state.sensors.values()
            ],
        })

    return app


app = create_app()

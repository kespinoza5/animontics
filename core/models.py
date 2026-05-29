"""Pydantic data models shared across the animontics node agent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ConnectionConfig(BaseModel):
    """Hardware connection parameters for a sensor."""

    type: Literal["uart", "i2c", "usb_cdc"]
    # UART / USB CDC
    port: str | None = None
    baud_rate: int | None = None
    # I2C
    bus: int | None = None
    address: int | None = None  # device address as int (e.g. 0x29 → 41)


class SensorConfig(BaseModel):
    """Configuration for a single sensor instance on this node."""

    id: str                     # unique within this node, e.g. "lidar_front"
    type: str                   # maps to a @register key in the sensor registry
    enabled: bool = True
    connection: ConnectionConfig


class NetworkConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class CameraConfig(BaseModel):
    enabled: bool = True
    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30


class NodeConfig(BaseModel):
    """Complete per-board configuration loaded from config.yaml."""

    node_id: str
    node_type: str
    hostname: str
    network: NetworkConfig = NetworkConfig()
    camera: CameraConfig | None = None
    sensors: list[SensorConfig] = []


class SensorReading(BaseModel):
    """
    Standardized reading emitted by every sensor.

    Standardized data keys per sensor type:
      tf_mini, lv_maxsonar, vl53l1x:
        distance_mm: int
        strength:    int | None
        temp_c:      float | None
      mlx90640:
        pixels:   list[float]  (768 values, row-major 32×24)
        min_temp: float
        max_temp: float
        width:    int (32)
        height:   int (24)
    """

    sensor_id: str
    sensor_type: str
    timestamp: float            # Unix epoch seconds
    data: dict[str, Any]

    def to_sse(self) -> str:
        """Format as an SSE data frame."""
        return f"data: {self.model_dump_json()}\n\n"

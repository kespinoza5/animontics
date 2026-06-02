"""Pydantic data models shared across the animontics node agent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ConnectionConfig(BaseModel):
    """Hardware connection parameters for a sensor."""

    type: Literal["uart", "i2c", "usb_cdc", "ir"]
    # UART / USB CDC
    port: str | None = None
    baud_rate: int | None = None
    # I2C
    bus: int | None = None
    address: int | None = None  # device address as int (e.g. 0x29 → 41)
    # IR (LIRC)
    rx_device: str | None = None   # e.g. /dev/lirc0  — omit to disable RX
    tx_device: str | None = None   # e.g. /dev/lirc1  — omit to disable TX


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


# ── Fleet / animon.yaml models ────────────────────────────────────────────────

class AnimonSensorRef(BaseModel):
    """A sensor assignment in the fleet topology.

    Intentionally minimal — contains only what the fleet needs to know.
    Wiring details (port, bus, address, baud_rate) live in the board's
    config.yaml; hardware constraints live in each sensor's METADATA dict.
    """

    id: str    # sensor instance id, e.g. "lidar_front"
    type: str  # sensor type key matching a @register decorator, e.g. "tf_mini"


class AnimonUsbMcu(BaseModel):
    """A microcontroller attached via USB hub."""

    type: str                    # e.g. "rp2040", "samd20", "arduino"
    usb_port: str                # hub port identifier, e.g. "1-1"
    role: str | None = None      # optional role label, e.g. "power_control"


class AnimonNodeConnection(BaseModel):
    """Describes how a node connects to the network (for non-Ethernet nodes)."""

    via: str   # e.g. "usb_gadget"
    host: str  # id of the host node that bridges this connection


class AnimonNodeCamera(BaseModel):
    """Camera presence flag for a node in the fleet topology."""

    enabled: bool = True


class AnimonNodeEntry(BaseModel):
    """A single node in the animon.yaml fleet topology."""

    id: str
    hostname: str
    ip: str | None = None            # None for USB-attached nodes
    type: str                        # board type, e.g. "orangepi_zero2"
    port: int = 8080
    ssh_user: str | None = None      # overrides AnimonDefaults.ssh_user
    deploy_path: str | None = None   # overrides AnimonDefaults.deploy_path
    sensors: list[AnimonSensorRef] = []
    capabilities: list[str] = []
    connection: AnimonNodeConnection | None = None
    usb_attached: list[str] = []     # ids of USB-gadget child nodes
    usb_mcus: list[AnimonUsbMcu] = []
    camera: AnimonNodeCamera | None = None


class AnimonDefaults(BaseModel):
    """Fleet-wide defaults, overridable per node."""

    ssh_user: str = "pi"
    deploy_path: str = "/opt/animontics"


class AnimonConfig(BaseModel):
    """Complete fleet topology loaded from animon.yaml."""

    system_name: str
    defaults: AnimonDefaults = AnimonDefaults()
    nodes: list[AnimonNodeEntry] = []

    def get_node(self, node_id: str) -> AnimonNodeEntry | None:
        """Return the node entry with the given id, or None if not found."""
        return next((n for n in self.nodes if n.id == node_id), None)

    def effective_ssh_user(self, node: AnimonNodeEntry) -> str:
        """Resolve SSH user for a node (node override → fleet default)."""
        return node.ssh_user or self.defaults.ssh_user

    def effective_deploy_path(self, node: AnimonNodeEntry) -> str:
        """Resolve deploy path for a node (node override → fleet default)."""
        return node.deploy_path or self.defaults.deploy_path


# ── Runtime sensor readings ───────────────────────────────────────────────────

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
      ir_xcvr:
        protocol : str   — "NEC" | "NECX" | "NEC32" | "RC5" | … | "PROTO_N"
        address  : int   — decoded device address
        command  : int   — decoded command byte
        scancode : int   — raw kernel scancode (address << 8 | command for NEC)
        repeat   : bool  — True when this is a held-key repeat frame
    """

    sensor_id: str
    sensor_type: str
    timestamp: float            # Unix epoch seconds
    data: dict[str, Any]

    def to_sse(self) -> str:
        """Format as an SSE data frame."""
        return f"data: {self.model_dump_json()}\n\n"

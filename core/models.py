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


class SensorChannel(BaseModel):
    """One channel of an array sensor — its source, meaning, and calibration.

    Array sensors read a flat vector of raw values from one or more devices.
    `device` is the device id this channel comes from (a logical sensor may span
    several — e.g. cranial pressure across 4 MCUs); `index` is the position within
    that device's frame; `signal` is the node-side name; `calibration` is applied
    in Python. Authored consistently with the MCU's config/mcus/<id>.yaml.
    """

    index: int                          # position within the device's frame
    signal: str                         # human signal name, e.g. "mq135"
    device: str | None = None           # device id this channel reads from
    calibration: dict[str, Any] = {"type": "raw"}


class DeviceConfig(BaseModel):
    """A shared peripheral on this node — an MCU link, an ADS1115 chip, etc.

    A device owns its transport; sensors read through it and effectors write
    through it. Created at node startup and bound to sensors/effectors by id.
    """

    id: str
    kind: str                           # "mcu_serial" | "ads1115" | ...
    # mcu_serial
    port: str | None = None
    baud: int | None = None
    # i2c (ads1115)
    bus: int | None = None
    address: int | None = None          # device address as int (0x48 → 72)


class SensorConfig(BaseModel):
    """Configuration for a single sensor instance on this node."""

    id: str                     # unique within this node, e.g. "lidar_front"
    type: str                   # maps to a @register key in the sensor registry
    enabled: bool = True
    connection: ConnectionConfig | None = None  # None for device-fed array sensors
    devices: list[str] = []     # device-fed sensors: derive `channels` from these
    channels: list[SensorChannel] = []          # array sensors; empty for scalars


class EffectorChannel(BaseModel):
    """One output channel of an effector — a name (API/UX) and an index (wire)."""

    name: str
    index: int


class EffectorConfig(BaseModel):
    """An output device on this node (fans, LEDs, motors, …).

    `backend` selects where it writes: {device: <id>} drives a device's command
    sink (e.g. an MCU's PWM); an SBC-direct backend (e.g. {type: sbc_pwm, pins})
    is a later addition. Channels carry name+index.
    """

    id: str
    type: str                           # maps to a @register_effector key
    enabled: bool = True
    backend: dict[str, Any] = {}
    channels: list[EffectorChannel] = []
    params: dict[str, Any] = {}         # effector-type settings (e.g. pwm min_duty)


class PolicyConfig(BaseModel):
    """A control loop on this node. The behavior is code (a registered PolicyBase
    subclass named by `type`); this only declares the wiring + params.

    `observation` is a list of relay signal names (e.g. "gas_array.raw.mq135",
    "board_temp.cpu_c"); `action` targets an effector ({effector: <id>});
    `always_on` marks a reflex that should keep running when cortical policies are
    absent. Learned policies reference weights via `params`.
    """

    id: str
    type: str                           # maps to a @register_policy key
    enabled: bool = True
    always_on: bool = False
    observation: list[str] = []
    action: dict[str, Any] = {}
    params: dict[str, Any] = {}


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
    devices: list[DeviceConfig] = []
    sensors: list[SensorConfig] = []
    effectors: list[EffectorConfig] = []
    policies: list[PolicyConfig] = []


# ── Fleet models ──────────────────────────────────────────────────────────────

class AnimonSensorRef(BaseModel):
    """A sensor assignment in the fleet topology (id + type only).

    Intentionally minimal — wiring details (port, bus, address, baud_rate)
    live in the board's config.yaml / config/boards/<id>.yaml; hardware
    constraints live in each sensor's METADATA dict.
    """

    id: str    # sensor instance id, e.g. "lidar_front"
    type: str  # sensor type key matching a @register decorator, e.g. "tf_mini"


class AnimonUsbMcu(BaseModel):
    """A microcontroller attached via USB hub.

    The optional `id` names this MCU instance and links it to its forge build
    contract at config/mcus/<id>.yaml; `contract` overrides that path stem if it
    differs from `id`. Both are optional so existing node files stay valid.
    """

    type: str                    # e.g. "rp2040", "samd20", "arduino"
    usb_port: str                # hub port identifier, e.g. "1-1"
    role: str | None = None      # optional role label, e.g. "power_control"
    id: str | None = None        # instance id; matches config/mcus/<id>.yaml
    contract: str | None = None  # forge contract stem (defaults to id)


class AnimonNodeConnection(BaseModel):
    """Network connection details for non-Ethernet nodes (e.g. USB gadget)."""

    via: str              # e.g. "usb_gadget"
    host: str             # id of the host node that bridges this connection
    usb_ip: str | None = None  # IP on the USB gadget network


class AnimonNodeCamera(BaseModel):
    """Camera presence flag for a node in the fleet topology."""

    enabled: bool = True


class NodeDesiredState(BaseModel):
    """Desired state for one node — lives in config/nodes/<id>.yaml (in repo).

    Contains the logical description of what a node should run: sensors,
    capabilities, board type. No IPs, no SSH users, no physical wiring.
    """

    id: str
    type: str                        # board type, e.g. "raspberry_pi_5"
    hostname: str
    port: int = 8080
    role: str | None = None          # informational, e.g. "vision", "proprioception"
    sensors: list[AnimonSensorRef] = []
    capabilities: list[str] = []
    camera: AnimonNodeCamera | None = None
    usb_mcus: list[AnimonUsbMcu] = []
    usb_attached: list[str] = []     # ids of USB-gadget child nodes


class AnimonNodeAccess(BaseModel):
    """Access details for one node — lives in config/animon.yaml (gitignored).

    Contains only the information needed to reach the board: IP address,
    SSH credentials, network topology. Never mixed with desired state.
    """

    ip: str | None = None            # GbE address; None for USB-only nodes
    wifi_ip: str | None = None       # WiFi address if dual-homed
    ssh_user: str | None = None      # overrides AnimonDefaults.ssh_user
    deploy_path: str | None = None   # overrides AnimonDefaults.deploy_path
    connection: AnimonNodeConnection | None = None  # for USB-gadget nodes


class AnimonDefaults(BaseModel):
    """Fleet-wide defaults, overridable per node in config/animon.yaml."""

    ssh_user: str = "pi"
    deploy_path: str = "/opt/animontics"


class AnimonNodeEntry(BaseModel):
    """Merged working view of a node used by the fleet tool at runtime.

    Assembled by load_fleet() from NodeDesiredState (config/nodes/) and
    AnimonNodeAccess (config/animon.yaml). Code that reads fleet state
    should always work with this type, not the split sources.
    """

    # From NodeDesiredState (config/nodes/<id>.yaml)
    id: str
    type: str
    hostname: str
    port: int = 8080
    role: str | None = None
    sensors: list[AnimonSensorRef] = []
    capabilities: list[str] = []
    camera: AnimonNodeCamera | None = None
    usb_mcus: list[AnimonUsbMcu] = []
    usb_attached: list[str] = []

    # From AnimonNodeAccess (config/animon.yaml)
    ip: str | None = None
    wifi_ip: str | None = None
    ssh_user: str | None = None
    deploy_path: str | None = None
    connection: AnimonNodeConnection | None = None


class BoardOverride(BaseModel):
    """Marker for an ad-hoc config deployed to a board outside the normal flow.

    Lives at config/boards/<id>.override.yaml (gitignored). Records a deliberate
    deviation from the staged baseline (config/boards/<id>.yaml) for testing,
    debugging, or rollback. While an override is active the baseline is never
    overwritten, so `animon revert <id>` can restore it exactly and delete this
    marker. There is intentionally only one override state — the human reason for
    the deviation lives in `note`, not in a typed category.
    """

    deployed_at: str             # ISO-8601 UTC timestamp of the override deploy
    source: str | None = None    # path the override config was loaded from
    note: str | None = None      # free-text reason, e.g. "test tf_mini @ 230400"
    config: NodeConfig           # the exact config pushed to the board


class AnimonConfig(BaseModel):
    """Complete fleet topology — merged from config/nodes/ + config/animon.yaml."""

    system_name: str = ""
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

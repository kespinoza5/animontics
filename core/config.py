"""Configuration loaders for animontics.

Three config sources feed the fleet tool:

  config/nodes/<id>.yaml    Desired state per node (in repo, no secrets).
                            Loaded by load_fleet() → NodeDesiredState.

  config/animon.yaml        Access layer: IPs, SSH users (gitignored).
                            Loaded by load_fleet() → AnimonNodeAccess per node.

  config/boards/<id>.yaml   Dev-machine staging copy of each board's wiring
  (or board's config.yaml)  config. Gitignored. Same schema as NodeConfig.
                            Loaded directly by deploy/diff when reading
                            current board state offline.

The primary entry point is load_fleet(), which merges the first two sources
into an AnimonConfig whose nodes are AnimonNodeEntry objects. The fleet tool
always works with AnimonNodeEntry — it never reads the split sources directly.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from core.models import (
    AnimonConfig,
    AnimonDefaults,
    AnimonNodeAccess,
    AnimonNodeEntry,
    NodeConfig,
    NodeDesiredState,
)


# ---------------------------------------------------------------------------
# Fleet loader — merges config/nodes/ + config/animon.yaml
# ---------------------------------------------------------------------------

def load_fleet(
    project_root: Path | None = None,
    *,
    nodes_dir: Path | None = None,
    animon_path: Path | None = None,
) -> AnimonConfig:
    """Load and merge the fleet desired state and access layer.

    Reads all config/nodes/<id>.yaml files (desired state, in repo) and
    config/animon.yaml (access details, gitignored) and merges them into
    an AnimonConfig whose nodes are ready-to-use AnimonNodeEntry objects.

    Either supply a project_root (auto-discovers both sources) or override
    nodes_dir / animon_path individually for testing.

    The access config (animon.yaml) is optional: if absent, all access
    fields (ip, ssh_user, etc.) on the resulting nodes will be None. The
    fleet tool will then fail at connection time with a clear error.

    Args:
        project_root: Repo root; auto-detected from this file if None.
        nodes_dir:    Path to config/nodes/ (overrides project_root).
        animon_path:  Path to config/animon.yaml (overrides project_root).

    Returns:
        AnimonConfig with merged nodes, ready for fleet operations.

    Raises:
        FileNotFoundError: if config/nodes/ does not exist.
    """
    root = project_root or _project_root()
    nodes_dir = nodes_dir or root / "config" / "nodes"
    animon_path = animon_path or root / "config" / "animon.yaml"

    if not nodes_dir.exists():
        raise FileNotFoundError(
            f"Node desired-state directory not found: {nodes_dir}\n"
            f"Create config/nodes/<node-id>.yaml for each node in your fleet.\n"
            f"See config/animon.example.yaml for the schema."
        )

    # ── Load access layer (optional — gitignored, may not exist) ──────────────
    system_name = ""
    defaults = AnimonDefaults()
    access_by_id: dict[str, AnimonNodeAccess] = {}

    if animon_path.exists():
        raw = yaml.safe_load(animon_path.read_text(encoding="utf-8")) or {}
        system_name = raw.get("system_name", "")
        if "defaults" in raw:
            defaults = AnimonDefaults.model_validate(raw["defaults"])
        for nid, ndata in (raw.get("nodes") or {}).items():
            access_by_id[nid] = AnimonNodeAccess.model_validate(ndata or {})

    # ── Load desired state files and merge ────────────────────────────────────
    nodes: list[AnimonNodeEntry] = []
    for yaml_file in sorted(nodes_dir.glob("*.yaml")):
        raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        if not raw:
            continue
        desired = NodeDesiredState.model_validate(raw)
        access = access_by_id.get(desired.id, AnimonNodeAccess())
        nodes.append(_merge(desired, access))

    return AnimonConfig(system_name=system_name, defaults=defaults, nodes=nodes)


def _merge(desired: NodeDesiredState, access: AnimonNodeAccess) -> AnimonNodeEntry:
    """Merge desired state + access details into a working AnimonNodeEntry."""
    return AnimonNodeEntry(
        # Desired state
        id=desired.id,
        type=desired.type,
        hostname=desired.hostname,
        port=desired.port,
        role=desired.role,
        sensors=desired.sensors,
        capabilities=desired.capabilities,
        camera=desired.camera,
        usb_mcus=desired.usb_mcus,
        usb_attached=desired.usb_attached,
        # Access layer
        ip=access.ip,
        wifi_ip=access.wifi_ip,
        ssh_user=access.ssh_user,
        deploy_path=access.deploy_path,
        connection=access.connection,
    )


def _project_root() -> Path:
    """Return the project root (three levels up from core/config.py)."""
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Board config loader — per-board wiring (config.yaml / boards/<id>.yaml)
# ---------------------------------------------------------------------------

def load_node_config(path: str | Path = "config/config.yaml") -> NodeConfig:
    """Load and validate a per-board node configuration.

    Used by the node agent at startup and by the fleet tool when reading
    staging copies from config/boards/<id>.yaml.

    Args:
        path: Path to a board config YAML file.

    Returns:
        Validated NodeConfig instance.

    Raises:
        FileNotFoundError: if the config file does not exist.
        pydantic.ValidationError: if the config is malformed.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Board config not found: {p}\n"
            f"Copy config/config.example.yaml to {p} and edit it for this board."
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return NodeConfig.model_validate(raw)


def load_board_staging(
    node_id: str,
    project_root: Path | None = None,
) -> NodeConfig | None:
    """Load the dev-machine staging copy of a board's wiring config.

    Returns the NodeConfig from config/boards/<node-id>.yaml, or None if
    no staging copy exists yet (run 'animon pull <node-id>' to create one).
    """
    root = project_root or _project_root()
    path = root / "config" / "boards" / f"{node_id}.yaml"
    if not path.exists():
        return None
    return load_node_config(path)


def save_board_staging(
    node_id: str,
    config: NodeConfig,
    project_root: Path | None = None,
) -> Path:
    """Write a board's wiring config to the dev-machine staging directory.

    Creates config/boards/ if it doesn't exist. Called by 'animon deploy'
    and 'animon pull' to keep the staging copy in sync with the board.

    Returns the path written.
    """
    root = project_root or _project_root()
    boards_dir = root / "config" / "boards"
    boards_dir.mkdir(parents=True, exist_ok=True)

    path = boards_dir / f"{node_id}.yaml"
    path.write_text(
        yaml.dump(config.model_dump(exclude_none=True), default_flow_style=False,
                  allow_unicode=True),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Back-compat shim — kept for any code that still calls load_animon_config()
# ---------------------------------------------------------------------------

def load_animon_config(path: str | Path = "config/animon.yaml") -> AnimonConfig:
    """Deprecated shim: use load_fleet() instead.

    Attempts to load from the split nodes/ + animon.yaml layout first.
    Falls back to reading a legacy monolithic animon.yaml for migration.
    """
    p = Path(path)
    root = p.parent.parent  # config/ → project root
    nodes_dir = p.parent / "nodes"

    if nodes_dir.exists():
        return load_fleet(root, animon_path=p)

    # Legacy monolithic format (pre-split)
    if not p.exists():
        raise FileNotFoundError(
            f"Fleet config not found: {p}\n"
            f"Create config/nodes/<node-id>.yaml files for your fleet nodes.\n"
            f"See config/animon.example.yaml for the schema."
        )
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return AnimonConfig.model_validate(raw)

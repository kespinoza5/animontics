from __future__ import annotations

from pathlib import Path

import yaml

from core.models import NodeConfig


def load_node_config(path: str | Path = "config/config.yaml") -> NodeConfig:
    """
    Load and validate the per-board node configuration.

    Args:
        path: Path to a YAML config file. Defaults to config/config.yaml.

    Returns:
        Validated NodeConfig instance.

    Raises:
        FileNotFoundError: if the config file does not exist.
        pydantic.ValidationError: if the config is malformed.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Node config not found: {p}\n"
            f"Copy config/config.example.yaml to {p} and edit it for this board."
        )
    raw = yaml.safe_load(p.read_text())
    return NodeConfig.model_validate(raw)

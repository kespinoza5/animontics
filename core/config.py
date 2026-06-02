"""Per-board YAML configuration loader."""
from __future__ import annotations

from pathlib import Path

import yaml

from core.models import AnimonConfig, NodeConfig


def load_animon_config(path: str | Path = "config/animon.yaml") -> AnimonConfig:
    """
    Load and validate the fleet topology from animon.yaml.

    Args:
        path: Path to animon.yaml. Defaults to config/animon.yaml.

    Returns:
        Validated AnimonConfig instance.

    Raises:
        FileNotFoundError: if the file does not exist.
        pydantic.ValidationError: if the file is malformed.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Fleet config not found: {p}\n"
            f"Expected animon.yaml at {p}."
        )
    raw = yaml.safe_load(p.read_text())
    return AnimonConfig.model_validate(raw)


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

"""builder.py — the target-pluggable Builder interface + registry.

A Builder turns a per-instance contract into a flashable artifact through four
steps:

    validate(ctx) -> [issues]   static checks before building (read-only)
    compose(ctx)  -> project    render a buildable project from the contract
    build(ctx)    -> Artifact   compile the project to a flashable file
    deploy(ctx, artifact, ...)  ship + flash it to the target

forge dispatches on the contract's `target` key (e.g. "mcu.arduino"). FPGA and
accelerator (Hailo/Coral) builders register under their own keys with zero churn
to existing ones — the orchestrator never names a concrete builder. This mirrors
the sensor registry in core/registry.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from tools.forge.contract import McuTarget


class BuildError(Exception):
    """Raised when composition, compilation, or deployment fails."""


@dataclass
class BuildContext:
    """Everything a builder needs for one instance."""

    contract: "McuTarget"
    project_root: Path        # repo root (locates mcu/<family>/ source)
    out_dir: Path             # firmware/<id>/ (composed project + artifact)


@dataclass
class Artifact:
    """The result of a successful build."""

    path: Path                # the flashable file (.hex/.uf2/.bin)
    project_dir: Path         # the composed project directory


class Builder(ABC):
    """Base class for every forge target. Subclasses set the two class vars and
    register with @register_builder."""

    target_type: ClassVar[str]      # e.g. "mcu.arduino"
    artifact_suffix: ClassVar[str]  # e.g. ".hex"

    @abstractmethod
    def validate(self, ctx: BuildContext) -> list[str]:
        """Return a list of human-readable problems (empty == OK). Read-only."""

    @abstractmethod
    def compose(self, ctx: BuildContext) -> Path:
        """Render a buildable project into ctx.out_dir; return the project dir."""

    @abstractmethod
    def build(self, ctx: BuildContext) -> Artifact:
        """Compose (if needed) and compile; return the flashable Artifact."""

    @abstractmethod
    def deploy(self, ctx: BuildContext, artifact: Artifact, *,
               host: str, user: str, dry_run: bool = False) -> None:
        """Ship the artifact to the target and flash it (over the host's SSH)."""


_builders: dict[str, type[Builder]] = {}


def register_builder(target_type: str):
    """Class decorator registering a Builder subclass under its target key."""
    def decorator(cls: type[Builder]) -> type[Builder]:
        cls.target_type = target_type
        _builders[target_type] = cls
        return cls
    return decorator


def get_builder(target_type: str) -> Builder:
    """Instantiate the builder for a target key. Raises BuildError if unknown."""
    cls = _builders.get(target_type)
    if cls is None:
        raise BuildError(
            f"No builder for target '{target_type}'. "
            f"Known: {sorted(_builders)}. Is its builders/ module imported?"
        )
    return cls()


def registered_builders() -> list[str]:
    return sorted(_builders)

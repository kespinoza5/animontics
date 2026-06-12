"""Policies — a cortex's control loop: observation → action.

A policy maps a vector of named afferent signals (read from the relay) to actions
on effectors. It is tunable, trainable, swappable, composable, and light enough
for a node CPU or eventually an MCU. Reflexes are just **always-on** policies that
keep the body safe while higher (cortical) policies are down or hot-swapping.

A policy is *code*, not config: `PolicyConfig` only declares the observation/action
wiring + params; the behavior is a registered `PolicyBase` subclass — today a
hand-written curve, later a learned/stochastic model behind the identical
`step(obs) → action` contract. Policies *use* models (perception); they are not
models.

`PolicyRuntime` is the loop that, each tick, snapshots sensors into the relay,
builds each policy's observation, steps it, and applies the action to its effector.
"""
from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.effector_base import EffectorBase
    from core.models import PolicyConfig
    from core.relay import Relay
    from core.sensor_base import SensorBase

log = logging.getLogger(__name__)

_registry: dict[str, type["PolicyBase"]] = {}


def register_policy(policy_type: str):
    def decorator(cls: type["PolicyBase"]) -> type["PolicyBase"]:
        cls.policy_type = policy_type
        _registry[policy_type] = cls
        return cls
    return decorator


def registered_specs() -> dict[str, dict]:
    """Return {type: SPEC} for every registered policy type (see PolicyBase.SPEC)."""
    return {t: getattr(cls, "SPEC", {}) for t, cls in _registry.items()}


def create_policy(config: "PolicyConfig") -> "PolicyBase":
    cls = _registry.get(config.type)
    if cls is None:
        raise ValueError(
            f"Unknown policy type '{config.type}'. Known: {sorted(_registry)}."
        )
    return cls(config.id, config)


class PolicyBase(ABC):
    """Base control loop. Subclasses implement `step(obs) → action`."""

    policy_type: str = "policy"

    #: Authoring spec — what a board config `policies:` entry for this type
    #: must/may contain. Validated by `animon deploy` BEFORE pushing.
    #: Keys (all optional):
    #:   description       — one line for `animon types`
    #:   needs_effector    — True if action.effector is required
    #:   needs_observation — True if an empty observation list is suspicious
    #:   params            — known `params:` keys (unknown keys ⇒ deploy warning)
    SPEC: dict = {}

    def __init__(self, policy_id: str, config: "PolicyConfig") -> None:
        self.id = policy_id
        self.config = config
        self.enabled = config.enabled
        self.observation_names: list[str] = list(config.observation)
        self.target_effector_id: str | None = config.action.get("effector")
        self._target_channels: list[str] = []
        self.last_obs: dict = {}
        self.last_action: dict = {}

    @property
    def always_on(self) -> bool:
        return self.config.always_on

    def bind_effector(self, effector: "EffectorBase") -> None:
        """Learn the effector's channel names so actions can target them."""
        self._target_channels = [c.name for c in effector.channels]

    @abstractmethod
    def step(self, obs: dict) -> dict:
        """Map observation {signal_name: value} → action {channel_name: value}."""


# Concrete policy types live in the policies/ plugin tree (policies/curve, …),
# auto-discovered like sensors. The runtime below stays in core.


class PolicyRuntime:
    """Runs the node's policy stack on a fixed tick.

    Each tick: snapshot sensor readings into the relay, then for each enabled
    policy build its observation, `step`, and apply the action to its effector via
    the request lane. always_on policies are ordered first so reflexes run even if
    a later cortical policy errors.
    """

    def __init__(self, policies, sensors, effectors, relay: "Relay", hz: float = 10.0):
        # always-on (reflex) policies first
        self._policies = sorted(policies, key=lambda p: not p.always_on)
        self._sensors: dict[str, "SensorBase"] = sensors
        self._effectors: dict[str, "EffectorBase"] = effectors
        self._relay = relay
        self._period = 1.0 / hz if hz > 0 else 0.1
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # bind each policy to its target effector's channels
        for p in self._policies:
            eff = self._effectors.get(p.target_effector_id)
            if eff is not None:
                p.bind_effector(eff)

    def tick(self) -> None:
        """One control step (also called directly in tests)."""
        for sid, sensor in self._sensors.items():
            reading = sensor.latest
            if reading is not None:
                self._relay.publish_tree(sid, reading.data)

        for policy in self._policies:
            if not policy.enabled:
                continue
            obs = {name: self._relay.latest(name) for name in policy.observation_names}
            try:
                action = policy.step(obs)
            except Exception:
                log.exception("policy %s: step failed", policy.id)
                continue
            policy.last_obs, policy.last_action = obs, action
            eff = self._effectors.get(policy.target_effector_id)
            if eff is not None and action:
                eff.handle_request({"levels": action})
            self._relay.publish(f"{policy.id}.action", action)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="policy-runtime")
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self._period)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def policies(self):
        return self._policies

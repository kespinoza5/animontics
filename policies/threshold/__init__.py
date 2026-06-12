try:
    from policies.threshold.policy import ThresholdPolicy
except ImportError:
    pass  # METADATA below must still load

METADATA = {
    "type": "threshold",
    "description": "Trip/release guard — drives an effector when a signal crosses a threshold.",
    "needs_effector": True,
    "needs_observation": True,
    "params": ["trip_above", "release_below", "latch"],
}

__all__ = ["ThresholdPolicy", "METADATA"]

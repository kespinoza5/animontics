try:
    from policies.curve.policy import CurvePolicy
except ImportError:
    pass  # METADATA below must still load

METADATA = {
    "type": "curve",
    "description": "Piecewise-linear map: observations → one effector's channels.",
    "needs_effector": True,
    "needs_observation": True,
    "params": ["in_min", "in_max", "out_min", "out_max"],
}

__all__ = ["CurvePolicy", "METADATA"]

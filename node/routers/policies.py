"""Policy routes — inspect and toggle the node's control loops.

A policy maps observations (relay signals) to actions (effector channels). These
routes expose its wiring and current obs/action, and let an operator (or an
upstream cortex) enable/disable it. Hot-swapping a policy's behavior is a later
addition; the interface is the seam.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

router = APIRouter(tags=["policies"])


def _view(p) -> dict:
    return {
        "id": p.id,
        "type": p.policy_type,
        "always_on": p.always_on,
        "enabled": p.enabled,
        "observation": p.observation_names,
        "action": {"effector": p.target_effector_id},
        "last_obs": p.last_obs,
        "last_action": p.last_action,
    }


def _get(request: Request, policy_id: str):
    policy = getattr(request.app.state, "policies", {}).get(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found")
    return policy


@router.get("/policies")
async def list_policies(request: Request):
    return [_view(p) for p in getattr(request.app.state, "policies", {}).values()]


@router.get("/policies/{policy_id}")
async def get_policy(policy_id: str, request: Request):
    return _view(_get(request, policy_id))


@router.post("/policies/{policy_id}/enable")
async def enable_policy(policy_id: str, request: Request, enabled: bool = Body(..., embed=True)):
    policy = _get(request, policy_id)
    policy.enabled = enabled
    return {"id": policy.id, "enabled": policy.enabled}

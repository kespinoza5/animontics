"""Launch the node agent, binding from its serving config.

    python -m node                          # binds from config.network
    ANIMONTICS_CONFIG=/path/to/config.yaml python -m node

The bind host:port is the node's **serving config** (`config/boards/<id>.yaml`
`network:`), which `animon deploy` projects from the authoritative port in
`config/animon.yaml`. This is the single source of truth for the port: the fleet
connects to the access port, and the agent binds the same value here — no drift.

For ad-hoc runs you can still bind explicitly with uvicorn:
    uvicorn node.app:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import os

import uvicorn

from core.config import load_node_config


def main() -> None:
    config_path = os.environ.get("ANIMONTICS_CONFIG", "config/config.yaml")
    net = load_node_config(config_path).network
    uvicorn.run("node.app:app", host=net.host, port=net.port)


if __name__ == "__main__":
    main()

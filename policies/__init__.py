import importlib
import logging
import pkgutil
from pathlib import Path

log = logging.getLogger(__name__)

# Auto-discovers the policy packages present on disk (mirrors sensors/__init__).
# Each package's import triggers its @register_policy decorator.
for _pkg in pkgutil.iter_modules([str(Path(__file__).parent)]):
    try:
        importlib.import_module(f"policies.{_pkg.name}")
    except ImportError as _e:
        log.debug("policies.%s: skipped — missing dependency (%s)", _pkg.name, _e)

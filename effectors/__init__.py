import importlib
import logging
import pkgutil
from pathlib import Path

log = logging.getLogger(__name__)

# Auto-discovers the effector packages present on disk (mirrors sensors/__init__).
# Each package's import triggers its @register_effector decorator. Boards carry
# only the effector types they use; missing deps are logged and skipped.
for _pkg in pkgutil.iter_modules([str(Path(__file__).parent)]):
    try:
        importlib.import_module(f"effectors.{_pkg.name}")
    except ImportError as _e:
        log.debug("effectors.%s: skipped — missing dependency (%s)", _pkg.name, _e)

import importlib
import logging
import pkgutil
from pathlib import Path

log = logging.getLogger(__name__)

# Auto-discovers the device packages present on disk (mirrors sensors/__init__,
# effectors/__init__, policies/__init__). Each package's import triggers its
# @register_device decorator. Boards carry only the device kinds they use;
# missing hardware deps (pyserial, smbus2, gpiod) are logged and skipped.
for _pkg in pkgutil.iter_modules([str(Path(__file__).parent)]):
    try:
        importlib.import_module(f"devices.{_pkg.name}")
    except ImportError as _e:
        log.debug("devices.%s: skipped — missing dependency (%s)", _pkg.name, _e)

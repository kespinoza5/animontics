import importlib
import logging
import pkgutil
from pathlib import Path

log = logging.getLogger(__name__)

# Auto-discovers only the sensor packages physically present on disk.
# Each board is deployed only the sensor packages it needs, so this list
# differs per node. No static imports required — adding a sensor to a board
# means scp-ing the package directory and restarting the service.
for _pkg in pkgutil.iter_modules([str(Path(__file__).parent)]):
    try:
        importlib.import_module(f"sensors.{_pkg.name}")
    except ImportError as _e:
        # Hardware-specific dependencies (smbus2, pyserial, etc.) may not be
        # installed on all machines. Log and skip rather than crashing.
        log.debug("sensors.%s: skipped — missing dependency (%s)", _pkg.name, _e)

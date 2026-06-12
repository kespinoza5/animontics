# SPDX-License-Identifier: MIT
"""Pin-capability probe — prints this board's table for mcu/circuit_python/boards/.

Bench script (validate_* convention — runs ON a CircuitPython board, never
collected by pytest). Copy to the board's CIRCUITPY drive as code.py, open the
serial console, and diff the output against the authored
mcu/circuit_python/boards/<profile>.yaml — the chip is the source of truth for
every `# VERIFY` entry.

Probes by instantiation: for each pin in `board.*`, try the peripheral class
behind each capability kind and catch the ValueError CircuitPython raises on
an incapable pin. Alias names (D0/A0 on the same pad) are listed under both
names, matching the authored tables. Bus roles (uart.tx, spi.mosi, …) are NOT
probed — pairwise bus construction is O(n²) and noisy; those stay
datasheet-authored.
"""
import board
import microcontroller


def _pins():
    """Sorted (name, Pin) for every pin attribute on the board module."""
    out = []
    for name in sorted(dir(board)):
        if name.startswith("_"):
            continue
        obj = getattr(board, name)
        if isinstance(obj, microcontroller.Pin):
            out.append((name, obj))
    return out


def _probe(make):
    """Names of pins that accept the peripheral constructor `make`."""
    good = []
    for name, pin in _pins():
        try:
            dev = make(pin)
        except ValueError:
            continue
        except Exception:
            continue  # pin busy (e.g. onboard LED driver) — treat as unknown
        dev.deinit()
        good.append(name)
    return good


def _capability_probes():
    """capability kind → constructor, skipping classes this build lacks."""
    probes = {}

    try:
        import digitalio
        probes["gpio"] = lambda p: digitalio.DigitalInOut(p)
    except ImportError:
        pass
    try:
        import analogio
        probes["adc"] = lambda p: analogio.AnalogIn(p)
        probes["dac"] = lambda p: analogio.AnalogOut(p)
    except ImportError:
        pass
    try:
        import pwmio
        probes["pwm"] = lambda p: pwmio.PWMOut(p)
    except ImportError:
        pass
    try:
        import countio
        probes["countio"] = lambda p: countio.Counter(p)
    except ImportError:
        probes["countio"] = None   # not in this CP build — distinct from "no pins"
    return probes


def main():
    print("# probed by validate_pins.py — paste/diff against")
    print("# mcu/circuit_python/boards/<profile>.yaml")
    print("board: %s" % board.board_id)
    print("logic_v: 3.3")
    print("pins:")
    for kind, make in _capability_probes().items():
        if make is None:
            print("  # %s: peripheral class missing from this CircuitPython build" % kind)
            continue
        print("  %s: [%s]" % (kind, ", ".join(_probe(make))))
    print("  # bus roles (uart/i2c/spi/i2s) are datasheet-authored — not probed")


main()

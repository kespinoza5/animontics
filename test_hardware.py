#!/usr/bin/env python3
"""
IR transceiver hardware debug script.

Deploy this file to the node alongside the sensor package and run it directly
to verify the TSOP38238 (RX) and TSAL6200 (TX) are wired and working before
the full animontics stack is involved.  No animontics imports required.

Usage
-----
  # Listen for IR codes (point any remote at the receiver):
  python3 test_hardware.py rx

  # Send a test NEC code (NEC addr=0x04 cmd=0x08 by default):
  python3 test_hardware.py tx

  # Loopback: send a code then listen for it back (emitter pointed at receiver):
  python3 test_hardware.py loopback

  # Override devices or test payload:
  python3 test_hardware.py rx   --rx /dev/lirc0
  python3 test_hardware.py tx   --tx /dev/lirc1 --addr 0x20 --cmd 0x01
  python3 test_hardware.py loopback --rx /dev/lirc0 --tx /dev/lirc1

Options
-------
  --rx     RX LIRC device  (default: /dev/lirc0)
  --tx     TX LIRC device  (default: /dev/lirc1)
  --addr   NEC address to transmit, hex or decimal  (default: 0x04)
  --cmd    NEC command to transmit, hex or decimal  (default: 0x08)
  --time   How many seconds to listen in rx / loopback mode  (default: 15)
"""

from __future__ import annotations

import argparse
import os
import select
import struct
import sys
import time

# ── Optional: use codec from this package for mode2 decoding ─────────────────
try:
    _pkg_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _pkg_dir not in sys.path:
        sys.path.insert(0, _pkg_dir)
    from sensors.ir_xcvr.codec import decode_nec, encode_nec, RC_PROTO_NAMES
    _CODEC_AVAILABLE = True
except ImportError:
    _CODEC_AVAILABLE = False

# ── LIRC constants (duplicated here so the script is self-contained) ──────────

_SC_FMT  = "<QHHIQ"
_SC_SIZE = struct.calcsize(_SC_FMT)   # 24 bytes

_LIRC_MODE_SCANCODE   = 0x08
_LIRC_MODE_PULSE      = 0x02
_LIRC_MODE_MODE2      = 0x04
_LIRC_SET_REC_MODE    = 0x40046919
_LIRC_SET_SEND_MODE   = 0x40046911
_LIRC_SET_SEND_CARRIER = 0x40046913
_IR_CARRIER_HZ        = 38_000

_MODE2_PULSE   = 0x01000000
_MODE2_SPACE   = 0x00000000
_MODE2_TIMEOUT = 0x03000000
_MODE2_MASK    = 0xFF000000

_SCANCODE_FLAG_REPEAT = 0x02

_RC_PROTO_NEC  = 9
_RC_PROTO_NECX = 10
_PROTO_NAMES   = {9: "NEC", 10: "NECX", 11: "NEC32", 2: "RC5", 15: "RC6_0"}

# ── Colour helpers ────────────────────────────────────────────────────────────

_USE_COLOR = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def ok(msg: str)   -> str: return _c("32", f"  ✓  {msg}")
def fail(msg: str) -> str: return _c("31", f"  ✗  {msg}")
def info(msg: str) -> str: return _c("36", f"  →  {msg}")
def warn(msg: str) -> str: return _c("33", f"  !  {msg}")
def head(msg: str) -> str: return _c("1",  f"\n{msg}")


# ── LIRC helpers (stdlib only) ────────────────────────────────────────────────

def _ioctl(fd: int, request: int, arg: bytes) -> None:
    import fcntl
    fcntl.ioctl(fd, request, arg)


def _open_rx(device: str) -> tuple[int, bool]:
    """Open LIRC RX device. Returns (fd, scancode_mode)."""
    fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    mode = struct.pack("<I", _LIRC_MODE_SCANCODE)
    try:
        _ioctl(fd, _LIRC_SET_REC_MODE, mode)
        return fd, True
    except OSError:
        pass
    mode = struct.pack("<I", _LIRC_MODE_MODE2)
    _ioctl(fd, _LIRC_SET_REC_MODE, mode)
    return fd, False


def _open_tx(device: str) -> tuple[int, bool]:
    """Open LIRC TX device. Returns (fd, scancode_mode)."""
    fd = os.open(device, os.O_RDWR | os.O_NONBLOCK)
    mode = struct.pack("<I", _LIRC_MODE_SCANCODE)
    try:
        _ioctl(fd, _LIRC_SET_SEND_MODE, mode)
        return fd, True
    except OSError:
        pass
    mode = struct.pack("<I", _LIRC_MODE_PULSE)
    _ioctl(fd, _LIRC_SET_SEND_MODE, mode)
    carrier = struct.pack("<I", _IR_CARRIER_HZ)
    _ioctl(fd, _LIRC_SET_SEND_CARRIER, carrier)
    return fd, False


def _read_scancode(fd: int) -> tuple[str, int, int, int, bool] | None:
    raw = os.read(fd, _SC_SIZE)
    if len(raw) < _SC_SIZE:
        return None
    _ts, flags, rc_proto, _key, scancode = struct.unpack(_SC_FMT, raw)
    repeat   = bool(flags & _SCANCODE_FLAG_REPEAT)
    protocol = _PROTO_NAMES.get(rc_proto, f"PROTO_{rc_proto}")
    if rc_proto == _RC_PROTO_NEC:
        addr, cmd = (scancode >> 8) & 0xFF, scancode & 0xFF
    elif rc_proto == _RC_PROTO_NECX:
        addr, cmd = (scancode >> 8) & 0xFFFF, scancode & 0xFF
    else:
        addr, cmd = int(scancode >> 8), int(scancode & 0xFF)
    return protocol, addr, cmd, int(scancode), repeat


def _send_scancode(fd: int, protocol: str, address: int, command: int) -> bool:
    proto_map = {"NEC": _RC_PROTO_NEC, "NECX": _RC_PROTO_NECX}
    rc_proto  = proto_map.get(protocol.upper())
    if rc_proto is None:
        return False
    scancode = (address << 8) | command
    payload  = struct.pack(_SC_FMT, 0, 0, rc_proto, 0, scancode)
    return os.write(fd, payload) == _SC_SIZE


def _send_raw(fd: int, pulses: list[int]) -> bool:
    raw = struct.pack(f"<{len(pulses)}I", *pulses)
    return os.write(fd, raw) == len(raw)


# ── Test modes ────────────────────────────────────────────────────────────────

def test_rx(rx_device: str, duration: int) -> bool:
    print(head("RX TEST — TSOP38238"))
    print(info(f"Device : {rx_device}"))
    print(info(f"Duration: {duration} s — point any IR remote at the receiver now\n"))

    try:
        fd, scancode_mode = _open_rx(rx_device)
    except FileNotFoundError:
        print(fail(f"Device not found: {rx_device}"))
        print(      "       Is the sun4i-ir module loaded?  Try: lsmod | grep sun4i")
        return False
    except PermissionError:
        print(fail(f"Permission denied: {rx_device}"))
        print(      "       Try: sudo chmod a+rw /dev/lirc*   or run as root")
        return False
    except OSError as exc:
        print(fail(f"Cannot open {rx_device}: {exc}"))
        return False

    mode_label = "scancode (kernel-decoded)" if scancode_mode else "mode2 (raw pulses)"
    print(ok(f"Opened {rx_device} in {mode_label} mode"))

    received = 0
    deadline = time.monotonic() + duration
    pulse_buf: list[int] = []

    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))

            if not ready:
                if pulse_buf and not scancode_mode:
                    # Timeout mid-frame — try to decode what we have
                    if _CODEC_AVAILABLE:
                        result = decode_nec(pulse_buf)
                        if result:
                            received += 1
                            _print_rx(result.protocol, result.address,
                                      result.command, result.scancode, result.repeat)
                    pulse_buf = []
                continue

            if scancode_mode:
                decoded = _read_scancode(fd)
                if decoded:
                    protocol, address, command, scancode, repeat = decoded
                    received += 1
                    _print_rx(protocol, address, command, scancode, repeat)

            else:
                raw = os.read(fd, 4)
                if len(raw) < 4:
                    continue
                word     = struct.unpack("<I", raw)[0]
                kind     = word & _MODE2_MASK
                duration_us = word & ~_MODE2_MASK

                if kind == _MODE2_TIMEOUT:
                    if pulse_buf and _CODEC_AVAILABLE:
                        result = decode_nec(pulse_buf)
                        if result:
                            received += 1
                            _print_rx(result.protocol, result.address,
                                      result.command, result.scancode, result.repeat)
                        elif pulse_buf:
                            print(warn(f"  Unrecognised frame ({len(pulse_buf)} pulses): "
                                       f"{pulse_buf[:6]}…"))
                    pulse_buf = []
                elif duration_us > 10_000 and pulse_buf:
                    if _CODEC_AVAILABLE:
                        result = decode_nec(pulse_buf)
                        if result:
                            received += 1
                            _print_rx(result.protocol, result.address,
                                      result.command, result.scancode, result.repeat)
                    pulse_buf = []
                    pulse_buf.append(duration_us)
                else:
                    pulse_buf.append(duration_us)
                    if not _CODEC_AVAILABLE and len(pulse_buf) <= 8:
                        print(f"  raw  {kind >> 24:02X}  {duration_us:6d} µs")

    except KeyboardInterrupt:
        print()

    finally:
        os.close(fd)

    if received:
        print(ok(f"\nReceived {received} code(s) — RX hardware OK"))
        return True
    else:
        print(fail("\nNo codes received in the test window"))
        print(      "  Check:")
        print(      "   • TSOP38238 OUT → PH10/IR_RX pin (not swapped with VCC/GND)")
        print(      "   • 100 Ω + 100 nF filter on TSOP38238 supply pin")
        print(      "   • sun4i-ir and ir-nec-decoder kernel modules loaded")
        print(      "   • Device tree IR_RX function enabled for PH10")
        return False


def _print_rx(protocol: str, address: int, command: int,
              scancode: int, repeat: bool) -> None:
    flag = "  [repeat]" if repeat else ""
    print(
        f"  {_c('32', '←RX')}  {protocol:<6}  "
        f"addr=0x{address:04X}  cmd=0x{command:02X}  "
        f"scancode=0x{scancode:06X}{flag}"
    )


def test_tx(tx_device: str, address: int, command: int) -> bool:
    print(head("TX TEST — TSAL6200"))
    print(info(f"Device  : {tx_device}"))
    print(info(f"Sending : NEC  addr=0x{address:04X}  cmd=0x{command:02X}\n"))

    try:
        fd, scancode_mode = _open_tx(tx_device)
    except FileNotFoundError:
        print(fail(f"Device not found: {tx_device}"))
        print(      "       Is the pwm-ir-tx overlay loaded?  "
                    "Check /boot/orangepi*.dts or /boot/armbianEnv.txt")
        return False
    except PermissionError:
        print(fail(f"Permission denied: {tx_device}"))
        return False
    except OSError as exc:
        print(fail(f"Cannot open {tx_device}: {exc}"))
        return False

    mode_label = "scancode" if scancode_mode else "raw pulse"
    print(ok(f"Opened {tx_device} in {mode_label} mode"))

    try:
        if scancode_mode:
            success = _send_scancode(fd, "NEC", address, command)
        else:
            if not _CODEC_AVAILABLE:
                print(fail("Codec not available — cannot encode raw pulses"))
                print(      "       Ensure the sensors/ir_xcvr package is on sys.path")
                os.close(fd)
                return False
            pulses  = encode_nec(address, command)
            success = _send_raw(fd, pulses)
    except OSError as exc:
        print(fail(f"Write failed: {exc}"))
        os.close(fd)
        return False
    finally:
        os.close(fd)

    if success:
        print(ok("Write succeeded"))
        print(info("Verify with a phone IR camera / phone camera (some detect 940 nm)"))
        print(info("Or run 'python3 test_hardware.py loopback' to verify electrically"))
        return True
    else:
        print(fail("Write returned fewer bytes than expected"))
        return False


def test_loopback(rx_device: str, tx_device: str,
                  address: int, command: int, duration: int) -> bool:
    print(head("LOOPBACK TEST"))
    print(info(f"RX: {rx_device}  TX: {tx_device}"))
    print(info(f"Sending NEC addr=0x{address:04X} cmd=0x{command:02X} "
               f"then listening {duration} s for it back\n"))
    print(warn("Point the TSAL6200 directly at the TSOP38238 (< 10 cm for reliability)\n"))

    # Open both devices
    try:
        rx_fd, rx_sc = _open_rx(rx_device)
    except OSError as exc:
        print(fail(f"Cannot open RX {rx_device}: {exc}"))
        return False

    try:
        tx_fd, tx_sc = _open_tx(tx_device)
    except OSError as exc:
        print(fail(f"Cannot open TX {tx_device}: {exc}"))
        os.close(rx_fd)
        return False

    # Flush any stale data from the RX buffer
    while True:
        r, _, _ = select.select([rx_fd], [], [], 0)
        if not r:
            break
        os.read(rx_fd, 128)

    # Transmit
    print(info("Transmitting…"))
    try:
        if tx_sc:
            tx_ok = _send_scancode(tx_fd, "NEC", address, command)
        else:
            if not _CODEC_AVAILABLE:
                print(fail("Codec unavailable — cannot encode"))
                os.close(rx_fd); os.close(tx_fd)
                return False
            tx_ok = _send_raw(tx_fd, encode_nec(address, command))
    except OSError as exc:
        print(fail(f"TX write error: {exc}"))
        os.close(rx_fd); os.close(tx_fd)
        return False
    finally:
        os.close(tx_fd)

    if not tx_ok:
        print(fail("TX write returned short — transmit failed"))
        os.close(rx_fd)
        return False

    print(ok("TX write OK — listening for echo…\n"))

    # Listen for the code back
    found       = False
    deadline    = time.monotonic() + duration
    pulse_buf: list[int] = []

    try:
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            ready, _, _ = select.select([rx_fd], [], [], min(remaining, 0.5))

            if not ready:
                if pulse_buf and not rx_sc and _CODEC_AVAILABLE:
                    result = decode_nec(pulse_buf)
                    if result and not result.repeat:
                        _check_loopback(result, address, command)
                        found = True
                        break
                pulse_buf = []
                continue

            if rx_sc:
                decoded = _read_scancode(rx_fd)
                if decoded:
                    protocol, rx_addr, rx_cmd, scancode, repeat = decoded
                    if not repeat:
                        _print_rx(protocol, rx_addr, rx_cmd, scancode, repeat)
                        if rx_addr == address and rx_cmd == command:
                            found = True
                            break
            else:
                raw = os.read(rx_fd, 4)
                if len(raw) < 4:
                    continue
                word = struct.unpack("<I", raw)[0]
                kind = word & _MODE2_MASK
                duration_us = word & ~_MODE2_MASK
                if kind == _MODE2_TIMEOUT:
                    if pulse_buf and _CODEC_AVAILABLE:
                        result = decode_nec(pulse_buf)
                        if result and not result.repeat:
                            _print_rx(result.protocol, result.address,
                                      result.command, result.scancode, result.repeat)
                            if result.address == address and result.command == command:
                                found = True
                                break
                    pulse_buf = []
                else:
                    pulse_buf.append(duration_us)

    except KeyboardInterrupt:
        print()
    finally:
        os.close(rx_fd)

    print()
    if found:
        print(ok("Loopback PASS — TX and RX are both working"))
        return True
    else:
        print(fail("Loopback FAIL — code was not received back"))
        print(      "  Check:")
        print(      "   • Emitter physically aimed at receiver (< 10 cm)")
        print(      "   • Transistor base resistor (1 kΩ) wired to PH0/PWM3")
        print(      "   • 33 Ω current-limiting resistor on TSAL6200 anode")
        print(      "   • pwm-ir-tx overlay enabled and /dev/lirc1 present")
        print(      "   • Run 'python3 test_hardware.py rx' with a known-good remote")
        print(      "     to confirm the receiver works independently first")
        return False


def _check_loopback(result: object, expected_addr: int, expected_cmd: int) -> None:
    _print_rx(result.protocol, result.address, result.command,     # type: ignore[attr-defined]
              result.scancode, result.repeat)                       # type: ignore[attr-defined]
    if result.address == expected_addr and result.command == expected_cmd: # type: ignore[attr-defined]
        print(ok("Address and command match — loopback verified"))
    else:
        print(warn(f"Received addr=0x{result.address:04X} cmd=0x{result.command:02X} "  # type: ignore[attr-defined]
                   f"but expected addr=0x{expected_addr:04X} cmd=0x{expected_cmd:02X}"))


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_int(value: str) -> int:
    return int(value, 0)   # handles 0x prefix


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IR transceiver hardware debug — TSOP38238 + TSAL6200 via LIRC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("mode", choices=["rx", "tx", "loopback"],
                        help="Test mode: receive only, transmit only, or loopback")
    parser.add_argument("--rx",   default="/dev/lirc0", help="RX LIRC device (default: /dev/lirc0)")
    parser.add_argument("--tx",   default="/dev/lirc1", help="TX LIRC device (default: /dev/lirc1)")
    parser.add_argument("--addr", default="0x04", type=_parse_int,
                        help="NEC address to transmit (default: 0x04)")
    parser.add_argument("--cmd",  default="0x08", type=_parse_int,
                        help="NEC command to transmit (default: 0x08)")
    parser.add_argument("--time", default=15, type=int, dest="duration",
                        help="Listen duration in seconds (default: 15)")
    args = parser.parse_args()

    if _CODEC_AVAILABLE:
        print(info("Codec loaded from sensors.ir_xcvr.codec"))
    else:
        print(warn("Codec not found — mode2 decode and raw TX unavailable"))
        print(warn("Add the animontics root to PYTHONPATH or run from the project root\n"))

    if args.mode == "rx":
        success = test_rx(args.rx, args.duration)
    elif args.mode == "tx":
        success = test_tx(args.tx, args.addr, args.cmd)
    elif args.mode == "loopback":
        success = test_loopback(args.rx, args.tx, args.addr, args.cmd, args.duration)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

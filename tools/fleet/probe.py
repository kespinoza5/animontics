"""Hardware probing — SSH into a board, detect devices, suggest config."""
from __future__ import annotations

import re
from typing import Any

from tools.fleet.ssh import run_remote


def probe_hardware(host: str, user: str) -> dict[str, Any]:
    """Run hardware detection on a remote board.

    Scans I2C buses, UART devices, and USB CDC devices.
    Returns a structured dict of detected hardware.
    """
    result: dict[str, Any] = {
        "i2c": {},
        "uart": [],
        "usb_cdc": [],
        "usb_devices": [],
    }

    # I2C — list buses then scan each
    stdout, _, rc = run_remote(
        host, user,
        "ls /dev/i2c-* 2>/dev/null",
        check=False,
    )
    if rc == 0:
        for bus_path in stdout.split():
            m = re.search(r"i2c-(\d+)$", bus_path)
            if not m:
                continue
            bus_num = int(m.group(1))
            scan_out, _, _ = run_remote(
                host, user,
                f"i2cdetect -y -r {bus_num} 2>/dev/null",
                check=False,
            )
            addresses = _parse_i2cdetect(scan_out)
            result["i2c"][bus_num] = addresses

    # UART
    stdout, _, _ = run_remote(
        host, user,
        "ls /dev/ttyAMA* /dev/ttyS0 /dev/ttyO* 2>/dev/null",
        check=False,
    )
    result["uart"] = [d.strip() for d in stdout.split() if d.strip()]

    # USB CDC
    stdout, _, _ = run_remote(
        host, user,
        "ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null",
        check=False,
    )
    for dev in stdout.split():
        dev = dev.strip()
        if not dev:
            continue
        base = dev.rsplit("/", 1)[-1]
        product, _, _ = run_remote(
            host, user,
            f"cat /sys/class/tty/{base}/device/product 2>/dev/null || echo ''",
            check=False,
        )
        result["usb_cdc"].append({
            "port": dev,
            "product": product.strip(),
        })

    # LIRC (IR transceiver)
    stdout, _, _ = run_remote(
        host, user,
        "ls /dev/lirc* 2>/dev/null",
        check=False,
    )
    lirc_devs: list[dict] = []
    for dev in stdout.split():
        dev = dev.strip()
        if not dev:
            continue
        # Try to read the device name from sysfs
        base = dev.rsplit("/", 1)[-1]
        name_out, _, _ = run_remote(
            host, user,
            f"cat /sys/class/lirc/{base}/device/name 2>/dev/null || echo ''",
            check=False,
        )
        lirc_devs.append({"device": dev, "name": name_out.strip()})
    result["lirc"] = lirc_devs

    # USB device summary
    stdout, _, _ = run_remote(
        host, user,
        "lsusb 2>/dev/null",
        check=False,
    )
    result["usb_devices"] = [l.strip() for l in stdout.splitlines() if l.strip()]

    return result


def match_hardware_to_sensors(
    detected: dict[str, Any],
    metadata: dict[str, dict],
) -> list[dict[str, Any]]:
    """Match detected hardware against sensor METADATA.

    Returns a list of candidate matches:
    [
      {
        "sensor_type": "mlx90640",
        "confidence": "high",
        "connection": {"type": "i2c", "bus": 3, "address": 0x33},
        "reason": "I2C address 0x33 matches MLX90640 default",
      },
      ...
    ]
    """
    matches = []

    for sensor_type, meta in metadata.items():
        conn_meta = meta.get("connection", {})
        supported = conn_meta.get("supported", [])
        defaults = conn_meta.get("defaults", {})
        valid = conn_meta.get("valid", {})

        # Check I2C sensors
        if "i2c" in supported:
            default_addr = defaults.get("address")
            valid_addrs = valid.get("address", [default_addr] if default_addr else [])
            default_bus = defaults.get("bus", 1)

            for bus_num, addresses in detected.get("i2c", {}).items():
                for addr in addresses:
                    if addr in valid_addrs:
                        matches.append({
                            "sensor_type": sensor_type,
                            "confidence": "high",
                            "connection": {
                                "type": "i2c",
                                "bus": bus_num,
                                "address": addr,
                            },
                            "reason": (
                                f"I2C bus {bus_num} address {hex(addr)} matches "
                                f"{meta['name']} default address"
                            ),
                        })

        # Check UART/USB-CDC sensors — we can detect the port but not the sensor type,
        # so confidence is lower
        for conn_type in ("uart", "usb_cdc"):
            if conn_type not in supported:
                continue
            devices = detected.get(conn_type, [])
            if isinstance(devices, list) and devices:
                for dev in devices:
                    port = dev if isinstance(dev, str) else dev.get("port", "")
                    product = "" if isinstance(dev, str) else dev.get("product", "")
                    matches.append({
                        "sensor_type": sensor_type,
                        "confidence": "medium",
                        "connection": {
                            "type": conn_type,
                            "port": port,
                            "baud_rate": defaults.get("baud_rate"),
                        },
                        "reason": (
                            f"{conn_type.upper()} device {port}"
                            + (f" ({product})" if product else "")
                            + f" could be {meta['name']} — verify wiring"
                        ),
                    })

        # Check IR (LIRC) sensors — presence of /dev/lirc* devices is a strong signal
        if "ir" in supported:
            lirc_devs = detected.get("lirc", [])
            if lirc_devs:
                rx_dev = defaults.get("rx_device")
                tx_dev = defaults.get("tx_device")
                # Check if the expected default devices are present
                found_devs = {d["device"] for d in lirc_devs}
                has_rx = rx_dev in found_devs if rx_dev else False
                has_tx = tx_dev in found_devs if tx_dev else False
                present = [d["device"] for d in lirc_devs]
                name_hints = [d["name"] for d in lirc_devs if d["name"]]
                confidence = "high" if (has_rx or has_tx) else "medium"
                matches.append({
                    "sensor_type": sensor_type,
                    "confidence": confidence,
                    "connection": {
                        "type": "ir",
                        "rx_device": present[0] if present else rx_dev,
                        "tx_device": present[1] if len(present) > 1 else tx_dev,
                    },
                    "reason": (
                        f"LIRC device(s) found: {', '.join(present)}"
                        + (f" ({', '.join(name_hints)})" if name_hints else "")
                        + f" — likely {meta['name']}"
                    ),
                })

    # Deduplicate: if uart and usb_cdc both match same sensor, keep both
    return matches


def format_probe_report(
    node_id: str,
    detected: dict[str, Any],
    matches: list[dict[str, Any]],
    desired_types: list[str],
) -> str:
    """Format a human-readable probe report."""
    lines = [
        f"Probe report: {node_id}",
        "─" * 50,
        "",
        "Detected hardware:",
    ]

    i2c = detected.get("i2c", {})
    if i2c:
        for bus, addrs in sorted(i2c.items()):
            addr_str = ", ".join(hex(a) for a in addrs) if addrs else "(empty)"
            lines.append(f"  I2C /dev/i2c-{bus}: {addr_str}")
    else:
        lines.append("  I2C: none found")

    uart = detected.get("uart", [])
    lines.append(f"  UART: {', '.join(uart) if uart else 'none found'}")

    usb_cdc = detected.get("usb_cdc", [])
    if usb_cdc:
        for dev in usb_cdc:
            port = dev if isinstance(dev, str) else dev.get("port", "")
            product = "" if isinstance(dev, str) else dev.get("product", "")
            lines.append(f"  USB CDC: {port}" + (f"  ({product})" if product else ""))
    else:
        lines.append("  USB CDC: none found")

    lirc = detected.get("lirc", [])
    if lirc:
        for dev in lirc:
            label = dev["device"] + (f"  ({dev['name']})" if dev.get("name") else "")
            lines.append(f"  LIRC: {label}")
    else:
        lines.append("  LIRC: none found")

    lines.extend(["", "Sensor matches:"])

    if not matches:
        lines.append("  No sensor matches found.")
    else:
        for m in matches:
            conn = m["connection"]
            if conn["type"] == "i2c":
                conn_str = f"bus={conn['bus']} addr={hex(conn['address'])}"
            elif conn["type"] == "ir":
                rx = conn.get("rx_device") or "—"
                tx = conn.get("tx_device") or "—"
                conn_str = f"rx={rx} tx={tx}"
            else:
                conn_str = f"port={conn.get('port', 'TBD')} baud={conn.get('baud_rate')}"
            desired_marker = " ✓" if m["sensor_type"] in desired_types else " (not in animon.yaml)"
            lines.append(
                f"  [{m['confidence'].upper():6}] {m['sensor_type']:20} "
                f"{conn_str}{desired_marker}"
            )
            lines.append(f"           {m['reason']}")

    unmatched = [t for t in desired_types if not any(m["sensor_type"] == t for m in matches)]
    if unmatched:
        lines.extend(["", "Not detected (in animon.yaml but no hardware match):"])
        for t in unmatched:
            lines.append(f"  ! {t}")

    return "\n".join(lines)


def _parse_i2cdetect(output: str) -> list[int]:
    """Parse i2cdetect -y output into a list of detected addresses."""
    detected = []
    for line in output.splitlines():
        if ":" not in line:
            continue
        _, _, cells = line.partition(":")
        for cell in cells.split():
            if len(cell) == 2 and cell != "--":
                try:
                    detected.append(int(cell, 16))
                except ValueError:
                    pass
    return sorted(detected)

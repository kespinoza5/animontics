import asyncio
import glob
import subprocess

from fastapi import APIRouter

router = APIRouter()


def _parse_i2cdetect(output: str) -> list[int]:
    """Return sorted list of detected 7-bit addresses from i2cdetect stdout."""
    detected = []
    for line in output.splitlines():
        if ":" not in line:
            continue
        row_hex, _, cells_str = line.partition(":")
        row_hex = row_hex.strip()
        if not row_hex:
            continue
        try:
            int(row_hex, 16)
        except ValueError:
            continue
        for cell in cells_str.split():
            if len(cell) == 2 and cell != "--":
                try:
                    detected.append(int(cell, 16))
                except ValueError:
                    pass
    return sorted(detected)


def scan_i2c_buses() -> dict:
    """Run i2cdetect on every /dev/i2c-* bus. Returns {bus_num: [addrs] | {"error": str}}."""
    result = {}
    for path in sorted(glob.glob("/dev/i2c-*")):
        try:
            bus_num = int(path.rsplit("-", 1)[-1])
        except ValueError:
            continue
        try:
            proc = subprocess.run(
                ["i2cdetect", "-y", "-r", str(bus_num)],
                capture_output=True, text=True, timeout=5,
            )
            result[bus_num] = _parse_i2cdetect(proc.stdout)
        except FileNotFoundError:
            result[bus_num] = {"error": "i2cdetect not found — run: sudo apt install i2c-tools"}
        except subprocess.TimeoutExpired:
            result[bus_num] = {"error": "timeout"}
        except Exception as exc:
            result[bus_num] = {"error": str(exc)}
    return result


@router.get("/i2c")
async def i2c_scan():
    return await asyncio.to_thread(scan_i2c_buses)

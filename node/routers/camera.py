from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.models import CameraConfig

try:
    import cv2
except ImportError:
    cv2 = None  # optional dep — only boards with camera.enabled install opencv

router = APIRouter()

# Module-level singleton; replaced by start_camera() at app startup.
_camera: Optional["CameraThread"] = None


class CameraThread:
    """
    Reads raw MJPEG bytes from V4L2 without decode/re-encode.
    CAP_PROP_CONVERT_RGB=0 tells OpenCV to return the compressed frame
    the camera already produced in hardware.
    """

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._jpeg: Optional[bytes] = None
        self._seq   = 0
        self._lock  = threading.Lock()
        self._stop  = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="camera").start()

    def stop(self) -> None:
        self._stop.set()

    def frame_and_seq(self) -> tuple[Optional[bytes], int]:
        with self._lock:
            return self._jpeg, self._seq

    def _loop(self) -> None:
        cfg = self._config
        cap = cv2.VideoCapture(cfg.device, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC,       cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.height)
        cap.set(cv2.CAP_PROP_FPS,          cfg.fps)
        cap.set(cv2.CAP_PROP_CONVERT_RGB,  0)  # raw passthrough

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
            raw = frame.tobytes()
            if raw[:2] == b"\xff\xd8":  # valid JPEG SOI marker
                with self._lock:
                    self._jpeg = raw
                    self._seq += 1

        cap.release()


def start_camera(config: CameraConfig) -> CameraThread:
    global _camera
    if cv2 is None:
        raise RuntimeError(
            "camera is enabled in this board's config but opencv is not "
            "installed — pip install opencv-python-headless"
        )
    _camera = CameraThread(config)
    _camera.start()
    return _camera


def stop_camera() -> None:
    if _camera:
        _camera.stop()


async def _mjpeg_stream():
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    last_seq = -1
    while True:
        if _camera is None:
            await asyncio.sleep(0.1)
            continue
        jpeg, seq = _camera.frame_and_seq()
        if jpeg is not None and seq != last_seq:
            yield boundary + jpeg + b"\r\n"
            last_seq = seq
        await asyncio.sleep(0.001)


@router.get("/camera")
async def video_stream():
    if _camera is None:
        from fastapi import Response
        return Response(status_code=503, content="Camera not configured on this node.")
    return StreamingResponse(
        _mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

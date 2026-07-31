import logging
import threading
import time

import cv2

from .ring_buffer import FrameRingBuffer

logger = logging.getLogger(__name__)


class RtspReader(threading.Thread):
    """Lit un flux RTSP et échantillonne des frames JPEG vers le buffer circulaire.

    Reconnexion automatique avec backoff exponentiel en cas de coupure.
    """

    def __init__(
        self,
        url: str,
        buffer: FrameRingBuffer,
        target_fps: float = 8.0,
        jpeg_quality: int = 80,
        reconnect_max_wait: float = 30.0,
    ):
        super().__init__(daemon=True, name="rtsp-reader")
        self._url = url
        self._buffer = buffer
        self._interval = 1.0 / target_fps
        self._jpeg_quality = int(jpeg_quality)
        self._reconnect_max_wait = reconnect_max_wait
        self._stop = threading.Event()
        self.connected = False

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        wait = 1.0
        while not self._stop.is_set():
            capture = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            if not capture.isOpened():
                capture.release()
                self.connected = False
                logger.warning("RTSP connection failed, retrying in %.0fs", wait)
                self._stop.wait(wait)
                wait = min(wait * 2, self._reconnect_max_wait)
                continue

            logger.info("RTSP connected (%.1f fps sampling)", 1.0 / self._interval)
            self.connected = True
            wait = 1.0
            next_sample = 0.0
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    logger.warning("RTSP read failed, reconnecting")
                    break
                now = time.time()
                if now < next_sample:
                    continue
                next_sample = now + self._interval
                ok, jpeg = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality]
                )
                if ok:
                    self._buffer.append(now, jpeg.tobytes())

            self.connected = False
            capture.release()
